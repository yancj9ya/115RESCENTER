from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.config.yaml_writer import update_yaml_values

_SAMPLE = """\
organize:
  # 媒体库根目录 CID
  media_library_root_cid: 100
  # 自动整理开关
  auto_organize: true
"""


class UpdateYamlValuesTest(unittest.TestCase):
    def test_updates_nested_value_and_preserves_comments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_dir = Path(tmp_dir)
            (config_dir / "organize.yml").write_text(_SAMPLE, encoding="utf-8")

            update_yaml_values(config_dir, "organize", {"organize.media_library_root_cid": 999})

            content = (config_dir / "organize.yml").read_text(encoding="utf-8")

        self.assertIn("media_library_root_cid: 999", content)
        self.assertIn("媒体库根目录 CID", content)
        self.assertIn("auto_organize: true", content)

    def test_creates_missing_nested_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_dir = Path(tmp_dir)
            (config_dir / "netdisk.yml").write_text("p115:\n  cookies: \"x\"\n", encoding="utf-8")

            update_yaml_values(config_dir, "netdisk", {"p115.transfer_cid": 42})

            content = (config_dir / "netdisk.yml").read_text(encoding="utf-8")

        self.assertIn("transfer_cid: 42", content)
        self.assertIn("cookies:", content)

    def test_missing_file_raises_file_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(FileNotFoundError):
                update_yaml_values(Path(tmp_dir), "missing", {"a.b": 1})


if __name__ == "__main__":
    unittest.main()
