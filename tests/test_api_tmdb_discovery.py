from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.dependencies import get_tmdb_discovery_service
from src.config.settings import AppSettings
from src.organizing.tmdb import TmdbCredentialError, TmdbRetryableError
from src.organizing.tmdb_discovery import TmdbAliasBundle, TmdbSearchResult


class FakeDiscoveryService:
    def __init__(
        self,
        *,
        search_results: list[TmdbSearchResult] | None = None,
        alias_bundle: TmdbAliasBundle | None = None,
        search_error: Exception | None = None,
        alias_error: Exception | None = None,
        trending_results: list[TmdbSearchResult] | None = None,
        trending_error: Exception | None = None,
    ) -> None:
        self._search_results = search_results or []
        self._alias_bundle = alias_bundle
        self._search_error = search_error
        self._alias_error = alias_error
        self._trending_results = trending_results or []
        self._trending_error = trending_error
        self.search_calls: list[tuple[str, int]] = []
        self.alias_calls: list[tuple[str, int]] = []
        self.trending_calls: list[tuple[str, int]] = []

    def search_multi(self, query: str, *, limit: int = 10) -> list[TmdbSearchResult]:
        self.search_calls.append((query, limit))
        if self._search_error is not None:
            raise self._search_error
        return self._search_results

    def fetch_trending(self, list_key: str, *, limit: int = 20) -> list[TmdbSearchResult]:
        self.trending_calls.append((list_key, limit))
        if self._trending_error is not None:
            raise self._trending_error
        return self._trending_results

    def collect_aliases(self, kind: str, tmdb_id: int) -> TmdbAliasBundle:
        self.alias_calls.append((kind, tmdb_id))
        if self._alias_error is not None:
            raise self._alias_error
        if self._alias_bundle is None:
            raise AssertionError("alias bundle not configured")
        return self._alias_bundle


class _DiscoveryApiTestCase(unittest.TestCase):
    def build_client(self, service: FakeDiscoveryService) -> TestClient:
        api_app = create_app(settings=AppSettings())
        api_app.dependency_overrides[get_tmdb_discovery_service] = lambda: service
        self.addCleanup(api_app.dependency_overrides.clear)
        return TestClient(api_app)


class TmdbDiscoverySearchApiTest(_DiscoveryApiTestCase):
    def test_search_returns_items_with_kind_and_aliases(self) -> None:
        service = FakeDiscoveryService(
            search_results=[
                TmdbSearchResult(
                    tmdb_id=1,
                    kind="movie",
                    title="电影 A",
                    original_title="Movie A",
                    year=2024,
                    overview="desc",
                    poster_path="/a.jpg",
                ),
                TmdbSearchResult(
                    tmdb_id=2,
                    kind="tv",
                    title="剧 B",
                    original_title="Series B",
                    year=None,
                    overview="",
                    poster_path=None,
                ),
            ]
        )
        client = self.build_client(service)

        response = client.get("/tmdb/discovery/search", params={"query": "abc", "limit": 5})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["query"], "abc")
        self.assertEqual(len(body["items"]), 2)
        self.assertEqual(body["items"][0]["tmdb_id"], 1)
        self.assertEqual(body["items"][0]["kind"], "movie")
        self.assertEqual(body["items"][1]["kind"], "tv")
        self.assertEqual(service.search_calls, [("abc", 5)])

    def test_search_credential_error_returns_401(self) -> None:
        service = FakeDiscoveryService(search_error=TmdbCredentialError("nope"))
        client = self.build_client(service)

        response = client.get("/tmdb/discovery/search", params={"query": "abc"})

        self.assertEqual(response.status_code, 401)

    def test_search_retryable_error_returns_503(self) -> None:
        service = FakeDiscoveryService(search_error=TmdbRetryableError("rate"))
        client = self.build_client(service)

        response = client.get("/tmdb/discovery/search", params={"query": "abc"})

        self.assertEqual(response.status_code, 503)

    def test_search_blank_query_returns_422(self) -> None:
        service = FakeDiscoveryService()
        client = self.build_client(service)

        response = client.get("/tmdb/discovery/search", params={"query": ""})

        self.assertEqual(response.status_code, 422)


class TmdbDiscoveryAliasApiTest(_DiscoveryApiTestCase):
    def test_aliases_endpoint_returns_alias_bundle(self) -> None:
        service = FakeDiscoveryService(
            alias_bundle=TmdbAliasBundle(
                tmdb_id=42,
                kind="movie",
                title="三体",
                original_title="The Three-Body Problem",
                year=2024,
                aliases=("三体", "The Three-Body Problem", "Three-Body"),
            )
        )
        client = self.build_client(service)

        response = client.get("/tmdb/discovery/aliases/movie/42")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["tmdb_id"], 42)
        self.assertEqual(body["kind"], "movie")
        self.assertEqual(body["aliases"], ["三体", "The Three-Body Problem", "Three-Body"])
        self.assertEqual(service.alias_calls, [("movie", 42)])

    def test_aliases_endpoint_rejects_unknown_kind(self) -> None:
        service = FakeDiscoveryService()
        client = self.build_client(service)

        response = client.get("/tmdb/discovery/aliases/person/1")

        self.assertEqual(response.status_code, 422)

    def test_aliases_endpoint_rejects_non_positive_id(self) -> None:
        service = FakeDiscoveryService()
        client = self.build_client(service)

        response = client.get("/tmdb/discovery/aliases/movie/0")

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
