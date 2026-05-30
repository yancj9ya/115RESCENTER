from __future__ import annotations

import importlib
import inspect
import tempfile
import unittest
from dataclasses import fields, is_dataclass
from pathlib import Path

from src.queue import FAILED, PENDING, SKIPPED, SUCCESS, ShareLink
from src.queue.repository import QueueRepository
from src.subscriptions.matcher import SubscriptionMatcher, SubscriptionRule


class CollectQueueProcessorTestCase(unittest.TestCase):
    def make_repo(self, tmp_dir: str) -> QueueRepository:
        repo = QueueRepository(Path(tmp_dir) / "queue.db")
        repo.init_schema()
        return repo

    def make_processor(self, repo: QueueRepository, rules: list[SubscriptionRule] | None = None):
        from src.processors.collect_queue import CollectQueueProcessor

        matcher = SubscriptionMatcher(rules or [SubscriptionRule(id="movie", name="Movie", pattern="movie")])
        return CollectQueueProcessor(repo, matcher, staging_cid=9001)

    def enqueue_message(
        self,
        repo: QueueRepository,
        *,
        message_id: str = "101",
        message_text: str = "movie release",
        share_url: str = "https://115.com/s/a1",
    ):
        return repo.enqueue_collected_message(
            source_type="telegram_web",
            source_id="movie_channel",
            message_id=message_id,
            message_url=f"https://t.me/s/movie_channel/{message_id}",
            message_text=message_text,
            published_at="2026-05-26T10:00:00",
            shares=[ShareLink(share_code=share_url.rsplit("/", 1)[-1], receive_code="r1", share_url=share_url)],
        )


class CollectQueueProcessorContractTest(CollectQueueProcessorTestCase):
    def test_result_dataclass_contract(self) -> None:
        from src.processors.collect_queue import CollectQueueProcessResult

        self.assertTrue(is_dataclass(CollectQueueProcessResult))
        self.assertEqual(
            [field.name for field in fields(CollectQueueProcessResult)],
            ["claimed", "collect_id", "status", "transfer_count", "error"],
        )
        result = CollectQueueProcessResult(claimed=False)
        self.assertFalse(result.claimed)
        self.assertIsNone(result.collect_id)
        self.assertIsNone(result.status)
        self.assertEqual(result.transfer_count, 0)
        self.assertIsNone(result.error)

    def test_processor_import_is_side_effect_free(self) -> None:
        module = importlib.import_module("src.processors.collect_queue")

        self.assertTrue(hasattr(module, "CollectQueueProcessor"))
        self.assertTrue(hasattr(module, "CollectQueueProcessResult"))

    def test_forbidden_runtime_dependencies_are_not_imported(self) -> None:
        import src.processors.collect_queue as collect_queue

        source = inspect.getsource(collect_queue)
        forbidden = [
            "Storage115Service",
            "save_share",
            "telegram_web",
            "parse_115_shares",
            "tmdb",
            "notification",
            "requests",
            "urllib.request",
            "threading",
            "asyncio",
        ]
        for text in forbidden:
            self.assertNotIn(text, source)


class CollectQueueProcessorBehaviorTest(CollectQueueProcessorTestCase):
    def test_empty_queue_returns_no_op_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = self.make_repo(tmp_dir)
            processor = self.make_processor(repo)

            result = processor.process_next_collect()

            self.assertFalse(result.claimed)
            self.assertIsNone(result.collect_id)
            self.assertIsNone(result.status)
            self.assertEqual(result.transfer_count, 0)
            self.assertEqual(repo.get_collect_status_counts(), {})
            self.assertEqual(repo.get_transfer_status_counts(), {})

    def test_success_enqueues_transfer_and_marks_collect_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = self.make_repo(tmp_dir)
            record = self.enqueue_message(repo)
            processor = self.make_processor(repo)

            result = processor.process_next_collect()

            self.assertTrue(result.claimed)
            self.assertEqual(result.collect_id, record.id)
            self.assertEqual(result.status, SUCCESS)
            self.assertEqual(result.transfer_count, 1)
            self.assertIsNone(result.error)
            collects = repo.list_collect_queue()
            transfers = repo.list_transfer_queue()
            self.assertEqual(collects[0].status, SUCCESS)
            self.assertEqual(len(transfers), 1)
            transfer = transfers[0]
            self.assertEqual(transfer.share_code, "a1")
            self.assertEqual(transfer.receive_code, "r1")
            self.assertEqual(transfer.share_url, "https://115.com/s/a1")
            self.assertEqual(transfer.staging_cid, 9001)
            self.assertEqual(transfer.status, PENDING)
            self.assertEqual(len(transfer.matched_rules_json), 1)
            self.assertEqual(transfer.matched_rules_json[0].rule_id, "movie")
            self.assertEqual(transfer.matched_rules_json[0].matched_keywords, ["movie"])
            self.assertEqual(len(transfer.source_messages_json), 1)
            source = transfer.source_messages_json[0]
            self.assertEqual(source.collect_id, record.id)
            self.assertEqual(source.source_type, "telegram_web")
            self.assertEqual(source.source_id, "movie_channel")
            self.assertEqual(source.message_id, "101")
            self.assertEqual(source.message_url, "https://t.me/s/movie_channel/101")
            self.assertEqual(source.published_at, "2026-05-26T10:00:00")

    def test_no_subscription_match_marks_collect_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = self.make_repo(tmp_dir)
            record = self.enqueue_message(repo, message_text="unrelated text")
            processor = self.make_processor(repo)

            result = processor.process_next_collect()

            self.assertTrue(result.claimed)
            self.assertEqual(result.collect_id, record.id)
            self.assertEqual(result.status, SKIPPED)
            self.assertEqual(result.transfer_count, 0)
            self.assertEqual(repo.list_collect_queue()[0].status, SKIPPED)
            self.assertEqual(repo.list_transfer_queue(), [])

    def test_matcher_exception_marks_collect_failed_with_error(self) -> None:
        class RaisingMatcher:
            def match_share(self, share):
                raise RuntimeError(f"matcher exploded for {share.share_code}")

        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = self.make_repo(tmp_dir)
            record = self.enqueue_message(repo)
            from src.processors.collect_queue import CollectQueueProcessor

            processor = CollectQueueProcessor(repo, RaisingMatcher(), staging_cid=9001)

            result = processor.process_next_collect()

            self.assertTrue(result.claimed)
            self.assertEqual(result.collect_id, record.id)
            self.assertEqual(result.status, FAILED)
            self.assertIn("matcher exploded", result.error or "")
            collect = repo.list_collect_queue()[0]
            self.assertEqual(collect.status, FAILED)
            self.assertIn("matcher exploded", collect.last_error or "")
            self.assertEqual(repo.list_transfer_queue(), [])

    def test_duplicate_transfer_merges_source_messages_across_collect_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = self.make_repo(tmp_dir)
            first = self.enqueue_message(repo, message_id="101", share_url="https://115.com/s/dup1")
            second = self.enqueue_message(repo, message_id="102", share_url="https://115.com/s/dup1")
            processor = self.make_processor(repo)

            first_result = processor.process_next_collect()
            second_result = processor.process_next_collect()

            self.assertEqual(first_result.status, SUCCESS)
            self.assertEqual(second_result.status, SUCCESS)
            self.assertEqual(first_result.transfer_count, 1)
            self.assertEqual(second_result.transfer_count, 1)
            transfers = repo.list_transfer_queue()
            self.assertEqual(len(transfers), 1)
            transfer = transfers[0]
            self.assertEqual(transfer.share_url, "https://115.com/s/dup1")
            self.assertEqual([source.collect_id for source in transfer.source_messages_json], [first.id, second.id])
            self.assertEqual([source.message_id for source in transfer.source_messages_json], ["101", "102"])
            self.assertEqual(len(transfer.matched_rules_json), 1)
            self.assertEqual(repo.get_collect_status_counts(), {SUCCESS: 2})


if __name__ == "__main__":
    unittest.main()
