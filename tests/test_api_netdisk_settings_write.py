from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from src.config.settings import AppSettings

try:
    from src.api.app import create_app
except ModuleNotFoundError as import_error:
    create_app = None
    CREATE_APP_IMPORT_ERROR = import_error
else:
    CREATE_APP_IMPORT_ERROR = None

_NETDISK_YML = """\
p115:
  # 115 网盘 Cookie
  cookies: "old-secret"
  ensure_cookies: false
  cache_home: ".p115client.cache.d"
  transfer_cid: 100
"""

_ORGANIZE_YML = """\
organize:
  # 媒体库根目录
  media_library_root_cid: 555
"""


def _seed_config(config_dir: Path) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "netdisk.yml").write_text(_NETDISK_YML, encoding="utf-8")
    (config_dir / "organize.yml").write_text(_ORGANIZE_YML, encoding="utf-8")


class NetdiskSettingsWriteApiTest(unittest.TestCase):
    def build_client(self, db_path: Path, config_dir: Path) -> TestClient:
        if create_app is None:
            raise unittest.SkipTest(f"src.api.app.create_app is not implemented yet: {CREATE_APP_IMPORT_ERROR}")
        api_app = create_app(db_path=db_path, settings=AppSettings())
        api_app.state.config_dir = config_dir
        return TestClient(api_app)

    def test_patch_settings_updates_netdisk_yaml_and_returns_safe_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_dir = root / "config"
            _seed_config(config_dir)
            response = self.build_client(root / "api.db", config_dir).patch(
                "/netdisk/settings",
                json={
                    "transfer_cid": 9001,
                    "ensure_cookies": True,
                    "cache_home": ".cache/p115",
                    "cookies": "new-secret-cookie",
                },
            )
            content = (config_dir / "netdisk.yml").read_text(encoding="utf-8")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["configured"])
        self.assertEqual(payload["transfer_cid"], "9001")
        self.assertTrue(payload["ensure_cookies"])
        self.assertTrue(payload["cache_home_configured"])
        self.assertNotIn("new-secret-cookie", response.text)
        self.assertIn("transfer_cid: 9001", content)
        self.assertIn("ensure_cookies: true", content)
        self.assertIn(".cache/p115", content)
        self.assertIn("new-secret-cookie", content)
        # 注释保留
        self.assertIn("115 网盘 Cookie", content)

    def test_patch_settings_does_not_overwrite_cookies_when_omitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_dir = root / "config"
            _seed_config(config_dir)
            response = self.build_client(root / "api.db", config_dir).patch(
                "/netdisk/settings",
                json={"transfer_cid": 42},
            )
            content = (config_dir / "netdisk.yml").read_text(encoding="utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("old-secret", content)
        self.assertNotIn("old-secret", response.text)
        self.assertIn("transfer_cid: 42", content)

    def test_patch_settings_rejects_invalid_transfer_cid_and_blank_cookies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_dir = root / "config"
            _seed_config(config_dir)
            client = self.build_client(root / "api.db", config_dir)
            invalid_cid = client.patch("/netdisk/settings", json={"transfer_cid": -1})
            blank_cookies = client.patch("/netdisk/settings", json={"cookies": "   "})

        self.assertEqual(invalid_cid.status_code, 422)
        self.assertEqual(blank_cookies.status_code, 422)

    def test_patch_settings_returns_503_when_config_file_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            if create_app is None:
                self.skipTest(f"src.api.app.create_app is not implemented yet: {CREATE_APP_IMPORT_ERROR}")
            root = Path(tmp_dir)
            config_dir = root / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            # 不写 netdisk.yml
            client = self.build_client(root / "api.db", config_dir)
            response = client.patch("/netdisk/settings", json={"transfer_cid": 1})

        self.assertEqual(response.status_code, 503)

    def test_patch_organizer_settings_updates_organize_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_dir = root / "config"
            _seed_config(config_dir)
            response = self.build_client(root / "api.db", config_dir).patch(
                "/organizer/settings",
                json={"media_library_root_cid": 7777},
            )
            content = (config_dir / "organize.yml").read_text(encoding="utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["media_library_root_cid"], "7777")
        self.assertIn("media_library_root_cid: 7777", content)
        # 注释保留
        self.assertIn("媒体库根目录", content)


if __name__ == "__main__":
    unittest.main()
