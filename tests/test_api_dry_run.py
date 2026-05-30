from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

try:
    from src.api.app import create_app
except ModuleNotFoundError as import_error:
    create_app = None
    CREATE_APP_IMPORT_ERROR = import_error
else:
    CREATE_APP_IMPORT_ERROR = None


class FastApiDryRunBackendTest(unittest.TestCase):
    def build_client(self) -> TestClient:
        if create_app is None:
            raise unittest.SkipTest(f"src.api.app.create_app is not implemented yet: {CREATE_APP_IMPORT_ERROR}")
        return TestClient(create_app())

    def test_dry_run_backend_returns_summary_for_matching_115_message(self) -> None:
        client = self.build_client()

        response = client.post(
            "/dry-run/backend",
            json={
                "messages": [
                    {
                        "source_type": "tg_web",
                        "source_id": "movie_channel",
                        "message_id": "101",
                        "message_text": "Movie night https://115.com/s/a1?password=r1",
                        "published_at": "2026-05-26T10:00:00",
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "collect_enqueued": 1,
                "collect_processed": 1,
                "transfer_processed": 1,
                "organize_scanned": 0,
                "organize_planned": 0,
                "organize_moved": 0,
                "notification_count": 2,
                "errors": [],
            },
        )
        self.assertNotIn("P115_COOKIES", response.text)
        self.assertNotIn("TMDB_BEARER_TOKEN", response.text)

    def test_dry_run_backend_skips_nonmatching_or_shareless_messages(self) -> None:
        client = self.build_client()

        response = client.post(
            "/dry-run/backend",
            json={
                "messages": [
                    {
                        "source_type": "tg_web",
                        "source_id": "movie_channel",
                        "message_id": "201",
                        "message_text": "Series update https://115.com/s/s1",
                    },
                    {
                        "source_type": "tg_web",
                        "source_id": "movie_channel",
                        "message_id": "202",
                        "message_text": "Movie but no share link here",
                    },
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "collect_enqueued": 1,
                "collect_processed": 1,
                "transfer_processed": 0,
                "organize_scanned": 0,
                "organize_planned": 0,
                "organize_moved": 0,
                "notification_count": 1,
                "errors": [],
            },
        )


if __name__ == "__main__":
    unittest.main()
