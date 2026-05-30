from __future__ import annotations

import json
from pathlib import Path

from src.db import connect, migrate

from .models import (
    CollectQueueRecord,
    CollectorCursor,
    FAILED,
    PENDING,
    RUNNING,
    SKIPPED,
    SUCCESS,
    ShareLink,
    TransferQueueRecord,
    TransferRuleContext,
    TransferSourceMessage,
)


class QueueRepository:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)

    def init_schema(self) -> None:
        migrate(self._db_path)

    def get_collector_cursor(self, *, source_type: str, source_id: str) -> CollectorCursor | None:
        connection = connect(self._db_path)
        try:
            row = connection.execute(
                """
                SELECT source_type, source_id, last_seen_message_id, last_poll_at, last_status, last_error
                FROM collector_cursors
                WHERE source_type = ? AND source_id = ?
                """,
                (source_type, source_id),
            ).fetchone()
            if row is None:
                return None
            return self._collector_cursor_from_row(row)
        finally:
            connection.close()

    def upsert_collector_cursor(
        self,
        *,
        source_type: str,
        source_id: str,
        last_seen_message_id: str | None,
        last_poll_at: str | None,
        last_status: str,
        last_error: str | None,
    ) -> CollectorCursor:
        connection = connect(self._db_path)
        try:
            connection.execute(
                """
                INSERT INTO collector_cursors (
                    source_type,
                    source_id,
                    last_seen_message_id,
                    last_poll_at,
                    last_status,
                    last_error
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_type, source_id) DO UPDATE SET
                    last_seen_message_id = excluded.last_seen_message_id,
                    last_poll_at = excluded.last_poll_at,
                    last_status = excluded.last_status,
                    last_error = excluded.last_error,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (source_type, source_id, last_seen_message_id, last_poll_at, last_status, last_error),
            )
            connection.commit()
            row = connection.execute(
                """
                SELECT source_type, source_id, last_seen_message_id, last_poll_at, last_status, last_error
                FROM collector_cursors
                WHERE source_type = ? AND source_id = ?
                """,
                (source_type, source_id),
            ).fetchone()
            return self._collector_cursor_from_row(row)
        finally:
            connection.close()

    def enqueue_collected_message(
        self,
        *,
        source_type: str,
        source_id: str,
        message_id: str,
        message_url: str | None,
        message_text: str,
        published_at: str | None,
        shares: list[ShareLink],
    ) -> CollectQueueRecord:
        if not shares:
            raise ValueError("shares must not be empty")

        shares_json = [share.__dict__ for share in shares]
        connection = connect(self._db_path)
        try:
            connection.execute(
                """
                INSERT INTO collect_queue (
                    source_type,
                    source_id,
                    message_id,
                    message_url,
                    message_text,
                    published_at,
                    shares_json,
                    status,
                    attempt_count,
                    last_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, NULL)
                ON CONFLICT(source_type, source_id, message_id) DO NOTHING
                """,
                (
                    source_type,
                    source_id,
                    message_id,
                    message_url,
                    message_text,
                    published_at,
                    json.dumps(shares_json, ensure_ascii=False),
                    PENDING,
                ),
            )
            connection.commit()
            row = connection.execute(
                """
                SELECT id, source_type, source_id, message_id, message_url, message_text, published_at,
                       shares_json, status, attempt_count, last_error, created_at, updated_at
                FROM collect_queue
                WHERE source_type = ? AND source_id = ? AND message_id = ?
                """,
                (source_type, source_id, message_id),
            ).fetchone()
            return self._collect_record_from_row(row)
        finally:
            connection.close()

    def claim_next_collect(self) -> CollectQueueRecord | None:
        connection = connect(self._db_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT id
                FROM collect_queue
                WHERE status = ?
                ORDER BY id ASC
                LIMIT 1
                """,
                (PENDING,),
            ).fetchone()
            if row is None:
                connection.rollback()
                return None

            collect_id = row[0]
            connection.execute(
                """
                UPDATE collect_queue
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (RUNNING, collect_id),
            )
            connection.commit()
            claimed_row = connection.execute(
                """
                SELECT id, source_type, source_id, message_id, message_url, message_text, published_at,
                       shares_json, status, attempt_count, last_error, created_at, updated_at
                FROM collect_queue
                WHERE id = ?
                """,
                (collect_id,),
            ).fetchone()
            return self._collect_record_from_row(claimed_row)
        finally:
            connection.close()

    def mark_collect_success(self, collect_id: int) -> None:
        self._update_collect_status(collect_id, SUCCESS, None)

    def mark_collect_skipped(self, collect_id: int) -> None:
        self._update_collect_status(collect_id, SKIPPED, None)

    def mark_collect_failed(self, collect_id: int, error: str) -> None:
        self._update_collect_status(collect_id, FAILED, error)

    def get_collect_status_counts(self) -> dict[str, int]:
        return self._get_status_counts("collect_queue")

    def list_collect_queue(
        self,
        *,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[CollectQueueRecord]:
        rows = self._list_queue_rows(
            table_name="collect_queue",
            columns=(
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
            ),
            status=status,
            limit=limit,
        )
        return [self._collect_record_from_row(row) for row in rows]

    def enqueue_transfer_task(
        self,
        *,
        share_code: str,
        receive_code: str,
        share_url: str,
        staging_cid: int,
        matched_rule: TransferRuleContext,
        source_message: TransferSourceMessage,
    ) -> TransferQueueRecord:
        connection = connect(self._db_path)
        try:
            existing = connection.execute(
                """
                SELECT id, share_code, receive_code, share_url, staging_cid, matched_rules_json,
                       source_messages_json, status, attempt_count, last_error, created_at, updated_at
                FROM transfer_queue
                WHERE share_url = ? AND staging_cid = ?
                """,
                (share_url, staging_cid),
            ).fetchone()

            if existing is None:
                connection.execute(
                    """
                    INSERT INTO transfer_queue (
                        share_code,
                        receive_code,
                        share_url,
                        staging_cid,
                        matched_rules_json,
                        source_messages_json,
                        status,
                        attempt_count,
                        last_error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, NULL)
                    """,
                    (
                        share_code,
                        receive_code,
                        share_url,
                        staging_cid,
                        json.dumps([matched_rule.__dict__], ensure_ascii=False),
                        json.dumps([source_message.__dict__], ensure_ascii=False),
                        PENDING,
                    ),
                )
                connection.commit()
            else:
                matched_rules = self._merge_unique_contexts(json.loads(existing[5]), matched_rule.__dict__)
                source_messages = self._merge_unique_contexts(json.loads(existing[6]), source_message.__dict__)
                connection.execute(
                    """
                    UPDATE transfer_queue
                    SET share_code = ?,
                        receive_code = ?,
                        matched_rules_json = ?,
                        source_messages_json = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        share_code,
                        receive_code,
                        json.dumps(matched_rules, ensure_ascii=False),
                        json.dumps(source_messages, ensure_ascii=False),
                        existing[0],
                    ),
                )
                connection.commit()

            row = connection.execute(
                """
                SELECT id, share_code, receive_code, share_url, staging_cid, matched_rules_json,
                       source_messages_json, status, attempt_count, last_error, created_at, updated_at
                FROM transfer_queue
                WHERE share_url = ? AND staging_cid = ?
                """,
                (share_url, staging_cid),
            ).fetchone()
            return self._transfer_record_from_row(row)
        finally:
            connection.close()

    def claim_next_transfer(self) -> TransferQueueRecord | None:
        connection = connect(self._db_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT id
                FROM transfer_queue
                WHERE status = ?
                ORDER BY id ASC
                LIMIT 1
                """,
                (PENDING,),
            ).fetchone()
            if row is None:
                connection.rollback()
                return None

            transfer_id = row[0]
            connection.execute(
                """
                UPDATE transfer_queue
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (RUNNING, transfer_id),
            )
            connection.commit()
            claimed_row = connection.execute(
                """
                SELECT id, share_code, receive_code, share_url, staging_cid, matched_rules_json,
                       source_messages_json, status, attempt_count, last_error, created_at, updated_at
                FROM transfer_queue
                WHERE id = ?
                """,
                (transfer_id,),
            ).fetchone()
            return self._transfer_record_from_row(claimed_row)
        finally:
            connection.close()

    def mark_transfer_success(self, transfer_id: int) -> None:
        self._update_transfer_status(transfer_id, SUCCESS, None, increment_attempt=False)

    def mark_transfer_failed_or_retry(self, transfer_id: int, error: str, max_attempts: int = 3) -> None:
        connection = connect(self._db_path)
        try:
            row = connection.execute(
                """
                SELECT attempt_count
                FROM transfer_queue
                WHERE id = ?
                """,
                (transfer_id,),
            ).fetchone()
            if row is None:
                return

            next_attempt = row[0] + 1
            next_status = PENDING if next_attempt < max_attempts else FAILED
            connection.execute(
                """
                UPDATE transfer_queue
                SET attempt_count = ?,
                    status = ?,
                    last_error = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (next_attempt, next_status, error, transfer_id),
            )
            connection.commit()
        finally:
            connection.close()

    def get_transfer_status_counts(self) -> dict[str, int]:
        return self._get_status_counts("transfer_queue")

    def list_transfer_queue(
        self,
        *,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[TransferQueueRecord]:
        rows = self._list_queue_rows(
            table_name="transfer_queue",
            columns=(
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
            ),
            status=status,
            limit=limit,
        )
        return [self._transfer_record_from_row(row) for row in rows]

    def _update_collect_status(self, collect_id: int, status: str, error: str | None) -> None:
        connection = connect(self._db_path)
        try:
            connection.execute(
                """
                UPDATE collect_queue
                SET status = ?, last_error = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, error, collect_id),
            )
            connection.commit()
        finally:
            connection.close()

    def _update_transfer_status(self, transfer_id: int, status: str, error: str | None, *, increment_attempt: bool) -> None:
        connection = connect(self._db_path)
        try:
            if increment_attempt:
                connection.execute(
                    """
                    UPDATE transfer_queue
                    SET attempt_count = attempt_count + 1,
                        status = ?,
                        last_error = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (status, error, transfer_id),
                )
            else:
                connection.execute(
                    """
                    UPDATE transfer_queue
                    SET status = ?,
                        last_error = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (status, error, transfer_id),
                )
            connection.commit()
        finally:
            connection.close()

    def reset_running_collects(self) -> int:
        return self._reset_running_rows("collect_queue")

    def reset_running_transfers(self) -> int:
        return self._reset_running_rows("transfer_queue")

    def _get_status_counts(self, table_name: str) -> dict[str, int]:
        connection = connect(self._db_path)
        try:
            rows = connection.execute(
                f"""
                SELECT status, COUNT(*)
                FROM {table_name}
                GROUP BY status
                ORDER BY status ASC
                """
            ).fetchall()
            return {row[0]: row[1] for row in rows}
        finally:
            connection.close()

    def _list_queue_rows(
        self,
        *,
        table_name: str,
        columns: tuple[str, ...],
        status: str | None,
        limit: int | None,
    ) -> list[tuple[object, ...]]:
        query = f"SELECT {', '.join(columns)} FROM {table_name}"
        parameters: list[object] = []
        if status is not None:
            query += " WHERE status = ?"
            parameters.append(status)
        query += " ORDER BY id DESC"
        if limit is not None:
            query += " LIMIT ?"
            parameters.append(limit)

        connection = connect(self._db_path)
        try:
            return connection.execute(query, tuple(parameters)).fetchall()
        finally:
            connection.close()

    def _reset_running_rows(self, table_name: str) -> int:
        connection = connect(self._db_path)
        try:
            cursor = connection.execute(
                f"""
                UPDATE {table_name}
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE status = ?
                """,
                (PENDING, RUNNING),
            )
            connection.commit()
            return cursor.rowcount
        finally:
            connection.close()

    def _collector_cursor_from_row(self, row: tuple[object, ...]) -> CollectorCursor:
        return CollectorCursor(
            source_type=row[0],
            source_id=row[1],
            last_seen_message_id=row[2],
            last_poll_at=row[3],
            last_status=row[4],
            last_error=row[5],
        )

    def _collect_record_from_row(self, row: tuple[object, ...]) -> CollectQueueRecord:
        shares = [ShareLink(**share) for share in json.loads(row[7])]
        return CollectQueueRecord(
            id=row[0],
            source_type=row[1],
            source_id=row[2],
            message_id=row[3],
            message_url=row[4],
            message_text=row[5],
            published_at=row[6],
            shares_json=shares,
            status=row[8],
            attempt_count=row[9],
            last_error=row[10],
            created_at=row[11],
            updated_at=row[12],
        )

    def _transfer_record_from_row(self, row: tuple[object, ...]) -> TransferQueueRecord:
        return TransferQueueRecord(
            id=row[0],
            share_code=row[1],
            receive_code=row[2],
            share_url=row[3],
            staging_cid=row[4],
            matched_rules_json=[TransferRuleContext(**item) for item in json.loads(row[5])],
            source_messages_json=[TransferSourceMessage(**item) for item in json.loads(row[6])],
            status=row[7],
            attempt_count=row[8],
            last_error=row[9],
            created_at=row[10],
            updated_at=row[11],
        )

    def _merge_unique_contexts(self, existing: list[dict[str, object]], new_item: dict[str, object]) -> list[dict[str, object]]:
        if new_item not in existing:
            existing.append(new_item)
        return existing

