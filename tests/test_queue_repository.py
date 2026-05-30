from __future__ import annotations

import sqlite3
import tempfile
import unittest
from dataclasses import fields, is_dataclass
from pathlib import Path


class QueueModelImportTest(unittest.TestCase):
    def test_queue_exports_are_available_without_side_effects(self) -> None:
        from src.queue import (  # noqa: PLC0415
            COLLECT_QUEUE_STATUSES,
            FAILED,
            PENDING,
            RUNNING,
            SKIPPED,
            SUCCESS,
            TRANSFER_FAILED,
            TRANSFER_PENDING,
            TRANSFER_QUEUE_STATUSES,
            TRANSFER_RUNNING,
            TRANSFER_SUCCESS,
            CollectQueueRecord,
            ShareLink,
            TransferQueueRecord,
            TransferRuleContext,
            TransferSourceMessage,
        )

        self.assertEqual(PENDING, "PENDING")
        self.assertEqual(RUNNING, "RUNNING")
        self.assertEqual(SUCCESS, "SUCCESS")
        self.assertEqual(SKIPPED, "SKIPPED")
        self.assertEqual(FAILED, "FAILED")
        self.assertEqual(TRANSFER_PENDING, "PENDING")
        self.assertEqual(TRANSFER_RUNNING, "RUNNING")
        self.assertEqual(TRANSFER_SUCCESS, "SUCCESS")
        self.assertEqual(TRANSFER_FAILED, "FAILED")
        self.assertEqual(COLLECT_QUEUE_STATUSES, ("PENDING", "RUNNING", "SUCCESS", "SKIPPED", "FAILED"))
        self.assertEqual(TRANSFER_QUEUE_STATUSES, ("PENDING", "RUNNING", "SUCCESS", "FAILED"))
        self.assertTrue(is_dataclass(CollectQueueRecord))
        self.assertTrue(is_dataclass(TransferQueueRecord))
        self.assertTrue(is_dataclass(TransferRuleContext))
        self.assertTrue(is_dataclass(TransferSourceMessage))
        self.assertTrue(is_dataclass(ShareLink))


class QueueModelContractTest(unittest.TestCase):
    def test_record_field_contracts_match_queue_plan(self) -> None:
        from src.queue import (  # noqa: PLC0415
            CollectQueueRecord,
            ShareLink,
            TransferQueueRecord,
            TransferRuleContext,
            TransferSourceMessage,
        )

        self.assertEqual(
            [field.name for field in fields(CollectQueueRecord)],
            [
                "id",
                "source_type",
                "source_id",
                "message_id",
                "message_url",
                "message_text",
                "published_at",
                "shares_json",
                "status",
                "attempt_count",
                "last_error",
                "created_at",
                "updated_at",
            ],
        )
        self.assertEqual(
            [field.name for field in fields(TransferQueueRecord)],
            [
                "id",
                "share_code",
                "receive_code",
                "share_url",
                "staging_cid",
                "matched_rules_json",
                "source_messages_json",
                "status",
                "attempt_count",
                "last_error",
                "created_at",
                "updated_at",
            ],
        )
        self.assertEqual([field.name for field in fields(TransferRuleContext)], ["rule_id", "rule_name", "matched_keywords"])
        self.assertEqual(
            [field.name for field in fields(TransferSourceMessage)],
            ["collect_id", "source_type", "source_id", "message_id", "message_url", "published_at"],
        )
        self.assertEqual([field.name for field in fields(ShareLink)], ["share_code", "receive_code", "share_url"])

        collect_record = CollectQueueRecord(
            id=1,
            source_type="telegram_web",
            source_id="channel-x",
            message_id="42",
            message_url="https://t.me/s/channel-x/42",
            message_text="sample message",
            published_at=None,
        )
        transfer_record = TransferQueueRecord(
            id=2,
            share_code="abc123",
            receive_code="",
            share_url="https://115.com/s/abc123",
            staging_cid=1001,
        )

        self.assertEqual(collect_record.status, "PENDING")
        self.assertEqual(transfer_record.status, "PENDING")
        self.assertEqual(collect_record.shares_json, [])
        self.assertEqual(transfer_record.matched_rules_json, [])
        self.assertEqual(transfer_record.source_messages_json, [])


class QueueRepositorySchemaTest(unittest.TestCase):
    def test_init_schema_creates_both_tables_and_is_idempotent(self) -> None:
        from src.queue.repository import QueueRepository

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "queue.db"
            repo = QueueRepository(db_path)
            repo.init_schema()
            repo.init_schema()

            connection = sqlite3.connect(db_path)
            try:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                    )
                }
                collect_schema = connection.execute(
                    "SELECT sql FROM sqlite_master WHERE name='collect_queue'"
                ).fetchone()[0]
                transfer_schema = connection.execute(
                    "SELECT sql FROM sqlite_master WHERE name='transfer_queue'"
                ).fetchone()[0]
                collect_index_names = {
                    row[1]
                    for row in connection.execute("PRAGMA index_list('collect_queue')")
                    if row[2]
                }
                transfer_index_names = {
                    row[1]
                    for row in connection.execute("PRAGMA index_list('transfer_queue')")
                    if row[2]
                }
            finally:
                connection.close()

            self.assertIn("collect_queue", tables)
            self.assertIn("transfer_queue", tables)
            self.assertIn("UNIQUE(source_type, source_id, message_id)", collect_schema)
            self.assertIn("UNIQUE(share_url, staging_cid)", transfer_schema)
            self.assertTrue(collect_index_names)
            self.assertTrue(transfer_index_names)


class QueueRepositoryCollectTest(unittest.TestCase):
    def test_rejects_collect_message_without_shares(self) -> None:
        from src.queue.repository import QueueRepository

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "queue.db"
            repo = QueueRepository(db_path)
            repo.init_schema()

            with self.assertRaises(ValueError):
                repo.enqueue_collected_message(
                    source_type="telegram_web",
                    source_id="movie_channel",
                    message_id="101",
                    message_url="https://t.me/s/movie_channel/101",
                    message_text="no links",
                    published_at=None,
                    shares=[],
                )

            connection = sqlite3.connect(db_path)
            try:
                count = connection.execute("SELECT COUNT(*) FROM collect_queue").fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(count, 0)

    def test_enqueue_claim_and_mark_collect_lifecycle(self) -> None:
        from src.queue import ShareLink
        from src.queue.repository import QueueRepository

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "queue.db"
            repo = QueueRepository(db_path)
            repo.init_schema()

            first = repo.enqueue_collected_message(
                source_type="telegram_web",
                source_id="movie_channel",
                message_id="101",
                message_url="https://t.me/s/movie_channel/101",
                message_text="movie one",
                published_at="2026-05-26T10:00:00",
                shares=[
                    ShareLink(share_code="a1", receive_code="r1", share_url="https://115.com/s/a1"),
                    ShareLink(share_code="b2", receive_code="", share_url="https://115.com/s/b2"),
                ],
            )
            second = repo.enqueue_collected_message(
                source_type="telegram_web",
                source_id="movie_channel",
                message_id="102",
                message_url="https://t.me/s/movie_channel/102",
                message_text="movie two",
                published_at="2026-05-26T10:01:00",
                shares=[ShareLink(share_code="c3", receive_code="", share_url="https://115.com/s/c3")],
            )
            duplicate = repo.enqueue_collected_message(
                source_type="telegram_web",
                source_id="movie_channel",
                message_id="101",
                message_url="https://t.me/s/movie_channel/101",
                message_text="movie one changed",
                published_at="2026-05-26T10:02:00",
                shares=[ShareLink(share_code="z9", receive_code="", share_url="https://115.com/s/z9")],
            )

            self.assertEqual(first.id, duplicate.id)
            self.assertEqual(first.shares_json[0].share_code, "a1")
            self.assertEqual(len(first.shares_json), 2)
            self.assertEqual(second.id, first.id + 1)

            claimed = repo.claim_next_collect()
            self.assertIsNotNone(claimed)
            assert claimed is not None
            self.assertEqual(claimed.id, first.id)
            self.assertEqual(claimed.status, "RUNNING")

            repo.mark_collect_success(claimed.id)
            repo.mark_collect_skipped(second.id)

            connection = sqlite3.connect(db_path)
            try:
                rows = {
                    row[0]: row
                    for row in connection.execute(
                        "SELECT id, status, last_error FROM collect_queue ORDER BY id"
                    )
                }
            finally:
                connection.close()

            self.assertEqual(rows[first.id][1], "SUCCESS")
            self.assertIsNone(rows[first.id][2])
            self.assertEqual(rows[second.id][1], "SKIPPED")
            self.assertIsNone(rows[second.id][2])

    def test_claim_oldest_pending_collect_and_mark_failed(self) -> None:
        from src.queue import ShareLink
        from src.queue.repository import QueueRepository

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "queue.db"
            repo = QueueRepository(db_path)
            repo.init_schema()

            first = repo.enqueue_collected_message(
                source_type="telegram_web",
                source_id="movie_channel",
                message_id="101",
                message_url="https://t.me/s/movie_channel/101",
                message_text="movie one",
                published_at=None,
                shares=[ShareLink(share_code="a1", receive_code="", share_url="https://115.com/s/a1")],
            )
            second = repo.enqueue_collected_message(
                source_type="telegram_web",
                source_id="movie_channel",
                message_id="102",
                message_url="https://t.me/s/movie_channel/102",
                message_text="movie two",
                published_at=None,
                shares=[ShareLink(share_code="b2", receive_code="", share_url="https://115.com/s/b2")],
            )

            claimed_one = repo.claim_next_collect()
            claimed_two = repo.claim_next_collect()
            claimed_three = repo.claim_next_collect()

            self.assertEqual(claimed_one.id, first.id)
            self.assertEqual(claimed_two.id, second.id)
            self.assertIsNone(claimed_three)

            repo.mark_collect_failed(first.id, "boom")
            connection = sqlite3.connect(db_path)
            try:
                row = connection.execute(
                    "SELECT status, last_error FROM collect_queue WHERE id = ?",
                    (first.id,),
                ).fetchone()
            finally:
                connection.close()
            self.assertEqual(row[0], "FAILED")
            self.assertEqual(row[1], "boom")


class QueueRepositoryTransferTest(unittest.TestCase):
    def test_enqueue_merges_duplicate_rule_and_source_contexts(self) -> None:
        from src.queue import TransferRuleContext, TransferSourceMessage
        from src.queue.repository import QueueRepository

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "queue.db"
            repo = QueueRepository(db_path)
            repo.init_schema()

            first = repo.enqueue_transfer_task(
                share_code="sw3abc1",
                receive_code="xy12",
                share_url="https://115.com/s/sw3abc1?password=xy12",
                staging_cid=9001,
                matched_rule=TransferRuleContext(rule_id="rule-4k", rule_name="4K movies", matched_keywords=["4k"]),
                source_message=TransferSourceMessage(
                    collect_id=1,
                    source_type="telegram_web",
                    source_id="movie_channel",
                    message_id="101",
                    message_url="https://t.me/s/movie_channel/101",
                    published_at="2026-05-26T10:00:00",
                ),
            )
            second = repo.enqueue_transfer_task(
                share_code="sw3abc1",
                receive_code="xy12",
                share_url="https://115.com/s/sw3abc1?password=xy12",
                staging_cid=9001,
                matched_rule=TransferRuleContext(rule_id="rule-4k", rule_name="4K movies", matched_keywords=["4k"]),
                source_message=TransferSourceMessage(
                    collect_id=1,
                    source_type="telegram_web",
                    source_id="movie_channel",
                    message_id="101",
                    message_url="https://t.me/s/movie_channel/101",
                    published_at="2026-05-26T10:00:00",
                ),
            )
            third = repo.enqueue_transfer_task(
                share_code="sw3abc1",
                receive_code="xy12",
                share_url="https://115.com/s/sw3abc1?password=xy12",
                staging_cid=9001,
                matched_rule=TransferRuleContext(rule_id="rule-hdr", rule_name="HDR movies", matched_keywords=["hdr"]),
                source_message=TransferSourceMessage(
                    collect_id=2,
                    source_type="telegram_web",
                    source_id="movie_channel",
                    message_id="102",
                    message_url="https://t.me/s/movie_channel/102",
                    published_at="2026-05-26T10:01:00",
                ),
            )

            self.assertEqual(first.id, second.id)
            self.assertEqual(first.id, third.id)
            self.assertEqual([ctx.rule_id for ctx in third.matched_rules_json], ["rule-4k", "rule-hdr"])
            self.assertEqual([msg.collect_id for msg in third.source_messages_json], [1, 2])
            self.assertEqual(len(third.matched_rules_json), 2)
            self.assertEqual(len(third.source_messages_json), 2)

            rows = repo.list_transfer_queue()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].id, first.id)
            self.assertEqual([ctx.rule_id for ctx in rows[0].matched_rules_json], ["rule-4k", "rule-hdr"])
            self.assertEqual([msg.message_id for msg in rows[0].source_messages_json], ["101", "102"])

            connection = sqlite3.connect(db_path)
            try:
                count = connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM transfer_queue
                    WHERE share_url = ? AND staging_cid = ?
                    """,
                    ("https://115.com/s/sw3abc1?password=xy12", 9001),
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(count, 1)

    def test_same_share_different_staging_creates_separate_rows(self) -> None:
        from src.queue import TransferRuleContext, TransferSourceMessage
        from src.queue.repository import QueueRepository

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "queue.db"
            repo = QueueRepository(db_path)
            repo.init_schema()

            first = repo.enqueue_transfer_task(
                share_code="sw3abc1",
                receive_code="xy12",
                share_url="https://115.com/s/sw3abc1?password=xy12",
                staging_cid=9001,
                matched_rule=TransferRuleContext(rule_id="rule-4k", rule_name="4K movies", matched_keywords=["4k"]),
                source_message=TransferSourceMessage(
                    collect_id=1,
                    source_type="telegram_web",
                    source_id="movie_channel",
                    message_id="101",
                    message_url="https://t.me/s/movie_channel/101",
                    published_at=None,
                ),
            )
            second = repo.enqueue_transfer_task(
                share_code="sw3abc1",
                receive_code="xy12",
                share_url="https://115.com/s/sw3abc1?password=xy12",
                staging_cid=9002,
                matched_rule=TransferRuleContext(rule_id="rule-4k", rule_name="4K movies", matched_keywords=["4k"]),
                source_message=TransferSourceMessage(
                    collect_id=1,
                    source_type="telegram_web",
                    source_id="movie_channel",
                    message_id="101",
                    message_url="https://t.me/s/movie_channel/101",
                    published_at=None,
                ),
            )

            self.assertNotEqual(first.id, second.id)
            connection = sqlite3.connect(db_path)
            try:
                count = connection.execute("SELECT COUNT(*) FROM transfer_queue").fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(count, 2)

    def test_claim_retry_and_failed_exclusion(self) -> None:
        from src.queue import TransferRuleContext, TransferSourceMessage
        from src.queue.repository import QueueRepository

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "queue.db"
            repo = QueueRepository(db_path)
            repo.init_schema()

            failing = repo.enqueue_transfer_task(
                share_code="sw3abc1",
                receive_code="xy12",
                share_url="https://115.com/s/sw3abc1?password=xy12",
                staging_cid=9001,
                matched_rule=TransferRuleContext(rule_id="rule-4k", rule_name="4K movies", matched_keywords=["4k"]),
                source_message=TransferSourceMessage(
                    collect_id=1,
                    source_type="telegram_web",
                    source_id="movie_channel",
                    message_id="101",
                    message_url="https://t.me/s/movie_channel/101",
                    published_at=None,
                ),
            )
            failed = repo.enqueue_transfer_task(
                share_code="sw3abc2",
                receive_code="xy13",
                share_url="https://115.com/s/sw3abc2?password=xy13",
                staging_cid=9001,
                matched_rule=TransferRuleContext(rule_id="rule-hdr", rule_name="HDR movies", matched_keywords=["hdr"]),
                source_message=TransferSourceMessage(
                    collect_id=2,
                    source_type="telegram_web",
                    source_id="movie_channel",
                    message_id="102",
                    message_url="https://t.me/s/movie_channel/102",
                    published_at=None,
                ),
            )

            claimed = repo.claim_next_transfer()
            self.assertIsNotNone(claimed)
            assert claimed is not None
            self.assertEqual(claimed.id, failing.id)
            self.assertEqual(claimed.status, "RUNNING")

            repo.mark_transfer_failed_or_retry(claimed.id, "first failure", max_attempts=3)
            connection = sqlite3.connect(db_path)
            try:
                row = connection.execute(
                    "SELECT status, attempt_count, last_error FROM transfer_queue WHERE id = ?",
                    (claimed.id,),
                ).fetchone()
            finally:
                connection.close()
            self.assertEqual(row[0], "PENDING")
            self.assertEqual(row[1], 1)
            self.assertEqual(row[2], "first failure")

            claimed_again = repo.claim_next_transfer()
            self.assertIsNotNone(claimed_again)
            assert claimed_again is not None
            self.assertEqual(claimed_again.id, failing.id)
            repo.mark_transfer_failed_or_retry(claimed_again.id, "second failure", max_attempts=3)
            repo.claim_next_transfer()
            repo.mark_transfer_failed_or_retry(failing.id, "third failure", max_attempts=3)

            connection = sqlite3.connect(db_path)
            try:
                final_row = connection.execute(
                    "SELECT status, attempt_count, last_error FROM transfer_queue WHERE id = ?",
                    (failing.id,),
                ).fetchone()
            finally:
                connection.close()
            self.assertEqual(final_row[0], "FAILED")
            self.assertEqual(final_row[1], 3)
            self.assertEqual(final_row[2], "third failure")

            next_claim = repo.claim_next_transfer()
            self.assertIsNotNone(next_claim)
            assert next_claim is not None
            self.assertEqual(next_claim.id, failed.id)
            repo.mark_transfer_success(next_claim.id)
            self.assertIsNone(repo.claim_next_transfer())


class QueueRepositoryReadHelpersTest(unittest.TestCase):
    def test_collect_read_helpers_return_counts_and_descending_filtered_rows_without_mutation(self) -> None:
        from src.queue import ShareLink
        from src.queue.repository import QueueRepository

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "queue.db"
            repo = QueueRepository(db_path)
            repo.init_schema()

            collect_one = repo.enqueue_collected_message(
                source_type="telegram_web",
                source_id="movie_channel",
                message_id="101",
                message_url="https://t.me/s/movie_channel/101",
                message_text="pending one",
                published_at="2026-05-26T10:00:00",
                shares=[ShareLink(share_code="a1", receive_code="", share_url="https://115.com/s/a1")],
            )
            collect_two = repo.enqueue_collected_message(
                source_type="telegram_web",
                source_id="movie_channel",
                message_id="102",
                message_url="https://t.me/s/movie_channel/102",
                message_text="pending two",
                published_at="2026-05-26T10:01:00",
                shares=[ShareLink(share_code="b2", receive_code="", share_url="https://115.com/s/b2")],
            )
            collect_three = repo.enqueue_collected_message(
                source_type="telegram_web",
                source_id="movie_channel",
                message_id="103",
                message_url="https://t.me/s/movie_channel/103",
                message_text="running",
                published_at="2026-05-26T10:02:00",
                shares=[ShareLink(share_code="c3", receive_code="", share_url="https://115.com/s/c3")],
            )
            collect_four = repo.enqueue_collected_message(
                source_type="telegram_web",
                source_id="movie_channel",
                message_id="104",
                message_url="https://t.me/s/movie_channel/104",
                message_text="success",
                published_at="2026-05-26T10:03:00",
                shares=[ShareLink(share_code="d4", receive_code="", share_url="https://115.com/s/d4")],
            )
            collect_five = repo.enqueue_collected_message(
                source_type="telegram_web",
                source_id="movie_channel",
                message_id="105",
                message_url="https://t.me/s/movie_channel/105",
                message_text="failed",
                published_at="2026-05-26T10:04:00",
                shares=[ShareLink(share_code="e5", receive_code="", share_url="https://115.com/s/e5")],
            )

            claimed_one = repo.claim_next_collect()
            claimed_two = repo.claim_next_collect()
            claimed_three = repo.claim_next_collect()
            self.assertIsNotNone(claimed_one)
            self.assertIsNotNone(claimed_two)
            self.assertIsNotNone(claimed_three)
            assert claimed_one is not None
            assert claimed_two is not None
            assert claimed_three is not None

            repo.mark_collect_skipped(claimed_one.id)
            repo.mark_collect_success(collect_four.id)
            repo.mark_collect_failed(collect_five.id, "collect boom")

            before_connection = sqlite3.connect(db_path)
            try:
                before_rows = before_connection.execute(
                    "SELECT id, status, attempt_count, last_error, created_at, updated_at FROM collect_queue ORDER BY id"
                ).fetchall()
            finally:
                before_connection.close()

            counts = repo.get_collect_status_counts()
            all_rows = repo.list_collect_queue()
            running_rows = repo.list_collect_queue(status="RUNNING")
            limited_rows = repo.list_collect_queue(limit=2)

            after_connection = sqlite3.connect(db_path)
            try:
                after_rows = after_connection.execute(
                    "SELECT id, status, attempt_count, last_error, created_at, updated_at FROM collect_queue ORDER BY id"
                ).fetchall()
            finally:
                after_connection.close()

            self.assertEqual(
                counts,
                {
                    "FAILED": 1,
                    "RUNNING": 2,
                    "SKIPPED": 1,
                    "SUCCESS": 1,
                },
            )
            self.assertEqual([row.id for row in all_rows], [collect_five.id, collect_four.id, collect_three.id, collect_two.id, collect_one.id])
            self.assertEqual([row.id for row in running_rows], [collect_three.id, collect_two.id])
            self.assertTrue(all(row.status == "RUNNING" for row in running_rows))
            self.assertEqual([row.id for row in limited_rows], [collect_five.id, collect_four.id])
            self.assertEqual(before_rows, after_rows)

    def test_transfer_read_helpers_return_counts_and_descending_filtered_rows_without_mutation(self) -> None:
        from src.queue import TransferRuleContext, TransferSourceMessage
        from src.queue.repository import QueueRepository

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "queue.db"
            repo = QueueRepository(db_path)
            repo.init_schema()

            transfer_one = repo.enqueue_transfer_task(
                share_code="sw3abc1",
                receive_code="xy12",
                share_url="https://115.com/s/sw3abc1?password=xy12",
                staging_cid=9001,
                matched_rule=TransferRuleContext(rule_id="rule-4k", rule_name="4K movies", matched_keywords=["4k"]),
                source_message=TransferSourceMessage(
                    collect_id=1,
                    source_type="telegram_web",
                    source_id="movie_channel",
                    message_id="101",
                    message_url="https://t.me/s/movie_channel/101",
                    published_at=None,
                ),
            )
            transfer_two = repo.enqueue_transfer_task(
                share_code="sw3abc2",
                receive_code="xy13",
                share_url="https://115.com/s/sw3abc2?password=xy13",
                staging_cid=9001,
                matched_rule=TransferRuleContext(rule_id="rule-hdr", rule_name="HDR movies", matched_keywords=["hdr"]),
                source_message=TransferSourceMessage(
                    collect_id=2,
                    source_type="telegram_web",
                    source_id="movie_channel",
                    message_id="102",
                    message_url="https://t.me/s/movie_channel/102",
                    published_at=None,
                ),
            )
            transfer_three = repo.enqueue_transfer_task(
                share_code="sw3abc3",
                receive_code="xy14",
                share_url="https://115.com/s/sw3abc3?password=xy14",
                staging_cid=9001,
                matched_rule=TransferRuleContext(rule_id="rule-sdr", rule_name="SDR movies", matched_keywords=["sdr"]),
                source_message=TransferSourceMessage(
                    collect_id=3,
                    source_type="telegram_web",
                    source_id="movie_channel",
                    message_id="103",
                    message_url="https://t.me/s/movie_channel/103",
                    published_at=None,
                ),
            )
            transfer_four = repo.enqueue_transfer_task(
                share_code="sw3abc4",
                receive_code="xy15",
                share_url="https://115.com/s/sw3abc4?password=xy15",
                staging_cid=9001,
                matched_rule=TransferRuleContext(rule_id="rule-remux", rule_name="Remux movies", matched_keywords=["remux"]),
                source_message=TransferSourceMessage(
                    collect_id=4,
                    source_type="telegram_web",
                    source_id="movie_channel",
                    message_id="104",
                    message_url="https://t.me/s/movie_channel/104",
                    published_at=None,
                ),
            )

            claimed = repo.claim_next_transfer()
            self.assertIsNotNone(claimed)
            assert claimed is not None
            repo.mark_transfer_success(claimed.id)
            repo.mark_transfer_failed_or_retry(transfer_two.id, "transfer boom", max_attempts=1)

            before_connection = sqlite3.connect(db_path)
            try:
                before_rows = before_connection.execute(
                    "SELECT id, status, attempt_count, last_error, created_at, updated_at FROM transfer_queue ORDER BY id"
                ).fetchall()
            finally:
                before_connection.close()

            counts = repo.get_transfer_status_counts()
            all_rows = repo.list_transfer_queue()
            pending_rows = repo.list_transfer_queue(status="PENDING")
            limited_rows = repo.list_transfer_queue(limit=2)

            after_connection = sqlite3.connect(db_path)
            try:
                after_rows = after_connection.execute(
                    "SELECT id, status, attempt_count, last_error, created_at, updated_at FROM transfer_queue ORDER BY id"
                ).fetchall()
            finally:
                after_connection.close()

            self.assertEqual(
                counts,
                {
                    "FAILED": 1,
                    "PENDING": 2,
                    "SUCCESS": 1,
                },
            )
            self.assertEqual([row.id for row in all_rows], [transfer_four.id, transfer_three.id, transfer_two.id, transfer_one.id])
            self.assertEqual([row.id for row in pending_rows], [transfer_four.id, transfer_three.id])
            self.assertTrue(all(row.status == "PENDING" for row in pending_rows))
            self.assertEqual([row.id for row in limited_rows], [transfer_four.id, transfer_three.id])
            self.assertEqual(before_rows, after_rows)


class QueueRepositoryRecoveryTest(unittest.TestCase):
    def test_reset_running_collects_and_transfers_only_affect_running_rows(self) -> None:
        from src.queue import ShareLink, TransferRuleContext, TransferSourceMessage
        from src.queue.repository import QueueRepository

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "queue.db"
            repo = QueueRepository(db_path)
            repo.init_schema()

            collect_pending = repo.enqueue_collected_message(
                source_type="telegram_web",
                source_id="movie_channel",
                message_id="101",
                message_url="https://t.me/s/movie_channel/101",
                message_text="pending",
                published_at=None,
                shares=[ShareLink(share_code="a1", receive_code="", share_url="https://115.com/s/a1")],
            )
            collect_running = repo.enqueue_collected_message(
                source_type="telegram_web",
                source_id="movie_channel",
                message_id="102",
                message_url="https://t.me/s/movie_channel/102",
                message_text="running",
                published_at=None,
                shares=[ShareLink(share_code="b2", receive_code="", share_url="https://115.com/s/b2")],
            )
            collect_success = repo.enqueue_collected_message(
                source_type="telegram_web",
                source_id="movie_channel",
                message_id="103",
                message_url="https://t.me/s/movie_channel/103",
                message_text="success",
                published_at=None,
                shares=[ShareLink(share_code="c3", receive_code="", share_url="https://115.com/s/c3")],
            )
            collect_skipped = repo.enqueue_collected_message(
                source_type="telegram_web",
                source_id="movie_channel",
                message_id="104",
                message_url="https://t.me/s/movie_channel/104",
                message_text="skipped",
                published_at=None,
                shares=[ShareLink(share_code="d4", receive_code="", share_url="https://115.com/s/d4")],
            )
            collect_failed = repo.enqueue_collected_message(
                source_type="telegram_web",
                source_id="movie_channel",
                message_id="105",
                message_url="https://t.me/s/movie_channel/105",
                message_text="failed",
                published_at=None,
                shares=[ShareLink(share_code="e5", receive_code="", share_url="https://115.com/s/e5")],
            )

            repo.claim_next_collect()
            repo.mark_collect_success(collect_success.id)
            repo.mark_collect_skipped(collect_skipped.id)
            repo.mark_collect_failed(collect_failed.id, "boom")

            transfer_running = repo.enqueue_transfer_task(
                share_code="sw3abc1",
                receive_code="xy12",
                share_url="https://115.com/s/sw3abc1?password=xy12",
                staging_cid=9001,
                matched_rule=TransferRuleContext(rule_id="rule-4k", rule_name="4K movies", matched_keywords=["4k"]),
                source_message=TransferSourceMessage(
                    collect_id=1,
                    source_type="telegram_web",
                    source_id="movie_channel",
                    message_id="101",
                    message_url="https://t.me/s/movie_channel/101",
                    published_at=None,
                ),
            )
            transfer_success = repo.enqueue_transfer_task(
                share_code="sw3abc2",
                receive_code="xy13",
                share_url="https://115.com/s/sw3abc2?password=xy13",
                staging_cid=9001,
                matched_rule=TransferRuleContext(rule_id="rule-hdr", rule_name="HDR movies", matched_keywords=["hdr"]),
                source_message=TransferSourceMessage(
                    collect_id=2,
                    source_type="telegram_web",
                    source_id="movie_channel",
                    message_id="102",
                    message_url="https://t.me/s/movie_channel/102",
                    published_at=None,
                ),
            )
            transfer_failed = repo.enqueue_transfer_task(
                share_code="sw3abc3",
                receive_code="xy14",
                share_url="https://115.com/s/sw3abc3?password=xy14",
                staging_cid=9001,
                matched_rule=TransferRuleContext(rule_id="rule-sdr", rule_name="SDR movies", matched_keywords=["sdr"]),
                source_message=TransferSourceMessage(
                    collect_id=3,
                    source_type="telegram_web",
                    source_id="movie_channel",
                    message_id="103",
                    message_url="https://t.me/s/movie_channel/103",
                    published_at=None,
                ),
            )

            repo.claim_next_transfer()
            repo.mark_transfer_success(transfer_success.id)
            repo.mark_transfer_failed_or_retry(transfer_failed.id, "boom", max_attempts=1)

            reset_collects = repo.reset_running_collects()
            reset_transfers = repo.reset_running_transfers()
            reset_collects_again = repo.reset_running_collects()
            reset_transfers_again = repo.reset_running_transfers()

            self.assertEqual(reset_collects, 1)
            self.assertEqual(reset_transfers, 1)
            self.assertEqual(reset_collects_again, 0)
            self.assertEqual(reset_transfers_again, 0)

            connection = sqlite3.connect(db_path)
            try:
                collect_rows = {
                    row[0]: row[1]
                    for row in connection.execute(
                        "SELECT id, status FROM collect_queue ORDER BY id"
                    )
                }
                transfer_rows = {
                    row[0]: row[1]
                    for row in connection.execute(
                        "SELECT id, status FROM transfer_queue ORDER BY id"
                    )
                }
            finally:
                connection.close()

            self.assertEqual(collect_rows[collect_pending.id], "PENDING")
            self.assertEqual(collect_rows[collect_running.id], "PENDING")
            self.assertEqual(collect_rows[collect_success.id], "SUCCESS")
            self.assertEqual(collect_rows[collect_skipped.id], "SKIPPED")
            self.assertEqual(collect_rows[collect_failed.id], "FAILED")
            self.assertEqual(transfer_rows[transfer_running.id], "PENDING")
            self.assertEqual(transfer_rows[transfer_success.id], "SUCCESS")
            self.assertEqual(transfer_rows[transfer_failed.id], "FAILED")


class QueueRepositoryJsonTest(unittest.TestCase):
    def test_unicode_long_text_and_deduped_json_round_trip(self) -> None:
        from src.queue import ShareLink, TransferRuleContext, TransferSourceMessage
        from src.queue.repository import QueueRepository

        long_message = "长文本🚀" * 1000 + "<>\"'&"
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "queue.db"
            repo = QueueRepository(db_path)
            repo.init_schema()

            collect_record = repo.enqueue_collected_message(
                source_type="telegram_web",
                source_id="中文频道",
                message_id="200",
                message_url="https://t.me/s/中文频道/200",
                message_text=long_message,
                published_at="2026-05-26T12:00:00",
                shares=[
                    ShareLink(share_code="abc中文", receive_code="口令😀", share_url="https://115.com/s/abc中文"),
                    ShareLink(share_code="abc中文", receive_code="口令😀", share_url="https://115.com/s/abc中文"),
                ],
            )
            self.assertEqual(collect_record.message_text, long_message)
            self.assertEqual(len(collect_record.shares_json), 2)
            self.assertEqual(collect_record.shares_json[0].share_code, "abc中文")
            self.assertEqual(collect_record.shares_json[0].receive_code, "口令😀")

            transfer_record = repo.enqueue_transfer_task(
                share_code="abc中文",
                receive_code="口令😀",
                share_url="https://115.com/s/abc中文?password=口令😀",
                staging_cid=9001,
                matched_rule=TransferRuleContext(rule_id="规则-1", rule_name="标题✨", matched_keywords=["中文", "✨"]),
                source_message=TransferSourceMessage(
                    collect_id=collect_record.id,
                    source_type="telegram_web",
                    source_id="中文频道",
                    message_id="200",
                    message_url="https://t.me/s/中文频道/200",
                    published_at="2026-05-26T12:00:00",
                ),
            )
            transfer_record = repo.enqueue_transfer_task(
                share_code="abc中文",
                receive_code="口令😀",
                share_url="https://115.com/s/abc中文?password=口令😀",
                staging_cid=9001,
                matched_rule=TransferRuleContext(rule_id="规则-1", rule_name="标题✨", matched_keywords=["中文", "✨"]),
                source_message=TransferSourceMessage(
                    collect_id=collect_record.id,
                    source_type="telegram_web",
                    source_id="中文频道",
                    message_id="200",
                    message_url="https://t.me/s/中文频道/200",
                    published_at="2026-05-26T12:00:00",
                ),
            )

            self.assertEqual(transfer_record.matched_rules_json[0].rule_name, "标题✨")
            self.assertEqual(transfer_record.source_messages_json[0].source_id, "中文频道")
            self.assertEqual(transfer_record.source_messages_json[0].message_url, "https://t.me/s/中文频道/200")

            connection = sqlite3.connect(db_path)
            try:
                collect_row = connection.execute(
                    "SELECT shares_json, message_text FROM collect_queue WHERE id = ?",
                    (collect_record.id,),
                ).fetchone()
                transfer_row = connection.execute(
                    "SELECT matched_rules_json, source_messages_json FROM transfer_queue WHERE id = ?",
                    (transfer_record.id,),
                ).fetchone()
            finally:
                connection.close()

            self.assertIn("中文", collect_row[0])
            self.assertIn("长文本🚀", collect_row[1])
            self.assertEqual(transfer_row[0].count("规则-1"), 1)
            self.assertEqual(transfer_row[1].count("collect_id"), 1)

    def test_duplicate_json_contexts_do_not_accumulate(self) -> None:
        from src.queue import TransferRuleContext, TransferSourceMessage
        from src.queue.repository import QueueRepository

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "queue.db"
            repo = QueueRepository(db_path)
            repo.init_schema()

            first = repo.enqueue_transfer_task(
                share_code="dup1",
                receive_code="",
                share_url="https://115.com/s/dup1",
                staging_cid=1001,
                matched_rule=TransferRuleContext(rule_id="rule-x", rule_name="重复规则", matched_keywords=["dup"]),
                source_message=TransferSourceMessage(
                    collect_id=1,
                    source_type="telegram_web",
                    source_id="频道",
                    message_id="1",
                    message_url="https://t.me/s/频道/1",
                    published_at=None,
                ),
            )
            second = repo.enqueue_transfer_task(
                share_code="dup1",
                receive_code="",
                share_url="https://115.com/s/dup1",
                staging_cid=1001,
                matched_rule=TransferRuleContext(rule_id="rule-x", rule_name="重复规则", matched_keywords=["dup"]),
                source_message=TransferSourceMessage(
                    collect_id=1,
                    source_type="telegram_web",
                    source_id="频道",
                    message_id="1",
                    message_url="https://t.me/s/频道/1",
                    published_at=None,
                ),
            )

            self.assertEqual(first.id, second.id)
            self.assertEqual(len(second.matched_rules_json), 1)
            self.assertEqual(len(second.source_messages_json), 1)


class QueueRepositoryCursorTest(unittest.TestCase):
    def test_init_schema_creates_cursor_table_and_is_idempotent(self) -> None:
        from src.queue.repository import QueueRepository

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "queue.db"
            repo = QueueRepository(db_path)
            repo.init_schema()
            repo.init_schema()

            connection = sqlite3.connect(db_path)
            try:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                    )
                }
                cursor_schema = connection.execute(
                    "SELECT sql FROM sqlite_master WHERE name='collector_cursors'"
                ).fetchone()[0]
            finally:
                connection.close()

            self.assertIn("collector_cursors", tables)
            self.assertIn("source_type TEXT NOT NULL", cursor_schema)
            self.assertIn("source_id TEXT NOT NULL", cursor_schema)
            self.assertIn("last_seen_message_id TEXT", cursor_schema)
            self.assertIn("last_poll_at TEXT", cursor_schema)
            self.assertIn("last_status TEXT NOT NULL", cursor_schema)
            self.assertIn("last_error TEXT", cursor_schema)
            self.assertIn("UNIQUE(source_type, source_id)", cursor_schema)

    def test_get_collector_cursor_returns_none_for_unknown_source(self) -> None:
        from src.queue.repository import QueueRepository

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "queue.db"
            repo = QueueRepository(db_path)
            repo.init_schema()

            cursor = repo.get_collector_cursor(
                source_type="telegram_web",
                source_id="unknown_channel",
            )

            self.assertIsNone(cursor)

    def test_upsert_success_cursor_stores_checkpoint_status_time_and_clears_error(self) -> None:
        from src.queue.repository import QueueRepository

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "queue.db"
            repo = QueueRepository(db_path)
            repo.init_schema()

            repo.upsert_collector_cursor(
                source_type="telegram_web",
                source_id="movie_channel",
                last_seen_message_id="41",
                last_poll_at="2026-05-27T10:00:00Z",
                last_status="FAILED",
                last_error="temporary failure",
            )
            repo.upsert_collector_cursor(
                source_type="telegram_web",
                source_id="movie_channel",
                last_seen_message_id="42",
                last_poll_at="2026-05-27T10:05:00Z",
                last_status="SUCCESS",
                last_error=None,
            )

            cursor = repo.get_collector_cursor(
                source_type="telegram_web",
                source_id="movie_channel",
            )

            self.assertIsNotNone(cursor)
            assert cursor is not None
            self.assertEqual(cursor.source_type, "telegram_web")
            self.assertEqual(cursor.source_id, "movie_channel")
            self.assertEqual(cursor.last_seen_message_id, "42")
            self.assertEqual(cursor.last_poll_at, "2026-05-27T10:05:00Z")
            self.assertEqual(cursor.last_status, "SUCCESS")
            self.assertIsNone(cursor.last_error)

    def test_upsert_failure_cursor_stores_error_without_requiring_checkpoint_advance(self) -> None:
        from src.queue.repository import QueueRepository

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "queue.db"
            repo = QueueRepository(db_path)
            repo.init_schema()

            repo.upsert_collector_cursor(
                source_type="telegram_web",
                source_id="movie_channel",
                last_seen_message_id="42",
                last_poll_at="2026-05-27T10:05:00Z",
                last_status="SUCCESS",
                last_error=None,
            )
            repo.upsert_collector_cursor(
                source_type="telegram_web",
                source_id="movie_channel",
                last_seen_message_id="42",
                last_poll_at="2026-05-27T10:10:00Z",
                last_status="FAILED",
                last_error="HTTP 502",
            )

            cursor = repo.get_collector_cursor(
                source_type="telegram_web",
                source_id="movie_channel",
            )

            self.assertIsNotNone(cursor)
            assert cursor is not None
            self.assertEqual(cursor.last_seen_message_id, "42")
            self.assertEqual(cursor.last_poll_at, "2026-05-27T10:10:00Z")
            self.assertEqual(cursor.last_status, "FAILED")
            self.assertEqual(cursor.last_error, "HTTP 502")

    def test_collector_cursor_persists_across_repository_instances(self) -> None:
        from src.queue.repository import QueueRepository

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "queue.db"
            first_repo = QueueRepository(db_path)
            first_repo.init_schema()
            first_repo.upsert_collector_cursor(
                source_type="telegram_web",
                source_id="movie_channel",
                last_seen_message_id="42",
                last_poll_at="2026-05-27T10:05:00Z",
                last_status="SUCCESS",
                last_error=None,
            )

            second_repo = QueueRepository(db_path)
            second_repo.init_schema()
            cursor = second_repo.get_collector_cursor(
                source_type="telegram_web",
                source_id="movie_channel",
            )

            self.assertIsNotNone(cursor)
            assert cursor is not None
            self.assertEqual(cursor.source_type, "telegram_web")
            self.assertEqual(cursor.source_id, "movie_channel")
            self.assertEqual(cursor.last_seen_message_id, "42")
            self.assertEqual(cursor.last_poll_at, "2026-05-27T10:05:00Z")
            self.assertEqual(cursor.last_status, "SUCCESS")
            self.assertIsNone(cursor.last_error)


class QueueRepositoryTransferRetryTest(QueueRepositoryTransferTest):
    pass


if __name__ == "__main__":
    unittest.main()

