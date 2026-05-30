from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from src.collectors.tencent_ranks import TencentRankItem
from src.organizing.tmdb_discovery import TmdbSearchResult

logger = logging.getLogger(__name__)

# 腾讯频道 → TMDB 期望 kind：电影频道收 movie，其余（电视剧/综艺/动漫）都收 tv。
# 综艺/动漫在 TMDB 里基本是 tv 条目；强制约束可避免电影混入这些频道。
_CHANNEL_EXPECTED_KIND: dict[str, str] = {
    "movie": "movie",
    "tv": "tv",
    "variety": "tv",
    "cartoon": "tv",
}

# 反查时多取几个候选，便于按期望 kind 过滤后仍有命中。
_MATCH_CANDIDATES = 5


@dataclass(frozen=True)
class EnrichedRankItem:
    rank: int
    title: str
    raw_title: str
    tmdb_id: int
    kind: str
    original_title: str
    year: int | None
    overview: str
    poster_path: str | None


class _Collector(Protocol):
    def fetch_channel(self, channel: str, *, limit: int = 10) -> list[TencentRankItem]: ...


class _Discovery(Protocol):
    def search_multi(self, query: str, *, limit: int = 10) -> list[TmdbSearchResult]: ...


class TencentRankEnricher:
    """抓腾讯频道榜 → 用清洗后的片名反查 TMDB → 补全 tmdb_id 等元数据。

    反查不到 TMDB 结果的条目直接丢弃（隐藏），保留下来的条目按原榜单顺序重排 rank。
    """

    def __init__(self, collector: _Collector, discovery: _Discovery) -> None:
        self._collector = collector
        self._discovery = discovery

    def enrich_channel(self, channel: str, *, limit: int = 10) -> list[EnrichedRankItem]:
        rank_items = self._collector.fetch_channel(channel, limit=limit)
        expected_kind = _CHANNEL_EXPECTED_KIND.get(channel)

        enriched: list[EnrichedRankItem] = []
        seen_tmdb_ids: set[int] = set()
        for item in rank_items:
            match = self._best_match(item.title, expected_kind)
            if match is None:
                logger.debug(f"腾讯榜单项「{item.title}」未匹配到 TMDB（或类型不符），隐藏")
                continue
            if match.tmdb_id in seen_tmdb_ids:
                # 多季剧清洗后同名，反查到同一 tmdb_id；去重，保留先出现的
                logger.debug(f"腾讯榜单项「{item.title}」tmdb_id={match.tmdb_id} 重复，跳过")
                continue
            seen_tmdb_ids.add(match.tmdb_id)
            enriched.append(
                EnrichedRankItem(
                    rank=len(enriched) + 1,
                    title=item.title,
                    raw_title=item.raw_title,
                    tmdb_id=match.tmdb_id,
                    kind=match.kind,
                    original_title=match.original_title,
                    year=match.year,
                    overview=match.overview,
                    poster_path=match.poster_path,
                )
            )
        return enriched

    def _best_match(self, title: str, expected_kind: str | None) -> TmdbSearchResult | None:
        # 单条反查失败（TMDB 瞬时断连等）只隐藏该条，不能中止整榜刷新。
        try:
            results = self._discovery.search_multi(title, limit=_MATCH_CANDIDATES)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"腾讯榜单项「{title}」反查 TMDB 失败（已隐藏该条）: {exc}")
            return None
        if not results:
            return None
        if expected_kind is None:
            return results[0]
        for result in results:
            if result.kind == expected_kind:
                return result
        return None
