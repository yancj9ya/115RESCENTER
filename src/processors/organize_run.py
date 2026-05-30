from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from src.organizing import (
    OrganizeMetadata,
    OrganizeRule,
    build_organize_plan,
    extract_media_title,
    is_season_folder_name,
    parse_folder_name,
)
from src.organizing.repository import (
    FAILED,
    PARTIAL_SUCCESS,
    PLANNED,
    SKIPPED_DIR,
    SKIPPED_DUPLICATE,
    SKIPPED_UNMATCHED,
    SUCCESS,
    OrganizeRepository,
)
from src.processors.organize_folder import OrganizeStorage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OrganizeRunOnceResult:
    run_id: int
    status: str
    scanned_count: int
    planned_count: int
    success_count: int
    skipped_count: int
    failed_count: int
    last_error: str | None = None


@dataclass
class _RunCounters:
    scanned: int = 0
    planned: int = 0
    success: int = 0
    skipped: int = 0
    failed: int = 0
    last_error: str | None = None
    folder_metadata_cache: dict[tuple[str, ...], OrganizeMetadata | None] = field(default_factory=dict)


class OrganizeRunService:
    def __init__(
        self,
        repository: OrganizeRepository,
        storage: OrganizeStorage,
        rule: OrganizeRule,
        metadata_resolver: Callable[[Any], OrganizeMetadata | None],
        *,
        folder_resolver: Callable[[str, int | None, int | None], OrganizeMetadata | None] | None = None,
        sleeper: Callable[[float], None] | None = None,
        min_interval_seconds: float = 0.5,
        max_depth: int = 10,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._rule = rule
        self._metadata_resolver = metadata_resolver
        self._folder_resolver = folder_resolver
        self._sleeper = sleeper or time.sleep
        self._min_interval_seconds = max(0.0, min_interval_seconds)
        self._max_depth = max_depth

    def run_once(self, staging_cid: int) -> OrganizeRunOnceResult:
        run = self._repository.create_run(staging_cid)
        logger.info(f"开始整理运行: run_id={run.id}, staging_cid={staging_cid}")

        try:
            items = self._storage.list_folder(staging_cid)
            logger.info(f"扫描到 {len(items)} 个文件/文件夹")
        except Exception as exc:
            error = str(exc)
            logger.error(f"整理运行失败 (run_id={run.id}): 无法列出文件夹内容 - {error}")
            self._repository.finish_run(
                run.id,
                planned_count=0,
                success_count=0,
                skipped_count=0,
                failed_count=0,
                status=FAILED,
                error=error,
            )
            return OrganizeRunOnceResult(
                run_id=run.id,
                status=FAILED,
                scanned_count=0,
                planned_count=0,
                success_count=0,
                skipped_count=0,
                failed_count=0,
                last_error=error,
            )

        counters = _RunCounters()
        logger.info(f"开始处理 {len(items)} 个项目")
        self._process_items(run.id, items, depth=0, ancestors=(), counters=counters)

        status = PARTIAL_SUCCESS if counters.failed else SUCCESS
        logger.info(
            f"整理运行完成 (run_id={run.id}): 扫描={counters.scanned}, 计划={counters.planned}, "
            f"成功={counters.success}, 跳过={counters.skipped}, 失败={counters.failed}"
        )
        self._repository.finish_run(
            run.id,
            planned_count=counters.planned,
            success_count=counters.success,
            skipped_count=counters.skipped,
            failed_count=counters.failed,
            status=status,
            error=counters.last_error,
        )
        return OrganizeRunOnceResult(
            run_id=run.id,
            status=status,
            scanned_count=counters.scanned,
            planned_count=counters.planned,
            success_count=counters.success,
            skipped_count=counters.skipped,
            failed_count=counters.failed,
            last_error=counters.last_error,
        )

    def _process_items(
        self,
        run_id: int,
        items: list[Any],
        *,
        depth: int,
        ancestors: tuple[str, ...],
        counters: _RunCounters,
    ) -> None:
        for item in items:
            counters.scanned += 1
            file_id = int(_get_item_value(item, "id"))
            file_name = str(_get_item_value(item, "name"))
            is_dir = _get_item_is_dir(item)

            if is_dir:
                self._process_directory(
                    run_id, item, file_id, file_name, depth=depth, ancestors=ancestors, counters=counters
                )
                continue

            self._process_file(run_id, item, file_id, file_name, ancestors=ancestors, counters=counters)

    def _process_directory(
        self,
        run_id: int,
        item: Any,
        file_id: int,
        file_name: str,
        *,
        depth: int,
        ancestors: tuple[str, ...],
        counters: _RunCounters,
    ) -> None:
        if depth >= self._max_depth:
            logger.warning(f"达到最大递归深度 {self._max_depth}，跳过子目录: {file_name} (ID: {file_id})")
            self._repository.create_item(
                run_id,
                file_id=file_id,
                file_name=file_name,
                is_dir=True,
                status=SKIPPED_DIR,
                reason=f"max recursion depth {self._max_depth} reached",
            )
            counters.skipped += 1
            return

        logger.info(f"进入子目录递归整理: {file_name} (ID: {file_id})")
        self._repository.create_item(
            run_id,
            file_id=file_id,
            file_name=file_name,
            is_dir=True,
            status=SKIPPED_DIR,
            reason="directory recursed",
        )
        counters.skipped += 1

        try:
            children = self._storage.list_folder(file_id)
        except Exception as exc:
            error = str(exc)
            logger.error(f"无法列出子目录内容: {file_name} (ID: {file_id}) - {error}")
            counters.last_error = error
            return

        self._sleep_between_calls()
        self._process_items(
            run_id, children, depth=depth + 1, ancestors=ancestors + (file_name,), counters=counters
        )

    def _process_file(
        self,
        run_id: int,
        item: Any,
        file_id: int,
        file_name: str,
        *,
        ancestors: tuple[str, ...],
        counters: _RunCounters,
    ) -> None:
        item_record = None
        metadata: OrganizeMetadata | None = None
        try:
            extracted_title = extract_media_title(file_name)
            logger.debug(f"解析元数据: {file_name}")
            logger.info(f"提取媒体标题: '{file_name}' -> '{extracted_title}'")
            metadata = self._metadata_resolver(item)
            if metadata is None:
                metadata = self._resolve_from_ancestors(ancestors, counters)
            plan = build_organize_plan(item, metadata, self._rule)
            if plan is None:
                logger.info(f"跳过未匹配文件: {file_name} (无元数据)")
                self._repository.create_item(
                    run_id,
                    file_id=file_id,
                    file_name=file_name,
                    is_dir=False,
                    status=SKIPPED_UNMATCHED,
                    reason="no metadata matched",
                    metadata=metadata,
                )
                counters.skipped += 1
                return

            counters.planned += 1
            target_path = _target_path(plan.target_folder_segments)
            logger.info(f"计划整理: {file_name} -> {target_path}/{plan.new_name}")
            item_record = self._repository.create_item(
                run_id,
                file_id=plan.file_id,
                file_name=plan.original_name,
                is_dir=False,
                status=PLANNED,
                target_cid=plan.target_cid,
                target_path=target_path,
                new_name=plan.new_name,
                reason=plan.reason,
                metadata=plan.metadata,
            )

            target_cid = self._ensure_target_folder(plan.target_parent_cid, plan.target_folder_segments)

            # Check for duplicate file in target directory
            existing_items = self._storage.list_folder(target_cid)
            existing_file = None
            for existing_item in existing_items:
                if not _get_item_is_dir(existing_item) and str(_get_item_value(existing_item, "name")) == plan.new_name:
                    existing_file = existing_item
                    break

            if existing_file is not None:
                # Compare file sizes
                _cur_raw = _get_item_value(item, "size")
                _ext_raw = _get_item_value(existing_file, "size")
                current_size = int(_cur_raw) if _cur_raw is not None else 0
                existing_size = int(_ext_raw) if _ext_raw is not None else 0

                if current_size <= existing_size:
                    # Skip smaller or equal file
                    reason = f"duplicate file exists with larger or equal size ({existing_size} >= {current_size})"
                    logger.info(f"跳过重复文件: {file_name} - {reason}")
                    self._repository.mark_item_skipped(
                        item_record.id,
                        status=SKIPPED_DUPLICATE,
                        reason=reason,
                        metadata=plan.metadata,
                    )
                    counters.skipped += 1
                    counters.planned -= 1
                    return
                else:
                    # Delete existing smaller file
                    existing_file_id = int(_get_item_value(existing_file, "id"))
                    logger.info(f"删除较小的重复文件: {file_name} (旧大小: {existing_size}, 新大小: {current_size})")
                    self._storage.delete_file(existing_file_id)

            if plan.new_name != plan.original_name:
                logger.debug(f"重命名文件: {plan.original_name} -> {plan.new_name}")
                self._storage.rename_file(plan.file_id, plan.new_name)

            logger.debug(f"移动文件到目标目录: CID={target_cid}")
            self._storage.move_file(plan.file_id, target_cid)
            logger.info(f"整理成功: {file_name} -> {target_path}/{plan.new_name}")
            self._repository.mark_item_success(
                item_record.id,
                target_cid=target_cid,
                target_path=target_path,
                new_name=plan.new_name,
                reason=plan.reason,
                metadata=plan.metadata,
            )
            counters.success += 1
        except Exception as exc:
            error = str(exc)
            logger.error(f"整理失败: {file_name} - {error}", exc_info=True)
            if item_record is None:
                item_record = self._repository.create_item(
                    run_id,
                    file_id=file_id,
                    file_name=file_name,
                    is_dir=False,
                    status=PLANNED,
                    metadata=metadata,
                )
            self._repository.mark_item_failed(item_record.id, error, metadata=metadata)
            counters.failed += 1
            counters.last_error = error
        finally:
            self._sleep_between_calls()

    def _sleep_between_calls(self) -> None:
        if self._min_interval_seconds > 0:
            self._sleeper(self._min_interval_seconds)

    def _resolve_from_ancestors(
        self,
        ancestors: tuple[str, ...],
        counters: _RunCounters,
    ) -> OrganizeMetadata | None:
        """文件名 TMDB 搜索失败时，从最近的父级文件夹向上溯源（跳过季度文件夹），
        用文件夹名（解析剧名/年份/tmdb-id）做 TMDB 搜索。结果按文件夹链缓存，同目录复用。"""
        if self._folder_resolver is None:
            return None

        for index in range(len(ancestors) - 1, -1, -1):
            folder_name = ancestors[index]
            if is_season_folder_name(folder_name):
                continue

            chain = ancestors[: index + 1]
            if chain in counters.folder_metadata_cache:
                cached = counters.folder_metadata_cache[chain]
                if cached is not None:
                    logger.info(f"复用文件夹元数据: '{folder_name}' -> {cached.title}")
                return cached

            parsed = parse_folder_name(folder_name)
            if not parsed.title and parsed.tmdb_id is None:
                counters.folder_metadata_cache[chain] = None
                continue

            logger.info(
                f"文件名搜索失败，向上溯源用文件夹名搜索 TMDB: "
                f"'{folder_name}' -> title='{parsed.title}', year={parsed.year}, tmdb_id={parsed.tmdb_id}"
            )
            try:
                metadata = self._folder_resolver(parsed.title, parsed.tmdb_id, parsed.year)
            except Exception as exc:
                logger.error(f"文件夹名 TMDB 搜索失败: '{folder_name}' - {exc}")
                metadata = None

            counters.folder_metadata_cache[chain] = metadata
            self._sleep_between_calls()
            if metadata is not None:
                logger.info(f"文件夹名命中 TMDB: '{folder_name}' -> {metadata.title} ({metadata.year})")
                return metadata

        return None

    def _ensure_target_folder(self, parent_cid: int, folder_segments: tuple[str, ...]) -> int:
        current_parent_cid = parent_cid
        for folder_name in folder_segments:
            target_folder = self._storage.ensure_folder(current_parent_cid, folder_name)
            current_parent_cid = _get_item_cid(target_folder)
        return current_parent_cid


def _target_path(folder_segments: tuple[str, ...]) -> str | None:
    if not folder_segments:
        return None
    return "/".join(folder_segments)


def _get_item_value(item: Any, key: str) -> Any:
    if isinstance(item, dict):
        return item[key]
    return getattr(item, key)


def _get_item_is_dir(item: Any) -> bool:
    return bool(_get_item_value(item, "is_dir"))


def _get_item_cid(item: Any) -> int:
    for key in ("cid", "id", "file_id"):
        try:
            value = _get_item_value(item, key)
        except (AttributeError, KeyError):
            continue
        if value is not None:
            return int(value)
    raise ValueError("unable to determine folder cid from ensured folder result")
