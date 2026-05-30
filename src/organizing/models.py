from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from .filename_parser import CategoryHint

MEDIA_KIND_MOVIE: Final[str] = "movie"
MEDIA_KIND_SERIES: Final[str] = "series"
MEDIA_KIND_UNKNOWN: Final[str] = "unknown"


@dataclass(frozen=True)
class OrganizeMetadata:
    title: str
    year: int | None
    kind: str
    season: int | None = None
    episode: int | None = None
    region_primary: str | None = None
    region_candidates: tuple[str, ...] = field(default_factory=tuple)
    region_category: str | None = None
    region_source: str | None = None
    region_confidence: str = "low"
    tmdb_id: int | None = None
    genre_ids: tuple[int, ...] = field(default_factory=tuple)
    category_hint: CategoryHint | None = None


@dataclass(frozen=True)
class OrganizeRule:
    media_library_root_cid: int


@dataclass(frozen=True)
class OrganizePlan:
    file_id: int
    original_name: str
    new_name: str
    target_parent_cid: int
    target_folder_name: str
    target_folder_segments: tuple[str, ...] = field(default_factory=tuple)
    target_cid: int | None = None
    reason: str = ""
    metadata: OrganizeMetadata | None = None
