from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from src.queue import ShareLink, TransferRuleContext, TransferSourceMessage
from src.queue.repository import QueueRepository

try:
    from src.api.app import create_app
except ModuleNotFoundError as import_error:
    create_app = None
    CREATE_APP_IMPORT_ERROR = import_error
else:
    CREATE_APP_IMPORT_ERROR = None


class QueueApiTestFixture:
    def __init__(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._temp_dir.name)
        self.db_path = self.tmp_path / "queue.db"
        self.repo = QueueRepository(self.db_path)
        self.repo.init_schema()

        self.collect_pending = self.repo.enqueue_collected_message(
            source_type="telegram_web",
            source_id="movie_channel",
            message_id="101",
            message_url="https://t.me/s/movie_channel/101",
            message_text="Movie A https://115.com/s/a1",
            published_at="2026-05-26T10:00:00",
            shares=[ShareLink(share_code="a1", receive_code="r1", share_url="https://115.com/s/a1")],
        )
        self.collect_success = self.repo.enqueue_collected_message(
            source_type="telegram_web",
            source_id="movie_channel",
            message_id="102",
            message_url="https://t.me/s/movie_channel/102",
            message_text="Movie B https://115.com/s/b2",
            published_at="2026-05-26T10:01:00",
            shares=[ShareLink(share_code="b2", receive_code="", share_url="https://115.com/s/b2")],
        )
        self.collect_skipped = self.repo.enqueue_collected_message(
            source_type="telegram_web",
            source_id="movie_channel",
            message_id="103",
            message_url="https://t.me/s/movie_channel/103",
            message_text="Movie C https://115.com/s/c3",
            published_at="2026-05-26T10:02:00",
            shares=[ShareLink(share_code="c3", receive_code="", share_url="https://115.com/s/c3")],
        )
        self.collect_failed = self.repo.enqueue_collected_message(
            source_type="telegram_web",
            source_id="movie_channel",
            message_id="104",
            message_url="https://t.me/s/movie_channel/104",
            message_text="Movie D https://115.com/s/d4",
            published_at="2026-05-26T10:03:00",
            shares=[ShareLink(share_code="d4", receive_code="", share_url="https://115.com/s/d4")],
        )
        self.repo.mark_collect_success(self.collect_success.id)
        self.repo.mark_collect_skipped(self.collect_skipped.id)
        self.repo.mark_collect_failed(self.collect_failed.id, "collect boom")

        self.transfer_pending = self.repo.enqueue_transfer_task(
            share_code="share-pending",
            receive_code="pw1",
            share_url="https://115.com/s/share-pending?password=pw1",
            staging_cid=9001,
            matched_rule=TransferRuleContext(
                rule_id="rule-4k",
                rule_name="4K movies",
                matched_keywords=["4k"],
            ),
            source_message=TransferSourceMessage(
                collect_id=self.collect_pending.id,
                source_type="telegram_web",
                source_id="movie_channel",
                message_id=self.collect_pending.message_id,
                message_url=self.collect_pending.message_url or "",
                published_at=self.collect_pending.published_at,
            ),
        )
        self.transfer_success = self.repo.enqueue_transfer_task(
            share_code="share-success",
            receive_code="pw2",
            share_url="https://115.com/s/share-success?password=pw2",
            staging_cid=9002,
            matched_rule=TransferRuleContext(
                rule_id="rule-hdr",
                rule_name="HDR movies",
                matched_keywords=["hdr"],
            ),
            source_message=TransferSourceMessage(
                collect_id=self.collect_success.id,
                source_type="telegram_web",
                source_id="movie_channel",
                message_id=self.collect_success.message_id,
                message_url=self.collect_success.message_url or "",
                published_at=self.collect_success.published_at,
            ),
        )
        self.transfer_failed = self.repo.enqueue_transfer_task(
            share_code="share-failed",
            receive_code="",
            share_url="https://115.com/s/share-failed",
            staging_cid=9003,
            matched_rule=TransferRuleContext(
                rule_id="rule-cn",
                rule_name="CN movies",
                matched_keywords=["国语"],
            ),
            source_message=TransferSourceMessage(
                collect_id=self.collect_failed.id,
                source_type="telegram_web",
                source_id="movie_channel",
                message_id=self.collect_failed.message_id,
                message_url=self.collect_failed.message_url or "",
                published_at=self.collect_failed.published_at,
            ),
        )
        self.repo.mark_transfer_success(self.transfer_success.id)
        self.repo.mark_transfer_failed_or_retry(
            self.transfer_failed.id,
            "transfer boom",
            max_attempts=1,
        )

    def cleanup(self) -> None:
        self._temp_dir.cleanup()

    def build_client(self) -> TestClient:
        if create_app is None:
            raise unittest.SkipTest(
                f"src.api.app.create_app is not implemented yet: {CREATE_APP_IMPORT_ERROR}"
            )
        return TestClient(create_app(db_path=self.db_path))


class QueueApiTestFixtureTest(unittest.TestCase):
    def test_fixture_initializes_temp_sqlite_db_and_seeds_collect_rows(self) -> None:
        fixture = QueueApiTestFixture()
        try:
            self.assertTrue(fixture.db_path.exists())
            self.assertEqual(fixture.db_path.parent, fixture.tmp_path)

            rows = fixture.repo.list_collect_queue()
            self.assertEqual([row.id for row in rows], [4, 3, 2, 1])
            self.assertEqual([row.status for row in rows], ["FAILED", "SKIPPED", "SUCCESS", "PENDING"])
            self.assertEqual(rows[-1].shares_json[0].share_code, "a1")
        finally:
            fixture.cleanup()

    def test_fixture_seeds_transfer_rows_with_deterministic_statuses(self) -> None:
        fixture = QueueApiTestFixture()
        try:
            rows = fixture.repo.list_transfer_queue()
            self.assertEqual([row.id for row in rows], [3, 2, 1])
            self.assertEqual([row.status for row in rows], ["FAILED", "SUCCESS", "PENDING"])
            self.assertEqual(rows[0].attempt_count, 1)
            self.assertEqual(rows[0].last_error, "transfer boom")
            self.assertEqual(rows[-1].matched_rules_json[0].rule_id, "rule-4k")
            self.assertEqual(rows[-1].source_messages_json[0].collect_id, fixture.collect_pending.id)
        finally:
            fixture.cleanup()

    def test_cleanup_removes_temporary_directory(self) -> None:
        fixture = QueueApiTestFixture()
        tmp_path = fixture.tmp_path
        fixture.cleanup()

        self.assertFalse(tmp_path.exists())


class FastApiHealthTest(unittest.TestCase):
    def test_health_returns_exact_ok_json(self) -> None:
        if create_app is None:
            self.skipTest(f"src.api.app.create_app is not implemented yet: {CREATE_APP_IMPORT_ERROR}")

        client = TestClient(create_app())
        response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_app_factory_stores_injected_db_path(self) -> None:
        if create_app is None:
            self.skipTest(f"src.api.app.create_app is not implemented yet: {CREATE_APP_IMPORT_ERROR}")

        fixture = QueueApiTestFixture()
        try:
            api_app = create_app(db_path=fixture.db_path)
            self.assertEqual(api_app.state.db_path, fixture.db_path)
        finally:
            fixture.cleanup()


class QueueApiClientFactoryTest(unittest.TestCase):
    def test_build_client_uses_create_app_with_temp_db_path(self) -> None:
        fixture = QueueApiTestFixture()
        try:
            if create_app is None:
                with self.assertRaises(unittest.SkipTest) as context:
                    fixture.build_client()
                self.assertIn("create_app is not implemented yet", str(context.exception))
                return

            client = fixture.build_client()
            self.assertIsInstance(client, TestClient)
        finally:
            fixture.cleanup()


class FastApiQueueStatusTest(unittest.TestCase):
    def _snapshot_queue_rows(self, repo: QueueRepository) -> dict[str, list[tuple[int, str, int, str | None, str]]]:
        return {
            "collect_queue": [
                (row.id, row.status, row.attempt_count, row.last_error, row.updated_at)
                for row in repo.list_collect_queue()
            ],
            "transfer_queue": [
                (row.id, row.status, row.attempt_count, row.last_error, row.updated_at)
                for row in repo.list_transfer_queue()
            ],
        }

    def test_queue_status_returns_seeded_counts(self) -> None:
        fixture = QueueApiTestFixture()
        try:
            client = fixture.build_client()
            response = client.get("/queues/status")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json(),
                {
                    "collect_queue": {
                        "PENDING": 1,
                        "RUNNING": 0,
                        "SUCCESS": 1,
                        "SKIPPED": 1,
                        "FAILED": 1,
                    },
                    "transfer_queue": {
                        "PENDING": 1,
                        "RUNNING": 0,
                        "SUCCESS": 1,
                        "FAILED": 1,
                    },
                },
            )
        finally:
            fixture.cleanup()

    def test_queue_status_returns_zero_defaults_for_empty_db(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        try:
            db_path = Path(temp_dir.name) / "queue.db"
            repo = QueueRepository(db_path)
            repo.init_schema()
            client = TestClient(create_app(db_path=db_path))

            response = client.get("/queues/status")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json(),
                {
                    "collect_queue": {
                        "PENDING": 0,
                        "RUNNING": 0,
                        "SUCCESS": 0,
                        "SKIPPED": 0,
                        "FAILED": 0,
                    },
                    "transfer_queue": {
                        "PENDING": 0,
                        "RUNNING": 0,
                        "SUCCESS": 0,
                        "FAILED": 0,
                    },
                },
            )
        finally:
            temp_dir.cleanup()

    def test_queue_status_is_read_only_for_queue_rows(self) -> None:
        fixture = QueueApiTestFixture()
        try:
            client = fixture.build_client()
            before_snapshot = self._snapshot_queue_rows(fixture.repo)

            response = client.get("/queues/status")

            self.assertEqual(response.status_code, 200)
            after_snapshot = self._snapshot_queue_rows(fixture.repo)
            self.assertEqual(after_snapshot, before_snapshot)
        finally:
            fixture.cleanup()


class FastApiCollectListTest(unittest.TestCase):
    def _snapshot_collect_rows(self, repo: QueueRepository) -> list[tuple[int, str, int, str | None, str]]:
        return [(row.id, row.status, row.attempt_count, row.last_error, row.updated_at) for row in repo.list_collect_queue()]

    def test_collect_items_return_id_desc_order_and_share_payload(self) -> None:
        fixture = QueueApiTestFixture()
        try:
            response = fixture.build_client().get("/queues/collect/items")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["queue_name"], "collect")
            self.assertEqual([item["id"] for item in payload["items"]], [4, 3, 2, 1])
            self.assertEqual(payload["items"][0]["last_error"], "collect boom")
            self.assertEqual(
                payload["items"][-1]["shares"],
                [{"share_code": "a1", "receive_code": "r1", "share_url": "https://115.com/s/a1"}],
            )
        finally:
            fixture.cleanup()

    def test_collect_items_filter_by_status(self) -> None:
        fixture = QueueApiTestFixture()
        try:
            response = fixture.build_client().get("/queues/collect/items", params={"status": "SUCCESS"})

            self.assertEqual(response.status_code, 200)
            items = response.json()["items"]
            self.assertEqual([item["id"] for item in items], [fixture.collect_success.id])
            self.assertEqual([item["status"] for item in items], ["SUCCESS"])
        finally:
            fixture.cleanup()

    def test_collect_items_limit_one(self) -> None:
        fixture = QueueApiTestFixture()
        try:
            response = fixture.build_client().get("/queues/collect/items", params={"limit": 1})

            self.assertEqual(response.status_code, 200)
            self.assertEqual([item["id"] for item in response.json()["items"]], [fixture.collect_failed.id])
        finally:
            fixture.cleanup()

    def test_collect_items_invalid_status_returns_422(self) -> None:
        fixture = QueueApiTestFixture()
        try:
            response = fixture.build_client().get("/queues/collect/items", params={"status": "DONE"})

            self.assertEqual(response.status_code, 422)
        finally:
            fixture.cleanup()

    def test_collect_items_invalid_limit_returns_422(self) -> None:
        fixture = QueueApiTestFixture()
        try:
            client = fixture.build_client()
            self.assertEqual(client.get("/queues/collect/items", params={"limit": 0}).status_code, 422)
            self.assertEqual(client.get("/queues/collect/items", params={"limit": 201}).status_code, 422)
        finally:
            fixture.cleanup()

    def test_collect_items_invalid_queue_returns_404(self) -> None:
        fixture = QueueApiTestFixture()
        try:
            response = fixture.build_client().get("/queues/unknown/items")

            self.assertEqual(response.status_code, 404)
        finally:
            fixture.cleanup()

    def test_collect_items_is_read_only(self) -> None:
        fixture = QueueApiTestFixture()
        try:
            before_snapshot = self._snapshot_collect_rows(fixture.repo)

            response = fixture.build_client().get("/queues/collect/items")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(self._snapshot_collect_rows(fixture.repo), before_snapshot)
        finally:
            fixture.cleanup()


class FastApiTransferListTest(unittest.TestCase):
    def test_transfer_items_return_id_desc_order_and_context_payloads(self) -> None:
        fixture = QueueApiTestFixture()
        try:
            response = fixture.build_client().get("/queues/transfer/items")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["queue_name"], "transfer")
            self.assertEqual([item["id"] for item in payload["items"]], [3, 2, 1])
            self.assertEqual(payload["items"][0]["matched_contexts"][0]["rule_id"], "rule-cn")
            self.assertEqual(payload["items"][0]["matched_contexts"][0]["matched_keywords"], ["国语"])
            self.assertEqual(payload["items"][0]["source_messages"][0]["collect_id"], fixture.collect_failed.id)
            self.assertEqual(payload["items"][0]["last_error"], "transfer boom")
        finally:
            fixture.cleanup()

    def test_transfer_items_filter_by_status(self) -> None:
        fixture = QueueApiTestFixture()
        try:
            response = fixture.build_client().get("/queues/transfer/items", params={"status": "SUCCESS"})

            self.assertEqual(response.status_code, 200)
            items = response.json()["items"]
            self.assertEqual([item["id"] for item in items], [fixture.transfer_success.id])
            self.assertEqual([item["status"] for item in items], ["SUCCESS"])
        finally:
            fixture.cleanup()

    def test_transfer_items_limit_one(self) -> None:
        fixture = QueueApiTestFixture()
        try:
            response = fixture.build_client().get("/queues/transfer/items", params={"limit": 1})

            self.assertEqual(response.status_code, 200)
            self.assertEqual([item["id"] for item in response.json()["items"]], [fixture.transfer_failed.id])
        finally:
            fixture.cleanup()

    def test_transfer_items_invalid_status_returns_422(self) -> None:
        fixture = QueueApiTestFixture()
        try:
            response = fixture.build_client().get("/queues/transfer/items", params={"status": "SKIPPED"})

            self.assertEqual(response.status_code, 422)
        finally:
            fixture.cleanup()

    def test_transfer_items_invalid_limit_returns_422(self) -> None:
        fixture = QueueApiTestFixture()
        try:
            client = fixture.build_client()
            self.assertEqual(client.get("/queues/transfer/items", params={"limit": 0}).status_code, 422)
            self.assertEqual(client.get("/queues/transfer/items", params={"limit": 201}).status_code, 422)
        finally:
            fixture.cleanup()

    def test_transfer_items_invalid_queue_returns_404(self) -> None:
        fixture = QueueApiTestFixture()
        try:
            response = fixture.build_client().get("/queues/nope/items")

            self.assertEqual(response.status_code, 404)
        finally:
            fixture.cleanup()
