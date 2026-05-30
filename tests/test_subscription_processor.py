from __future__ import annotations

import importlib
import inspect
import tempfile
import unittest
from dataclasses import fields, is_dataclass
from pathlib import Path

from src.queue import PENDING, SKIPPED, SUCCESS, ShareLink
from src.queue.repository import QueueRepository
from src.subscriptions.repository import SubscriptionRepository


class SubscriptionProcessorTestCase(unittest.TestCase):
    def make_repositories(self, tmp_dir: str) -> tuple[QueueRepository, SubscriptionRepository]:
        db_path = Path(tmp_dir) / "queue.db"
        queue_repository = QueueRepository(db_path)
        subscription_repository = SubscriptionRepository(db_path)
        queue_repository.init_schema()
        subscription_repository.init_schema()
        return queue_repository, subscription_repository

    def make_processor(
        self,
        queue_repository: QueueRepository,
        subscription_repository: SubscriptionRepository,
        staging_cid: int | None = 9001,
    ):
        from src.processors.subscription_processor import SubscriptionProcessor

        return SubscriptionProcessor(queue_repository, subscription_repository, staging_cid=staging_cid)

    def enqueue_message(
        self,
        repository: QueueRepository,
        *,
        message_id: str = "101",
        message_text: str = "Movie 1080P release",
        share_url: str = "https://115.com/s/a1",
    ):
        return repository.enqueue_collected_message(
            source_type="telegram_web",
            source_id="movie_channel",
            message_id=message_id,
            message_url=f"https://t.me/s/movie_channel/{message_id}",
            message_text=message_text,
            published_at="2026-05-26T10:00:00",
            shares=[ShareLink(share_code=share_url.rsplit("/", 1)[-1], receive_code="r1", share_url=share_url)],
        )


class SubscriptionProcessorContractTest(SubscriptionProcessorTestCase):
    def test_summary_dataclass_contract(self) -> None:
        from src.processors.subscription_processor import SubscriptionProcessSummary

        self.assertTrue(is_dataclass(SubscriptionProcessSummary))
        self.assertEqual(
            [field.name for field in fields(SubscriptionProcessSummary)],
            ["scanned", "matched", "created", "skipped", "errors"],
        )
        summary = SubscriptionProcessSummary()
        self.assertEqual(summary.scanned, 0)
        self.assertEqual(summary.matched, 0)
        self.assertEqual(summary.created, 0)
        self.assertEqual(summary.skipped, 0)
        self.assertEqual(summary.errors, [])

    def test_processor_import_is_side_effect_free(self) -> None:
        module = importlib.import_module("src.processors.subscription_processor")

        self.assertTrue(hasattr(module, "SubscriptionProcessor"))
        self.assertTrue(hasattr(module, "SubscriptionProcessSummary"))

    def test_forbidden_runtime_dependencies_are_not_imported(self) -> None:
        import src.processors.subscription_processor as subscription_processor

        source = inspect.getsource(subscription_processor)
        forbidden = [
            "Storage115Service",
            "P115Client",
            "save_share",
            "telegram_web",
            "parse_115_shares",
            "TmdbMovieResolver",
            "TmdbMultiResolver",
            "notification",
            "requests",
            "urllib.request",
            "threading",
            "asyncio",
        ]
        for text in forbidden:
            self.assertNotIn(text, source)


class SubscriptionProcessorBehaviorTest(SubscriptionProcessorTestCase):
    def test_matching_collect_item_enqueues_transfer_and_marks_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            queue_repository, subscription_repository = self.make_repositories(tmp_dir)
            record = self.enqueue_message(queue_repository)
            rule = subscription_repository.create_rule(name="Movies", pattern="1080p", enabled=True)
            processor = self.make_processor(queue_repository, subscription_repository)

            summary = processor.process()

            self.assertEqual(summary.scanned, 1)
            self.assertEqual(summary.matched, 1)
            self.assertEqual(summary.created, 1)
            self.assertEqual(summary.skipped, 0)
            self.assertEqual(summary.errors, [])
            self.assertEqual(queue_repository.list_collect_queue()[0].status, SUCCESS)
            transfers = queue_repository.list_transfer_queue()
            self.assertEqual(len(transfers), 1)
            transfer = transfers[0]
            self.assertEqual(transfer.share_code, "a1")
            self.assertEqual(transfer.receive_code, "r1")
            self.assertEqual(transfer.share_url, "https://115.com/s/a1")
            self.assertEqual(transfer.staging_cid, 9001)
            self.assertEqual(len(transfer.matched_rules_json), 1)
            self.assertEqual(transfer.matched_rules_json[0].rule_id, str(rule.id))
            self.assertEqual(transfer.matched_rules_json[0].rule_name, "Movies")
            self.assertEqual(transfer.matched_rules_json[0].matched_keywords, ["1080p"])
            self.assertEqual(len(transfer.source_messages_json), 1)
            source = transfer.source_messages_json[0]
            self.assertEqual(source.collect_id, record.id)
            self.assertEqual(source.source_type, "telegram_web")
            self.assertEqual(source.source_id, "movie_channel")
            self.assertEqual(source.message_id, "101")
            self.assertEqual(source.message_url, "https://t.me/s/movie_channel/101")
            self.assertEqual(source.published_at, "2026-05-26T10:00:00")

    def test_repeated_process_runs_create_no_duplicate_transfer_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            queue_repository, subscription_repository = self.make_repositories(tmp_dir)
            self.enqueue_message(queue_repository, message_id="101", share_url="https://115.com/s/dup1")
            self.enqueue_message(queue_repository, message_id="102", share_url="https://115.com/s/dup1")
            subscription_repository.create_rule(name="Movies", pattern="1080p", enabled=True)
            processor = self.make_processor(queue_repository, subscription_repository)

            first_summary = processor.process(limit=1)
            second_summary = processor.process(limit=100)
            third_summary = processor.process(limit=100)

            self.assertEqual(first_summary.created, 1)
            self.assertEqual(second_summary.scanned, 1)
            self.assertEqual(second_summary.matched, 1)
            self.assertEqual(second_summary.created, 0)
            self.assertEqual(third_summary.scanned, 0)
            transfers = queue_repository.list_transfer_queue()
            self.assertEqual(len(transfers), 1)
            self.assertEqual([source.message_id for source in transfers[0].source_messages_json], ["101", "102"])
            self.assertEqual(queue_repository.get_collect_status_counts(), {SUCCESS: 2})

    def test_disabled_rules_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            queue_repository, subscription_repository = self.make_repositories(tmp_dir)
            self.enqueue_message(queue_repository)
            subscription_repository.create_rule(name="Disabled", pattern="1080p", enabled=False)
            processor = self.make_processor(queue_repository, subscription_repository)

            summary = processor.process()

            self.assertEqual(summary.scanned, 1)
            self.assertEqual(summary.matched, 0)
            self.assertEqual(summary.created, 0)
            self.assertEqual(summary.skipped, 1)
            self.assertEqual(summary.errors, [])
            self.assertEqual(queue_repository.list_collect_queue()[0].status, SKIPPED)
            self.assertEqual(queue_repository.list_transfer_queue(), [])

    def test_no_enabled_rules_is_not_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            queue_repository, subscription_repository = self.make_repositories(tmp_dir)
            self.enqueue_message(queue_repository)
            processor = self.make_processor(queue_repository, subscription_repository)

            summary = processor.process()

            self.assertEqual(summary.scanned, 1)
            self.assertEqual(summary.matched, 0)
            self.assertEqual(summary.created, 0)
            self.assertEqual(summary.skipped, 1)
            self.assertEqual(summary.errors, [])
            self.assertEqual(queue_repository.list_collect_queue()[0].status, SKIPPED)
            self.assertEqual(queue_repository.list_transfer_queue(), [])

    def test_missing_staging_cid_fails_fast_without_claiming_or_enqueuing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            queue_repository, subscription_repository = self.make_repositories(tmp_dir)
            self.enqueue_message(queue_repository)
            subscription_repository.create_rule(name="Movies", pattern="1080p", enabled=True)
            processor = self.make_processor(queue_repository, subscription_repository, staging_cid=None)

            summary = processor.process()

            self.assertEqual(summary.scanned, 0)
            self.assertEqual(summary.matched, 0)
            self.assertEqual(summary.created, 0)
            self.assertEqual(summary.skipped, 0)
            self.assertEqual(len(summary.errors), 1)
            self.assertIn("P115_TRANSFER_CID", summary.errors[0])
            self.assertEqual(queue_repository.list_collect_queue()[0].status, PENDING)
            self.assertEqual(queue_repository.list_transfer_queue(), [])

    def test_limit_scans_at_most_eligible_collect_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            queue_repository, subscription_repository = self.make_repositories(tmp_dir)
            self.enqueue_message(queue_repository, message_id="101", share_url="https://115.com/s/a1")
            self.enqueue_message(queue_repository, message_id="102", share_url="https://115.com/s/a2")
            self.enqueue_message(queue_repository, message_id="103", share_url="https://115.com/s/a3")
            subscription_repository.create_rule(name="Movies", pattern="1080p", enabled=True)
            processor = self.make_processor(queue_repository, subscription_repository)

            summary = processor.process(limit=2)

            self.assertEqual(summary.scanned, 2)
            self.assertEqual(summary.matched, 2)
            self.assertEqual(summary.created, 2)
            self.assertEqual(summary.skipped, 0)
            self.assertEqual(summary.errors, [])
            self.assertEqual(queue_repository.get_collect_status_counts(), {PENDING: 1, SUCCESS: 2})
            self.assertEqual(len(queue_repository.list_transfer_queue()), 2)

    def test_record_exception_marks_collect_failed_and_adds_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            queue_repository, subscription_repository = self.make_repositories(tmp_dir)
            queue_repository.enqueue_collected_message(
                source_type="telegram_web",
                source_id="bad_channel",
                message_id="bad-regex",
                message_url="https://t.me/s/bad_channel/bad-regex",
                message_text="Movie 1080P release",
                published_at=None,
                shares=[ShareLink(share_code="bad", receive_code="", share_url="https://115.com/s/bad")],
            )
            subscription_repository.create_rule(name="Bad", pattern="[", enabled=True)
            processor = self.make_processor(queue_repository, subscription_repository)

            summary = processor.process()

            self.assertEqual(summary.scanned, 0)
            self.assertEqual(summary.matched, 0)
            self.assertEqual(summary.created, 0)
            self.assertEqual(summary.skipped, 0)
            self.assertEqual(len(summary.errors), 1)
            self.assertIn("invalid subscription pattern", summary.errors[0])
            self.assertEqual(queue_repository.list_collect_queue()[0].status, PENDING)
            self.assertEqual(queue_repository.list_transfer_queue(), [])


if __name__ == "__main__":
    unittest.main()
