from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from .models import MEDIA_KIND_MOVIE, MEDIA_KIND_SERIES, OrganizeMetadata

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TmdbConfig:
    bearer_token: str
    language: str = "zh-CN"
    base_url: str = "https://api.themoviedb.org/3"
    timeout_seconds: float = 10.0


@dataclass(frozen=True)
class _RegionMetadata:
    primary: str | None
    candidates: tuple[str, ...]
    category: str | None
    source: str | None
    confidence: str


class TmdbError(Exception):
    """Base error raised by TMDB movie resolution."""


class TmdbCredentialError(TmdbError):
    """Raised when TMDB rejects the configured bearer token."""


class TmdbRetryableError(TmdbError):
    """Raised for rate-limit and transient TMDB server failures."""


class _Response(Protocol):
    status_code: int

    def json(self) -> Any: ...


class _Client(Protocol):
    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, Any],
    ) -> _Response: ...


class TmdbMovieResolver:
    def __init__(self, config: TmdbConfig, client: _Client | None = None) -> None:
        self._config = config
        self._client = client

    def resolve_movie(self, query: str, *, year: int | None = None) -> OrganizeMetadata | None:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query must not be empty")

        logger.info(f"TMDB 电影搜索: query='{normalized_query}', year={year}")

        if self._client is not None:
            return self._resolve_with_client(self._client, normalized_query, year)

        # 创建带有重试和 SSL 配置的客户端
        try:
            with httpx.Client(
                timeout=self._config.timeout_seconds,
                verify=True,
                http2=False,  # 禁用 HTTP/2 可能解决某些 SSL 问题
            ) as client:
                return self._resolve_with_client(client, normalized_query, year)
        except httpx.TransportError as e:
            logger.error(f"TMDB 连接错误: {e}")
            raise TmdbRetryableError(f"TMDB API 连接失败: {e}") from e

    def _resolve_with_client(
        self,
        client: _Client,
        query: str,
        year: int | None,
    ) -> OrganizeMetadata | None:
        response = client.get(
            self._search_movie_url(),
            headers={
                "Authorization": f"Bearer {self._config.bearer_token}",
                "Accept": "application/json",
            },
            params=self._build_params(query, year),
        )
        self._raise_for_status(response.status_code)

        payload = response.json()
        results = payload.get("results", []) if isinstance(payload, dict) else []
        if not results:
            logger.warning(f"TMDB 搜索无结果: query='{query}', year={year}")
            return None

        result = results[0]
        if not isinstance(result, dict):
            logger.warning("TMDB 返回无效结果格式")
            return None

        title = str(result.get("title", "")).strip()
        if not title:
            logger.warning("TMDB 搜索结果缺少有效标题")
            return None

        release_date = result.get("release_date")
        region_source_payload = self._fetch_movie_detail(client, result) or result
        region = _extract_movie_region(region_source_payload)

        metadata = OrganizeMetadata(
            title=title,
            year=_parse_release_year(release_date),
            kind=MEDIA_KIND_MOVIE,
            tmdb_id=_parse_tmdb_id(result),
            genre_ids=_parse_genre_ids(result, region_source_payload),
            region_primary=region.primary,
            region_candidates=region.candidates,
            region_category=region.category,
            region_source=region.source,
            region_confidence=region.confidence,
        )

        logger.info(f"TMDB 解析成功: '{title}' ({metadata.year}), 地区: {region.primary}")
        return metadata

    def _search_movie_url(self) -> str:
        return f"{self._config.base_url.rstrip('/')}/search/movie"

    def _movie_detail_url(self, movie_id: int) -> str:
        return f"{self._config.base_url.rstrip('/')}/movie/{movie_id}"

    def _fetch_movie_detail(self, client: _Client, result: Any) -> dict[str, Any] | None:
        movie_id = _parse_movie_id(result)
        if movie_id is None:
            return None
        response = client.get(
            self._movie_detail_url(movie_id),
            headers={
                "Authorization": f"Bearer {self._config.bearer_token}",
                "Accept": "application/json",
            },
            params=self._build_detail_params(),
        )
        self._raise_for_status(response.status_code)
        payload = response.json()
        return payload if isinstance(payload, dict) else None

    def _build_params(self, query: str, year: int | None) -> dict[str, Any]:
        params: dict[str, Any] = {"query": query}
        if self._config.language:
            params["language"] = self._config.language
        if year is not None and year > 0:
            params["year"] = year
        return params

    def _build_detail_params(self) -> dict[str, Any]:
        if not self._config.language:
            return {}
        return {"language": self._config.language}

    def _raise_for_status(self, status_code: int) -> None:
        if status_code == 200:
            return
        if status_code == 401:
            raise TmdbCredentialError("TMDB credentials were rejected")
        if status_code == 429 or 500 <= status_code <= 599:
            raise TmdbRetryableError(f"TMDB request failed with retryable status {status_code}")
        raise TmdbError(f"TMDB request failed with status {status_code}")


class TmdbMultiResolver(TmdbMovieResolver):
    def resolve_by_id(self, tmdb_id: int) -> OrganizeMetadata | None:
        """根据 TMDB ID 直接获取元数据（自动尝试 movie 和 tv 类型）

        Args:
            tmdb_id: TMDB ID

        Returns:
            OrganizeMetadata 或 None（如果 ID 无效或请求失败）
        """
        if tmdb_id <= 0:
            raise ValueError(f"tmdb_id must be a positive integer, got {tmdb_id}")

        logger.info(f"TMDB ID 查询: tmdb_id={tmdb_id}")

        if self._client is not None:
            return self._resolve_by_id_with_client(self._client, tmdb_id)

        try:
            with httpx.Client(
                timeout=self._config.timeout_seconds,
                verify=True,
                http2=False,
            ) as client:
                return self._resolve_by_id_with_client(client, tmdb_id)
        except httpx.TransportError as e:
            logger.error(f"TMDB 连接错误: {e}")
            raise TmdbRetryableError(f"TMDB API 连接失败: {e}") from e

    def _resolve_by_id_with_client(
        self,
        client: _Client,
        tmdb_id: int,
    ) -> OrganizeMetadata | None:
        # 先尝试 TV（因为剧集更常见）
        try:
            detail = self._fetch_tv_detail(client, {"id": tmdb_id})
            if detail:
                title = str(detail.get("name", "")).strip()
                if title:
                    first_air_date = detail.get("first_air_date")
                    region = _extract_tv_region(detail)
                    logger.info(f"TMDB ID 查询成功 (TV): '{title}' ({_parse_release_year(first_air_date)})")
                    return OrganizeMetadata(
                        title=title,
                        year=_parse_release_year(first_air_date),
                        kind=MEDIA_KIND_SERIES,
                        tmdb_id=_parse_tmdb_id(detail),
                        genre_ids=_parse_genre_ids(detail),
                        region_primary=region.primary,
                        region_candidates=region.candidates,
                        region_category=region.category,
                        region_source=region.source,
                        region_confidence=region.confidence,
                    )
        except TmdbError:
            pass  # TV 查询失败，尝试 Movie

        # 尝试 Movie
        try:
            detail = self._fetch_movie_detail(client, {"id": tmdb_id})
            if detail:
                title = str(detail.get("title", "")).strip()
                if title:
                    release_date = detail.get("release_date")
                    region = _extract_movie_region(detail)
                    logger.info(f"TMDB ID 查询成功 (Movie): '{title}' ({_parse_release_year(release_date)})")
                    return OrganizeMetadata(
                        title=title,
                        year=_parse_release_year(release_date),
                        kind=MEDIA_KIND_MOVIE,
                        tmdb_id=_parse_tmdb_id(detail),
                        genre_ids=_parse_genre_ids(detail),
                        region_primary=region.primary,
                        region_candidates=region.candidates,
                        region_category=region.category,
                        region_source=region.source,
                        region_confidence=region.confidence,
                    )
        except TmdbError:
            pass  # Movie 查询也失败

        logger.warning(f"TMDB ID 查询失败: tmdb_id={tmdb_id}（TV 和 Movie 都未找到）")
        return None

    def resolve_multi(self, query: str, *, year: int | None = None) -> OrganizeMetadata | None:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query must not be empty")

        logger.info(f"TMDB 多类型搜索: query='{normalized_query}', year={year}")

        if self._client is not None:
            return self._resolve_multi_with_client(self._client, normalized_query, year)

        # 创建带有重试和 SSL 配置的客户端
        try:
            with httpx.Client(
                timeout=self._config.timeout_seconds,
                verify=True,
                http2=False,
            ) as client:
                return self._resolve_multi_with_client(client, normalized_query, year)
        except httpx.TransportError as e:
            logger.error(f"TMDB 连接错误: {e}")
            raise TmdbRetryableError(f"TMDB API 连接失败: {e}") from e

    def _resolve_multi_with_client(
        self,
        client: _Client,
        query: str,
        year: int | None,
    ) -> OrganizeMetadata | None:
        response = client.get(
            self._search_multi_url(),
            headers={
                "Authorization": f"Bearer {self._config.bearer_token}",
                "Accept": "application/json",
            },
            params=self._build_params(query, year),
        )
        self._raise_for_status(response.status_code)

        payload = response.json()
        results = payload.get("results", []) if isinstance(payload, dict) else []
        for result in results:
            metadata = self._metadata_from_multi_result(client, result)
            if metadata is not None:
                return metadata
        return None

    def _search_multi_url(self) -> str:
        return f"{self._config.base_url.rstrip('/')}/search/multi"

    def _tv_detail_url(self, tv_id: int) -> str:
        return f"{self._config.base_url.rstrip('/')}/tv/{tv_id}"

    def _metadata_from_multi_result(self, client: _Client, result: Any) -> OrganizeMetadata | None:
        if not isinstance(result, dict):
            return None
        media_type = result.get("media_type")
        if media_type == "movie":
            return self._movie_metadata_from_multi_result(client, result)
        if media_type == "tv":
            return self._tv_metadata_from_multi_result(client, result)
        return None

    def _movie_metadata_from_multi_result(self, client: _Client, result: dict[str, Any]) -> OrganizeMetadata | None:
        title = str(result.get("title", "")).strip()
        if not title:
            logger.warning("TMDB multi 搜索结果缺少有效标题")
            return None
        release_date = result.get("release_date")
        region_source_payload = self._fetch_movie_detail(client, result) or result
        region = _extract_movie_region(region_source_payload)
        return OrganizeMetadata(
            title=title,
            year=_parse_release_year(release_date),
            kind=MEDIA_KIND_MOVIE,
            tmdb_id=_parse_tmdb_id(result),
            genre_ids=_parse_genre_ids(result, region_source_payload),
            region_primary=region.primary,
            region_candidates=region.candidates,
            region_category=region.category,
            region_source=region.source,
            region_confidence=region.confidence,
        )

    def _tv_metadata_from_multi_result(self, client: _Client, result: dict[str, Any]) -> OrganizeMetadata | None:
        title = str(result.get("name", "")).strip()
        if not title:
            logger.warning("TMDB multi 搜索结果缺少有效标题")
            return None
        first_air_date = result.get("first_air_date")
        detail = self._fetch_tv_detail(client, result)
        region_source_payload = detail or result
        region = _extract_tv_region(region_source_payload)
        return OrganizeMetadata(
            title=title,
            year=_parse_release_year(first_air_date),
            kind=MEDIA_KIND_SERIES,
            tmdb_id=_parse_tmdb_id(result),
            genre_ids=_parse_genre_ids(result, region_source_payload),
            region_primary=region.primary,
            region_candidates=region.candidates,
            region_category=region.category,
            region_source=region.source,
            region_confidence=region.confidence,
        )

    def _fetch_tv_detail(self, client: _Client, result: Any) -> dict[str, Any] | None:
        tv_id = _parse_tmdb_id(result)
        if tv_id is None:
            return None
        response = client.get(
            self._tv_detail_url(tv_id),
            headers={
                "Authorization": f"Bearer {self._config.bearer_token}",
                "Accept": "application/json",
            },
            params=self._build_detail_params(),
        )
        self._raise_for_status(response.status_code)
        payload = response.json()
        return payload if isinstance(payload, dict) else None


DOMESTIC_COUNTRIES = frozenset({"CN", "HK", "TW"})
EAST_ASIA_COUNTRIES = frozenset({"JP", "KR"})
WESTERN_COUNTRIES = frozenset(
    {
        "US",
        "CA",
        "GB",
        "FR",
        "DE",
        "IT",
        "ES",
        "NL",
        "SE",
        "NO",
        "DK",
        "BE",
        "CH",
        "AT",
        "IE",
        "PT",
        "AU",
        "NZ",
    }
)


def _parse_release_year(release_date: Any) -> int | None:
    if not isinstance(release_date, str) or len(release_date) < 4:
        return None
    year_text = release_date[:4]
    if not year_text.isdigit():
        return None
    year = int(year_text)
    # 验证年份在合理范围内（1800-2100）
    if year < 1800 or year > 2100:
        return None
    return year


def _parse_tmdb_id(result: Any) -> int | None:
    if not isinstance(result, dict):
        return None
    tmdb_id = result.get("id")
    if isinstance(tmdb_id, int) and tmdb_id > 0:
        return tmdb_id
    return None


def _parse_genre_ids(*sources: Any) -> tuple[int, ...]:
    """从搜索结果的 genre_ids 或详情的 genres 提取 TMDB 类型 ID，按出现顺序去重。"""
    ids: list[int] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        for value in _genre_id_values(source.get("genre_ids")):
            if value not in ids:
                ids.append(value)
        for genre in source.get("genres") or []:
            if isinstance(genre, dict):
                genre_id = genre.get("id")
                if isinstance(genre_id, int) and genre_id > 0 and genre_id not in ids:
                    ids.append(genre_id)
    return tuple(ids)


def _genre_id_values(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, int) and item > 0]


def _parse_movie_id(result: Any) -> int | None:
    return _parse_tmdb_id(result)


def _extract_movie_region(result: Any) -> _RegionMetadata:
    if not isinstance(result, dict):
        return _unknown_region()

    production_countries = _country_codes_from_production_countries(result.get("production_countries"))
    if production_countries:
        return _build_region(production_countries, source="production_countries", confidence="high")

    company_countries = _country_codes_from_origin_country(result.get("production_companies"))
    if company_countries:
        return _build_region(company_countries, source="production_companies", confidence="medium")

    return _unknown_region()


def _extract_tv_region(result: Any) -> _RegionMetadata:
    if not isinstance(result, dict):
        return _unknown_region()

    origin_countries = _country_codes_from_strings(result.get("origin_country"))
    if origin_countries:
        return _build_region(origin_countries, source="origin_country", confidence="high")

    production_countries = _country_codes_from_production_countries(result.get("production_countries"))
    if production_countries:
        return _build_region(production_countries, source="production_countries", confidence="high")

    company_countries = _country_codes_from_origin_country(result.get("production_companies"))
    if company_countries:
        return _build_region(company_countries, source="production_companies", confidence="medium")

    network_countries = _country_codes_from_origin_country(result.get("networks"))
    if network_countries:
        return _build_region(network_countries, source="networks", confidence="medium")

    return _unknown_region()


def _country_codes_from_strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    codes: list[str] = []
    for item in value:
        _append_country_code(codes, item)
    return tuple(codes)


def _country_codes_from_production_countries(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    codes: list[str] = []
    for country in value:
        if isinstance(country, dict):
            _append_country_code(codes, country.get("iso_3166_1"))
    return tuple(codes)


def _country_codes_from_origin_country(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    codes: list[str] = []
    for item in value:
        if isinstance(item, dict):
            _append_country_code(codes, item.get("origin_country"))
    return tuple(codes)


def _append_country_code(codes: list[str], value: Any) -> None:
    if not isinstance(value, str):
        return
    code = value.strip().upper()
    if len(code) != 2 or code in codes:
        return
    codes.append(code)


def _build_region(candidates: tuple[str, ...], *, source: str, confidence: str) -> _RegionMetadata:
    primary = candidates[0]
    return _RegionMetadata(
        primary=primary,
        candidates=candidates,
        category=_region_category(primary),
        source=source,
        confidence=confidence,
    )


def _unknown_region() -> _RegionMetadata:
    return _RegionMetadata(primary=None, candidates=(), category=None, source=None, confidence="low")


def _region_category(country_code: str) -> str:
    if country_code in DOMESTIC_COUNTRIES:
        return "国产"
    if country_code in EAST_ASIA_COUNTRIES:
        return "日韩"
    if country_code in WESTERN_COUNTRIES:
        return "欧美"
    return "其他"


__all__ = [
    "TmdbConfig",
    "TmdbCredentialError",
    "TmdbError",
    "TmdbMovieResolver",
    "TmdbMultiResolver",
    "TmdbRetryableError",
]
