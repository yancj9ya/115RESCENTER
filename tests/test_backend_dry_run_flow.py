from __future__ import annotations

import inspect
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.notifications import InMemoryNotifier, ORGANIZE_SUCCESS, TRANSFER_SUCCESS
from src.organizing.models import MEDIA_KIND_MOVIE, OrganizeMetadata, OrganizeRule
from src.processors.dry_run_backend import DryRunBackendService
from src.processors.fakes import FakeMetadataResolver, FakeOrganizeStorage, FakeTransferStorage
from src.queue import SUCCESS
from src.queue.repository import QueueRepository
from src.subscriptions.matcher import SubscriptionMatcher, SubscriptionRule

try:
    from src.api.app import create_app
except ModuleNotFoundError as import_error:
    create_app = None
    CREATE_APP_IMPORT_ERROR = import_error
else:
    CREATE_APP_IMPORT_ERROR = None


class BackendDryRunFlowTest(unittest.TestCase):
    def make_repo(self, tmp_dir: str) -> QueueRepository:
        repo = QueueRepository(Path(tmp_dir) / "queue.db")
        repo.init_schema()
        return repo

    def make_matcher(self) -> SubscriptionMatcher:
        return SubscriptionMatcher(
            [
                SubscriptionRule(
                    id="movie-rule",
                    name="Movie Rule",
                    pattern="movie",
                )
            ]
        )

    def make_service(self, repository: QueueRepository, notifier: InMemoryNotifier) -> DryRunBackendService:
        return DryRunBackendService(
            repository=repository,
            matcher=self.make_matcher(),
            transfer_storage=FakeTransferStorage(),
            organize_storage=FakeOrganizeStorage(
                items=[
                    {
                        "id": 31,
                        "name": "raw.release.2024.mkv",
                        "is_dir": False,
                    }
                ]
            ),
            metadata_resolver=FakeMetadataResolver(
                {
                    31: OrganizeMetadata(
                        title="Dry Run Movie",
                        year=2024,
                        kind=MEDIA_KIND_MOVIE,
                    )
                }
            ),
            organize_rule=OrganizeRule(media_library_root_cid=100),
            notifier=notifier,
            staging_cid=9001,
        )

    def build_client(self) -> TestClient:
        if create_app is None:
            raise unittest.SkipTest(f"src.api.app.create_app is not implemented yet: {CREATE_APP_IMPORT_ERROR}")
        return TestClient(create_app())

    def test_dry_run_backend_full_flow_keeps_no_credential_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repository = self.make_repo(tmp_dir)
            notifier = InMemoryNotifier()
            service = self.make_service(repository, notifier)

            summary = service.run_messages(
                [
                    {
                        "share_code": "a1",
                        "receive_code": "r1",
                        "share_url": "https://115.com/s/a1?password=r1",
                        "source_type": "tg_web",
                        "source_id": "movie_channel",
                        "message_id": "101",
                        "message_text": "movie release https://115.com/s/a1?password=r1",
                        "published_at": datetime(2026, 5, 26, 10, 0, 0),
                    }
                ]
            )

            self.assertEqual(summary.collect_enqueued, 1)
            self.assertEqual(summary.collect_processed, 1)
            self.assertEqual(summary.transfer_processed, 1)
            self.assertEqual(summary.organize_scanned, 1)
            self.assertEqual(summary.organize_planned, 1)
            self.assertEqual(summary.organize_moved, 1)
            self.assertEqual(summary.notification_count, 2)
            self.assertEqual(summary.errors, ())

            self.assertEqual(repository.get_collect_status_counts(), {SUCCESS: 1})
            self.assertEqual(repository.get_transfer_status_counts(), {SUCCESS: 1})

            collect_record = repository.list_collect_queue()[0]
            self.assertEqual(collect_record.status, SUCCESS)
            self.assertEqual(collect_record.message_url, "https://t.me/s/movie_channel/101")
            self.assertEqual(collect_record.shares_json[0].share_code, "a1")

            transfer_record = repository.list_transfer_queue()[0]
            self.assertEqual(transfer_record.status, SUCCESS)
            self.assertEqual(transfer_record.share_code, "a1")
            self.assertEqual(transfer_record.staging_cid, 9001)
            self.assertEqual(transfer_record.matched_rules_json[0].matched_keywords, ["movie"])
            self.assertEqual(transfer_record.source_messages_json[0].message_id, "101")

            event_types = [event.event_type for event in notifier.events]
            self.assertIn(TRANSFER_SUCCESS, event_types)
            self.assertIn(ORGANIZE_SUCCESS, event_types)
            self.assertEqual(event_types, [TRANSFER_SUCCESS, ORGANIZE_SUCCESS])

    def test_dry_run_backend_api_endpoint_exposes_summary_without_credentials(self) -> None:
        env_without_webhook = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("NOTIFICATION_WEBHOOK_")
        }
        with patch.dict(os.environ, env_without_webhook, clear=True):
            client = self.build_client()

            with patch(
                "src.notifications.WebhookNotifier",
                side_effect=AssertionError("dry-run endpoint must not use webhook"),
            ) as webhook_notifier:
                response = client.post(
                    "/dry-run/backend",
                    json={
                        "messages": [
                            {
                                "source_type": "tg_web",
                                "source_id": "movie_channel",
                                "message_id": "101",
                                "message_text": "Movie night https://115.com/s/a1?password=r1",
                                "published_at": "2026-05-26T10:00:00",
                            }
                        ]
                    },
                )

        self.assertFalse(webhook_notifier.called)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["collect_enqueued"], 1)
        self.assertEqual(payload["collect_processed"], 1)
        self.assertEqual(payload["transfer_processed"], 1)
        self.assertEqual(payload["notification_count"], 2)
        self.assertEqual(payload["errors"], [])
        self.assertNotIn("P115_COOKIES", response.text)
        self.assertNotIn("TMDB_BEARER_TOKEN", response.text)
        self.assertNotIn("NOTIFICATION_WEBHOOK_", response.text)

    def test_dry_run_backend_sources_stay_off_real_network_and_sdk_boundaries(self) -> None:
        import src.notifications as notifications
        import src.processors.dry_run_backend as dry_run_backend
        import src.processors.fakes as fakes

        source = "\n".join(
            [
                inspect.getsource(dry_run_backend),
                inspect.getsource(fakes),
                inspect.getsource(notifications),
            ]
        )
        forbidden = [
            "Storage115Service",
            "p115",
            "httpx",
            "requests",
            "urllib.request",
            "telegram",
            "TMDB_BEARER_TOKEN",
            "P115_COOKIES",
        ]
        for text in forbidden:
            with self.subTest(text=text):
                self.assertNotIn(text, source)


if __name__ == "__main__":
    unittest.main()
