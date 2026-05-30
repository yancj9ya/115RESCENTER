from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any, Final

from src.db import connect, migrate

RUNNING: Final[str] = "RUNNING"
SUCCESS: Final[str] = "SUCCESS"
PARTIAL_SUCCESS: Final[str] = "PARTIAL_SUCCESS"
FAILED: Final[str] = "FAILED"
CANCELLED: Final[str] = "CANCELLED"

PLANNED: Final[str] = "PLANNED"
SKIPPED_DIR: Final[str] = "SKIPPED_DIR"
SKIPPED_UNMATCHED: Final[str] = "SKIPPED_UNMATCHED"
SKIPPED_DUPLICATE: Final[str] = "SKIPPED_DUPLICATE"

ORGANIZE_RUN_STATUSES: Final[tuple[str, ...]] = (RUNNING, SUCCESS, PARTIAL_SUCCESS, FAILED, CANCELLED)
ORGANIZE_RUN_ITEM_STATUSES: Final[tuple[str, ...]] = (
    PLANNED,
    SKIPPED_DIR,
    SKIPPED_UNMATCHED,
    SKIPPED_DUPLICATE,
    SUCCESS,
    FAILED,
)


@dataclass(frozen=True)
class OrganizeRunRecord:
    id: int
    staging_cid: int
    status: str = RUNNING
    planned_count: int = 0
    success_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    last_error: str | None = None
    started_at: str = ""
    finished_at: str | None = None
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class OrganizeRunItemRecord:
    id: int
    run_id: int
    file_id: int
    file_name: str
    is_dir: bool = False
    status: str = PLANNED
    target_cid: int | None = None
    target_path: str | None = None
    new_name: str | None = None
    reason: str | None = None
    error: str | None = None
    metadata_json: str | None = None
    created_at: str = ""
    updated_at: str = ""


class OrganizeRepository:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)

    def init_schema(self) -> None:
        migrate(self._db_path)

    def create_run(self, staging_cid: int) -> OrganizeRunRecord:
        connection = connect(self._db_path)
        try:
            cursor = connection.execute(
                """
                INSERT INTO organize_runs (staging_cid, status)
                VALUES (?, ?)
                """,
                (staging_cid, RUNNING),
            )
            connection.commit()
            row = self._select_run_by_id(connection, cursor.lastrowid)
            return self._run_record_from_row(row)
        finally:
            connection.close()

    def finish_run(
        self,
        run_id: int,
        *,
        planned_count: int,
        success_count: int,
        skipped_count: int,
        failed_count: int,
        status: str,
        error: str | None = None,
    ) -> None:
        connection = connect(self._db_path)
        try:
            connection.execute(
                """
                UPDATE organize_runs
                SET planned_count = ?,
                    success_count = ?,
                    skipped_count = ?,
                    failed_count = ?,
                    status = ?,
                    last_error = ?,
                    finished_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (planned_count, success_count, skipped_count, failed_count, status, error, run_id),
            )
            connection.commit()
        finally:
            connection.close()

    def create_item(
        self,
        run_id: int,
        *,
        file_id: int,
        file_name: str,
        is_dir: bool = False,
        status: str = PLANNED,
        target_cid: int | None = None,
        target_path: str | None = None,
        new_name: str | None = None,
        reason: str | None = None,
        error: str | None = None,
        metadata: object | None = None,
    ) -> OrganizeRunItemRecord:
        metadata_json = self._serialize_metadata(metadata)
        connection = connect(self._db_path)
        try:
            cursor = connection.execute(
                """
                INSERT INTO organize_run_items (
                    run_id,
                    file_id,
                    file_name,
                    is_dir,
                    status,
                    target_cid,
                    target_path,
                    new_name,
                    reason,
                    error,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    file_id,
                    file_name,
                    int(is_dir),
                    status,
                    target_cid,
                    target_path,
                    new_name,
                    reason,
                    error,
                    metadata_json,
                ),
            )
            connection.commit()
            row = self._select_item_by_id(connection, cursor.lastrowid)
            return self._item_record_from_row(row)
        finally:
            connection.close()

    def mark_item_success(
        self,
        item_id: int,
        *,
        target_cid: int | None = None,
        target_path: str | None = None,
        new_name: str | None = None,
        reason: str | None = None,
        metadata: object | None = None,
    ) -> None:
        self._update_item_status(
            item_id,
            SUCCESS,
            target_cid=target_cid,
            target_path=target_path,
            new_name=new_name,
            reason=reason,
            error=None,
            metadata=metadata,
        )

    def mark_item_failed(self, item_id: int, error: str, *, metadata: object | None = None) -> None:
        self._update_item_status(
            item_id,
            FAILED,
            target_cid=None,
            target_path=None,
            new_name=None,
            reason=None,
            error=error,
            metadata=metadata,
        )

    def mark_item_skipped(
        self, item_id: int, *, status: str, reason: str, metadata: object | None = None
    ) -> None:
        self._update_item_status(
            item_id,
            status,
            target_cid=None,
            target_path=None,
            new_name=None,
            reason=reason,
            error=None,
            metadata=metadata,
        )

    def list_runs(self, limit: int, status: str | None = None) -> list[OrganizeRunRecord]:
        query = """
            SELECT id, staging_cid, status, planned_count, success_count, skipped_count,
                   failed_count, last_error, started_at, finished_at, created_at, updated_at
            FROM organize_runs
        """
        parameters: list[object] = []
        if status is not None:
            query += " WHERE status = ?"
            parameters.append(status)
        query += " ORDER BY id DESC LIMIT ?"
        parameters.append(limit)

        connection = connect(self._db_path)
        try:
            rows = connection.execute(query, tuple(parameters)).fetchall()
            return [self._run_record_from_row(row) for row in rows]
        finally:
            connection.close()

    def get_run(self, run_id: int) -> OrganizeRunRecord | None:
        connection = connect(self._db_path)
        try:
            row = self._select_run_by_id(connection, run_id)
            if row is None:
                return None
            return self._run_record_from_row(row)
        finally:
            connection.close()

    def list_run_items(self, run_id: int) -> list[OrganizeRunItemRecord]:
        connection = connect(self._db_path)
        try:
            rows = connection.execute(
                """
                SELECT id, run_id, file_id, file_name, is_dir, status, target_cid, target_path,
                       new_name, reason, error, metadata_json, created_at, updated_at
                FROM organize_run_items
                WHERE run_id = ?
                ORDER BY id ASC
                """,
                (run_id,),
            ).fetchall()
            return [self._item_record_from_row(row) for row in rows]
        finally:
            connection.close()

    def list_items(
        self, limit: int, status: str | None = None, keyword: str | None = None
    ) -> list[OrganizeRunItemRecord]:
        query = """
            SELECT id, run_id, file_id, file_name, is_dir, status, target_cid, target_path,
                   new_name, reason, error, metadata_json, created_at, updated_at
            FROM organize_run_items
        """
        conditions: list[str] = ["is_dir = 0"]
        parameters: list[object] = []
        if status is not None:
            conditions.append("status = ?")
            parameters.append(status)
        if keyword:
            like = f"%{keyword}%"
            conditions.append(
                "(file_name LIKE ? OR target_path LIKE ? OR new_name LIKE ? OR error LIKE ?)"
            )
            parameters.extend([like, like, like, like])
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY id DESC LIMIT ?"
        parameters.append(limit)

        connection = connect(self._db_path)
        try:
            rows = connection.execute(query, tuple(parameters)).fetchall()
            return [self._item_record_from_row(row) for row in rows]
        finally:
            connection.close()

    def get_latest_run(self) -> OrganizeRunRecord | None:
        connection = connect(self._db_path)
        try:
            row = connection.execute(
                """
                SELECT id, staging_cid, status, planned_count, success_count, skipped_count,
                       failed_count, last_error, started_at, finished_at, created_at, updated_at
                FROM organize_runs
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            return self._run_record_from_row(row)
        finally:
            connection.close()

    def delete_item(self, item_id: int) -> bool:
        connection = connect(self._db_path)
        try:
            cursor = connection.execute(
                "DELETE FROM organize_run_items WHERE id = ?",
                (item_id,),
            )
            connection.commit()
            return cursor.rowcount > 0
        finally:
            connection.close()

    def delete_all_items(self) -> int:
        connection = connect(self._db_path)
        try:
            cursor = connection.execute("DELETE FROM organize_run_items")
            connection.commit()
            return cursor.rowcount
        finally:
            connection.close()

    def get_status_counts(self) -> dict[str, int]:
        connection = connect(self._db_path)
        try:
            rows = connection.execute(
                """
                SELECT status, COUNT(*)
                FROM organize_runs
                GROUP BY status
                ORDER BY status ASC
                """
            ).fetchall()
            return {row[0]: row[1] for row in rows}
        finally:
            connection.close()

    def _update_item_status(
        self,
        item_id: int,
        status: str,
        *,
        target_cid: int | None,
        target_path: str | None,
        new_name: str | None,
        reason: str | None,
        error: str | None,
        metadata: object | None,
    ) -> None:
        metadata_json = self._serialize_metadata(metadata)
        connection = connect(self._db_path)
        try:
            if metadata is None:
                connection.execute(
                    """
                    UPDATE organize_run_items
                    SET status = ?,
                        target_cid = COALESCE(?, target_cid),
                        target_path = COALESCE(?, target_path),
                        new_name = COALESCE(?, new_name),
                        reason = COALESCE(?, reason),
                        error = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (status, target_cid, target_path, new_name, reason, error, item_id),
                )
            else:
                connection.execute(
                    """
                    UPDATE organize_run_items
                    SET status = ?,
                        target_cid = COALESCE(?, target_cid),
                        target_path = COALESCE(?, target_path),
                        new_name = COALESCE(?, new_name),
                        reason = COALESCE(?, reason),
                        error = ?,
                        metadata_json = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (status, target_cid, target_path, new_name, reason, error, metadata_json, item_id),
                )
            connection.commit()
        finally:
            connection.close()

    def _select_run_by_id(self, connection: sqlite3.Connection, run_id: int) -> tuple[object, ...] | None:
        return connection.execute(
            """
            SELECT id, staging_cid, status, planned_count, success_count, skipped_count,
                   failed_count, last_error, started_at, finished_at, created_at, updated_at
            FROM organize_runs
            WHERE id = ?
            """,
            (run_id,),
        ).fetchone()

    def _select_item_by_id(self, connection: sqlite3.Connection, item_id: int) -> tuple[object, ...] | None:
        return connection.execute(
            """
            SELECT id, run_id, file_id, file_name, is_dir, status, target_cid, target_path,
                   new_name, reason, error, metadata_json, created_at, updated_at
            FROM organize_run_items
            WHERE id = ?
            """,
            (item_id,),
        ).fetchone()

    def _run_record_from_row(self, row: tuple[object, ...]) -> OrganizeRunRecord:
        return OrganizeRunRecord(
            id=row[0],
            staging_cid=row[1],
            status=row[2],
            planned_count=row[3],
            success_count=row[4],
            skipped_count=row[5],
            failed_count=row[6],
            last_error=row[7],
            started_at=row[8],
            finished_at=row[9],
            created_at=row[10],
            updated_at=row[11],
        )

    def _item_record_from_row(self, row: tuple[object, ...]) -> OrganizeRunItemRecord:
        return OrganizeRunItemRecord(
            id=row[0],
            run_id=row[1],
            file_id=row[2],
            file_name=row[3],
            is_dir=bool(row[4]),
            status=row[5],
            target_cid=row[6],
            target_path=row[7],
            new_name=row[8],
            reason=row[9],
            error=row[10],
            metadata_json=row[11],
            created_at=row[12],
            updated_at=row[13],
        )

    def _serialize_metadata(self, metadata: object | None) -> str | None:
        if metadata is None:
            return None
        if is_dataclass(metadata) and not isinstance(metadata, type):
            metadata = asdict(metadata)
        elif hasattr(metadata, "__dict__") and not isinstance(metadata, dict):
            metadata = vars(metadata)
        return json.dumps(metadata, ensure_ascii=False, sort_keys=True, default=self._json_default)

    def _json_default(self, value: Any) -> object:
        if is_dataclass(value) and not isinstance(value, type):
            return asdict(value)
        if hasattr(value, "__dict__"):
            return vars(value)
        raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
