from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from src.config.settings import AppSettings
from src.organizing.repository import OrganizeRepository
from src.processors.organize_run import OrganizeRunOnceResult

try:
    from src.api.app import create_app
except ModuleNotFoundError as import_error:
    create_app = None
    CREATE_APP_IMPORT_ERROR = import_error
else:
    CREATE_APP_IMPORT_ERROR = None


class FakeOrganizeRunService:
    def __init__(self) -> None:
        self.calls: list[int] = []
        self.default_staging_cid = 9001

    def run_once(self, staging_cid: int) -> OrganizeRunOnceResult:
        self.calls.append(staging_cid)
        return OrganizeRunOnceResult(
            run_id=7,
            status="SUCCESS",
            scanned_count=2,
            planned_count=1,
            success_count=1,
            skipped_count=1,
            failed_count=0,
            last_error=None,
        )


class OrganizeApiTestCase(unittest.TestCase):
    def build_client(
        self,
        db_path: Path,
        *,
        service: FakeOrganizeRunService | None = None,
        settings: AppSettings | None = None,
    ) -> TestClient:
        if create_app is None:
            raise unittest.SkipTest(f"src.api.app.create_app is not implemented yet: {CREATE_APP_IMPORT_ERROR}")
        api_app = create_app(db_path=db_path, settings=settings)
        if service is not None:
            api_app.state.organize_run_service = service
        return TestClient(api_app)

    def seed_repository(self, db_path: Path) -> OrganizeRepository:
        repository = OrganizeRepository(db_path)
        repository.init_schema()
        first_run = repository.create_run(staging_cid=9001)
        first_item = repository.create_item(
            first_run.id,
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
            first_item.id,
            target_cid=3001,
            target_path="国产/Movie A (2026)",
            new_name="Movie A (2026).mkv",
            reason="movie metadata matched",
            metadata={"title": "Movie A", "year": 2026},
        )
        repository.finish_run(
            first_run.id,
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


class FastApiOrganizerRunOnceTest(OrganizeApiTestCase):
    def test_run_once_uses_injected_fake_service_and_request_staging_cid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_service = FakeOrganizeRunService()
            client = self.build_client(Path(tmp_dir) / "api.db", service=fake_service)
            response = client.post("/organizer/run-once", json={"staging_cid": 1234})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(fake_service.calls, [1234])
        self.assertEqual(
            response.json(),
            {
                "run_id": 7,
                "status": "SUCCESS",
                "scanned_count": 2,
                "planned_count": 1,
                "success_count": 1,
                "skipped_count": 1,
                "failed_count": 0,
                "last_error": None,
            },
        )

    def test_run_once_uses_settings_transfer_cid_as_default_staging_cid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_service = FakeOrganizeRunService()
            fake_service.default_staging_cid = 9001
            client = self.build_client(Path(tmp_dir) / "api.db", service=fake_service)
            response = client.post("/organizer/run-once", json={})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(fake_service.calls, [9001])

    def test_run_once_without_storage_configuration_returns_503_and_does_not_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            response = self.build_client(Path(tmp_dir) / "api.db", settings=AppSettings()).post(
                "/organizer/run-once",
                json={"staging_cid": 9001},
            )

        self.assertEqual(response.status_code, 503)
        self.assertIn("115 storage", response.json()["detail"])

    def test_run_once_without_staging_cid_returns_422_before_fake_service_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_service = FakeOrganizeRunService()
            fake_service.default_staging_cid = 0
            response = self.build_client(Path(tmp_dir) / "api.db", service=fake_service).post(
                "/organizer/run-once",
                json={},
            )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(fake_service.calls, [])


class FastApiOrganizerReadEndpointsTest(OrganizeApiTestCase):
    def test_list_runs_returns_id_desc_order_and_filters_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "api.db"
            self.seed_repository(db_path)
            client = self.build_client(db_path)
            all_response = client.get("/organizer/runs")
            failed_response = client.get("/organizer/runs", params={"status": "FAILED"})

        self.assertEqual(all_response.status_code, 200)
        self.assertEqual([item["id"] for item in all_response.json()["items"]], [2, 1])
        self.assertEqual([item["status"] for item in failed_response.json()["items"]], ["FAILED"])

    def test_list_runs_invalid_status_returns_422(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            response = self.build_client(Path(tmp_dir) / "api.db").get(
                "/organizer/runs",
                params={"status": "DONE"},
            )

        self.assertEqual(response.status_code, 422)

    def test_list_runs_validates_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            client = self.build_client(Path(tmp_dir) / "api.db")
            self.assertEqual(client.get("/organizer/runs", params={"limit": 0}).status_code, 422)
            self.assertEqual(client.get("/organizer/runs", params={"limit": 201}).status_code, 422)

    def test_detail_returns_run_and_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "api.db"
            self.seed_repository(db_path)
            response = self.build_client(db_path).get("/organizer/runs/1")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["run"]["status"], "SUCCESS")
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["file_name"], "Movie.A.2026.mkv")
        self.assertIn("Movie A", payload["items"][0]["metadata_json"])

    def test_detail_unknown_run_returns_404(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            response = self.build_client(Path(tmp_dir) / "api.db").get("/organizer/runs/404")

        self.assertEqual(response.status_code, 404)

    def test_status_returns_latest_run_and_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "api.db"
            self.seed_repository(db_path)
            response = self.build_client(db_path).get("/organizer/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["latest_run"]["id"], 2)
        self.assertEqual(payload["counts"]["SUCCESS"], 1)
        self.assertEqual(payload["counts"]["FAILED"], 1)
        self.assertEqual(payload["counts"]["RUNNING"], 0)

    def test_status_on_empty_db_returns_no_latest_and_zero_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            response = self.build_client(Path(tmp_dir) / "api.db").get("/organizer/status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "latest_run": None,
                "counts": {
                    "RUNNING": 0,
                    "SUCCESS": 0,
                    "PARTIAL_SUCCESS": 0,
                    "FAILED": 0,
                    "CANCELLED": 0,
                },
            },
        )


if __name__ == "__main__":
    unittest.main()
