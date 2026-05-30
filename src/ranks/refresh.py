from __future__ import annotations

import logging
from dataclasses import asdict, is_dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)

_SOURCE_TENCENT = "tencent"
_SOURCE_TMDB = "tmdb"

# 腾讯频道榜：4 个频道
_TENCENT_CHANNELS: tuple[str, ...] = ("tv", "movie", "variety", "cartoon")
# TMDB 榜单：4 个 list_key（与 TmdbDiscoveryService._TRENDING_LISTS 对齐）
_TMDB_LISTS: tuple[str, ...] = (
    "tv_on_the_air",
    "trending_tv_week",
    "tv_popular",
    "trending_movie_week",
)

_ITEM_FIELDS = ("tmdb_id", "kind", "title", "original_title", "year", "overview", "poster_path")
_ERROR_MAX_LEN = 500


class _Enricher(Protocol):
    def enrich_channel(self, channel: str, *, limit: int = 10) -> list[Any]: ...


class _Discovery(Protocol):
    def fetch_trending(self, list_key: str, *, limit: int = 20) -> list[Any]: ...


class _Repository(Protocol):
    def upsert(self, *, source: str, key: str, items: list[dict[str, Any]], status: str, error: str | None) -> Any: ...

    def get(self, *, source: str, key: str) -> Any: ...


class RankRefreshService:
    """后台榜单刷新：抓 4 个腾讯频道榜 + 4 个 TMDB 榜，整榜序列化进缓存。

    每个榜单独立 try/except——单个失败不影响其它榜单；失败时保留上一份缓存条目，
    仅把 status 置为 ``error`` 并记录错误信息（前端可据此显示降级提示）。
    """

    def __init__(
        self,
        *,
        repository: _Repository,
        enricher: _Enricher,
        discovery: _Discovery,
        tencent_limit: int = 10,
        tmdb_limit: int = 20,
    ) -> None:
        self._repository = repository
        self._enricher = enricher
        self._discovery = discovery
        self._tencent_limit = tencent_limit
        self._tmdb_limit = tmdb_limit

    def refresh_all(self) -> None:
        for channel in _TENCENT_CHANNELS:
            self._refresh_one(
                source=_SOURCE_TENCENT,
                key=channel,
                fetch=lambda ch=channel: self._enricher.enrich_channel(ch, limit=self._tencent_limit),
            )
        for list_key in _TMDB_LISTS:
            self._refresh_one(
                source=_SOURCE_TMDB,
                key=list_key,
                fetch=lambda lk=list_key: self._discovery.fetch_trending(lk, limit=self._tmdb_limit),
            )

    def _refresh_one(self, *, source: str, key: str, fetch: Any) -> None:
        try:
            raw_items = fetch()
            items = [_serialize_item(item) for item in raw_items]
            self._repository.upsert(source=source, key=key, items=items, status="ok", error=None)
        except Exception as exc:  # noqa: BLE001 - 单榜失败需隔离，不能中断其它榜单
            logger.warning(f"榜单刷新失败 source={source} key={key}: {exc}")
            previous = self._repository.get(source=source, key=key)
            preserved = list(previous.items) if previous is not None else []
            self._repository.upsert(
                source=source,
                key=key,
                items=preserved,
                status="error",
                error=_sanitize_error(str(exc)),
            )


def _serialize_item(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        source = item
    elif is_dataclass(item) and not isinstance(item, type):
        source = asdict(item)
    else:
        source = {field: getattr(item, field, None) for field in _ITEM_FIELDS}
    return {field: source.get(field) for field in _ITEM_FIELDS}


def _sanitize_error(message: str) -> str:
    cleaned = " ".join(message.split())
    if len(cleaned) > _ERROR_MAX_LEN:
        return cleaned[: _ERROR_MAX_LEN - 3] + "..."
    return cleaned


__all__ = ["RankRefreshService"]
