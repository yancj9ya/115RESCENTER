from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.config.settings import AppSettings
from src.organizing import TmdbConfig
from src.storage import Storage115Config, Storage115Item


SECRET_COOKIES = "UID=secret-cookie; CID=another-secret"


class FakeStorage115Service:
    def __init__(self, items=None, error=None):
        self.items = items or []
        self.error = error

    def list_folder(self, cid=0):
        if self.error is not None:
            raise self.error
        return self.items


class _FakeProbeResponse:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code


class _RecordingProbe:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code
        self.urls: list[str] = []

    def __call__(self, url: str) -> _FakeProbeResponse:
        self.urls.append(url)
        return _FakeProbeResponse(self.status_code)


def _write_notification_yaml(config_dir: Path, *, telegram=None, bark=None) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "notification": {
            "providers": {
                "telegram": telegram or [],
                "bark": bark or [],
            },
            "routing": {},
        }
    }
    with open(config_dir / "notification.yml", "w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, allow_unicode=True)


class ConnectivityApiTest(unittest.TestCase):
    def _build(self, *, settings, config_dir=None, fake_service=None):
        tmp = tempfile.mkdtemp()
        app = create_app(db_path=Path(tmp) / "queue.db", settings=settings)
        if config_dir is not None:
            app.state.config_dir = config_dir
        if fake_service is not None:
            app.state.storage115_service = fake_service
        return TestClient(app)

    def test_unconfigured_reports_items_as_not_configured(self) -> None:
        client = self._build(settings=AppSettings())

        response = client.get("/health/connectivity")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("checked_at", body)
        kinds = {item["kind"]: item for item in body["items"]}
        self.assertIn("netdisk", kinds)
        self.assertIn("tmdb", kinds)
        self.assertFalse(kinds["netdisk"]["configured"])
        self.assertFalse(kinds["netdisk"]["ok"])
        self.assertFalse(kinds["tmdb"]["configured"])

    def test_netdisk_ok_reports_latency_and_no_secret_leak(self) -> None:
        settings = AppSettings(
            transfer_cid=9001,
            p115=Storage115Config(cookies=SECRET_COOKIES, ensure_cookies=True),
        )
        client = self._build(
            settings=settings,
            fake_service=FakeStorage115Service([Storage115Item(id=1, name="a", is_dir=True)]),
        )

        response = client.get("/health/connectivity")

        body = response.json()
        netdisk = next(i for i in body["items"] if i["kind"] == "netdisk")
        self.assertTrue(netdisk["configured"])
        self.assertTrue(netdisk["ok"])
        self.assertIsNotNone(netdisk["latency_ms"])
        self.assertGreaterEqual(netdisk["latency_ms"], 0)
        self.assertNotIn("secret-cookie", response.text)

    def test_netdisk_error_is_sanitized(self) -> None:
        settings = AppSettings(
            transfer_cid=9001,
            p115=Storage115Config(cookies=SECRET_COOKIES),
        )
        client = self._build(
            settings=settings,
            fake_service=FakeStorage115Service(
                error=RuntimeError(f"bad {SECRET_COOKIES}\nsecond line")
            ),
        )

        response = client.get("/health/connectivity")

        netdisk = next(i for i in response.json()["items"] if i["kind"] == "netdisk")
        self.assertTrue(netdisk["configured"])
        self.assertFalse(netdisk["ok"])
        self.assertNotIn("secret-cookie", response.text)
        self.assertNotIn("second line", response.text)

    def test_enabled_notification_providers_are_checked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_dir = Path(tmp_dir) / "config"
            _write_notification_yaml(
                config_dir,
                telegram=[
                    {"name": "tg_on", "enabled": True, "bot_token": "T", "chat_id": "9"},
                    {"name": "tg_off", "enabled": False, "bot_token": "T", "chat_id": "9"},
                ],
                bark=[{"name": "bk_on", "enabled": True, "device_key": "K", "server_url": "https://api.day.app"}],
            )
            client = self._build(settings=AppSettings(), config_dir=config_dir)
            probe = _RecordingProbe(status_code=200)
            client.app.state.connectivity_http_probe = probe

            response = client.get("/health/connectivity")

            body = response.json()
            names = {item["name"] for item in body["items"]}
            self.assertIn("tg_on", names)
            self.assertIn("bk_on", names)
            self.assertNotIn("tg_off", names)
            tg = next(i for i in body["items"] if i["name"] == "tg_on")
            self.assertTrue(tg["ok"])
            self.assertIsNotNone(tg["latency_ms"])
            # 探测使用 getMe / 服务可达检查，绝不发送消息
            self.assertTrue(any("getMe" in u for u in probe.urls))
            self.assertFalse(any("sendMessage" in u for u in probe.urls))


if __name__ == "__main__":
    unittest.main()
