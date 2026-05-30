from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.config.settings import AppSettings
from src.storage import Storage115Config, Storage115Item


SECRET_COOKIES = "UID=secret-cookie; CID=another-secret"
SECRET_CACHE_HOME = Path("C:/very/secret/cache/path")


class FakeStorage115Service:
    def __init__(self, items: list[Storage115Item] | None = None, error: Exception | None = None) -> None:
        self.items = items or []
        self.error = error
        self.called_cids: list[Any] = []

    def list_folder(self, cid: int | str = 0) -> list[Storage115Item]:
        self.called_cids.append(cid)
        if self.error is not None:
            raise self.error
        return self.items


class NetdiskApiTest(unittest.TestCase):
    def build_client(
        self,
        settings: AppSettings,
        *,
        fake_service: FakeStorage115Service | None = None,
    ) -> TestClient:
        with tempfile.TemporaryDirectory() as tmp_dir:
            app = create_app(db_path=Path(tmp_dir) / "queue.db", settings=settings)
        if fake_service is not None:
            app.state.storage115_service = fake_service
        return TestClient(app)

    def configured_settings(self) -> AppSettings:
        return AppSettings(
            transfer_cid=9001,
            p115=Storage115Config(
                cookies=SECRET_COOKIES,
                ensure_cookies=True,
                cache_home=SECRET_CACHE_HOME,
            ),
        )

    def assert_no_secret_leakage(self, payload: object) -> None:
        raw = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("P115_COOKIES", raw)
        self.assertNotIn("secret-cookie", raw)
        self.assertNotIn("another-secret", raw)
        self.assertNotIn(str(SECRET_CACHE_HOME), raw)
        self.assertNotIn("very/secret/cache", raw)

    def test_settings_returns_safe_config_summary_without_cookie_or_cache_path(self) -> None:
        response = self.build_client(self.configured_settings()).get("/netdisk/settings")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "configured": True,
                "transfer_cid": "9001",
                "ensure_cookies": True,
                "cache_home_configured": True,
                "status": "configured",
                "error": None,
            },
        )
        self.assert_no_secret_leakage(response.json())

    def test_status_returns_safe_config_summary_without_cookie_or_cache_path(self) -> None:
        response = self.build_client(self.configured_settings()).get("/netdisk/status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "configured")
        self.assertTrue(response.json()["configured"])
        self.assert_no_secret_leakage(response.json())

    def test_missing_config_returns_unconfigured_settings_and_status(self) -> None:
        client = self.build_client(AppSettings())

        settings_response = client.get("/netdisk/settings")
        status_response = client.get("/netdisk/status")

        self.assertEqual(settings_response.status_code, 200)
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(settings_response.json()["configured"], False)
        self.assertEqual(status_response.json()["configured"], False)
        self.assertEqual(settings_response.json()["status"], "not_configured")
        self.assertEqual(status_response.json()["status"], "not_configured")
        self.assert_no_secret_leakage(settings_response.json())
        self.assert_no_secret_leakage(status_response.json())

    def test_missing_config_returns_503_for_test_without_network(self) -> None:
        response = self.build_client(AppSettings()).post("/netdisk/test", json={})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "115 storage is not configured"})
        self.assert_no_secret_leakage(response.json())

    def test_test_endpoint_uses_fake_service_and_default_cid_without_network(self) -> None:
        fake_service = FakeStorage115Service(
            [
                Storage115Item(id=1, name="Movie", is_dir=True),
                Storage115Item(id=2, name="file.mkv", is_dir=False),
            ]
        )
        response = self.build_client(self.configured_settings(), fake_service=fake_service).post("/netdisk/test", json={})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "configured": True,
                "status": "ok",
                "ok": True,
                "item_count": 2,
                "error": None,
            },
        )
        self.assertEqual(fake_service.called_cids, [0])
        self.assert_no_secret_leakage(response.json())

    def test_test_endpoint_uses_requested_cid(self) -> None:
        fake_service = FakeStorage115Service([])
        response = self.build_client(self.configured_settings(), fake_service=fake_service).post(
            "/netdisk/test",
            json={"cid": 12345},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["item_count"], 0)
        self.assertEqual(fake_service.called_cids, [12345])
        self.assert_no_secret_leakage(response.json())

    def test_test_endpoint_sanitizes_first_error_line(self) -> None:
        fake_service = FakeStorage115Service(
            error=RuntimeError(f"bad cookies {SECRET_COOKIES} at {SECRET_CACHE_HOME}\nsecond line leaked")
        )
        response = self.build_client(self.configured_settings(), fake_service=fake_service).post("/netdisk/test", json={})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "error")
        self.assertFalse(response.json()["ok"])
        self.assertNotIn("second line", response.json()["error"])
        self.assertIn("[redacted]", response.json()["error"])
        self.assert_no_secret_leakage(response.json())


if __name__ == "__main__":
    unittest.main()
