from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.config.settings import AppSettings
from src.organizing.tmdb import TmdbConfig
from src.storage import Storage115Config

try:
    from src.api.app import create_app
except ModuleNotFoundError as import_error:
    create_app = None
    CREATE_APP_IMPORT_ERROR = import_error
else:
    CREATE_APP_IMPORT_ERROR = None


class FakeRuntimeControlService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def status(self):
        self.calls.append("status")
        return _fake_status()

    def start(self):
        self.calls.append("start")
        return {**_fake_status(), "action": "start", "changed": True}

    def stop(self):
        self.calls.append("stop")
        return {**_fake_status(), "action": "stop", "changed": True}


def _fake_status() -> dict[str, object]:
    return {
        "desired_state": "stopped",
        "effective_state": "stopped",
        "control_plane_only": True,
        "started_at": None,
        "stopped_at": "2026-05-28T00:00:00",
        "updated_at": "2026-05-28T00:00:00",
        "message": "fake runtime",
        "components": [
            {
                "name": "transfer_processor",
                "desired_state": "stopped",
                "status": "blocked",
                "configured": False,
                "enabled": True,
                "detail": "fake blocked without secrets",
                "last_status": "failed",
                "last_error": "fake worker failed",
                "tick_count": 7,
                "last_started_at": "2026-05-28T00:00:01",
                "last_finished_at": "2026-05-28T00:00:02",
                "last_success": False,
                "last_heartbeat_at": "2026-05-28T00:00:03",
            }
        ],
        "queues": {
            "collect_queue": {"PENDING": 0, "RUNNING": 0, "SUCCESS": 0, "SKIPPED": 0, "FAILED": 0},
            "transfer_queue": {"PENDING": 0, "RUNNING": 0, "SUCCESS": 0, "FAILED": 0},
        },
        "organizer": {
            "latest_run": None,
            "counts": {"RUNNING": 0, "SUCCESS": 0, "PARTIAL_SUCCESS": 0, "FAILED": 0, "CANCELLED": 0},
        },
    }


class RuntimeApiTestCase(unittest.TestCase):
    def build_client(self, db_path: Path, *, settings: AppSettings | None = None, fake_service: FakeRuntimeControlService | None = None) -> TestClient:
        if create_app is None:
            raise unittest.SkipTest(f"src.api.app.create_app is not implemented yet: {CREATE_APP_IMPORT_ERROR}")
        api_app = create_app(db_path=db_path, settings=settings)
        if fake_service is not None:
            api_app.state.runtime_control_service = fake_service
        return TestClient(api_app)


class FastApiRuntimeControlTest(RuntimeApiTestCase):
    def test_status_returns_default_stopped_control_plane_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            response = self.build_client(Path(tmp_dir) / "api.db").get("/runtime/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["desired_state"], "stopped")
        self.assertEqual(payload["effective_state"], "stopped")
        self.assertTrue(payload["control_plane_only"])
        self.assertEqual(payload["queues"]["collect_queue"]["PENDING"], 0)
        self.assertEqual({component["name"] for component in payload["components"]}, {"telegram_collector", "subscription_processor", "transfer_processor", "organizer"})

    def test_start_stop_are_idempotent_and_persist_across_clients(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "api.db"
            client = self.build_client(db_path)
            first_start = client.post("/runtime/start")
            second_start = client.post("/runtime/start")
            reloaded_status = self.build_client(db_path).get("/runtime/status")
            first_stop = client.post("/runtime/stop")
            second_stop = client.post("/runtime/stop")

        self.assertEqual(first_start.status_code, 200)
        self.assertTrue(first_start.json()["changed"])
        self.assertEqual(first_start.json()["action"], "start")
        self.assertFalse(second_start.json()["changed"])
        self.assertEqual(reloaded_status.json()["desired_state"], "running")
        self.assertTrue(first_stop.json()["changed"])
        self.assertFalse(second_stop.json()["changed"])
        self.assertEqual(second_stop.json()["desired_state"], "stopped")

    def test_trigger_enqueues_manual_event_and_persists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "api.db"
            client = self.build_client(db_path)
            ok = client.post("/runtime/trigger", json={"event_name": "manual_collect"})
            bad = client.post("/runtime/trigger", json={"event_name": "nope"})

            from src.runtime.repository import RuntimeControlRepository

            repo = RuntimeControlRepository(db_path)
            claimed = repo.claim_pending_manual_triggers()

        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["event_name"], "manual_collect")
        self.assertGreater(ok.json()["trigger_id"], 0)
        self.assertEqual(bad.status_code, 422)
        self.assertEqual([name for _id, name, _src in claimed], ["manual_collect"])

    def test_injected_fake_runtime_service_is_used(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = AppSettings(
                transfer_cid=9001,
                p115=Storage115Config(cookies="super-secret-cookie", cache_home=Path("secret-cache")),
                tmdb=TmdbConfig(bearer_token="super-secret-token"),
            )
            fake_service = FakeRuntimeControlService()
            client = self.build_client(Path(tmp_dir) / "api.db", settings=settings, fake_service=fake_service)
            status_response = client.get("/runtime/status")
            start_response = client.post("/runtime/start")
            stop_response = client.post("/runtime/stop")

        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(start_response.status_code, 200)
        self.assertEqual(stop_response.status_code, 200)
        self.assertEqual(fake_service.calls, ["status", "start", "stop"])
        self.assertEqual(start_response.json()["message"], "fake runtime")
        component = start_response.json()["components"][0]
        self.assertEqual(component["tick_count"], 7)
        self.assertEqual(component["last_started_at"], "2026-05-28T00:00:01")
        self.assertEqual(component["last_finished_at"], "2026-05-28T00:00:02")
        self.assertFalse(component["last_success"])
        self.assertEqual(component["last_heartbeat_at"], "2026-05-28T00:00:03")
        body = start_response.text
        self.assertNotIn("super-secret-cookie", body)
        self.assertNotIn("super-secret-token", body)
        self.assertNotIn("secret-cache", body)

    def test_runtime_api_does_not_require_storage_or_tmdb_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            client = self.build_client(Path(tmp_dir) / "api.db", settings=AppSettings())
            status_response = client.get("/runtime/status")
            start_response = client.post("/runtime/start")

        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(start_response.status_code, 200)
        components = {component["name"]: component for component in start_response.json()["components"]}
        self.assertEqual(components["transfer_processor"]["status"], "blocked")
        self.assertEqual(components["organizer"]["status"], "blocked")

    def test_runtime_response_does_not_leak_secret_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = AppSettings(
                transfer_cid=9001,
                p115=Storage115Config(cookies="super-secret-cookie", cache_home=Path("secret-cache")),
                tmdb=TmdbConfig(bearer_token="super-secret-token"),
            )
            response = self.build_client(Path(tmp_dir) / "api.db", settings=settings).post("/runtime/start")

        body = response.text
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("super-secret-cookie", body)
        self.assertNotIn("super-secret-token", body)
        self.assertNotIn("secret-cache", body)

    def test_create_app_defaults_to_not_starting_embedded_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir, \
             patch("src.api.app.Thread") as thread_cls:
            api_app = create_app(db_path=Path(tmp_dir) / "api.db", settings=AppSettings())
            with TestClient(api_app):
                pass

        thread_cls.assert_not_called()

    def test_create_app_can_start_embedded_runtime_with_lifespan(self) -> None:
        if create_app is None:
            raise unittest.SkipTest(f"src.api.app.create_app is not implemented yet: {CREATE_APP_IMPORT_ERROR}")

        class FakeThread:
            def __init__(self, *, target, args, name, daemon):
                self.target = target
                self.args = args
                self.name = name
                self.daemon = daemon
                self.started = False
                self.join_timeout = None

            def start(self):
                self.started = True

            def join(self, timeout=None):
                self.join_timeout = timeout

        created_threads: list[FakeThread] = []

        def thread_factory(*, target, args, name, daemon):
            thread = FakeThread(target=target, args=args, name=name, daemon=daemon)
            created_threads.append(thread)
            return thread

        with tempfile.TemporaryDirectory() as tmp_dir, \
             patch("src.api.app.Thread", side_effect=thread_factory):
            api_app = create_app(db_path=Path(tmp_dir) / "api.db", settings=AppSettings(), start_runtime=True)
            with TestClient(api_app):
                self.assertEqual(len(created_threads), 1)
                self.assertTrue(created_threads[0].started)
                self.assertEqual(created_threads[0].name, "api-runtime-worker")

            self.assertEqual(created_threads[0].join_timeout, 5)


if __name__ == "__main__":
    unittest.main()
