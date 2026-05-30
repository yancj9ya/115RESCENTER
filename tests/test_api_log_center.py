from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from src.organizing.repository import OrganizeRepository
from tests.test_api_queue_read import QueueApiTestFixture

try:
    from src.api.app import create_app
except ModuleNotFoundError as import_error:
    create_app = None
    CREATE_APP_IMPORT_ERROR = import_error
else:
    CREATE_APP_IMPORT_ERROR = None


class LogCenterApiTestCase(unittest.TestCase):
    def build_client(self, db_path: Path) -> TestClient:
        if create_app is None:
            raise unittest.SkipTest(f"src.api.app.create_app is not implemented yet: {CREATE_APP_IMPORT_ERROR}")
        return TestClient(create_app(db_path=db_path))

    def seed_organizer(self, db_path: Path) -> OrganizeRepository:
        repository = OrganizeRepository(db_path)
        repository.init_schema()
        success_run = repository.create_run(staging_cid=9001)
        success_item = repository.create_item(
            success_run.id,
            file_id=100,
            file_name="Movie.A.2026.mkv",
            status="PLANNED",
            target_cid=3001,
            target_path="国产/Movie A (2026)",
            new_name="Movie A (2026).mkv",
            reason="movie metadata matched",
            metadata={"title": "Movie A", "year": 2026},
        )
        repository.mark_item_success(
            success_item.id,
            target_cid=3001,
            target_path="国产/Movie A (2026)",
            new_name="Movie A (2026).mkv",
            reason="movie metadata matched",
            metadata={"title": "Movie A", "year": 2026},
        )
        repository.finish_run(
            success_run.id,
            planned_count=1,
            success_count=1,
            skipped_count=0,
            failed_count=0,
            status="SUCCESS",
        )
        failed_run = repository.create_run(staging_cid=9002)
        repository.finish_run(
            failed_run.id,
            planned_count=0,
            success_count=0,
            skipped_count=0,
            failed_count=1,
            status="FAILED",
            error="storage boom",
        )
        return repository

    def queue_snapshot(self, fixture: QueueApiTestFixture) -> dict[str, list[tuple[int, str, int, str | None, str]]]:
        return {
            "collect": [
                (row.id, row.status, row.attempt_count, row.last_error, row.updated_at)
                for row in fixture.repo.list_collect_queue()
            ],
            "transfer": [
                (row.id, row.status, row.attempt_count, row.last_error, row.updated_at)
                for row in fixture.repo.list_transfer_queue()
            ],
        }

    def organize_snapshot(self, repository: OrganizeRepository) -> dict[str, object]:
        return {
            "runs": [(run.id, run.status, run.updated_at) for run in repository.list_runs(limit=50)],
            "items": [(item.id, item.status, item.updated_at) for item in repository.list_run_items(1)],
        }


class FastApiLogCenterSummaryTest(LogCenterApiTestCase):
    def test_summary_returns_queue_counts_organizer_counts_latest_and_recent_runs(self) -> None:
        fixture = QueueApiTestFixture()
        try:
            self.seed_organizer(fixture.db_path)
            response = fixture.build_client().get("/log-center/summary", params={"limit": 1})
        finally:
            fixture.cleanup()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["collect_queue"]["FAILED"], 1)
        self.assertEqual(payload["transfer_queue"]["SUCCESS"], 1)
        self.assertEqual(payload["organizer"]["latest_run"]["id"], 2)
        self.assertEqual(payload["organizer"]["counts"]["FAILED"], 1)
        self.assertEqual([run["id"] for run in payload["organizer"]["recent_runs"]], [2])

    def test_summary_is_read_only(self) -> None:
        fixture = QueueApiTestFixture()
        try:
            organize_repo = self.seed_organizer(fixture.db_path)
            before_queue = self.queue_snapshot(fixture)
            before_organize = self.organize_snapshot(organize_repo)
            response = fixture.build_client().get("/log-center/summary")
            after_queue = self.queue_snapshot(fixture)
            after_organize = self.organize_snapshot(organize_repo)
        finally:
            fixture.cleanup()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(after_queue, before_queue)
        self.assertEqual(after_organize, before_organize)

    def test_summary_validates_limit(self) -> None:
        fixture = QueueApiTestFixture()
        try:
            client = fixture.build_client()
            self.assertEqual(client.get("/log-center/summary", params={"limit": 0}).status_code, 422)
            self.assertEqual(client.get("/log-center/summary", params={"limit": 201}).status_code, 422)
        finally:
            fixture.cleanup()


class FastApiLogCenterQueueLogsTest(LogCenterApiTestCase):
    def test_collect_logs_return_id_desc_rows_with_share_payload_and_filter(self) -> None:
        fixture = QueueApiTestFixture()
        try:
            response = fixture.build_client().get("/log-center/collect/logs", params={"status": "FAILED"})
        finally:
            fixture.cleanup()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([item["id"] for item in payload["items"]], [4])
        self.assertEqual(payload["items"][0]["shares"][0]["share_code"], "d4")
        self.assertEqual(payload["items"][0]["last_error"], "collect boom")

    def test_collect_logs_reject_invalid_status_and_limit(self) -> None:
        fixture = QueueApiTestFixture()
        try:
            client = fixture.build_client()
            invalid_status = client.get("/log-center/collect/logs", params={"status": "DONE"})
            invalid_limit = client.get("/log-center/collect/logs", params={"limit": 0})
        finally:
            fixture.cleanup()

        self.assertEqual(invalid_status.status_code, 422)
        self.assertEqual(invalid_limit.status_code, 422)

    def test_transfer_logs_return_id_desc_rows_with_contexts_and_filter(self) -> None:
        fixture = QueueApiTestFixture()
        try:
            response = fixture.build_client().get("/log-center/transfer/logs", params={"status": "FAILED"})
        finally:
            fixture.cleanup()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([item["id"] for item in payload["items"]], [3])
        self.assertEqual(payload["items"][0]["matched_contexts"][0]["rule_name"], "CN movies")
        self.assertEqual(payload["items"][0]["source_messages"][0]["message_id"], "104")

    def test_transfer_logs_reject_invalid_status_and_limit(self) -> None:
        fixture = QueueApiTestFixture()
        try:
            client = fixture.build_client()
            invalid_status = client.get("/log-center/transfer/logs", params={"status": "DONE"})
            invalid_limit = client.get("/log-center/transfer/logs", params={"limit": 0})
        finally:
            fixture.cleanup()

        self.assertEqual(invalid_status.status_code, 422)
        self.assertEqual(invalid_limit.status_code, 422)

    def test_queue_log_endpoints_are_read_only(self) -> None:
        fixture = QueueApiTestFixture()
        try:
            before = self.queue_snapshot(fixture)
            client = fixture.build_client()
            collect_response = client.get("/log-center/collect/logs")
            transfer_response = client.get("/log-center/transfer/logs")
            after = self.queue_snapshot(fixture)
        finally:
            fixture.cleanup()

        self.assertEqual(collect_response.status_code, 200)
        self.assertEqual(transfer_response.status_code, 200)
        self.assertEqual(after, before)


class FastApiLogCenterOrganizerLogsTest(LogCenterApiTestCase):
    def test_organizer_runs_return_id_desc_rows_and_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "api.db"
            self.seed_organizer(db_path)
            client = self.build_client(db_path)
            all_response = client.get("/log-center/organizer/runs")
            failed_response = client.get("/log-center/organizer/runs", params={"status": "FAILED"})

        self.assertEqual(all_response.status_code, 200)
        self.assertEqual([item["id"] for item in all_response.json()["items"]], [2, 1])
        self.assertEqual([item["status"] for item in failed_response.json()["items"]], ["FAILED"])

    def test_organizer_runs_reject_invalid_status_and_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            client = self.build_client(Path(tmp_dir) / "api.db")
            invalid_status = client.get("/log-center/organizer/runs", params={"status": "DONE"})
            invalid_limit = client.get("/log-center/organizer/runs", params={"limit": 0})

        self.assertEqual(invalid_status.status_code, 422)
        self.assertEqual(invalid_limit.status_code, 422)

    def test_organizer_detail_returns_run_and_items_and_unknown_returns_404(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "api.db"
            self.seed_organizer(db_path)
            client = self.build_client(db_path)
            detail_response = client.get("/log-center/organizer/runs/1")
            missing_response = client.get("/log-center/organizer/runs/404")

        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["run"]["status"], "SUCCESS")
        self.assertEqual(detail_response.json()["items"][0]["file_name"], "Movie.A.2026.mkv")
        self.assertEqual(missing_response.status_code, 404)

    def test_organizer_log_endpoints_are_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "api.db"
            repository = self.seed_organizer(db_path)
            before = self.organize_snapshot(repository)
            client = self.build_client(db_path)
            list_response = client.get("/log-center/organizer/runs")
            detail_response = client.get("/log-center/organizer/runs/1")
            after = self.organize_snapshot(repository)

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
