from __future__ import annotations

import inspect
import unittest
from dataclasses import dataclass

from src.notifications import (
    ERROR,
    INFO,
    ORGANIZE_FAILED,
    ORGANIZE_SUCCESS,
    TRANSFER_FAILED,
    TRANSFER_SUCCESS,
    InMemoryNotifier,
)
from src.organizing import MEDIA_KIND_MOVIE, OrganizeMetadata
from src.processors.fakes import (
    FakeMetadataResolver,
    FakeOrganizeStorage,
    FakeTransferStorage,
    MoveFileCall,
    RenameFileCall,
    SaveShareCall,
    notify_organize_failure,
)
from src.processors.organize_folder import OrganizeStorage
from src.processors.transfer_queue import TransferStorage


@dataclass(frozen=True)
class ObjectItem:
    id: int
    name: str
    is_dir: bool = False


class DryRunFakesTest(unittest.TestCase):
    def test_fake_transfer_storage_satisfies_protocol_records_call_and_returns_payload(self) -> None:
        storage: TransferStorage = FakeTransferStorage()

        result = storage.save_share("abc123", "xy12", target_cid=9001, ids=[1, 2])

        self.assertEqual(result, {"state": True, "share_code": "abc123", "target_cid": 9001})
        self.assertEqual(
            storage.save_share_calls,  # type: ignore[attr-defined]
            [SaveShareCall(share_code="abc123", receive_code="xy12", target_cid=9001, ids=[1, 2])],
        )

    def test_fake_transfer_storage_emits_success_event(self) -> None:
        notifier = InMemoryNotifier()
        storage = FakeTransferStorage(notifier=notifier)

        storage.save_share("abc123", target_cid=9001)

        self.assertEqual(len(notifier.events), 1)
        event = notifier.events[0]
        self.assertEqual(event.event_type, TRANSFER_SUCCESS)
        self.assertEqual(event.severity, INFO)
        self.assertEqual(event.context, {"share_code": "abc123", "target_cid": 9001})

    def test_fake_transfer_storage_configurable_error_records_call_and_emits_failure(self) -> None:
        notifier = InMemoryNotifier()
        storage = FakeTransferStorage(error=RuntimeError("dry-run transfer blocked"), notifier=notifier)

        with self.assertRaisesRegex(RuntimeError, "dry-run transfer blocked"):
            storage.save_share("badshare", "pw", target_cid=7001)

        self.assertEqual(storage.save_share_calls, [SaveShareCall("badshare", "pw", 7001)])
        self.assertEqual(len(notifier.events), 1)
        event = notifier.events[0]
        self.assertEqual(event.event_type, TRANSFER_FAILED)
        self.assertEqual(event.severity, ERROR)
        self.assertEqual(event.context, {"share_code": "badshare", "target_cid": 7001, "error": "dry-run transfer blocked"})

    def test_fake_organize_storage_satisfies_protocol_lists_copy_and_records_calls(self) -> None:
        item = {"id": 11, "name": "raw.mkv", "is_dir": False}
        storage: OrganizeStorage = FakeOrganizeStorage([item])

        listed = storage.list_folder(5001)
        listed.append({"id": 12, "name": "other.mkv", "is_dir": False})
        folder = storage.ensure_folder(100, "Movie (2024)")
        rename_result = storage.rename_file(11, "Movie (2024).mkv")
        move_result = storage.move_file(11, int(folder["id"]))

        self.assertEqual(storage.list_folder(5001), [item])
        self.assertEqual(storage.list_folder_calls, [5001, 5001])  # type: ignore[attr-defined]
        self.assertEqual(storage.ensure_folder_calls, [(100, "Movie (2024)")])  # type: ignore[attr-defined]
        self.assertEqual(storage.rename_file_calls, [RenameFileCall(11, "Movie (2024).mkv")])  # type: ignore[attr-defined]
        self.assertEqual(storage.move_file_calls, [MoveFileCall(11, int(folder["id"]))])  # type: ignore[attr-defined]
        self.assertEqual(rename_result, {"state": True, "file_id": 11, "name": "Movie (2024).mkv"})
        self.assertEqual(move_result, {"state": True, "file_id": 11, "target_cid": int(folder["id"])})

    def test_fake_organize_storage_ensure_folder_returns_deterministic_folder_ids(self) -> None:
        storage = FakeOrganizeStorage()

        first = storage.ensure_folder(100, "Movie (2024)")
        second = storage.ensure_folder(100, "Movie (2024)")
        different_parent = storage.ensure_folder(101, "Movie (2024)")
        different_name = storage.ensure_folder(100, "Other (2024)")

        self.assertEqual(first, second)
        self.assertNotEqual(first["id"], different_parent["id"])
        self.assertNotEqual(first["id"], different_name["id"])
        self.assertEqual(first["name"], "Movie (2024)")
        self.assertIs(first["is_dir"], True)

    def test_fake_organize_storage_emits_success_events_for_rename_and_move(self) -> None:
        notifier = InMemoryNotifier()
        storage = FakeOrganizeStorage(notifier=notifier)

        storage.rename_file(11, "new.mkv")
        storage.move_file(11, 7001)

        self.assertEqual([event.event_type for event in notifier.events], [ORGANIZE_SUCCESS, ORGANIZE_SUCCESS])
        self.assertEqual([event.context["action"] for event in notifier.events], ["rename_file", "move_file"])

    def test_organize_failure_helper_emits_failure_event(self) -> None:
        notifier = InMemoryNotifier()

        notify_organize_failure(notifier, 11, "move_file", "target unavailable")

        self.assertEqual(len(notifier.events), 1)
        event = notifier.events[0]
        self.assertEqual(event.event_type, ORGANIZE_FAILED)
        self.assertEqual(event.severity, ERROR)
        self.assertEqual(event.context, {"file_id": 11, "action": "move_file", "error": "target unavailable"})

    def test_fake_metadata_resolver_looks_up_dict_and_object_items(self) -> None:
        movie = OrganizeMetadata(title="Movie", year=2024, kind=MEDIA_KIND_MOVIE)
        resolver = FakeMetadataResolver({11: movie})
        dict_item = {"id": 11, "name": "raw.mkv", "is_dir": False}
        object_item = ObjectItem(id=12, name="missing.mkv")

        self.assertEqual(resolver(dict_item), movie)
        self.assertIsNone(resolver(object_item))
        self.assertEqual(resolver.calls, [dict_item, object_item])

    def test_fake_sources_have_no_forbidden_dependencies(self) -> None:
        import src.processors.fakes as fakes

        source = inspect.getsource(fakes)
        forbidden = [
            "Storage115Service",
            "p115",
            "httpx",
            "requests",
            "telegram",
            "TMDB_BEARER_TOKEN",
            "P115_COOKIES",
        ]
        for text in forbidden:
            with self.subTest(text=text):
                self.assertNotIn(text, source)


if __name__ == "__main__":
    unittest.main()
