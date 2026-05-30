from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.organizing import MEDIA_KIND_MOVIE, OrganizeMetadata, OrganizeRule
from src.organizing.repository import SKIPPED_DUPLICATE, SUCCESS, OrganizeRepository
from src.processors.organize_run import OrganizeRunService


class FakeStorage:
    def __init__(self) -> None:
        self.staging_items: list[dict] = []
        self.target_items: list[dict] = []
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.deleted_ids: list[int] = []

    def list_folder(self, cid: int) -> list[dict]:
        self.calls.append(("list_folder", (cid,)))
        if cid == 9001:
            return list(self.staging_items)
        return list(self.target_items)

    def ensure_folder(self, parent_cid: int, name: str) -> dict:
        self.calls.append(("ensure_folder", (parent_cid, name)))
        return {"cid": 7001, "name": name}

    def rename_file(self, file_id: int, new_name: str) -> dict:
        self.calls.append(("rename_file", (file_id, new_name)))
        return {"state": True}

    def move_file(self, file_id: int, target_cid: int) -> dict:
        self.calls.append(("move_file", (file_id, target_cid)))
        return {"state": True}

    def delete_file(self, file_id: int) -> dict:
        self.calls.append(("delete_file", (file_id,)))
        self.deleted_ids.append(file_id)
        return {"state": True}


class OrganizeDuplicateHandlingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rule = OrganizeRule(media_library_root_cid=100)

    def test_skip_smaller_file_when_duplicate_exists_with_larger_size(self) -> None:
        storage = FakeStorage()
        storage.staging_items = [{"id": 11, "name": "movie.mkv", "is_dir": False, "size": 1000}]
        storage.target_items = [{"id": 99, "name": "Title（2024）.mkv", "is_dir": False, "size": 2000}]

        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = self._repo(tmp_dir)
            service = OrganizeRunService(
                repo,
                storage,
                self.rule,
                metadata_resolver=lambda item: OrganizeMetadata(title="Title", year=2024, kind=MEDIA_KIND_MOVIE),
            )

            result = service.run_once(9001)

            self.assertEqual(result.status, SUCCESS)
            self.assertEqual(result.planned_count, 0)
            self.assertEqual(result.success_count, 0)
            self.assertEqual(result.skipped_count, 1)
            self.assertEqual(result.failed_count, 0)
            items = repo.list_run_items(result.run_id)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].status, SKIPPED_DUPLICATE)
            self.assertEqual(items[0].file_id, 11)
            self.assertIn("duplicate file exists with larger or equal size", items[0].reason)
            self.assertIn("2000 >= 1000", items[0].reason)
            self.assertEqual(storage.deleted_ids, [])
            self.assertNotIn(("move_file", (11, 7001)), storage.calls)

    def test_skip_equal_size_file_when_duplicate_exists(self) -> None:
        storage = FakeStorage()
        storage.staging_items = [{"id": 12, "name": "movie.mkv", "is_dir": False, "size": 1500}]
        storage.target_items = [{"id": 98, "name": "Title（2024）.mkv", "is_dir": False, "size": 1500}]

        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = self._repo(tmp_dir)
            service = OrganizeRunService(
                repo,
                storage,
                self.rule,
                metadata_resolver=lambda item: OrganizeMetadata(title="Title", year=2024, kind=MEDIA_KIND_MOVIE),
            )

            result = service.run_once(9001)

            self.assertEqual(result.status, SUCCESS)
            self.assertEqual(result.skipped_count, 1)
            items = repo.list_run_items(result.run_id)
            self.assertEqual(items[0].status, SKIPPED_DUPLICATE)
            self.assertIn("1500 >= 1500", items[0].reason)
            self.assertEqual(storage.deleted_ids, [])

    def test_delete_smaller_existing_file_and_move_larger_new_file(self) -> None:
        storage = FakeStorage()
        storage.staging_items = [{"id": 13, "name": "movie.mkv", "is_dir": False, "size": 3000}]
        storage.target_items = [{"id": 97, "name": "Title（2024）.mkv", "is_dir": False, "size": 1000}]

        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = self._repo(tmp_dir)
            service = OrganizeRunService(
                repo,
                storage,
                self.rule,
                metadata_resolver=lambda item: OrganizeMetadata(title="Title", year=2024, kind=MEDIA_KIND_MOVIE),
            )

            result = service.run_once(9001)

            self.assertEqual(result.status, SUCCESS)
            self.assertEqual(result.planned_count, 1)
            self.assertEqual(result.success_count, 1)
            self.assertEqual(result.skipped_count, 0)
            self.assertEqual(result.failed_count, 0)
            items = repo.list_run_items(result.run_id)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].status, SUCCESS)
            self.assertEqual(items[0].file_id, 13)
            self.assertEqual(storage.deleted_ids, [97])
            self.assertIn(("delete_file", (97,)), storage.calls)
            self.assertIn(("rename_file", (13, "Title（2024）.mkv")), storage.calls)
            self.assertIn(("move_file", (13, 7001)), storage.calls)

    def test_no_duplicate_moves_file_normally(self) -> None:
        storage = FakeStorage()
        storage.staging_items = [{"id": 14, "name": "movie.mkv", "is_dir": False, "size": 2000}]
        storage.target_items = []

        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = self._repo(tmp_dir)
            service = OrganizeRunService(
                repo,
                storage,
                self.rule,
                metadata_resolver=lambda item: OrganizeMetadata(title="Title", year=2024, kind=MEDIA_KIND_MOVIE),
            )

            result = service.run_once(9001)

            self.assertEqual(result.status, SUCCESS)
            self.assertEqual(result.success_count, 1)
            self.assertEqual(result.skipped_count, 0)
            items = repo.list_run_items(result.run_id)
            self.assertEqual(items[0].status, SUCCESS)
            self.assertEqual(storage.deleted_ids, [])
            self.assertIn(("move_file", (14, 7001)), storage.calls)

    def _repo(self, tmp_dir: str) -> OrganizeRepository:
        repo = OrganizeRepository(Path(tmp_dir) / "organize.db")
        repo.init_schema()
        return repo


if __name__ == "__main__":
    unittest.main()
