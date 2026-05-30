from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path


@dataclass
class _Item:
    tmdb_id: int
    kind: str
    title: str
    original_title: str
    year: int | None
    overview: str
    poster_path: str | None


class _FakeEnricher:
    def __init__(self, by_channel: dict[str, list], fail: dict[str, Exception] | None = None) -> None:
        self._by_channel = by_channel
        self._fail = fail or {}
        self.calls: list[tuple[str, int]] = []

    def enrich_channel(self, channel: str, *, limit: int = 10) -> list:
        self.calls.append((channel, limit))
        if channel in self._fail:
            raise self._fail[channel]
        return self._by_channel.get(channel, [])


class _FakeDiscovery:
    def __init__(self, by_list: dict[str, list], fail: dict[str, Exception] | None = None) -> None:
        self._by_list = by_list
        self._fail = fail or {}
        self.calls: list[tuple[str, int]] = []

    def fetch_trending(self, list_key: str, *, limit: int = 20) -> list:
        self.calls.append((list_key, limit))
        if list_key in self._fail:
            raise self._fail[list_key]
        return self._by_list.get(list_key, [])


def _item(tmdb_id: int) -> _Item:
    return _Item(
        tmdb_id=tmdb_id,
        kind="tv",
        title=f"标题{tmdb_id}",
        original_title=f"Title{tmdb_id}",
        year=2024,
        overview="简介",
        poster_path=f"/{tmdb_id}.jpg",
    )


class RankRefreshServiceTest(unittest.TestCase):
    def _build(self, db_path: Path, enricher, discovery):
        from src.ranks.refresh import RankRefreshService
        from src.ranks.repository import RankCacheRepository

        repository = RankCacheRepository(db_path)
        repository.init_schema()
        service = RankRefreshService(
            repository=repository,
            enricher=enricher,
            discovery=discovery,
        )
        return service, repository

    def test_refresh_all_populates_four_tencent_and_four_tmdb_lists(self) -> None:
        enricher = _FakeEnricher(
            {
                "tv": [_item(1)],
                "movie": [_item(2)],
                "variety": [_item(3)],
                "cartoon": [_item(4)],
            }
        )
        discovery = _FakeDiscovery(
            {
                "tv_on_the_air": [_item(11)],
                "trending_tv_week": [_item(12)],
                "tv_popular": [_item(13)],
                "trending_movie_week": [_item(14)],
            }
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            service, repository = self._build(Path(tmp_dir) / "ranks.db", enricher, discovery)
            service.refresh_all()

            self.assertEqual(repository.count(), 8)
            tencent_tv = repository.get(source="tencent", key="tv")
            tmdb_pop = repository.get(source="tmdb", key="tv_popular")

        self.assertIsNotNone(tencent_tv)
        assert tencent_tv is not None
        self.assertEqual(tencent_tv.status, "ok")
        self.assertEqual(tencent_tv.items[0]["tmdb_id"], 1)
        self.assertEqual(tencent_tv.items[0]["kind"], "tv")
        self.assertIn("title", tencent_tv.items[0])
        self.assertIsNotNone(tmdb_pop)
        assert tmdb_pop is not None
        self.assertEqual(tmdb_pop.items[0]["tmdb_id"], 13)

    def test_refresh_records_error_status_per_list_without_aborting_others(self) -> None:
        enricher = _FakeEnricher(
            {"movie": [_item(2)], "variety": [_item(3)], "cartoon": [_item(4)]},
            fail={"tv": RuntimeError("腾讯抓取失败")},
        )
        discovery = _FakeDiscovery(
            {
                "trending_tv_week": [_item(12)],
                "tv_popular": [_item(13)],
                "trending_movie_week": [_item(14)],
            },
            fail={"tv_on_the_air": RuntimeError("TMDB 失败")},
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            service, repository = self._build(Path(tmp_dir) / "ranks.db", enricher, discovery)
            service.refresh_all()

            failed_tencent = repository.get(source="tencent", key="tv")
            ok_tencent = repository.get(source="tencent", key="movie")
            failed_tmdb = repository.get(source="tmdb", key="tv_on_the_air")
            ok_tmdb = repository.get(source="tmdb", key="tv_popular")

        self.assertIsNotNone(failed_tencent)
        assert failed_tencent is not None
        self.assertEqual(failed_tencent.status, "error")
        self.assertIsNotNone(failed_tencent.error)
        self.assertEqual(failed_tencent.items, [])
        self.assertIsNotNone(ok_tencent)
        assert ok_tencent is not None
        self.assertEqual(ok_tencent.status, "ok")
        self.assertIsNotNone(failed_tmdb)
        assert failed_tmdb is not None
        self.assertEqual(failed_tmdb.status, "error")
        self.assertIsNotNone(ok_tmdb)
        assert ok_tmdb is not None
        self.assertEqual(ok_tmdb.status, "ok")

    def test_existing_ok_entry_is_preserved_when_refresh_fails(self) -> None:
        good_enricher = _FakeEnricher({"tv": [_item(1)], "movie": [], "variety": [], "cartoon": []})
        good_discovery = _FakeDiscovery(
            {"tv_on_the_air": [], "trending_tv_week": [], "tv_popular": [], "trending_movie_week": []}
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "ranks.db"
            service, repository = self._build(db_path, good_enricher, good_discovery)
            service.refresh_all()
            self.assertEqual(repository.get(source="tencent", key="tv").items[0]["tmdb_id"], 1)

            failing = _FakeEnricher(
                {"movie": [], "variety": [], "cartoon": []},
                fail={"tv": RuntimeError("boom")},
            )
            service2 = type(service)(
                repository=repository,
                enricher=failing,
                discovery=good_discovery,
            )
            service2.refresh_all()
            tv = repository.get(source="tencent", key="tv")

        self.assertIsNotNone(tv)
        assert tv is not None
        self.assertEqual(tv.status, "error")
        # 旧数据保留：刷新失败时不清空上一份榜单
        self.assertEqual(tv.items[0]["tmdb_id"], 1)


if __name__ == "__main__":
    unittest.main()
