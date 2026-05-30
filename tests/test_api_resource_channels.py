from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from src.queue.repository import QueueRepository
from src.resources import TelegramWebChannelRepository

try:
    from src.api.app import create_app
except ModuleNotFoundError as import_error:
    create_app = None
    CREATE_APP_IMPORT_ERROR = import_error
else:
    CREATE_APP_IMPORT_ERROR = None


class TelegramWebChannelApiFixture:
    def __init__(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._temp_dir.name) / "resource.db"
        self.resource_repository = TelegramWebChannelRepository(self.db_path)
        self.resource_repository.init_schema()
        self.queue_repository = QueueRepository(self.db_path)
        self.queue_repository.init_schema()

    def cleanup(self) -> None:
        self._temp_dir.cleanup()

    def build_client(self) -> TestClient:
        if create_app is None:
            raise unittest.SkipTest(f"src.api.app.create_app is not implemented yet: {CREATE_APP_IMPORT_ERROR}")
        return TestClient(create_app(db_path=self.db_path))


class FastApiTelegramWebChannelResourceTest(unittest.TestCase):
    def test_create_list_get_update_delete_channel_contract(self) -> None:
        fixture = TelegramWebChannelApiFixture()
        try:
            client = fixture.build_client()

            create_response = client.post(
                "/resources/telegram-web/channels",
                json={
                    "channel": " https://t.me/s/Movie_Channel/ ",
                    "display_name": "  Movies  ",
                    "enabled": False,
                    "poll_interval_seconds": 900,
                },
            )
            self.assertEqual(create_response.status_code, 201)
            created = create_response.json()
            self.assertEqual(created["channel"], "Movie_Channel")
            self.assertEqual(created["display_name"], "Movies")
            self.assertFalse(created["enabled"])
            self.assertEqual(created["poll_interval_seconds"], 900)
            self.assertIsInstance(created["created_at"], str)
            self.assertIsInstance(created["updated_at"], str)

            list_response = client.get("/resources/telegram-web/channels")
            self.assertEqual(list_response.status_code, 200)
            self.assertEqual(list_response.json()["items"], [created])

            get_response = client.get("/resources/telegram-web/channels/@Movie_Channel")
            self.assertEqual(get_response.status_code, 200)
            self.assertEqual(get_response.json(), created)

            update_response = client.patch(
                "/resources/telegram-web/channels/Movie_Channel",
                json={"display_name": "Cinema", "enabled": True, "poll_interval_seconds": 1200},
            )
            self.assertEqual(update_response.status_code, 200)
            updated = update_response.json()
            self.assertEqual(updated["channel"], "Movie_Channel")
            self.assertEqual(updated["display_name"], "Cinema")
            self.assertTrue(updated["enabled"])
            self.assertEqual(updated["poll_interval_seconds"], 1200)

            delete_response = client.delete("/resources/telegram-web/channels/Movie_Channel")
            self.assertEqual(delete_response.status_code, 200)
            self.assertEqual(delete_response.json(), {"deleted": True})
            self.assertEqual(client.get("/resources/telegram-web/channels/Movie_Channel").status_code, 404)
        finally:
            fixture.cleanup()

    def test_missing_channel_endpoints_return_404(self) -> None:
        fixture = TelegramWebChannelApiFixture()
        try:
            client = fixture.build_client()

            self.assertEqual(client.get("/resources/telegram-web/channels/missing").status_code, 404)
            self.assertEqual(
                client.patch("/resources/telegram-web/channels/missing", json={"enabled": True}).status_code,
                404,
            )
            self.assertEqual(client.delete("/resources/telegram-web/channels/missing").status_code, 404)
            self.assertEqual(client.post("/resources/telegram-web/channels/missing/enable").status_code, 404)
            self.assertEqual(client.post("/resources/telegram-web/channels/missing/disable").status_code, 404)
            self.assertEqual(client.get("/resources/telegram-web/channels/missing/status").status_code, 404)
        finally:
            fixture.cleanup()

    def test_invalid_channel_payload_returns_422(self) -> None:
        fixture = TelegramWebChannelApiFixture()
        try:
            client = fixture.build_client()

            blank_response = client.post(
                "/resources/telegram-web/channels",
                json={"channel": "   ", "poll_interval_seconds": 900},
            )
            interval_response = client.post(
                "/resources/telegram-web/channels",
                json={"channel": "movies", "poll_interval_seconds": 0},
            )
            patch_interval_response = client.patch(
                "/resources/telegram-web/channels/movies",
                json={"poll_interval_seconds": 0},
            )

            self.assertEqual(blank_response.status_code, 422)
            self.assertEqual(interval_response.status_code, 422)
            self.assertEqual(patch_interval_response.status_code, 422)
        finally:
            fixture.cleanup()

    def test_enable_disable_channel_updates_enabled_flag(self) -> None:
        fixture = TelegramWebChannelApiFixture()
        try:
            client = fixture.build_client()
            create_response = client.post(
                "/resources/telegram-web/channels",
                json={"channel": "movies", "enabled": True, "poll_interval_seconds": 1800},
            )
            self.assertEqual(create_response.status_code, 201)

            disable_response = client.post("/resources/telegram-web/channels/movies/disable")
            self.assertEqual(disable_response.status_code, 200)
            self.assertFalse(disable_response.json()["enabled"])

            enable_response = client.post("/resources/telegram-web/channels/movies/enable")
            self.assertEqual(enable_response.status_code, 200)
            self.assertTrue(enable_response.json()["enabled"])
        finally:
            fixture.cleanup()

    def test_status_returns_unknown_without_cursor_and_seeded_cursor_contract(self) -> None:
        fixture = TelegramWebChannelApiFixture()
        try:
            client = fixture.build_client()
            create_response = client.post(
                "/resources/telegram-web/channels",
                json={"channel": "movies", "display_name": "Movies", "poll_interval_seconds": 1800},
            )
            self.assertEqual(create_response.status_code, 201)
            channel_payload = create_response.json()

            unknown_response = client.get("/resources/telegram-web/channels/movies/status")
            self.assertEqual(unknown_response.status_code, 200)
            self.assertEqual(
                unknown_response.json(),
                {"channel": channel_payload, "cursor": None, "status": "unknown", "error": None},
            )

            fixture.queue_repository.upsert_collector_cursor(
                source_type="telegram_web",
                source_id="movies",
                last_seen_message_id="222",
                last_poll_at="2026-05-28T10:00:00",
                last_status="success",
                last_error=None,
            )
            status_response = client.get("/resources/telegram-web/channels/movies/status")
            self.assertEqual(status_response.status_code, 200)
            self.assertEqual(
                status_response.json(),
                {"channel": channel_payload, "cursor": "222", "status": "success", "error": None},
            )
        finally:
            fixture.cleanup()


if __name__ == "__main__":
    unittest.main()
