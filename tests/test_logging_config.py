from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.logging_config import parse_log_lines, read_log_entries

_SAMPLE = """\
2026-05-30 01:25:26 [INFO] src.processors.subscription_processor [subscription_processor.process:41] - 开始订阅处理: limit=100
2026-05-30 01:25:26 [WARNING] src.processors.transfer_queue [transfer_queue.process_next_transfer:50] - 转存任务失败 (尝试 1/3): network unavailable
2026-05-30 01:25:27 [ERROR] src.processors.transfer_queue [transfer_queue.process_next_transfer:48] - 转存任务失败: bad share
Traceback (most recent call last):
  File "x.py", line 39, in process_next_transfer
ValueError: bad share
2026-05-30 01:25:28 [DEBUG] src.processors.organize_run [organize_run.run_once:94] - 跳过目录: Movie (2021)
"""


class ParseLogLinesTest(unittest.TestCase):
    def test_parses_structured_fields(self) -> None:
        entries = parse_log_lines(_SAMPLE.splitlines())

        self.assertEqual(len(entries), 4)
        first = entries[0]
        self.assertEqual(first["timestamp"], "2026-05-30 01:25:26")
        self.assertEqual(first["level"], "INFO")
        self.assertEqual(first["logger"], "src.processors.subscription_processor")
        self.assertEqual(first["module"], "subscription_processor")
        self.assertEqual(first["function"], "process")
        self.assertEqual(first["line"], 41)
        self.assertEqual(first["message"], "开始订阅处理: limit=100")

    def test_traceback_lines_merge_into_previous_entry(self) -> None:
        entries = parse_log_lines(_SAMPLE.splitlines())

        error_entry = entries[2]
        self.assertEqual(error_entry["level"], "ERROR")
        self.assertIn("Traceback (most recent call last):", error_entry["message"])
        self.assertIn("ValueError: bad share", error_entry["message"])

    def test_leading_orphan_lines_are_dropped(self) -> None:
        entries = parse_log_lines(["orphan continuation with no header"])
        self.assertEqual(entries, [])

    def test_preserves_chronological_order(self) -> None:
        entries = parse_log_lines(_SAMPLE.splitlines())
        levels = [entry["level"] for entry in entries]
        self.assertEqual(levels, ["INFO", "WARNING", "ERROR", "DEBUG"])


class ReadLogEntriesTest(unittest.TestCase):
    def test_returns_empty_list_when_file_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing = Path(tmp_dir) / "nope.log"
            self.assertEqual(read_log_entries(missing), [])

    def test_reads_and_parses_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = Path(tmp_dir) / "app.log"
            log_file.write_text(_SAMPLE, encoding="utf-8")
            entries = read_log_entries(log_file)

        self.assertEqual(len(entries), 4)
        self.assertEqual(entries[-1]["function"], "run_once")


if __name__ == "__main__":
    unittest.main()
