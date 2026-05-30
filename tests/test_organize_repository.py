from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from dataclasses import dataclass, fields, is_dataclass
from pathlib import Path


class OrganizeRepositoryModelTest(unittest.TestCase):
    def test_status_constants_and_dataclass_contracts(self) -> None:
        from src.organizing.repository import (
            CANCELLED,
            FAILED,
            ORGANIZE_RUN_ITEM_STATUSES,
            ORGANIZE_RUN_STATUSES,
            PARTIAL_SUCCESS,
            PLANNED,
            RUNNING,
            SKIPPED_DIR,
            SKIPPED_UNMATCHED,
            SUCCESS,
            OrganizeRunItemRecord,
            OrganizeRunRecord,
        )

        self.assertEqual(RUNNING, "RUNNING")
        self.assertEqual(SUCCESS, "SUCCESS")
        self.assertEqual(PARTIAL_SUCCESS, "PARTIAL_SUCCESS")
        self.assertEqual(FAILED, "FAILED")
        self.assertEqual(CANCELLED, "CANCELLED")
        self.assertEqual(PLANNED, "PLANNED")
        self.assertEqual(SKIPPED_DIR, "SKIPPED_DIR")
        self.assertEqual(SKIPPED_UNMATCHED, "SKIPPED_UNMATCHED")
        self.assertEqual(ORGANIZE_RUN_STATUSES, ("RUNNING", "SUCCESS", "PARTIAL_SUCCESS", "FAILED", "CANCELLED"))
        self.assertEqual(ORGANIZE_RUN_ITEM_STATUSES, ("PLANNED", "SKIPPED_DIR", "SKIPPED_UNMATCHED", "SKIPPED_DUPLICATE", "SUCCESS", "FAILED"))
        self.assertTrue(is_dataclass(OrganizeRunRecord))
        self.assertTrue(is_dataclass(OrganizeRunItemRecord))
        self.assertEqual(
            [field.name for field in fields(OrganizeRunRecord)],
            [
                "id",
                "staging_cid",
                "status",
                "planned_count",
                "success_count",
                "skipped_count",
                "failed_count",
                "last_error",
                "started_at",
                "finished_at",
                "created_at",
                "updated_at",
            ],
        )
        self.assertEqual(
            [field.name for field in fields(OrganizeRunItemRecord)],
            [
                "id",
                "run_id",
                "file_id",
                "file_name",
                "is_dir",
                "status",
                "target_cid",
                "target_path",
                "new_name",
                "reason",
                "error",
                "metadata_json",
                "created_at",
                "updated_at",
            ],
        )


class OrganizeRepositorySchemaTest(unittest.TestCase):
    def test_init_schema_creates_run_and_item_tables_idempotently(self) -> None:
        from src.organizing.repository import OrganizeRepository

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "organize.db"
            repo = OrganizeRepository(db_path)
            repo.init_schema()
            repo.init_schema()

            connection = sqlite3.connect(db_path)
            try:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                    )
                }
                run_schema = connection.execute(
                    "SELECT sql FROM sqlite_master WHERE name='organize_runs'"
                ).fetchone()[0]
                item_schema = connection.execute(
                    "SELECT sql FROM sqlite_master WHERE name='organize_run_items'"
                ).fetchone()[0]
                run_indexes = {row[1] for row in connection.execute("PRAGMA index_list('organize_runs')")}
                item_indexes = {row[1] for row in connection.execute("PRAGMA index_list('organize_run_items')")}
            finally:
                connection.close()

            self.assertIn("organize_runs", tables)
            self.assertIn("organize_run_items", tables)
            self.assertIn("staging_cid INTEGER NOT NULL", run_schema)
            self.assertIn("planned_count INTEGER NOT NULL DEFAULT 0", run_schema)
            self.assertIn("FOREIGN KEY(run_id) REFERENCES organize_runs(id)", item_schema)
            self.assertIn("metadata_json TEXT", item_schema)
            self.assertIn("idx_organize_runs_status_id", run_indexes)
            self.assertIn("idx_organize_run_items_run_id_id", item_indexes)


class OrganizeRepositoryRunTest(unittest.TestCase):
    def test_create_finish_get_latest_and_list_runs(self) -> None:
        from src.organizing.repository import FAILED, PARTIAL_SUCCESS, SUCCESS, OrganizeRepository

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "organize.db"
            repo = OrganizeRepository(db_path)
            repo.init_schema()

            self.assertIsNone(repo.get_latest_run())
            first = repo.create_run(staging_cid=9001)
            second = repo.create_run(staging_cid=9002)
            third = repo.create_run(staging_cid=9003)

            self.assertEqual(first.status, "RUNNING")
            self.assertEqual(first.planned_count, 0)
            self.assertEqual(second.id, first.id + 1)
            self.assertEqual(third.id, second.id + 1)
            self.assertEqual(repo.get_latest_run().id, third.id)

            repo.finish_run(
                first.id,
                planned_count=4,
                success_count=2,
                skipped_count=1,
                failed_count=1,
                status=PARTIAL_SUCCESS,
                error="one item failed",
            )
            repo.finish_run(
                second.id,
                planned_count=1,
                success_count=0,
                skipped_count=0,
                failed_count=1,
                status=FAILED,
                error="scan failed",
            )
            repo.finish_run(
                third.id,
                planned_count=2,
                success_count=2,
                skipped_count=0,
                failed_count=0,
                status=SUCCESS,
                error=None,
            )

            finished_first = repo.get_run(first.id)
            self.assertIsNotNone(finished_first)
            assert finished_first is not None
            self.assertEqual(finished_first.status, PARTIAL_SUCCESS)
            self.assertEqual(finished_first.planned_count, 4)
            self.assertEqual(finished_first.success_count, 2)
            self.assertEqual(finished_first.skipped_count, 1)
            self.assertEqual(finished_first.failed_count, 1)
            self.assertEqual(finished_first.last_error, "one item failed")
            self.assertIsNotNone(finished_first.finished_at)
            self.assertIsNone(repo.get_run(9999))

            self.assertEqual([run.id for run in repo.list_runs(2)], [third.id, second.id])
            self.assertEqual([run.id for run in repo.list_runs(10, status=FAILED)], [second.id])
            self.assertEqual(repo.get_status_counts(), {"FAILED": 1, "PARTIAL_SUCCESS": 1, "SUCCESS": 1})


class OrganizeRepositoryItemTest(unittest.TestCase):
    def test_create_items_mark_success_and_failed_list_by_run(self) -> None:
        from src.organizing.repository import FAILED, PLANNED, SKIPPED_DIR, SUCCESS, OrganizeRepository

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "organize.db"
            repo = OrganizeRepository(db_path)
            repo.init_schema()
            run = repo.create_run(staging_cid=9001)
            other_run = repo.create_run(staging_cid=9002)

            planned = repo.create_item(
                run.id,
                file_id=101,
                file_name="Movie.2026.mkv",
                target_cid=3001,
                target_path="/电影/Movie (2026)",
                new_name="Movie (2026).mkv",
                reason="matched movie",
                metadata={"title": "电影", "year": 2026, "tags": ["4K"]},
            )
            skipped = repo.create_item(
                run.id,
                file_id=102,
                file_name="Folder",
                is_dir=True,
                status=SKIPPED_DIR,
                reason="directory skipped",
            )
            failed = repo.create_item(other_run.id, file_id=201, file_name="Other.mkv")

            self.assertEqual(planned.status, PLANNED)
            self.assertFalse(planned.is_dir)
            self.assertTrue(skipped.is_dir)
            self.assertIn("电影", planned.metadata_json)

            repo.mark_item_success(
                planned.id,
                target_cid=4001,
                target_path="/电影/电影 (2026)",
                new_name="电影 (2026).mkv",
                reason="renamed and moved",
                metadata={"title": "电影", "year": 2026, "done": True},
            )
            repo.mark_item_failed(failed.id, "move failed", metadata={"file": "Other.mkv"})

            run_items = repo.list_run_items(run.id)
            other_items = repo.list_run_items(other_run.id)

            self.assertEqual([item.id for item in run_items], [planned.id, skipped.id])
            self.assertEqual(run_items[0].status, SUCCESS)
            self.assertEqual(run_items[0].target_cid, 4001)
            self.assertEqual(run_items[0].target_path, "/电影/电影 (2026)")
            self.assertEqual(run_items[0].new_name, "电影 (2026).mkv")
            self.assertEqual(run_items[0].reason, "renamed and moved")
            self.assertIsNone(run_items[0].error)
            self.assertEqual(json.loads(run_items[0].metadata_json), {"done": True, "title": "电影", "year": 2026})
            self.assertEqual(run_items[1].status, SKIPPED_DIR)
            self.assertEqual(run_items[1].reason, "directory skipped")

            self.assertEqual(len(other_items), 1)
            self.assertEqual(other_items[0].status, FAILED)
            self.assertEqual(other_items[0].error, "move failed")
            self.assertEqual(json.loads(other_items[0].metadata_json), {"file": "Other.mkv"})

    def test_metadata_serializes_dataclasses_and_plain_objects(self) -> None:
        from src.organizing.repository import OrganizeRepository

        @dataclass(frozen=True)
        class SampleMetadata:
            title: str
            year: int

        class PlainObject:
            def __init__(self) -> None:
                self.title = "对象"
                self.year = 2026

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "organize.db"
            repo = OrganizeRepository(db_path)
            repo.init_schema()
            run = repo.create_run(staging_cid=9001)

            dataclass_item = repo.create_item(
                run.id,
                file_id=301,
                file_name="Dataclass.mkv",
                metadata=SampleMetadata(title="数据类", year=2026),
            )
            object_item = repo.create_item(
                run.id,
                file_id=302,
                file_name="Object.mkv",
                metadata=PlainObject(),
            )
            none_item = repo.create_item(run.id, file_id=303, file_name="None.mkv")

            self.assertEqual(json.loads(dataclass_item.metadata_json), {"title": "数据类", "year": 2026})
            self.assertEqual(json.loads(object_item.metadata_json), {"title": "对象", "year": 2026})
            self.assertIsNone(none_item.metadata_json)

            connection = sqlite3.connect(db_path)
            try:
                stored = connection.execute(
                    "SELECT metadata_json FROM organize_run_items WHERE id = ?",
                    (dataclass_item.id,),
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertIn("数据类", stored)


if __name__ == "__main__":
    unittest.main()
