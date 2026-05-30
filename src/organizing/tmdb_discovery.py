from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from .tmdb import (
    TmdbConfig,
    TmdbCredentialError,
    TmdbError,
    TmdbRetryableError,
    _Client,
)


_TMDB_KIND_MOVIE = "movie"
_TMDB_KIND_TV = "tv"
_VALID_KINDS = frozenset({_TMDB_KIND_MOVIE, _TMDB_KIND_TV})

# 榜单 list_key → (endpoint 相对路径, 该榜单缺省 media_type 时使用的 kind)
_TRENDING_LISTS: dict[str, tuple[str, str]] = {
    "tv_on_the_air": ("tv/on_the_air", _TMDB_KIND_TV),
    "trending_tv_week": ("trending/tv/week", _TMDB_KIND_TV),
    "tv_popular": ("tv/popular", _TMDB_KIND_TV),
    "trending_movie_week": ("trending/movie/week", _TMDB_KIND_MOVIE),
}


@dataclass(frozen=True)
class TmdbSearchResult:
    tmdb_id: int
    kind: str
    title: str
    original_title: str
    year: int | None
    overview: str
    poster_path: str | None


@dataclass(frozen=True)
class TmdbAliasBundle:
    tmdb_id: int
    kind: str
    title: str
    original_title: str
    year: int | None
    aliases: tuple[str, ...] = field(default_factory=tuple)


class TmdbDiscoveryService:
    def __init__(self, config: TmdbConfig, client: _Client | None = None) -> None:
        self._config = config
        self._client = client

    def get_by_id(self, kind: str, tmdb_id: int) -> TmdbSearchResult | None:
        """根据 TMDB ID 直接获取媒体信息

        Args:
            kind: 媒体类型，"movie" 或 "tv"
            tmdb_id: TMDB ID

        Returns:
            TmdbSearchResult 或 None（如果 ID 无效或请求失败）
        """
        normalized_kind = kind.strip().lower()
        if normalized_kind not in _VALID_KINDS:
            raise ValueError(f"kind must be one of {sorted(_VALID_KINDS)}")
        if tmdb_id <= 0:
            raise ValueError(f"tmdb_id must be a positive integer, got {tmdb_id}")

        if self._client is not None:
            return self._get_by_id_with_client(self._client, normalized_kind, tmdb_id)
        with httpx.Client(timeout=self._config.timeout_seconds) as client:
            return self._get_by_id_with_client(client, normalized_kind, tmdb_id)

    def search_multi(self, query: str, *, limit: int = 10) -> list[TmdbSearchResult]:
        normalized = query.strip()
        if not normalized:
            raise ValueError("query must not be empty")
        if limit <= 0:
            raise ValueError(f"limit must be a positive integer, got {limit}")

        if self._client is not None:
            return self._search_multi_with_client(self._client, normalized, limit)
        with httpx.Client(timeout=self._config.timeout_seconds) as client:
            return self._search_multi_with_client(client, normalized, limit)

    def fetch_trending(self, list_key: str, *, limit: int = 20) -> list[TmdbSearchResult]:
        entry = _TRENDING_LISTS.get(list_key)
        if entry is None:
            raise ValueError(f"list_key must be one of {sorted(_TRENDING_LISTS)}")
        if limit <= 0:
            raise ValueError(f"limit must be a positive integer, got {limit}")
        path, default_kind = entry

        if self._client is not None:
            return self._fetch_trending_with_client(self._client, path, default_kind, limit)
        with httpx.Client(timeout=self._config.timeout_seconds) as client:
            return self._fetch_trending_with_client(client, path, default_kind, limit)

    def collect_aliases(self, kind: str, tmdb_id: int) -> TmdbAliasBundle:
        normalized_kind = kind.strip().lower()
        if normalized_kind not in _VALID_KINDS:
            raise ValueError(f"kind must be one of {sorted(_VALID_KINDS)}")
        if tmdb_id <= 0:
            raise ValueError(f"tmdb_id must be a positive integer, got {tmdb_id}")

        if self._client is not None:
            return self._collect_aliases_with_client(self._client, normalized_kind, tmdb_id)
        with httpx.Client(timeout=self._config.timeout_seconds) as client:
            return self._collect_aliases_with_client(client, normalized_kind, tmdb_id)

    def _get_by_id_with_client(
        self,
        client: _Client,
        kind: str,
        tmdb_id: int,
    ) -> TmdbSearchResult | None:
        try:
            detail = self._fetch_detail(client, kind, tmdb_id)
            if not detail:
                return None

            title = _detail_title(detail, kind)
            original_title = _detail_original_title(detail, kind)
            year = _detail_year(detail, kind)

            if not title and not original_title:
                return None

            overview = str(detail.get("overview", "")).strip()
            poster = detail.get("poster_path")

            return TmdbSearchResult(
                tmdb_id=tmdb_id,
                kind=kind,
                title=title if title else original_title,
                original_title=original_title if original_title else title,
                year=year,
                overview=overview,
                poster_path=poster if isinstance(poster, str) and poster else None,
            )
        except (TmdbError, httpx.HTTPError):
            return None

    def _search_multi_with_client(
        self,
        client: _Client,
        query: str,
        limit: int,
    ) -> list[TmdbSearchResult]:
        response = _get(
            client,
            f"{self._config.base_url.rstrip('/')}/search/multi",
            headers=self._headers(),
            params=self._build_search_params(query),
        )
        _raise_for_status(response.status_code)
        payload = response.json()
        raw = payload.get("results", []) if isinstance(payload, dict) else []
        results: list[TmdbSearchResult] = []
        for entry in raw:
            converted = _search_result_from_payload(entry)
            if converted is not None:
                results.append(converted)
                if len(results) >= limit:
                    break
        return results

    def _fetch_trending_with_client(
        self,
        client: _Client,
        path: str,
        default_kind: str,
        limit: int,
    ) -> list[TmdbSearchResult]:
        response = _get(
            client,
            f"{self._config.base_url.rstrip('/')}/{path}",
            headers=self._headers(),
            params=self._build_detail_params(),
        )
        _raise_for_status(response.status_code)
        payload = response.json()
        raw = payload.get("results", []) if isinstance(payload, dict) else []
        results: list[TmdbSearchResult] = []
        for entry in raw:
            converted = _list_result_from_payload(entry, default_kind)
            if converted is not None:
                results.append(converted)
                if len(results) >= limit:
                    break
        return results

    def _collect_aliases_with_client(
        self,
        client: _Client,
        kind: str,
        tmdb_id: int,
    ) -> TmdbAliasBundle:
        detail = self._fetch_detail(client, kind, tmdb_id)
        alt_titles = self._fetch_alternative_titles(client, kind, tmdb_id)
        title = _detail_title(detail, kind)
        original_title = _detail_original_title(detail, kind)
        year = _detail_year(detail, kind)
        aliases = _merge_aliases(
            title=title,
            original_title=original_title,
            detail=detail,
            alternative_titles=alt_titles,
        )
        return TmdbAliasBundle(
            tmdb_id=tmdb_id,
            kind=kind,
            title=title,
            original_title=original_title,
            year=year,
            aliases=aliases,
        )

    def _fetch_detail(self, client: _Client, kind: str, tmdb_id: int) -> dict[str, Any]:
        response = _get(
            client,
            f"{self._config.base_url.rstrip('/')}/{kind}/{tmdb_id}",
            headers=self._headers(),
            params=self._build_detail_params(),
        )
        _raise_for_status(response.status_code)
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def _fetch_alternative_titles(self, client: _Client, kind: str, tmdb_id: int) -> dict[str, Any]:
        response = _get(
            client,
            f"{self._config.base_url.rstrip('/')}/{kind}/{tmdb_id}/alternative_titles",
            headers=self._headers(),
            params={},
        )
        _raise_for_status(response.status_code)
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._config.bearer_token}",
            "Accept": "application/json",
        }

    def _build_search_params(self, query: str) -> dict[str, Any]:
        params: dict[str, Any] = {"query": query, "include_adult": "false"}
        if self._config.language:
            params["language"] = self._config.language
        return params

    def _build_detail_params(self) -> dict[str, Any]:
        if not self._config.language:
            return {}
        return {"language": self._config.language}


def _raise_for_status(status_code: int) -> None:
    if status_code == 200:
        return
    if status_code == 401:
        raise TmdbCredentialError("TMDB credentials were rejected")
    if status_code == 429 or 500 <= status_code <= 599:
        raise TmdbRetryableError(f"TMDB request failed with retryable status {status_code}")
    raise TmdbError(f"TMDB request failed with status {status_code}")


def _get(client: _Client, url: str, *, headers: dict[str, str], params: dict[str, Any]) -> Any:
    try:
        return client.get(url, headers=headers, params=params)
    except httpx.TransportError as exc:
        raise TmdbRetryableError(f"TMDB API 连接失败: {exc}") from exc


def _search_result_from_payload(entry: Any) -> TmdbSearchResult | None:
    if not isinstance(entry, dict):
        return None
    media_type = entry.get("media_type")
    if media_type not in _VALID_KINDS:
        return None
    tmdb_id = entry.get("id")
    if not (isinstance(tmdb_id, int) and tmdb_id > 0):
        return None
    if media_type == _TMDB_KIND_MOVIE:
        title = str(entry.get("title", "")).strip()
        original_title = str(entry.get("original_title", "")).strip()
        year = _parse_year(entry.get("release_date"))
    else:
        title = str(entry.get("name", "")).strip()
        original_title = str(entry.get("original_name", "")).strip()
        year = _parse_year(entry.get("first_air_date"))
    if not title and not original_title:
        return None
    poster = entry.get("poster_path")
    overview = str(entry.get("overview", "")).strip()
    return TmdbSearchResult(
        tmdb_id=tmdb_id,
        kind=media_type,
        title=title if title else original_title,
        original_title=original_title if original_title else title,
        year=year,
        overview=overview,
        poster_path=poster if isinstance(poster, str) and poster else None,
    )


def _list_result_from_payload(entry: Any, default_kind: str) -> TmdbSearchResult | None:
    if not isinstance(entry, dict):
        return None
    media_type = entry.get("media_type")
    kind = media_type if media_type in _VALID_KINDS else default_kind
    if kind not in _VALID_KINDS:
        return None
    tmdb_id = entry.get("id")
    if not (isinstance(tmdb_id, int) and tmdb_id > 0):
        return None
    if kind == _TMDB_KIND_MOVIE:
        title = str(entry.get("title", "")).strip()
        original_title = str(entry.get("original_title", "")).strip()
        year = _parse_year(entry.get("release_date"))
    else:
        title = str(entry.get("name", "")).strip()
        original_title = str(entry.get("original_name", "")).strip()
        year = _parse_year(entry.get("first_air_date"))
    if not title and not original_title:
        return None
    poster = entry.get("poster_path")
    overview = str(entry.get("overview", "")).strip()
    return TmdbSearchResult(
        tmdb_id=tmdb_id,
        kind=kind,
        title=title if title else original_title,
        original_title=original_title if original_title else title,
        year=year,
        overview=overview,
        poster_path=poster if isinstance(poster, str) and poster else None,
    )


def _detail_title(detail: dict[str, Any], kind: str) -> str:
    if kind == _TMDB_KIND_MOVIE:
        return str(detail.get("title", "") or "").strip()
    return str(detail.get("name", "") or "").strip()


def _detail_original_title(detail: dict[str, Any], kind: str) -> str:
    if kind == _TMDB_KIND_MOVIE:
        return str(detail.get("original_title", "") or "").strip()
    return str(detail.get("original_name", "") or "").strip()


def _detail_year(detail: dict[str, Any], kind: str) -> int | None:
    raw = detail.get("release_date") if kind == _TMDB_KIND_MOVIE else detail.get("first_air_date")
    return _parse_year(raw)


def _parse_year(raw: Any) -> int | None:
    if not isinstance(raw, str) or len(raw) < 4:
        return None
    head = raw[:4]
    if not head.isdigit():
        return None
    year = int(head)
    # 验证年份在合理范围内（1800-2100）
    if year < 1800 or year > 2100:
        return None
    return year


def _merge_aliases(
    *,
    title: str,
    original_title: str,
    detail: dict[str, Any],
    alternative_titles: dict[str, Any],
) -> tuple[str, ...]:
    seen: dict[str, None] = {}

    def _add(value: Any) -> None:
        if not isinstance(value, str):
            return
        cleaned = value.strip()
        if not cleaned:
            return
        seen.setdefault(cleaned, None)

    _add(title)
    _add(original_title)

    for key in ("titles", "results"):
        block = alternative_titles.get(key)
        if isinstance(block, list):
            for entry in block:
                if isinstance(entry, dict):
                    _add(entry.get("title"))

    return tuple(seen.keys())


__all__ = [
    "TmdbAliasBundle",
    "TmdbDiscoveryService",
    "TmdbSearchResult",
]
