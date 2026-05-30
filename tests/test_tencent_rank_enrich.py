from __future__ import annotations

import unittest

from src.collectors.tencent_ranks import TencentRankItem
from src.organizing.tmdb_discovery import TmdbSearchResult
from src.processors.tencent_rank_enrich import (
    EnrichedRankItem,
    TencentRankEnricher,
)


class _FakeCollector:
    def __init__(self, items: list[TencentRankItem]) -> None:
        self._items = items
        self.calls: list[tuple[str, int]] = []

    def fetch_channel(self, channel: str, *, limit: int = 10) -> list[TencentRankItem]:
        self.calls.append((channel, limit))
        return self._items


class _FakeDiscovery:
    def __init__(self, mapping: dict[str, list[TmdbSearchResult]]) -> None:
        self._mapping = mapping
        self.queries: list[str] = []

    def search_multi(self, query: str, *, limit: int = 10) -> list[TmdbSearchResult]:
        self.queries.append(query)
        return self._mapping.get(query, [])


def _result(tmdb_id: int, title: str, kind: str = "tv") -> TmdbSearchResult:
    return TmdbSearchResult(
        tmdb_id=tmdb_id,
        kind=kind,
        title=title,
        original_title=title,
        year=2026,
        overview="",
        poster_path=f"/{tmdb_id}.jpg",
    )


class TencentRankEnricherTest(unittest.TestCase):
    def test_enriches_items_with_first_tmdb_match(self) -> None:
        collector = _FakeCollector(
            [
                TencentRankItem(rank=1, title="主角", raw_title="主角"),
                TencentRankItem(rank=2, title="奔跑吧", raw_title="奔跑吧 第10季"),
            ]
        )
        discovery = _FakeDiscovery(
            {
                "主角": [_result(101, "主角")],
                "奔跑吧": [_result(202, "奔跑吧", kind="tv")],
            }
        )
        enricher = TencentRankEnricher(collector=collector, discovery=discovery)

        items = enricher.enrich_channel("tv", limit=5)

        self.assertEqual(collector.calls, [("tv", 5)])
        self.assertEqual([i.rank for i in items], [1, 2])
        self.assertEqual(items[0].tmdb_id, 101)
        self.assertEqual(items[0].title, "主角")
        self.assertEqual(items[0].raw_title, "主角")
        self.assertEqual(items[0].poster_path, "/101.jpg")
        self.assertEqual(items[1].tmdb_id, 202)
        self.assertTrue(all(isinstance(i, EnrichedRankItem) for i in items))

    def test_hides_items_with_no_tmdb_match(self) -> None:
        collector = _FakeCollector(
            [
                TencentRankItem(rank=1, title="主角", raw_title="主角"),
                TencentRankItem(rank=2, title="短剧X家族", raw_title="短剧X家族"),
            ]
        )
        discovery = _FakeDiscovery({"主角": [_result(101, "主角")]})
        enricher = TencentRankEnricher(collector=collector, discovery=discovery)

        items = enricher.enrich_channel("tv")

        # 反查无结果的「短剧X家族」被隐藏，rank 连续重排
        self.assertEqual([i.title for i in items], ["主角"])
        self.assertEqual([i.rank for i in items], [1])

    def test_uses_cleaned_title_as_query(self) -> None:
        collector = _FakeCollector(
            [TencentRankItem(rank=1, title="奔跑吧", raw_title="奔跑吧 第10季")]
        )
        discovery = _FakeDiscovery({"奔跑吧": [_result(202, "奔跑吧")]})
        enricher = TencentRankEnricher(collector=collector, discovery=discovery)

        enricher.enrich_channel("tv")

        # 用清洗后的 title 反查，而非带季号的 raw_title
        self.assertEqual(discovery.queries, ["奔跑吧"])

    def test_propagates_unknown_channel(self) -> None:
        class _Raising:
            def fetch_channel(self, channel: str, *, limit: int = 10):
                raise ValueError("bad channel")

        enricher = TencentRankEnricher(collector=_Raising(), discovery=_FakeDiscovery({}))
        with self.assertRaises(ValueError):
            enricher.enrich_channel("documentary")

    def test_dedupes_by_tmdb_id_keeping_first(self) -> None:
        # 多季剧清洗后同名，反查到同一 tmdb_id，应只保留第一条
        collector = _FakeCollector(
            [
                TencentRankItem(rank=1, title="庆余年", raw_title="庆余年 第二季"),
                TencentRankItem(rank=2, title="庆余年", raw_title="庆余年 第一季"),
                TencentRankItem(rank=3, title="主角", raw_title="主角"),
            ]
        )
        discovery = _FakeDiscovery(
            {
                "庆余年": [_result(500, "庆余年", kind="tv")],
                "主角": [_result(101, "主角", kind="tv")],
            }
        )
        enricher = TencentRankEnricher(collector=collector, discovery=discovery)

        items = enricher.enrich_channel("tv")

        self.assertEqual([i.tmdb_id for i in items], [500, 101])
        self.assertEqual([i.rank for i in items], [1, 2])

    def test_non_movie_channel_drops_movie_matches(self) -> None:
        # 综艺频道里反查首位是电影的条目应被丢弃，选 tv 候选
        collector = _FakeCollector(
            [
                TencentRankItem(rank=1, title="某综艺", raw_title="某综艺"),
                TencentRankItem(rank=2, title="混入的电影", raw_title="混入的电影"),
            ]
        )
        discovery = _FakeDiscovery(
            {
                # 首位是电影同名，但有 tv 候选 → 选 tv
                "某综艺": [_result(11, "某综艺", kind="movie"), _result(12, "某综艺", kind="tv")],
                # 只有电影候选 → 综艺频道丢弃
                "混入的电影": [_result(20, "混入的电影", kind="movie")],
            }
        )
        enricher = TencentRankEnricher(collector=collector, discovery=discovery)

        items = enricher.enrich_channel("variety")

        self.assertEqual([i.tmdb_id for i in items], [12])
        self.assertEqual(items[0].kind, "tv")

    def test_movie_channel_keeps_only_movie_matches(self) -> None:
        collector = _FakeCollector(
            [
                TencentRankItem(rank=1, title="电影A", raw_title="电影A"),
                TencentRankItem(rank=2, title="剧集B", raw_title="剧集B"),
            ]
        )
        discovery = _FakeDiscovery(
            {
                "电影A": [_result(30, "电影A", kind="movie")],
                # 电影频道里只有 tv 候选 → 丢弃
                "剧集B": [_result(40, "剧集B", kind="tv")],
            }
        )
        enricher = TencentRankEnricher(collector=collector, discovery=discovery)

        items = enricher.enrich_channel("movie")

        self.assertEqual([i.tmdb_id for i in items], [30])
        self.assertEqual(items[0].kind, "movie")


if __name__ == "__main__":
    unittest.main()
