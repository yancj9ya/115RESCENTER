from __future__ import annotations

from .filename_parser import (
    CategoryHint,
    EpisodeInfo,
    FilenameTags,
    ParsedFilename,
    ParsedFolderName,
    parse_filename,
    parse_folder_name,
    is_season_folder_name,
    extract_media_title,
    extract_tmdb_id,
)
from .categorizer import MediaCategory, categorize_tmdb_media
from .rename import compose_movie_filename, compose_tv_filename
from .models import (
    MEDIA_KIND_MOVIE,
    MEDIA_KIND_SERIES,
    MEDIA_KIND_UNKNOWN,
    OrganizeMetadata,
    OrganizePlan,
    OrganizeRule,
)
from .planner import build_organize_plan, build_organize_plans
from .tmdb import (
    TmdbConfig,
    TmdbCredentialError,
    TmdbError,
    TmdbMovieResolver,
    TmdbMultiResolver,
    TmdbRetryableError,
)
from .tmdb_discovery import TmdbAliasBundle, TmdbDiscoveryService, TmdbSearchResult

__all__ = [
    "CategoryHint",
    "EpisodeInfo",
    "FilenameTags",
    "MEDIA_KIND_MOVIE",
    "MEDIA_KIND_SERIES",
    "MEDIA_KIND_UNKNOWN",
    "MediaCategory",
    "OrganizeMetadata",
    "OrganizePlan",
    "OrganizeRule",
    "ParsedFilename",
    "ParsedFolderName",
    "TmdbAliasBundle",
    "TmdbConfig",
    "TmdbCredentialError",
    "TmdbDiscoveryService",
    "TmdbError",
    "TmdbMovieResolver",
    "TmdbMultiResolver",
    "TmdbRetryableError",
    "TmdbSearchResult",
    "build_organize_plan",
    "build_organize_plans",
    "categorize_tmdb_media",
    "compose_movie_filename",
    "compose_tv_filename",
    "parse_filename",
    "parse_folder_name",
    "is_season_folder_name",
    "extract_media_title",
    "extract_tmdb_id",
]
