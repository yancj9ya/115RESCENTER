from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.db import migrate
from src.runtime.repository import RuntimeControlRepository


class MigrationV2Tests(unittest.TestCase):
    def test_fresh_db_reaches_latest_version_with_trigger_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "queue.db"
            version = migrate(db_path)
            self.assertEqual(version, 4)

            repo = RuntimeControlRepository(db_path)
            repo.init_schema()
            self.assertEqual(repo.claim_pending_manual_triggers(), [])

    def test_enqueue_then_claim_marks_consumed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "queue.db"
            repo = RuntimeControlRepository(db_path)
            repo.init_schema()

            tid = repo.enqueue_manual_trigger(event_name="manual_collect", source="api")
            self.assertGreater(tid, 0)

            claimed = repo.claim_pending_manual_triggers()
            self.assertEqual(len(claimed), 1)
            self.assertEqual(claimed[0][1], "manual_collect")
            self.assertEqual(claimed[0][2], "api")

            # 二次认领应为空（已消费）
            self.assertEqual(repo.claim_pending_manual_triggers(), [])

    def test_claim_returns_in_id_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "queue.db"
            repo = RuntimeControlRepository(db_path)
            repo.init_schema()

            repo.enqueue_manual_trigger(event_name="manual_collect")
            repo.enqueue_manual_trigger(event_name="manual_transfer")
            repo.enqueue_manual_trigger(event_name="manual_organize")

            names = [name for _id, name, _source in repo.claim_pending_manual_triggers()]
            self.assertEqual(names, ["manual_collect", "manual_transfer", "manual_organize"])


if __name__ == "__main__":
    unittest.main()
