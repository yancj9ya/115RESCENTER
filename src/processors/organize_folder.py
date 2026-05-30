from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from src.organizing import OrganizeMetadata, OrganizeRule, build_organize_plan


class OrganizeStorage(Protocol):
    def list_folder(self, cid: int) -> list[Any]:
        ...

    def ensure_folder(self, parent_cid: int, name: str) -> Any:
        ...

    def rename_file(self, file_id: int, new_name: str) -> Any:
        ...

    def move_file(self, file_id: int, target_cid: int) -> Any:
        ...

    def delete_file(self, file_id: int) -> Any:
        ...


@dataclass(frozen=True)
class OrganizeItemError:
    file_id: int
    name: str
    error: str


@dataclass(frozen=True)
class OrganizeFolderProcessResult:
    scanned_count: int
    planned_count: int
    renamed_count: int
    moved_count: int
    skipped_count: int
    errors: tuple[OrganizeItemError, ...] = field(default_factory=tuple)


class OrganizeFolderProcessor:
    def __init__(
        self,
        storage: OrganizeStorage,
        rule: OrganizeRule,
        metadata_resolver: Callable[[Any], OrganizeMetadata | None],
    ) -> None:
        self._storage = storage
        self._rule = rule
        self._metadata_resolver = metadata_resolver

    def process_folder(self, staging_cid: int) -> OrganizeFolderProcessResult:
        items = self._storage.list_folder(staging_cid)
        scanned_count = len(items)
        planned_count = 0
        renamed_count = 0
        moved_count = 0
        skipped_count = 0
        errors: list[OrganizeItemError] = []

        for item in items:
            if _get_item_is_dir(item):
                skipped_count += 1
                continue

            file_id = int(_get_item_value(item, "id"))
            original_name = str(_get_item_value(item, "name"))

            try:
                metadata = self._metadata_resolver(item)
                plan = build_organize_plan(item, metadata, self._rule)
                if plan is None:
                    skipped_count += 1
                    continue

                planned_count += 1
                target_cid = self._ensure_target_folder(plan.target_parent_cid, plan.target_folder_segments)

                if plan.new_name != plan.original_name:
                    self._storage.rename_file(plan.file_id, plan.new_name)
                    renamed_count += 1

                self._storage.move_file(plan.file_id, target_cid)
                moved_count += 1
            except Exception as exc:
                errors.append(
                    OrganizeItemError(
                        file_id=file_id,
                        name=original_name,
                        error=str(exc),
                    )
                )

        skipped_count += len(errors)
        return OrganizeFolderProcessResult(
            scanned_count=scanned_count,
            planned_count=planned_count,
            renamed_count=renamed_count,
            moved_count=moved_count,
            skipped_count=skipped_count,
            errors=tuple(errors),
        )

    def _ensure_target_folder(self, parent_cid: int, folder_segments: tuple[str, ...]) -> int:
        current_parent_cid = parent_cid
        for folder_name in folder_segments:
            target_folder = self._storage.ensure_folder(current_parent_cid, folder_name)
            current_parent_cid = _get_item_cid(target_folder)
        return current_parent_cid


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
