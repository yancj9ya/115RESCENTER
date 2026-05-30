from __future__ import annotations

from typing import Final

from .categorizer import MediaCategory, categorize_tmdb_media
from .filename_parser import CategoryHint
from .models import MEDIA_KIND_MOVIE, MEDIA_KIND_SERIES, OrganizeMetadata

_FALLBACK_TITLE: Final[str] = "未识别"
_FALLBACK_REGION: Final[str] = "未分类地区"
_UNKNOWN_CATEGORY: Final[str] = "未识别"


def build_target_segments(
    metadata: OrganizeMetadata | None,
    *,
    parsed_category_hint: CategoryHint | None = None,
    parsed_season: int | None = None,
) -> tuple[str, ...]:
    """Return the directory segments under the media library root for one item.

    Layout: <category>/<region>/<title（year）{tmdb-id}>[/S0X]
    """
    if metadata is None:
        return (_UNKNOWN_CATEGORY, _FALLBACK_REGION, _FALLBACK_TITLE)

    category = _category_segment(metadata, parsed_category_hint)
    region = _region_segment(metadata)
    title_segment = _title_segment(metadata)
    segments: list[str] = [category, region, title_segment]

    if metadata.kind == MEDIA_KIND_SERIES:
        season = metadata.season
        if season is None:
            season = parsed_season if parsed_season is not None else 1
        segments.append(f"S{int(season):02d}")

    return tuple(_safe_segment(part) for part in segments)


def _category_segment(metadata: OrganizeMetadata, parsed_hint: CategoryHint | None) -> str:
    kind = _kind_for_categorizer(metadata.kind)
    hint = metadata.category_hint or parsed_hint
    category: MediaCategory = categorize_tmdb_media(
        kind=kind,
        genre_ids=metadata.genre_ids,
        title_hint=hint,
    )
    return _CATEGORY_LABELS.get(category, category)


def _kind_for_categorizer(kind: str | None) -> str | None:
    if kind == MEDIA_KIND_SERIES:
        return "tv"
    if kind == MEDIA_KIND_MOVIE:
        return "movie"
    return None


def _region_segment(metadata: OrganizeMetadata) -> str:
    if metadata.region_category:
        return metadata.region_category
    return _FALLBACK_REGION


def _title_segment(metadata: OrganizeMetadata) -> str:
    title = _safe_segment(metadata.title) or _FALLBACK_TITLE
    parts: list[str] = [title]
    if metadata.year is not None:
        parts.append(f"（{int(metadata.year)}）")
    if metadata.tmdb_id is not None:
        parts.append(f"{{tmdb-{int(metadata.tmdb_id)}}}")
    return "".join(parts)


def _safe_segment(value: str) -> str:
    cleaned = "".join("_" if _is_unsafe(character) else character for character in str(value))
    while ".." in cleaned:
        cleaned = cleaned.replace("..", ".")
    return cleaned.strip().strip(".") or _FALLBACK_TITLE


def _is_unsafe(character: str) -> bool:
    return character in {"/", "\\", ":", "*", "?", '"', "<", ">", "|"} or ord(character) < 32


_CATEGORY_LABELS: Final[dict[MediaCategory, str]] = {
    "anime": "动画",
    "variety": "综艺",
    "documentary": "纪录片",
    "movie": "电影",
    "tv": "剧集",
}


__all__ = [
    "build_target_segments",
]
