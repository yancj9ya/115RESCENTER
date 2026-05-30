from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path


class FakeStorage:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def save_share(self, *args: object, **kwargs: object) -> dict:
        self.calls.append((args, kwargs))
        if self.error is not None:
            raise self.error
        return {"state": True}


class TransferQueueProcessorTest(unittest.TestCase):
    def test_no_pending_transfer_returns_unclaimed_and_does_not_call_storage(self) -> None:
        from src.processors.transfer_queue import TransferQueueProcessor
        from src.queue.repository import QueueRepository

        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = QueueRepository(Path(tmp_dir) / "queue.db")
            repo.init_schema()
            storage = FakeStorage()

            result = TransferQueueProcessor(repo, storage).process_next_transfer()

            self.assertFalse(result.claimed)
            self.assertIsNone(result.transfer_id)
            self.assertIsNone(result.status)
            self.assertIsNone(result.error)
            self.assertEqual(storage.calls, [])

    def test_success_calls_storage_with_staging_cid_as_target_cid_and_marks_success(self) -> None:
        from src.processors.transfer_queue import TransferQueueProcessor
        from src.queue import SUCCESS
        from src.queue.repository import QueueRepository

        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = QueueRepository(Path(tmp_dir) / "queue.db")
            repo.init_schema()
            transfer = self._enqueue_transfer(repo, share_code="sw3abc1", receive_code="xy12", staging_cid=9001)
            storage = FakeStorage()

            result = TransferQueueProcessor(repo, storage).process_next_transfer()
            rows = repo.list_transfer_queue()

            self.assertTrue(result.claimed)
            self.assertEqual(result.transfer_id, transfer.id)
            self.assertEqual(result.status, SUCCESS)
            self.assertIsNone(result.error)
            self.assertEqual(storage.calls, [(('sw3abc1', 'xy12'), {'target_cid': 9001})])
            self.assertEqual(rows[0].status, SUCCESS)
            self.assertEqual(rows[0].attempt_count, 0)
            self.assertIsNone(rows[0].last_error)

    def test_failure_before_max_attempts_marks_retry_pending(self) -> None:
        from src.processors.transfer_queue import TransferQueueProcessor
        from src.queue import PENDING
        from src.queue.repository import QueueRepository

        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = QueueRepository(Path(tmp_dir) / "queue.db")
            repo.init_schema()
            transfer = self._enqueue_transfer(repo, share_code="retry1", receive_code="", staging_cid=7001)
            storage = FakeStorage(error=RuntimeError("network unavailable"))

            result = TransferQueueProcessor(repo, storage, max_attempts=3).process_next_transfer()
            rows = repo.list_transfer_queue()

            self.assertTrue(result.claimed)
            self.assertEqual(result.transfer_id, transfer.id)
            self.assertEqual(result.status, PENDING)
            self.assertEqual(result.error, "network unavailable")
            self.assertEqual(storage.calls, [(('retry1', ''), {'target_cid': 7001})])
            self.assertEqual(rows[0].status, PENDING)
            self.assertEqual(rows[0].attempt_count, 1)
            self.assertEqual(rows[0].last_error, "network unavailable")

    def test_failure_at_max_attempts_marks_failed(self) -> None:
        from src.processors.transfer_queue import TransferQueueProcessor
        from src.queue import FAILED
        from src.queue.repository import QueueRepository

        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = QueueRepository(Path(tmp_dir) / "queue.db")
            repo.init_schema()
            transfer = self._enqueue_transfer(repo, share_code="fail1", receive_code="pw", staging_cid=7002)
            storage = FakeStorage(error=ValueError("bad share"))

            result = TransferQueueProcessor(repo, storage, max_attempts=1).process_next_transfer()
            rows = repo.list_transfer_queue()

            self.assertTrue(result.claimed)
            self.assertEqual(result.transfer_id, transfer.id)
            self.assertEqual(result.status, FAILED)
            self.assertEqual(result.error, "bad share")
            self.assertEqual(storage.calls, [(('fail1', 'pw'), {'target_cid': 7002})])
            self.assertEqual(rows[0].status, FAILED)
            self.assertEqual(rows[0].attempt_count, 1)
            self.assertEqual(rows[0].last_error, "bad share")

    def test_processor_exports_import_without_storage115_side_effects(self) -> None:
        import src.processors as processors

        self.assertTrue(hasattr(processors, "TransferQueueProcessor"))
        self.assertTrue(hasattr(processors, "TransferQueueProcessResult"))

    def test_processor_module_has_no_forbidden_storage_dependencies(self) -> None:
        import src.processors.transfer_queue as transfer_queue

        source = inspect.getsource(transfer_queue)
        self.assertNotIn("Storage115Service", source)
        self.assertNotIn("p115", source.lower())
        self.assertNotIn("P115_COOKIES", source)
        self.assertNotIn("storage.service115", source)

    def _enqueue_transfer(self, repo, *, share_code: str, receive_code: str, staging_cid: int):
        from src.queue import TransferRuleContext, TransferSourceMessage

        return repo.enqueue_transfer_task(
            share_code=share_code,
            receive_code=receive_code,
            share_url=f"https://115.com/s/{share_code}",
            staging_cid=staging_cid,
            matched_rule=TransferRuleContext(rule_id="rule-1", rule_name="Movies", matched_keywords=["movie"]),
            source_message=TransferSourceMessage(
                collect_id=1,
                source_type="telegram_web",
                source_id="movie_channel",
                message_id="101",
                message_url="https://t.me/s/movie_channel/101",
                published_at=None,
            ),
        )


if __name__ == "__main__":
    unittest.main()
