from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

try:
    from src.api.app import create_app
except ModuleNotFoundError as import_error:
    create_app = None
    CREATE_APP_IMPORT_ERROR = import_error
else:
    CREATE_APP_IMPORT_ERROR = None


class FastApiTelegramCollectorContractTest(unittest.TestCase):
    def build_client(self, db_path: Path) -> TestClient:
        if create_app is None:
            raise unittest.SkipTest(f"src.api.app.create_app is not implemented yet: {CREATE_APP_IMPORT_ERROR}")
        return TestClient(create_app(db_path=db_path))

    def test_telegram_poll_returns_exact_summary_json_contract(self) -> None:
        html = '''
        <div class="tgme_widget_message" data-post="some_channel/101">
          <div class="tgme_widget_message_text js-message_text">
            Movie A https://115.com/s/abc123#xy9z
          </div>
        </div>
        <div class="tgme_widget_message" data-post="some_channel/102">
          <div class="tgme_widget_message_text js-message_text">
            Movie B https://115.com/s/def456#uv88
          </div>
        </div>
        '''
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "queue.db"
            client = self.build_client(db_path)
            response = client.post(
                "/collectors/telegram/some_channel/poll",
                json={"html": html},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "source_type": "telegram_web",
                "source_id": "some_channel",
                "scanned": 2,
                "parsed_shares": 2,
                "enqueued": 2,
                "skipped_existing": 0,
                "cursor": "102",
                "status": "success",
                "error": None,
            },
        )

    def test_telegram_status_returns_known_channel_cursor_status_error_contract(self) -> None:
        html = '''
        <div class="tgme_widget_message" data-post="some_channel/101">
          <div class="tgme_widget_message_text js-message_text">
            Movie A https://115.com/s/abc123#xy9z
          </div>
        </div>
        <div class="tgme_widget_message" data-post="some_channel/102">
          <div class="tgme_widget_message_text js-message_text">
            Movie B https://115.com/s/def456#uv88
          </div>
        </div>
        '''
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "queue.db"
            client = self.build_client(db_path)
            poll_response = client.post(
                "/collectors/telegram/some_channel/poll",
                json={"html": html},
            )
            response = client.get("/collectors/telegram/some_channel/status")

        self.assertEqual(poll_response.status_code, 200)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "source_type": "telegram_web",
                "source_id": "some_channel",
                "cursor": "102",
                "status": "success",
                "error": None,
            },
        )

    def test_telegram_status_returns_empty_contract_for_unknown_channel(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "queue.db"
            response = self.build_client(db_path).get("/collectors/telegram/unknown_channel/status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "source_type": "telegram_web",
                "source_id": "unknown_channel",
                "cursor": None,
                "status": "unknown",
                "error": None,
            },
        )


if __name__ == "__main__":
    unittest.main()
