from __future__ import annotations

import inspect
import unittest

from src.organizing import MEDIA_KIND_MOVIE, OrganizeMetadata, OrganizeRule


class FakeStorage:
    def __init__(self, items: list[object], *, ensure_folder_result: object | None = None) -> None:
        self.items = items
        self.ensure_folder_result = ensure_folder_result or {"cid": 9999, "name": "target"}
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.errors_by_call: dict[tuple[str, tuple[object, ...]], Exception] = {}

    def list_folder(self, cid: int) -> list[object]:
        self.calls.append(("list_folder", (cid,)))
        return list(self.items)

    def ensure_folder(self, parent_cid: int, name: str) -> object:
        call = ("ensure_folder", (parent_cid, name))
        self.calls.append(call)
        self._raise_if_needed(call)
        return self.ensure_folder_result

    def rename_file(self, file_id: int, new_name: str) -> object:
        call = ("rename_file", (file_id, new_name))
        self.calls.append(call)
        self._raise_if_needed(call)
        return {"state": True}

    def move_file(self, file_id: int, target_cid: int) -> object:
        call = ("move_file", (file_id, target_cid))
        self.calls.append(call)
        self._raise_if_needed(call)
        return {"state": True}

    def fail_on(self, method: str, *args: object, error: Exception) -> None:
        self.errors_by_call[(method, args)] = error

    def _raise_if_needed(self, call: tuple[str, tuple[object, ...]]) -> None:
        error = self.errors_by_call.get(call)
        if error is not None:
            raise error


class OrganizeFolderProcessorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rule = OrganizeRule(media_library_root_cid=100)

    def test_no_files_returns_zero_counts(self) -> None:
        from src.processors.organize_folder import OrganizeFolderProcessor

        storage = FakeStorage([])
        processor = OrganizeFolderProcessor(storage, self.rule, metadata_resolver=lambda item: None)

        result = processor.process_folder(9001)

        self.assertEqual(result.scanned_count, 0)
        self.assertEqual(result.planned_count, 0)
        self.assertEqual(result.renamed_count, 0)
        self.assertEqual(result.moved_count, 0)
        self.assertEqual(result.skipped_count, 0)
        self.assertEqual(result.errors, ())
        self.assertEqual(storage.calls, [("list_folder", (9001,))])

    def test_successful_movie_plan_renames_and_moves(self) -> None:
        from src.processors.organize_folder import OrganizeFolderProcessor

        item = {"id": 11, "name": "raw.mkv", "is_dir": False}
        storage = FakeStorage([item], ensure_folder_result={"cid": 7001, "name": "Title (2024)"})
        processor = OrganizeFolderProcessor(
            storage,
            self.rule,
            metadata_resolver=lambda current: OrganizeMetadata(
                title="Title", year=2024, kind=MEDIA_KIND_MOVIE, region_category="国产"
            ),
        )

        result = processor.process_folder(9001)

        self.assertEqual(result.scanned_count, 1)
        self.assertEqual(result.planned_count, 1)
        self.assertEqual(result.renamed_count, 1)
        self.assertEqual(result.moved_count, 1)
        self.assertEqual(result.skipped_count, 0)
        self.assertEqual(result.errors, ())
        self.assertEqual(
            storage.calls,
            [
                ("list_folder", (9001,)),
                ("ensure_folder", (100, "电影")),
                ("ensure_folder", (7001, "国产")),
                ("ensure_folder", (7001, "Title（2024）")),
                ("rename_file", (11, "Title（2024）.mkv")),
                ("move_file", (11, 7001)),
            ],
        )

    def test_no_metadata_skips_file_and_leaves_in_staging(self) -> None:
        from src.processors.organize_folder import OrganizeFolderProcessor

        item = {"id": 12, "name": "Original Name.mp4", "is_dir": False}
        storage = FakeStorage([item], ensure_folder_result={"cid": 7002})
        processor = OrganizeFolderProcessor(storage, self.rule, metadata_resolver=lambda current: None)

        result = processor.process_folder(9001)

        self.assertEqual(result.scanned_count, 1)
        self.assertEqual(result.planned_count, 0)
        self.assertEqual(result.renamed_count, 0)
        self.assertEqual(result.moved_count, 0)
        self.assertEqual(result.skipped_count, 1)
        self.assertEqual(result.errors, ())
        self.assertEqual(
            storage.calls,
            [
                ("list_folder", (9001,)),
            ],
        )

    def test_movie_region_plan_ensures_nested_folders_before_move(self) -> None:
        from src.processors.organize_folder import OrganizeFolderProcessor

        item = {"id": 15, "name": "raw.mkv", "is_dir": False}
        storage = FakeStorage([item])
        processor = OrganizeFolderProcessor(
            storage,
            self.rule,
            metadata_resolver=lambda current: OrganizeMetadata(
                title="Title",
                year=2024,
                kind=MEDIA_KIND_MOVIE,
                region_category="国产",
            ),
        )

        result = processor.process_folder(9001)

        self.assertEqual(result.errors, ())
        self.assertEqual(
            storage.calls,
            [
                ("list_folder", (9001,)),
                ("ensure_folder", (100, "电影")),
                ("ensure_folder", (9999, "国产")),
                ("ensure_folder", (9999, "Title（2024）")),
                ("rename_file", (15, "Title（2024）.mkv")),
                ("move_file", (15, 9999)),
            ],
        )

    def test_per_item_failure_marks_failed_and_continues_to_partial_success(self) -> None:
        from src.processors.organize_folder import OrganizeFolderProcessor

        first_item = {"id": 13, "name": "bad-source.mkv", "is_dir": False}
        second_item = {"id": 14, "name": "good-source.mkv", "is_dir": False}
        storage = FakeStorage([first_item, second_item], ensure_folder_result={"cid": 8001})
        storage.fail_on("rename_file", 13, "Broken（2024）.mkv", error=RuntimeError("rename exploded"))
        processor = OrganizeFolderProcessor(
            storage,
            self.rule,
            metadata_resolver=lambda current: OrganizeMetadata(
                title="Broken" if current["id"] == 13 else "Good",
                year=2024,
                kind=MEDIA_KIND_MOVIE,
                region_category="欧美",
            ),
        )

        result = processor.process_folder(9001)

        self.assertEqual(result.scanned_count, 2)
        self.assertEqual(result.planned_count, 2)
        self.assertEqual(result.renamed_count, 1)
        self.assertEqual(result.moved_count, 1)
        self.assertEqual(result.skipped_count, 1)
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(result.errors[0].file_id, 13)
        self.assertEqual(result.errors[0].name, "bad-source.mkv")
        self.assertEqual(result.errors[0].error, "rename exploded")
        self.assertEqual(
            storage.calls,
            [
                ("list_folder", (9001,)),
                ("ensure_folder", (100, "电影")),
                ("ensure_folder", (8001, "欧美")),
                ("ensure_folder", (8001, "Broken（2024）")),
                ("rename_file", (13, "Broken（2024）.mkv")),
                ("ensure_folder", (100, "电影")),
                ("ensure_folder", (8001, "欧美")),
                ("ensure_folder", (8001, "Good（2024）")),
                ("rename_file", (14, "Good（2024）.mkv")),
                ("move_file", (14, 8001)),
            ],
        )

    def test_module_has_no_forbidden_dependencies(self) -> None:
        import src.processors.organize_folder as organize_folder

        source = inspect.getsource(organize_folder)
        forbidden = [
            "Storage115Service",
            "p115",
            "P115_COOKIES",
            "tmdb",
            "notification",
            "requests",
            "httpx",
            "QueueRepository",
        ]
        for text in forbidden:
            self.assertNotIn(text, source)


if __name__ == "__main__":
    unittest.main()
