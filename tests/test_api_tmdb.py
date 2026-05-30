from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from src.config.settings import AppSettings
from src.organizing import MEDIA_KIND_MOVIE, MEDIA_KIND_SERIES, OrganizeMetadata, TmdbConfig, TmdbCredentialError, TmdbRetryableError
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
