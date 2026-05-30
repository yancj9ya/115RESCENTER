from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.notifications import (
    ERROR,
    INFO,
    ORGANIZE_FAILED,
    ORGANIZE_SUCCESS,
    TRANSFER_FAILED,
    TRANSFER_SUCCESS,
    NotificationEvent,
    Notifier,
)
from src.organizing import OrganizeMetadata


@dataclass(frozen=True)
class SaveShareCall:
    share_code: str
    receive_code: str
    target_cid: int
    ids: object = None


@dataclass(frozen=True)
class RenameFileCall:
    file_id: int
    new_name: str


@dataclass(frozen=True)
class MoveFileCall:
    file_id: int
    target_cid: int


class FakeTransferStorage:
    def __init__(self, *, error: Exception | None = None, notifier: Notifier | None = None) -> None:
        self.error = error
        self.notifier = notifier
        self.save_share_calls: list[SaveShareCall] = []

    def save_share(self, share_code: str, receive_code: str = "", target_cid: int = 0, ids: object = None) -> dict:
        call = SaveShareCall(share_code=share_code, receive_code=receive_code, target_cid=target_cid, ids=ids)
        self.save_share_calls.append(call)
        if self.error is not None:
            if self.notifier is not None:
                notify_transfer_failure(self.notifier, share_code, target_cid, str(self.error))
            raise self.error

        result = {"state": True, "share_code": share_code, "target_cid": target_cid}
        if self.notifier is not None:
            notify_transfer_success(self.notifier, share_code, target_cid)
        return result


class FakeOrganizeStorage:
    def __init__(self, items: list[Any] | None = None, *, notifier: Notifier | None = None) -> None:
        self.items = list(items or [])
        self.notifier = notifier
        self.list_folder_calls: list[int] = []
        self.ensure_folder_calls: list[tuple[int, str]] = []
        self.rename_file_calls: list[RenameFileCall] = []
        self.move_file_calls: list[MoveFileCall] = []
        self.delete_file_calls: list[int] = []

    def list_folder(self, cid: int) -> list[Any]:
        self.list_folder_calls.append(cid)
        if cid in {item.get("id") if isinstance(item, dict) else getattr(item, "id", None) for item in self.items if isinstance(item, dict) and item.get("is_dir") or hasattr(item, "is_dir") and getattr(item, "is_dir")}:
            return []
        return list(self.items)

    def ensure_folder(self, parent_cid: int, name: str) -> dict[str, object]:
        self.ensure_folder_calls.append((parent_cid, name))
        return {"id": _folder_id(parent_cid, name), "name": name, "is_dir": True}

    def rename_file(self, file_id: int, new_name: str) -> dict[str, object]:
        self.rename_file_calls.append(RenameFileCall(file_id=file_id, new_name=new_name))
        if self.notifier is not None:
            notify_organize_success(self.notifier, file_id, "rename_file")
        return {"state": True, "file_id": file_id, "name": new_name}

    def move_file(self, file_id: int, target_cid: int) -> dict[str, object]:
        self.move_file_calls.append(MoveFileCall(file_id=file_id, target_cid=target_cid))
        if self.notifier is not None:
            notify_organize_success(self.notifier, file_id, "move_file")
        return {"state": True, "file_id": file_id, "target_cid": target_cid}

    def delete_file(self, file_id: int) -> dict[str, object]:
        self.delete_file_calls.append(file_id)
        return {"state": True, "file_id": file_id}


class FakeMetadataResolver:
    def __init__(self, metadata_by_id: dict[int, OrganizeMetadata]) -> None:
        self.metadata_by_id = dict(metadata_by_id)
        self.calls: list[Any] = []

    def __call__(self, item: Any) -> OrganizeMetadata | None:
        self.calls.append(item)
        item_id = int(_item_value(item, "id"))
        return self.metadata_by_id.get(item_id)


def notify_transfer_success(notifier: Notifier, share_code: str, target_cid: int) -> None:
    notifier.notify(
        NotificationEvent(
            event_type=TRANSFER_SUCCESS,
            severity=INFO,
            title="Dry-run transfer succeeded",
            message=f"Share {share_code} would be saved to {target_cid}.",
            context={"share_code": share_code, "target_cid": target_cid},
        )
    )


def notify_transfer_failure(notifier: Notifier, share_code: str, target_cid: int, error: str) -> None:
    notifier.notify(
        NotificationEvent(
            event_type=TRANSFER_FAILED,
            severity=ERROR,
            title="Dry-run transfer failed",
            message=error,
            context={"share_code": share_code, "target_cid": target_cid, "error": error},
        )
    )


def notify_organize_success(notifier: Notifier, file_id: int, action: str) -> None:
    notifier.notify(
        NotificationEvent(
            event_type=ORGANIZE_SUCCESS,
            severity=INFO,
            title="Dry-run organize action succeeded",
            message=f"{action} completed for file {file_id}.",
            context={"file_id": file_id, "action": action},
        )
    )


def notify_organize_failure(notifier: Notifier, file_id: int, action: str, error: str) -> None:
    notifier.notify(
        NotificationEvent(
            event_type=ORGANIZE_FAILED,
            severity=ERROR,
            title="Dry-run organize action failed",
            message=error,
            context={"file_id": file_id, "action": action, "error": error},
        )
    )


def _folder_id(parent_cid: int, name: str) -> int:
    # Use a hash-based approach to keep IDs within SQLite INTEGER range
    # SQLite INTEGER max is 2^63-1 (9223372036854775807)
    hash_value = hash((parent_cid, name))
    # Ensure positive value within safe range
    return abs(hash_value) % 2_000_000_000 + 10_000


def _item_value(item: Any, key: str) -> Any:
    if isinstance(item, dict):
        return item[key]
    return getattr(item, key)


__all__ = [
    "FakeMetadataResolver",
    "FakeOrganizeStorage",
    "FakeTransferStorage",
    "MoveFileCall",
    "RenameFileCall",
    "SaveShareCall",
    "notify_organize_failure",
    "notify_organize_success",
    "notify_transfer_failure",
    "notify_transfer_success",
]
