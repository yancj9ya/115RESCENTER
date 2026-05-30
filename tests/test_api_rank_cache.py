from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.dependencies import get_rank_cache_repository, get_runtime_control_repository
from src.config.settings import AppSettings
from src.ranks.repository import RankCacheRecord


class _FakeCacheRepo:
    def __init__(self, records: dict[tuple[str, str], RankCacheRecord] | None = None) -> None:
        self._records = records or {}

    def get(self, *, source: str, key: str) -> RankCacheRecord | None:
        return self._records.get((source, key))


class _FakeRuntimeRepo:
    def __init__(self) -> None:
        self.enqueued: list[tuple[str, str]] = []

    def enqueue_manual_trigger(self, *, event_name: str, source: str = "api") -> int:
        self.enqueued.append((event_name, source))
        return len(self.enqueued)


def _record(source: str, key: str, *, status: str = "ok", items: list[dict] | None = None, refreshed_at: str | None = "2026-05-30 10:00:00") -> RankCacheRecord:
    return RankCacheRecord(
        source=source,
        key=key,
        items=items if items is not None else [
            {
                "tmdb_id": 101,
                "kind": "tv",
                "title": "甲",
                "original_title": "Jia",
                "year": 2026,
                "overview": "desc",
                "poster_path": "/101.jpg",
            }
        ],
        status=status,
        error=None,
        refreshed_at=refreshed_at,
    )


class _RankCacheApiTestCase(unittest.TestCase):
    def build_client(self, cache: _FakeCacheRepo, runtime: _FakeRuntimeRepo | None = None) -> TestClient:
        api_app = create_app(settings=AppSettings())
        api_app.dependency_overrides[get_rank_cache_repository] = lambda: cache
        if runtime is not None:
            api_app.dependency_overrides[get_runtime_control_repository] = lambda: runtime
        self.addCleanup(api_app.dependency_overrides.clear)
        return TestClient(api_app)


class TencentRankCacheApiTest(_RankCacheApiTestCase):
    def test_returns_cached_items_with_metadata(self) -> None:
        cache = _FakeCacheRepo({("tencent", "tv"): _record("tencent", "tv")})
        client = self.build_client(cache)

        response = client.get("/tencent/ranks", params={"channel": "tv"})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["channel"], "tv")
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["refreshed_at"], "2026-05-30 10:00:00")
        self.assertEqual(len(body["items"]), 1)
        self.assertEqual(body["items"][0]["tmdb_id"], 101)

    def test_empty_cache_returns_never_refreshed(self) -> None:
        client = self.build_client(_FakeCacheRepo())

        response = client.get("/tencent/ranks", params={"channel": "movie"})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "never_refreshed")
        self.assertEqual(body["items"], [])
        self.assertIsNone(body["refreshed_at"])

    def test_rejects_unknown_channel(self) -> None:
        client = self.build_client(_FakeCacheRepo())
        response = client.get("/tencent/ranks", params={"channel": "documentary"})
        self.assertEqual(response.status_code, 422)


class TmdbTrendingCacheApiTest(_RankCacheApiTestCase):
    def test_returns_cached_items(self) -> None:
        cache = _FakeCacheRepo({("tmdb", "tv_popular"): _record("tmdb", "tv_popular")})
        client = self.build_client(cache)

        response = client.get("/tmdb/discovery/trending", params={"list": "tv_popular"})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["list"], "tv_popular")
        self.assertEqual(body["status"], "ok")
        self.assertEqual(len(body["items"]), 1)

    def test_empty_cache_returns_never_refreshed(self) -> None:
        client = self.build_client(_FakeCacheRepo())
        response = client.get("/tmdb/discovery/trending", params={"list": "trending_movie_week"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "never_refreshed")


class RankRefreshApiTest(_RankCacheApiTestCase):
    def test_post_refresh_enqueues_manual_trigger(self) -> None:
        runtime = _FakeRuntimeRepo()
        client = self.build_client(_FakeCacheRepo(), runtime=runtime)

        response = client.post("/ranks/refresh")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["event_name"], "manual_refresh_ranks")
        self.assertGreater(body["trigger_id"], 0)
        self.assertEqual(runtime.enqueued, [("manual_refresh_ranks", "api")])


if __name__ == "__main__":
    unittest.main()
