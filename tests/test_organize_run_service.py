from __future__ import annotations

import inspect
import json
import tempfile
import unittest
from pathlib import Path

from src.organizing import MEDIA_KIND_MOVIE, MEDIA_KIND_SERIES, OrganizeMetadata, OrganizeRule
from src.organizing.repository import (
    FAILED,
    PARTIAL_SUCCESS,
    SKIPPED_DIR,
    SKIPPED_UNMATCHED,
    SUCCESS,
    OrganizeRepository,
)
from src.processors.organize_run import OrganizeRunService


class FakeStorage:
    def __init__(self, items: list[object], *, ensure_folder_result: object | None = None) -> None:
        self.items = items
        self.ensure_folder_result = ensure_folder_result or {"cid": 9999, "name": "target"}
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.errors_by_call: dict[tuple[str, tuple[object, ...]], Exception] = {}
        self.list_folder_error: Exception | None = None
        self.target_folder_items: list[object] = []

    def list_folder(self, cid: int) -> list[object]:
        self.calls.append(("list_folder", (cid,)))
        if self.list_folder_error is not None:
            raise self.list_folder_error
        if cid == 9001:
            return list(self.items)
        return list(self.target_folder_items)

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

    def delete_file(self, file_id: int) -> object:
        call = ("delete_file", (file_id,))
        self.calls.append(call)
        self._raise_if_needed(call)
        return {"state": True}

    def fail_on(self, method: str, *args: object, error: Exception) -> None:
        self.errors_by_call[(method, args)] = error

    def _raise_if_needed(self, call: tuple[str, tuple[object, ...]]) -> None:
        error = self.errors_by_call.get(call)
        if error is not None:
            raise error



class OrganizeRunServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rule = OrganizeRule(media_library_root_cid=100)

    def _service(self, repo, storage, metadata_resolver):
        return OrganizeRunService(
            repo,
            storage,
            self.rule,
            metadata_resolver=metadata_resolver,
            sleeper=lambda _seconds: None,
        )

    def test_successful_run_records_planned_item_and_executes_storage_operations(self) -> None:
        item = {"id": 11, "name": "raw.mkv", "is_dir": False}
        storage = FakeStorage([item], ensure_folder_result={"cid": 7001, "name": "Title（2024）"})

        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = self._repo(tmp_dir)
            service = self._service(
                repo,
                storage,
                metadata_resolver=lambda current: OrganizeMetadata(title="Title", year=2024, kind=MEDIA_KIND_MOVIE),
            )

            result = service.run_once(9001)

            self.assertEqual(result.status, SUCCESS)
            self.assertEqual(result.scanned_count, 1)
            self.assertEqual(result.planned_count, 1)
            self.assertEqual(result.success_count, 1)
            self.assertEqual(result.skipped_count, 0)
            self.assertEqual(result.failed_count, 0)
            run = repo.get_run(result.run_id)
            self.assertIsNotNone(run)
            assert run is not None
            self.assertEqual(run.status, SUCCESS)
            self.assertEqual(run.planned_count, 1)
            self.assertEqual(run.success_count, 1)
            items = repo.list_run_items(result.run_id)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].status, SUCCESS)
            self.assertEqual(items[0].file_id, 11)
            self.assertEqual(items[0].target_cid, 7001)
            self.assertEqual(items[0].target_path, "电影/未分类地区/Title（2024）")
            self.assertEqual(items[0].new_name, "Title（2024）.mkv")
            metadata_dict = json.loads(items[0].metadata_json)
            self.assertEqual(metadata_dict["kind"], "movie")
            self.assertEqual(metadata_dict["title"], "Title")
            self.assertEqual(metadata_dict["year"], 2024)
            self.assertIsNone(metadata_dict["region_category"])
            self.assertIsNone(metadata_dict["season"])
            self.assertIsNone(metadata_dict["episode"])
            # FakeStorage returns cid=7001 for all ensure_folder calls, so parent_cid becomes 7001 after first call
            self.assertEqual(
                storage.calls,
                [
                    ("list_folder", (9001,)),
                    ("ensure_folder", (100, "电影")),
                    ("ensure_folder", (7001, "未分类地区")),
                    ("ensure_folder", (7001, "Title（2024）")),
                    ("list_folder", (7001,)),
                    ("rename_file", (11, "Title（2024）.mkv")),
                    ("move_file", (11, 7001)),
                ],
            )

    def test_directories_become_skipped_dir_items(self) -> None:
        folder = {"id": 21, "name": "Already Organized", "is_dir": True}
        storage = FakeStorage([folder])

        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = self._repo(tmp_dir)
            service = self._service(repo, storage, metadata_resolver=lambda current: None)

            result = service.run_once(9001)

            self.assertEqual(result.status, SUCCESS)
            self.assertEqual(result.scanned_count, 1)
            self.assertEqual(result.planned_count, 0)
            self.assertEqual(result.success_count, 0)
            self.assertEqual(result.skipped_count, 1)
            self.assertEqual(result.failed_count, 0)
            items = repo.list_run_items(result.run_id)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].status, SKIPPED_DIR)
            self.assertTrue(items[0].is_dir)
            self.assertEqual(items[0].reason, "directory recursed")
            self.assertEqual(storage.calls, [("list_folder", (9001,)), ("list_folder", (21,))])

    def test_recurses_into_subdirectory_and_organizes_nested_files(self) -> None:
        folder = {"id": 21, "name": "Season 1", "is_dir": True}
        nested_file = {"id": 22, "name": "raw.mkv", "is_dir": False}

        class NestedStorage(FakeStorage):
            def list_folder(self, cid: int) -> list[object]:
                self.calls.append(("list_folder", (cid,)))
                if cid == 9001:
                    return [folder]
                if cid == 21:
                    return [nested_file]
                return list(self.target_folder_items)

        storage = NestedStorage([], ensure_folder_result={"cid": 7001, "name": "Title（2024）"})

        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = self._repo(tmp_dir)
            service = self._service(
                repo,
                storage,
                metadata_resolver=lambda current: OrganizeMetadata(title="Title", year=2024, kind=MEDIA_KIND_MOVIE),
            )

            result = service.run_once(9001)

            self.assertEqual(result.status, SUCCESS)
            self.assertEqual(result.scanned_count, 2)
            self.assertEqual(result.planned_count, 1)
            self.assertEqual(result.success_count, 1)
            self.assertEqual(result.skipped_count, 1)
            items = repo.list_run_items(result.run_id)
            statuses = sorted(item.status for item in items)
            self.assertEqual(statuses, sorted([SKIPPED_DIR, SUCCESS]))
            self.assertIn(("list_folder", (21,)), storage.calls)
            self.assertIn(("move_file", (22, 7001)), storage.calls)

    def test_does_not_recurse_beyond_max_depth(self) -> None:
        deep_dir = {"id": 50, "name": "Deep", "is_dir": True}

        class CyclicStorage(FakeStorage):
            def list_folder(self, cid: int) -> list[object]:
                self.calls.append(("list_folder", (cid,)))
                if cid == 9001 or cid == 50:
                    return [deep_dir]
                return []

        storage = CyclicStorage([])

        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = self._repo(tmp_dir)
            service = OrganizeRunService(
                repo,
                storage,
                self.rule,
                metadata_resolver=lambda current: None,
                sleeper=lambda _seconds: None,
                max_depth=3,
            )

            result = service.run_once(9001)

            self.assertEqual(result.status, SUCCESS)
            items = repo.list_run_items(result.run_id)
            reasons = [item.reason for item in items]
            self.assertIn("max recursion depth 3 reached", reasons)

    def test_falls_back_to_ancestor_folder_name_when_filename_resolution_fails(self) -> None:
        season_folder = {"id": 30, "name": "S01", "is_dir": True}
        nested_file = {"id": 31, "name": "ep07.mkv", "is_dir": False}
        title_folder = {"id": 20, "name": "英雄联盟：双城之战 (2021) {tmdb-94605}", "is_dir": True}

        class NestedStorage(FakeStorage):
            def list_folder(self, cid: int) -> list[object]:
                self.calls.append(("list_folder", (cid,)))
                if cid == 9001:
                    return [title_folder]
                if cid == 20:
                    return [season_folder]
                if cid == 30:
                    return [nested_file]
                return list(self.target_folder_items)

        storage = NestedStorage([], ensure_folder_result={"cid": 7001})
        folder_calls: list[tuple[str, object, object]] = []

        def folder_resolver(title: str, tmdb_id: object, year: object) -> OrganizeMetadata | None:
            folder_calls.append((title, tmdb_id, year))
            return OrganizeMetadata(title="Arcane", year=2021, kind=MEDIA_KIND_SERIES, season=1, episode=7)

        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = self._repo(tmp_dir)
            service = OrganizeRunService(
                repo,
                storage,
                self.rule,
                metadata_resolver=lambda current: None,
                folder_resolver=folder_resolver,
                sleeper=lambda _seconds: None,
            )

            result = service.run_once(9001)

            self.assertEqual(result.success_count, 1)
            # 跳过季度文件夹 S01，溯源到标题文件夹，优先用 tmdb-id
            self.assertEqual(folder_calls, [("英雄联盟：双城之战", 94605, 2021)])
            self.assertIn(("move_file", (31, 7001)), storage.calls)

    def test_ancestor_folder_metadata_is_reused_for_sibling_files(self) -> None:
        title_folder = {"id": 20, "name": "Some Show (2020)", "is_dir": True}
        file_a = {"id": 41, "name": "a.mkv", "is_dir": False}
        file_b = {"id": 42, "name": "b.mkv", "is_dir": False}

        class NestedStorage(FakeStorage):
            def list_folder(self, cid: int) -> list[object]:
                self.calls.append(("list_folder", (cid,)))
                if cid == 9001:
                    return [title_folder]
                if cid == 20:
                    return [file_a, file_b]
                return list(self.target_folder_items)

        storage = NestedStorage([], ensure_folder_result={"cid": 7001})
        folder_calls: list[str] = []

        def folder_resolver(title: str, tmdb_id: object, year: object) -> OrganizeMetadata | None:
            folder_calls.append(title)
            return OrganizeMetadata(title="Some Show", year=2020, kind=MEDIA_KIND_MOVIE)

        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = self._repo(tmp_dir)
            service = OrganizeRunService(
                repo,
                storage,
                self.rule,
                metadata_resolver=lambda current: None,
                folder_resolver=folder_resolver,
                sleeper=lambda _seconds: None,
            )

            result = service.run_once(9001)

            self.assertEqual(result.success_count, 2)
            # 同一文件夹只查一次 TMDB，第二个文件复用缓存
            self.assertEqual(folder_calls, ["Some Show"])

    def test_per_item_failure_marks_failed_and_continues_to_partial_success(self) -> None:
        bad_item = {"id": 31, "name": "bad.mkv", "is_dir": False}
        good_item = {"id": 32, "name": "good.mkv", "is_dir": False}
        storage = FakeStorage([bad_item, good_item], ensure_folder_result={"cid": 8001})
        storage.fail_on("rename_file", 31, "Broken（2025）.mkv", error=RuntimeError("rename exploded"))

        def resolve(item: object) -> OrganizeMetadata:
            current = item if isinstance(item, dict) else vars(item)
            title = "Broken" if current["id"] == 31 else "Good"
            return OrganizeMetadata(title=title, year=2025, kind=MEDIA_KIND_MOVIE)

        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = self._repo(tmp_dir)
            service = self._service(repo, storage, metadata_resolver=resolve)

            result = service.run_once(9001)

            self.assertEqual(result.status, PARTIAL_SUCCESS)
            self.assertEqual(result.scanned_count, 2)
            self.assertEqual(result.planned_count, 2)
            self.assertEqual(result.success_count, 1)
            self.assertEqual(result.skipped_count, 0)
            self.assertEqual(result.failed_count, 1)
            self.assertEqual(result.last_error, "rename exploded")
            run = repo.get_run(result.run_id)
            self.assertIsNotNone(run)
            assert run is not None
            self.assertEqual(run.status, PARTIAL_SUCCESS)
            self.assertEqual(run.last_error, "rename exploded")
            items = repo.list_run_items(result.run_id)
            self.assertEqual([item.status for item in items], [FAILED, SUCCESS])
            self.assertEqual(items[0].error, "rename exploded")
            self.assertEqual(items[0].new_name, "Broken（2025）.mkv")
            self.assertEqual(items[1].target_cid, 8001)
            # FakeStorage returns cid=8001 for all ensure_folder calls, so parent_cid stays 8001
            self.assertEqual(
                storage.calls,
                [
                    ("list_folder", (9001,)),
                    ("ensure_folder", (100, "电影")),
                    ("ensure_folder", (8001, "未分类地区")),
                    ("ensure_folder", (8001, "Broken（2025）")),
                    ("list_folder", (8001,)),
                    ("rename_file", (31, "Broken（2025）.mkv")),
                    ("ensure_folder", (100, "电影")),
                    ("ensure_folder", (8001, "未分类地区")),
                    ("ensure_folder", (8001, "Good（2025）")),
                    ("list_folder", (8001,)),
                    ("rename_file", (32, "Good（2025）.mkv")),
                    ("move_file", (32, 8001)),
                ],
            )

    def test_scan_failure_finishes_run_failed_without_items(self) -> None:
        storage = FakeStorage([])
        storage.list_folder_error = RuntimeError("scan exploded")

        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = self._repo(tmp_dir)
            service = self._service(repo, storage, metadata_resolver=lambda current: None)

            result = service.run_once(9001)

            self.assertEqual(result.status, FAILED)
            self.assertEqual(result.scanned_count, 0)
            self.assertEqual(result.planned_count, 0)
            self.assertEqual(result.success_count, 0)
            self.assertEqual(result.skipped_count, 0)
            self.assertEqual(result.failed_count, 0)
            self.assertEqual(result.last_error, "scan exploded")
            run = repo.get_run(result.run_id)
            self.assertIsNotNone(run)
            assert run is not None
            self.assertEqual(run.status, FAILED)
            self.assertEqual(run.last_error, "scan exploded")
            self.assertEqual(repo.list_run_items(result.run_id), [])
            self.assertEqual(storage.calls, [("list_folder", (9001,))])

    def test_series_nested_folder_and_no_metadata_skips_unknown(self) -> None:
        series_item = {"id": 41, "name": "episode.mkv", "is_dir": False}
        unknown_item = {"id": 42, "name": "Original Name.mp4", "is_dir": False}
        storage = FakeStorage([series_item, unknown_item], ensure_folder_result={"cid": 9009})

        def resolve(item: object) -> OrganizeMetadata | None:
            current = item if isinstance(item, dict) else vars(item)
            if current["id"] == 41:
                return OrganizeMetadata(
                    title="Show", year=2026, kind=MEDIA_KIND_SERIES, region_category="欧美", season=1, episode=2
                )
            return None

        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = self._repo(tmp_dir)
            service = self._service(repo, storage, metadata_resolver=resolve)

            result = service.run_once(9001)

            self.assertEqual(result.status, SUCCESS)
            self.assertEqual(result.planned_count, 1)
            self.assertEqual(result.success_count, 1)
            self.assertEqual(result.skipped_count, 1)
            items = repo.list_run_items(result.run_id)
            self.assertEqual(len(items), 2)
            self.assertEqual(items[0].new_name, "Show.2026.S01E02.第2集.mkv")
            self.assertEqual(items[0].target_path, "剧集/欧美/Show（2026）/S01")
            self.assertEqual(items[0].status, SUCCESS)
            self.assertEqual(items[1].file_name, "Original Name.mp4")
            self.assertEqual(items[1].status, SKIPPED_UNMATCHED)
            # FakeStorage returns cid=9009 for all ensure_folder calls
            self.assertEqual(
                storage.calls,
                [
                    ("list_folder", (9001,)),
                    ("ensure_folder", (100, "剧集")),
                    ("ensure_folder", (9009, "欧美")),
                    ("ensure_folder", (9009, "Show（2026）")),
                    ("ensure_folder", (9009, "S01")),
                    ("list_folder", (9009,)),
                    ("rename_file", (41, "Show.2026.S01E02.第2集.mkv")),
                    ("move_file", (41, 9009)),
                ],
            )

    def test_module_has_no_forbidden_dependencies(self) -> None:
        import src.processors.organize_run as organize_run

        source = inspect.getsource(organize_run)
        forbidden = [
            "Storage115Service",
            "p115",
            "P115_COOKIES",
            "src.organizing.tmdb",
            "TmdbMultiResolver",
            "TmdbConfig",
            "notification",
            "requests",
            "httpx",
            "QueueRepository",
        ]
        for text in forbidden:
            self.assertNotIn(text, source)

    def _repo(self, tmp_dir: str) -> OrganizeRepository:
        repo = OrganizeRepository(Path(tmp_dir) / "organize.db")
        repo.init_schema()
        return repo


if __name__ == "__main__":
    unittest.main()
