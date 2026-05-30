from __future__ import annotations

import importlib
import inspect
import tempfile
import unittest
from dataclasses import fields, is_dataclass
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from src.collectors import CollectedShare
from src.notifications import InMemoryNotifier, ORGANIZE_SUCCESS, TRANSFER_FAILED, TRANSFER_SUCCESS
from src.organizing.models import MEDIA_KIND_MOVIE, OrganizeMetadata, OrganizeRule
from src.processors.fakes import FakeMetadataResolver, FakeOrganizeStorage, FakeTransferStorage
from src.queue import FAILED, SUCCESS
from src.queue.repository import QueueRepository
from src.subscriptions.matcher import SubscriptionMatcher, SubscriptionRule


class DryRunBackendServiceTestCase(unittest.TestCase):
    def make_repo(self, tmp_dir: str) -> QueueRepository:
        repo = QueueRepository(Path(tmp_dir) / "queue.db")
        repo.init_schema()
        return repo

    def make_matcher(self) -> SubscriptionMatcher:
        return SubscriptionMatcher(
            [
                SubscriptionRule(
                    id="movie",
                    name="Movie",
                    pattern="movie",
                )
            ]
        )

    def make_share(
        self,
        *,
        share_code: str = "a1",
        message_id: str = "101",
        message_text: str = "movie release https://115.com/s/a1",
    ) -> CollectedShare:
        return CollectedShare(
            share_code=share_code,
            receive_code="r1",
            share_url=f"https://115.com/s/{share_code}",
            source_type="telegram_web",
            source_id="movie_channel",
            message_id=message_id,
            message_text=message_text,
            published_at=datetime(2026, 5, 26, 10, 0, 0),
        )


class DryRunBackendContractTest(DryRunBackendServiceTestCase):
    def test_summary_dataclass_contract(self) -> None:
        from src.processors.dry_run_backend import DryRunBackendSummary

        self.assertTrue(is_dataclass(DryRunBackendSummary))
        self.assertEqual(
            [field.name for field in fields(DryRunBackendSummary)],
            [
                "collect_enqueued",
                "collect_processed",
                "transfer_processed",
                "organize_scanned",
                "organize_planned",
                "organize_moved",
                "notification_count",
                "errors",
            ],
        )
        summary = DryRunBackendSummary(
            collect_enqueued=0,
            collect_processed=0,
            transfer_processed=0,
            organize_scanned=0,
            organize_planned=0,
            organize_moved=0,
            notification_count=0,
        )
        self.assertEqual(summary.errors, ())

    def test_processor_package_exports_backend_symbols(self) -> None:
        processors = importlib.import_module("src.processors")

        self.assertTrue(hasattr(processors, "DryRunBackendService"))
        self.assertTrue(hasattr(processors, "DryRunBackendSummary"))

    def test_module_has_no_forbidden_runtime_dependencies(self) -> None:
        import src.processors.dry_run_backend as dry_run_backend

        source = inspect.getsource(dry_run_backend)
        forbidden = [
            "Storage115Service",
            "p115",
            "httpx",
            "requests",
            "urllib.request",
            "telegram",
            "TmdbMovieResolver",
            "P115_COOKIES",
        ]
        for text in forbidden:
            self.assertNotIn(text, source)


class DryRunBackendBehaviorTest(DryRunBackendServiceTestCase):
    def test_run_collected_shares_orchestrates_collect_transfer_and_organize(self) -> None:
        from src.processors.dry_run_backend import DryRunBackendService

        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = self.make_repo(tmp_dir)
            notifier = InMemoryNotifier()
            transfer_storage = FakeTransferStorage()
            organize_storage = FakeOrganizeStorage(items=[{"id": 31, "name": "raw.mkv", "is_dir": False}])
            metadata_resolver = FakeMetadataResolver(
                {31: OrganizeMetadata(title="Title", year=2024, kind=MEDIA_KIND_MOVIE)}
            )
            service = DryRunBackendService(
                repository=repo,
                matcher=self.make_matcher(),
                transfer_storage=transfer_storage,
                organize_storage=organize_storage,
                metadata_resolver=metadata_resolver,
                organize_rule=OrganizeRule(media_library_root_cid=100),
                notifier=notifier,
                staging_cid=9001,
            )

            with patch("src.notifications.WebhookNotifier", side_effect=AssertionError("dry-run must not use webhook")) as webhook_notifier:
                summary = service.run_collected_shares([self.make_share()])

            self.assertFalse(webhook_notifier.called)
            self.assertIsInstance(notifier, InMemoryNotifier)
            self.assertEqual(summary.notification_count, len(notifier.events))

            self.assertEqual(summary.collect_enqueued, 1)
            self.assertEqual(summary.collect_processed, 1)
            self.assertEqual(summary.transfer_processed, 1)
            self.assertEqual(summary.organize_scanned, 1)
            self.assertEqual(summary.organize_planned, 1)
            self.assertEqual(summary.organize_moved, 1)
            self.assertEqual(summary.notification_count, 2)
            self.assertEqual(summary.errors, ())
            self.assertEqual(repo.get_collect_status_counts(), {SUCCESS: 1})
            self.assertEqual(repo.get_transfer_status_counts(), {SUCCESS: 1})
            self.assertEqual(len(transfer_storage.save_share_calls), 1)
            self.assertEqual(transfer_storage.save_share_calls[0].share_code, "a1")
            self.assertEqual(transfer_storage.save_share_calls[0].target_cid, 9001)
            self.assertEqual(organize_storage.list_folder_calls, [9001])
            self.assertEqual(len(organize_storage.move_file_calls), 1)
            self.assertEqual(
                [event.event_type for event in notifier.events],
                [TRANSFER_SUCCESS, ORGANIZE_SUCCESS],
            )

    def test_run_messages_accepts_dicts_and_reports_transfer_failures(self) -> None:
        from src.processors.dry_run_backend import DryRunBackendService

        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = self.make_repo(tmp_dir)
            notifier = InMemoryNotifier()
            transfer_storage = FakeTransferStorage(error=RuntimeError("save exploded"))
            organize_storage = FakeOrganizeStorage(items=[])
            metadata_resolver = FakeMetadataResolver({})
            service = DryRunBackendService(
                repository=repo,
                matcher=self.make_matcher(),
                transfer_storage=transfer_storage,
                organize_storage=organize_storage,
                metadata_resolver=metadata_resolver,
                organize_rule=OrganizeRule(media_library_root_cid=100),
                notifier=notifier,
                max_attempts=1,
                staging_cid=9001,
            )

            summary = service.run_messages(
                [
                    {
                        "share_code": "a1",
                        "receive_code": "r1",
                        "share_url": "https://115.com/s/a1",
                        "source_type": "telegram_web",
                        "source_id": "movie_channel",
                        "message_id": "101",
                        "message_text": "movie release https://115.com/s/a1",
                        "published_at": datetime(2026, 5, 26, 10, 0, 0),
                    }
                ]
            )

            self.assertEqual(summary.collect_enqueued, 1)
            self.assertEqual(summary.collect_processed, 1)
            self.assertEqual(summary.transfer_processed, 1)
            self.assertEqual(summary.organize_scanned, 0)
            self.assertEqual(summary.organize_planned, 0)
            self.assertEqual(summary.organize_moved, 0)
            self.assertEqual(summary.notification_count, 2)
            self.assertEqual(summary.errors, ("save exploded",))
            self.assertEqual(repo.get_collect_status_counts(), {SUCCESS: 1})
            self.assertEqual(repo.get_transfer_status_counts(), {FAILED: 1})
            transfer_record = repo.list_transfer_queue()[0]
            self.assertEqual(transfer_record.status, FAILED)
            self.assertEqual(transfer_record.last_error, "save exploded")
            self.assertEqual([event.event_type for event in notifier.events], [TRANSFER_FAILED, ORGANIZE_SUCCESS])


if __name__ == "__main__":
    unittest.main()
