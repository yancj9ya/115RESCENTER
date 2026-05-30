from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.runtime.repository import RuntimeControlRepository


class RuntimeControlRepositoryTest(unittest.TestCase):
    def build_repository(self, db_path: Path) -> RuntimeControlRepository:
        repository = RuntimeControlRepository(db_path)
        repository.init_schema()
        return repository

    def test_schema_initialization_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "runtime.db"
            repository = self.build_repository(db_path)
            repository.init_schema()

            connection = sqlite3.connect(db_path)
            try:
                tables = {
                    row[0]
                    for row in connection.execute(
                        """
                        SELECT name
                        FROM sqlite_master
                        WHERE type = 'table'
                        """
                    )
                }
                control_rows = connection.execute("SELECT COUNT(*) FROM runtime_control").fetchone()[0]
            finally:
                connection.close()

        self.assertIn("runtime_control", tables)
        self.assertIn("runtime_components", tables)
        self.assertIn("runtime_worker_heartbeats", tables)
        self.assertEqual(control_rows, 1)

    def test_start_and_stop_are_idempotent_and_preserve_state_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repository = self.build_repository(Path(tmp_dir) / "runtime.db")

            initial = repository.get_state()
            first_start, first_start_changed = repository.start()
            second_start, second_start_changed = repository.start()
            first_stop, first_stop_changed = repository.stop()
            second_stop, second_stop_changed = repository.stop()

        self.assertEqual(initial.desired_state, "stopped")
        self.assertTrue(first_start_changed)
        self.assertEqual(first_start.desired_state, "running")
        self.assertFalse(second_start_changed)
        self.assertEqual(second_start.desired_state, "running")
        self.assertTrue(first_stop_changed)
        self.assertEqual(first_stop.desired_state, "stopped")
        self.assertFalse(second_stop_changed)
        self.assertEqual(second_stop.desired_state, "stopped")

    def test_component_status_persists_and_reloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "runtime.db"
            repository = self.build_repository(db_path)
            saved = repository.save_component_status(
                name="telegram_collector",
                status="running",
                enabled=True,
                configured=True,
                started_at="2026-05-28T10:00:00",
                tick_count=2,
            )
            repository.save_component_status(
                name="telegram_collector",
                status="success",
                enabled=True,
                configured=True,
                started_at="2026-05-28T10:00:00",
                finished_at="2026-05-28T10:00:10",
                success=True,
                tick_count=None,
            )
            reloaded = RuntimeControlRepository(db_path)
            reloaded.init_schema()
            record = reloaded.get_component_status("telegram_collector")
            records = reloaded.list_component_statuses()

        self.assertEqual(saved.name, "telegram_collector")
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.status, "success")
        self.assertTrue(record.enabled)
        self.assertTrue(record.configured)
        self.assertTrue(record.success)
        self.assertEqual(record.tick_count, 2)
        self.assertEqual(record.finished_at, "2026-05-28T10:00:10")
        self.assertEqual([item.name for item in records], ["telegram_collector"])

    def test_component_tick_can_create_and_increment_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repository = self.build_repository(Path(tmp_dir) / "runtime.db")
            created = repository.increment_component_tick("subscription_processor", amount=3)
            incremented = repository.increment_component_tick("subscription_processor")

        self.assertEqual(created.tick_count, 3)
        self.assertEqual(incremented.tick_count, 4)
        self.assertEqual(incremented.status, "idle")
        self.assertFalse(incremented.enabled)
        self.assertFalse(incremented.configured)

    def test_worker_heartbeat_persists_and_reloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "runtime.db"
            repository = self.build_repository(db_path)
            repository.save_worker_heartbeat(
                worker_name="scheduler-main",
                component_name="telegram_collector",
                status="running",
                pid=1234,
            )
            saved = repository.save_worker_heartbeat(
                worker_name="scheduler-main",
                component_name="telegram_collector",
                status="degraded",
                pid=1234,
                error="temporary collection issue",
            )
            reloaded = RuntimeControlRepository(db_path)
            reloaded.init_schema()
            record = reloaded.get_worker_heartbeat("scheduler-main")
            records = reloaded.list_worker_heartbeats()

        self.assertEqual(saved.status, "degraded")
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.worker_name, "scheduler-main")
        self.assertEqual(record.component_name, "telegram_collector")
        self.assertEqual(record.pid, 1234)
        self.assertEqual(record.error, "temporary collection issue")
        self.assertEqual([item.worker_name for item in records], ["scheduler-main"])

    def test_repository_sanitizes_persisted_errors(self) -> None:
        noisy_error = " first line\n" + ("x" * 700) + "\nsecond line "
        with tempfile.TemporaryDirectory() as tmp_dir:
            repository = self.build_repository(Path(tmp_dir) / "runtime.db")
            component = repository.save_component_status(
                name="transfer_processor",
                status="failed",
                enabled=True,
                configured=True,
                success=False,
                error=noisy_error,
            )
            heartbeat = repository.save_worker_heartbeat(
                worker_name="transfer-worker",
                component_name="transfer_processor",
                status="failed",
                error=noisy_error,
            )

        self.assertIsNotNone(component.error)
        self.assertIsNotNone(heartbeat.error)
        assert component.error is not None
        assert heartbeat.error is not None
        self.assertLessEqual(len(component.error), 500)
        self.assertLessEqual(len(heartbeat.error), 500)
        self.assertNotIn("\n", component.error)
        self.assertNotIn("\n", heartbeat.error)
        self.assertTrue(component.error.endswith("..."))
        self.assertTrue(heartbeat.error.endswith("..."))


if __name__ == "__main__":
    unittest.main()
