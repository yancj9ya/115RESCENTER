from __future__ import annotations

from typing import Any, Mapping

from .filename_parser import EpisodeInfo, ParsedFilename, parse_filename
from .models import MEDIA_KIND_MOVIE, MEDIA_KIND_SERIES, OrganizeMetadata, OrganizePlan, OrganizeRule
from .rename import compose_movie_filename, compose_tv_filename
from .tree_builder import build_target_segments


def build_organize_plan(
    item: Any,
    metadata: OrganizeMetadata | None,
    rule: OrganizeRule,
) -> OrganizePlan | None:
    """Build a deterministic organize plan for one file-like item."""
    if _get_item_is_dir(item):
        return None

    if metadata is None:
        return None

    file_id = int(_get_item_value(item, "id"))
    original_name = str(_get_item_value(item, "name"))
    parsed = parse_filename(original_name)

    parsed_season = parsed.episode.season if parsed.episode is not None else None
    segments = build_target_segments(
        metadata,
        parsed_category_hint=parsed.category_hint,
        parsed_season=parsed_season,
    )
    new_name = _compose_new_name(parsed, metadata)
    folder_name = "/".join(segments)
    reason = _reason_for(metadata, folder_name)

    return OrganizePlan(
        file_id=file_id,
        original_name=original_name,
        new_name=new_name,
        target_parent_cid=int(rule.media_library_root_cid),
        target_folder_name=folder_name,
        target_folder_segments=segments,
        reason=reason,
        metadata=metadata,
    )


def build_organize_plans(
    items: list[Any],
    metadata_by_file_id: Mapping[int, OrganizeMetadata],
    rule: OrganizeRule,
) -> list[OrganizePlan]:
    """Build organize plans for file-like items, skipping directories."""
    plans: list[OrganizePlan] = []
    for item in items:
        if _get_item_is_dir(item):
            continue
        file_id = int(_get_item_value(item, "id"))
        plan = build_organize_plan(item, metadata_by_file_id.get(file_id), rule)
        if plan is not None:
            plans.append(plan)
    return plans


def _compose_new_name(parsed: ParsedFilename, metadata: OrganizeMetadata | None) -> str:
    extension = parsed.extension
    extinfo = parsed.tags.compose_extinfo()

    if metadata is not None and metadata.kind == MEDIA_KIND_MOVIE:
        return compose_movie_filename(
            title=metadata.title,
            year=metadata.year,
            extinfo=extinfo,
            extension=extension,
        )

    if metadata is not None and metadata.kind == MEDIA_KIND_SERIES:
        season, episode = _series_season_episode(metadata, parsed.episode)
        if episode is None:
            return parsed.raw
        return compose_tv_filename(
            title=metadata.title,
            year=metadata.year,
            season=season,
            episode=episode,
            extinfo=extinfo,
            extension=extension,
        )

    return parsed.raw


def _series_season_episode(
    metadata: OrganizeMetadata,
    parsed_episode: EpisodeInfo | None,
) -> tuple[int | None, int | None]:
    season = metadata.season
    episode = metadata.episode
    if season is None and parsed_episode is not None:
        season = parsed_episode.season
    if episode is None and parsed_episode is not None:
        episode = parsed_episode.episode
    return season, episode


def _reason_for(metadata: OrganizeMetadata | None, folder_name: str) -> str:
    if metadata is None:
        return f"unknown metadata; placing under {folder_name}"
    if metadata.kind == MEDIA_KIND_MOVIE:
        return f"movie metadata matched: {folder_name}"
    if metadata.kind == MEDIA_KIND_SERIES:
        return f"series metadata matched: {folder_name}"
    return f"metadata matched: {folder_name}"


def _get_item_value(item: Any, key: str) -> Any:
    if isinstance(item, Mapping):
        return item[key]
    return getattr(item, key)


def _get_item_is_dir(item: Any) -> bool:
    return bool(_get_item_value(item, "is_dir"))
