from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from src.config.settings import AppSettings
from src.organizing import MEDIA_KIND_MOVIE, MEDIA_KIND_SERIES, OrganizeMetadata, TmdbConfig, TmdbCredentialError, TmdbRetryableError
from src.organizing.ai_filename_parser import AiFilenameParseResult
from src.organizing.tmdb import TmdbError

try:
    from src.api.app import create_app
    from src.api.dependencies import get_tmdb_movie_resolver, get_tmdb_multi_resolver
except ModuleNotFoundError as import_error:
    create_app = None
    get_tmdb_movie_resolver = None
    get_tmdb_multi_resolver = None
    CREATE_APP_IMPORT_ERROR = import_error
else:
    CREATE_APP_IMPORT_ERROR = None


class FakeResolver:
    def __init__(self, result: OrganizeMetadata | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error
        self.calls: list[tuple[str, int | None]] = []

    def resolve_movie(self, query: str, *, year: int | None = None) -> OrganizeMetadata | None:
        self.calls.append((query, year))
        if self._error is not None:
            raise self._error
        return self._result

    def resolve_multi(self, query: str, *, year: int | None = None) -> OrganizeMetadata | None:
        self.calls.append((query, year))
        if self._error is not None:
            raise self._error
        return self._result


class FastApiAiFilenameParseTest(unittest.TestCase):
    def test_list_ai_models_returns_model_ids(self) -> None:
        if create_app is None:
            raise unittest.SkipTest(f"src.api.app.create_app is not implemented yet: {CREATE_APP_IMPORT_ERROR}")
        api_app = create_app(settings=AppSettings())
        client = TestClient(api_app)

        class FakeResponse:
            status_code = 200

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {"data": [{"id": "z-model"}, {"id": "a-model"}, {"object": "model"}]}

        from src.api import routes

        original_get = routes.httpx.get if hasattr(routes, "httpx") else None
        calls = []

        def fake_get(url, *, headers, timeout):
            calls.append((url, headers, timeout))
            return FakeResponse()

        import httpx

        original_httpx_get = httpx.get
        httpx.get = fake_get
        self.addCleanup(lambda: setattr(httpx, "get", original_httpx_get))
        if original_get is not None:
            self.addCleanup(lambda: setattr(routes.httpx, "get", original_get))

        response = client.post(
            "/ai/models",
            json={
                "provider": "openai_compatible",
                "api_key": "secret-key",
                "base_url": "https://api.example.test/v1",
                "timeout_seconds": 9,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"models": ["a-model", "z-model"]})
        self.assertEqual(calls[0][0], "https://api.example.test/v1/models")
        self.assertEqual(calls[0][1]["Authorization"], "Bearer secret-key")
        self.assertEqual(calls[0][2], 9)
        self.assertNotIn("secret-key", response.text)

    def test_list_ai_models_rejects_missing_config_without_leaking_secret(self) -> None:
        if create_app is None:
            raise unittest.SkipTest(f"src.api.app.create_app is not implemented yet: {CREATE_APP_IMPORT_ERROR}")
        client = TestClient(create_app(settings=AppSettings()))

        response = client.post(
            "/ai/models",
            json={"provider": "openai_compatible", "api_key": "", "base_url": ""},
        )

        self.assertEqual(response.status_code, 422)
        self.assertNotIn("secret", response.text)

    def test_parse_ai_filename_returns_result(self) -> None:
        if create_app is None:
            raise unittest.SkipTest(f"src.api.app.create_app is not implemented yet: {CREATE_APP_IMPORT_ERROR}")
        api_app = create_app(settings=AppSettings())
        self.addCleanup(api_app.dependency_overrides.clear)

        from src.api import routes

        original_builder = routes.build_ai_filename_parser

        class FakeParser:
            def parse(self, filename: str):
                self.filename = filename
                return AiFilenameParseResult(type="tv", title="主角", year=2026, season=1, episode=38)

        routes.build_ai_filename_parser = lambda _config: FakeParser()
        self.addCleanup(lambda: setattr(routes, "build_ai_filename_parser", original_builder))
        client = TestClient(api_app)

        response = client.post(
            "/ai/filename/parse",
            json={
                "filename": "主角.2026.S01E38.mkv",
                "enabled": True,
                "provider": "openai_compatible",
                "api_key": "secret-key",
                "base_url": "https://api.example.test/v1",
                "model": "parser-model",
                "timeout_seconds": 10,
                "title_similarity_threshold": 0.55,
                "prompt": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["filename"], "主角.2026.S01E38.mkv")
        self.assertEqual(payload["result"]["title"], "主角")
        self.assertEqual(payload["result"]["episode"], 38)
        self.assertNotIn("secret-key", response.text)

    def test_parse_ai_filename_rejects_missing_config(self) -> None:
        if create_app is None:
            raise unittest.SkipTest(f"src.api.app.create_app is not implemented yet: {CREATE_APP_IMPORT_ERROR}")
        client = TestClient(create_app(settings=AppSettings()))

        response = client.post(
            "/ai/filename/parse",
            json={
                "filename": "a.mkv",
                "enabled": True,
                "provider": "openai_compatible",
                "api_key": "",
                "base_url": "",
                "model": "",
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertNotIn("secret", response.text)


class FastApiTmdbMovieSearchTest(unittest.TestCase):
    def build_client(
        self,
        *,
        resolver: FakeResolver | None = None,
        settings: AppSettings | None = None,
    ) -> TestClient:
        if create_app is None or get_tmdb_movie_resolver is None:
            raise unittest.SkipTest(f"src.api.app.create_app is not implemented yet: {CREATE_APP_IMPORT_ERROR}")
        api_app = create_app(settings=settings or AppSettings())
        if resolver is not None:
            api_app.dependency_overrides[get_tmdb_movie_resolver] = lambda: resolver
            if get_tmdb_multi_resolver is not None:
                api_app.dependency_overrides[get_tmdb_multi_resolver] = lambda: resolver
        self.addCleanup(api_app.dependency_overrides.clear)
        return TestClient(api_app)

    def test_search_movie_returns_safe_metadata_payload(self) -> None:
        resolver = FakeResolver(
            result=OrganizeMetadata(
                title="Inception",
                year=2010,
                kind=MEDIA_KIND_MOVIE,
                region_primary="US",
                region_candidates=("US", "GB"),
                region_category="欧美",
                region_source="production_countries",
                region_confidence="high",
            )
        )
        client = self.build_client(resolver=resolver)

        response = client.get("/tmdb/search/movie", params={"query": "Inception", "year": 2010})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "query": "Inception",
                "year": 2010,
                "metadata": {
                    "title": "Inception",
                    "year": 2010,
                    "kind": "movie",
                    "region_primary": "US",
                    "region_candidates": ["US", "GB"],
                    "region_category": "欧美",
                    "region_source": "production_countries",
                    "region_confidence": "high",
                },
            },
        )
        self.assertEqual(resolver.calls, [("Inception", 2010)])
        self.assertNotIn("TMDB_BEARER_TOKEN", response.text)

    def test_search_movie_returns_null_metadata_for_no_match(self) -> None:
        resolver = FakeResolver(result=None)
        client = self.build_client(resolver=resolver)

        response = client.get("/tmdb/search/movie", params={"query": "Missing Movie"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "query": "Missing Movie",
                "year": None,
                "metadata": None,
            },
        )
        self.assertEqual(resolver.calls, [("Missing Movie", None)])

    def test_search_movie_maps_resolver_value_error_to_422(self) -> None:
        client = self.build_client(resolver=FakeResolver(error=ValueError("query must not be empty")))

        response = client.get("/tmdb/search/movie", params={"query": "   "})

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "query must not be empty")

    def test_search_movie_maps_tmdb_credential_error_to_401(self) -> None:
        client = self.build_client(resolver=FakeResolver(error=TmdbCredentialError("bad token")))

        response = client.get("/tmdb/search/movie", params={"query": "Movie"})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "TMDB credentials were rejected"})

    def test_search_movie_maps_tmdb_retryable_error_to_503(self) -> None:
        client = self.build_client(resolver=FakeResolver(error=TmdbRetryableError("rate limited")))

        response = client.get("/tmdb/search/movie", params={"query": "Movie"})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "TMDB search is temporarily unavailable"})

    def test_search_movie_maps_tmdb_error_to_502(self) -> None:
        client = self.build_client(resolver=FakeResolver(error=TmdbError("boom")))

        response = client.get("/tmdb/search/movie", params={"query": "Movie"})

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json(), {"detail": "TMDB search failed"})

    def test_search_movie_returns_503_when_tmdb_not_configured(self) -> None:
        client = self.build_client(settings=AppSettings())

        response = client.get("/tmdb/search/movie", params={"query": "Movie"})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "TMDB search is not configured"})

    def test_search_multi_returns_tv_metadata_payload(self) -> None:
        resolver = FakeResolver(
            result=OrganizeMetadata(
                title="逐玉",
                year=2026,
                kind=MEDIA_KIND_SERIES,
                region_primary="CN",
                region_candidates=("CN",),
                region_category="国产",
                region_source="origin_country",
                region_confidence="high",
            )
        )
        client = self.build_client(resolver=resolver)

        response = client.get("/tmdb/search/multi", params={"query": "逐玉"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "query": "逐玉",
                "year": None,
                "metadata": {
                    "title": "逐玉",
                    "year": 2026,
                    "kind": "series",
                    "region_primary": "CN",
                    "region_candidates": ["CN"],
                    "region_category": "国产",
                    "region_source": "origin_country",
                    "region_confidence": "high",
                },
            },
        )
        self.assertEqual(resolver.calls, [("逐玉", None)])

    def test_search_multi_returns_null_metadata_for_no_match(self) -> None:
        resolver = FakeResolver(result=None)
        client = self.build_client(resolver=resolver)

        response = client.get("/tmdb/search/multi", params={"query": "Missing"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"query": "Missing", "year": None, "metadata": None})

    def test_search_multi_maps_tmdb_errors_and_hides_token(self) -> None:
        client = self.build_client(resolver=FakeResolver(error=TmdbRetryableError("rate limited")))

        response = client.get("/tmdb/search/multi", params={"query": "逐玉"})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "TMDB search is temporarily unavailable"})
        self.assertNotIn("TMDB_BEARER_TOKEN", response.text)

    def test_search_multi_returns_503_when_tmdb_not_configured(self) -> None:
        client = self.build_client(settings=AppSettings())

        response = client.get("/tmdb/search/multi", params={"query": "逐玉"})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "TMDB search is not configured"})

        settings = AppSettings(tmdb=TmdbConfig(bearer_token="super-secret-token"))
        client = self.build_client(resolver=FakeResolver(result=None), settings=settings)

        response = client.get("/tmdb/search/movie", params={"query": "Movie"})

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("TMDB_BEARER_TOKEN", response.text)
        self.assertNotIn("super-secret-token", response.text)


if __name__ == "__main__":
    unittest.main()
