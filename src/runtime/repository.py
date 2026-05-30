from __future__ import annotations

import sqlite3
from pathlib import Path

from src.db import connect, migrate

from .models import (
    RuntimeComponentRecord,
    RuntimeDesiredState,
    RuntimeExecutionStatus,
    RuntimeStateRecord,
    RuntimeWorkerHeartbeatRecord,
)


_MAX_ERROR_LENGTH = 500


def _sanitize_error(error: str | None) -> str | None:
    if error is None:
        return None
    single_line = " ".join(error.split())
    if len(single_line) <= _MAX_ERROR_LENGTH:
        return single_line
    return single_line[: _MAX_ERROR_LENGTH - 3] + "..."


class RuntimeControlRepository:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)

    def init_schema(self) -> None:
        migrate(self._db_path)

    def get_state(self) -> RuntimeStateRecord:
        connection = connect(self._db_path)
        try:
            row = connection.execute(
                """
                SELECT desired_state, started_at, stopped_at, updated_at
                FROM runtime_control
                WHERE id = 1
                """
            ).fetchone()
            if row is None:
                raise RuntimeError("runtime_control schema is not initialized")
            return RuntimeStateRecord(
                desired_state=row[0],
                started_at=row[1],
                stopped_at=row[2],
                updated_at=row[3],
            )
        finally:
            connection.close()

    def start(self) -> tuple[RuntimeStateRecord, bool]:
        return self._set_desired_state("running")

    def stop(self) -> tuple[RuntimeStateRecord, bool]:
        return self._set_desired_state("stopped")

    def save_component_status(
        self,
        *,
        name: str,
        status: RuntimeExecutionStatus,
        enabled: bool,
        configured: bool,
        started_at: str | None = None,
        finished_at: str | None = None,
        success: bool | None = None,
        error: str | None = None,
        tick_count: int | None = None,
    ) -> RuntimeComponentRecord:
        connection = connect(self._db_path)
        try:
            connection.execute(
                """
                INSERT INTO runtime_components (
                    name, status, enabled, configured, started_at, finished_at,
                    success, error, tick_count, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, 0), CURRENT_TIMESTAMP)
                ON CONFLICT(name) DO UPDATE SET
                    status = excluded.status,
                    enabled = excluded.enabled,
                    configured = excluded.configured,
                    started_at = excluded.started_at,
                    finished_at = excluded.finished_at,
                    success = excluded.success,
                    error = excluded.error,
                    tick_count = CASE
                        WHEN ? IS NULL THEN runtime_components.tick_count
                        ELSE excluded.tick_count
                    END,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    name,
                    status,
                    int(enabled),
                    int(configured),
                    started_at,
                    finished_at,
                    None if success is None else int(success),
                    _sanitize_error(error),
                    tick_count,
                    tick_count,
                ),
            )
            connection.commit()
            record = self._get_component_status(connection, name)
            if record is None:
                raise RuntimeError("runtime component status was not persisted")
            return record
        finally:
            connection.close()

    def increment_component_tick(self, name: str, amount: int = 1) -> RuntimeComponentRecord:
        connection = connect(self._db_path)
        try:
            connection.execute(
                """
                INSERT INTO runtime_components (name, status, enabled, configured, tick_count, updated_at)
                VALUES (?, 'idle', 0, 0, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(name) DO UPDATE SET
                    tick_count = runtime_components.tick_count + excluded.tick_count,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (name, amount),
            )
            connection.commit()
            record = self._get_component_status(connection, name)
            if record is None:
                raise RuntimeError("runtime component tick was not persisted")
            return record
        finally:
            connection.close()

    def get_component_status(self, name: str) -> RuntimeComponentRecord | None:
        connection = connect(self._db_path)
        try:
            return self._get_component_status(connection, name)
        finally:
            connection.close()

    def list_component_statuses(self) -> list[RuntimeComponentRecord]:
        connection = connect(self._db_path)
        try:
            rows = connection.execute(
                """
                SELECT name, status, enabled, configured, started_at, finished_at,
                       success, error, tick_count, updated_at
                FROM runtime_components
                ORDER BY name
                """
            ).fetchall()
            return [self._component_record_from_row(row) for row in rows]
        finally:
            connection.close()

    def save_worker_heartbeat(
        self,
        *,
        worker_name: str,
        component_name: str,
        status: RuntimeExecutionStatus,
        pid: int | None = None,
        error: str | None = None,
    ) -> RuntimeWorkerHeartbeatRecord:
        connection = connect(self._db_path)
        try:
            connection.execute(
                """
                INSERT INTO runtime_worker_heartbeats (
                    worker_name, component_name, status, pid, error, heartbeat_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(worker_name) DO UPDATE SET
                    component_name = excluded.component_name,
                    status = excluded.status,
                    pid = excluded.pid,
                    error = excluded.error,
                    heartbeat_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (worker_name, component_name, status, pid, _sanitize_error(error)),
            )
            connection.commit()
            record = self._get_worker_heartbeat(connection, worker_name)
            if record is None:
                raise RuntimeError("runtime worker heartbeat was not persisted")
            return record
        finally:
            connection.close()

    def get_worker_heartbeat(self, worker_name: str) -> RuntimeWorkerHeartbeatRecord | None:
        connection = connect(self._db_path)
        try:
            return self._get_worker_heartbeat(connection, worker_name)
        finally:
            connection.close()

    def list_worker_heartbeats(self) -> list[RuntimeWorkerHeartbeatRecord]:
        connection = connect(self._db_path)
        try:
            rows = connection.execute(
                """
                SELECT worker_name, component_name, status, pid, error, heartbeat_at, updated_at
                FROM runtime_worker_heartbeats
                ORDER BY worker_name
                """
            ).fetchall()
            return [self._worker_heartbeat_record_from_row(row) for row in rows]
        finally:
            connection.close()

    def enqueue_manual_trigger(self, *, event_name: str, source: str = "api") -> int:
        """前端经 API 入队一次手动触发，返回新行 id。worker 会在下个 tick 认领。"""
        connection = connect(self._db_path)
        try:
            cursor = connection.execute(
                """
                INSERT INTO runtime_manual_triggers (event_name, source)
                VALUES (?, ?)
                """,
                (event_name, source),
            )
            connection.commit()
            return int(cursor.lastrowid)
        finally:
            connection.close()

    def claim_pending_manual_triggers(self) -> list[tuple[int, str, str]]:
        """认领所有未消费的手动触发并标记 consumed，返回 (id, event_name, source) 列表。

        ``BEGIN IMMEDIATE`` 防止多进程重复认领；标记后即从 pending 视图消失。
        """
        connection = connect(self._db_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """
                SELECT id, event_name, source
                FROM runtime_manual_triggers
                WHERE consumed_at IS NULL
                ORDER BY id ASC
                """
            ).fetchall()
            if not rows:
                connection.rollback()
                return []
            ids = [int(row[0]) for row in rows]
            placeholders = ",".join("?" for _ in ids)
            connection.execute(
                f"""
                UPDATE runtime_manual_triggers
                SET consumed_at = CURRENT_TIMESTAMP
                WHERE id IN ({placeholders})
                """,
                tuple(ids),
            )
            connection.commit()
            return [(int(row[0]), str(row[1]), str(row[2])) for row in rows]
        finally:
            connection.close()

    def _set_desired_state(self, desired_state: RuntimeDesiredState) -> tuple[RuntimeStateRecord, bool]:
        current = self.get_state()
        changed = current.desired_state != desired_state
        if not changed:
            return current, False

        connection = connect(self._db_path)
        try:
            if desired_state == "running":
                connection.execute(
                    """
                    UPDATE runtime_control
                    SET desired_state = 'running',
                        started_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1
                    """
                )
            else:
                connection.execute(
                    """
                    UPDATE runtime_control
                    SET desired_state = 'stopped',
                        stopped_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1
                    """
                )
            connection.commit()
        finally:
            connection.close()
        return self.get_state(), True

    def _get_component_status(
        self, connection: sqlite3.Connection, name: str
    ) -> RuntimeComponentRecord | None:
        row = connection.execute(
            """
            SELECT name, status, enabled, configured, started_at, finished_at,
                   success, error, tick_count, updated_at
            FROM runtime_components
            WHERE name = ?
            """,
            (name,),
        ).fetchone()
        if row is None:
            return None
        return self._component_record_from_row(row)

    @staticmethod
    def _component_record_from_row(row: sqlite3.Row | tuple[object, ...]) -> RuntimeComponentRecord:
        return RuntimeComponentRecord(
            name=str(row[0]),
            status=row[1],
            enabled=bool(row[2]),
            configured=bool(row[3]),
            started_at=row[4],
            finished_at=row[5],
            success=None if row[6] is None else bool(row[6]),
            error=row[7],
            tick_count=int(row[8]),
            updated_at=str(row[9]),
        )

    def _get_worker_heartbeat(
        self, connection: sqlite3.Connection, worker_name: str
    ) -> RuntimeWorkerHeartbeatRecord | None:
        row = connection.execute(
            """
            SELECT worker_name, component_name, status, pid, error, heartbeat_at, updated_at
            FROM runtime_worker_heartbeats
            WHERE worker_name = ?
            """,
            (worker_name,),
        ).fetchone()
        if row is None:
            return None
        return self._worker_heartbeat_record_from_row(row)

    @staticmethod
    def _worker_heartbeat_record_from_row(
        row: sqlite3.Row | tuple[object, ...]
    ) -> RuntimeWorkerHeartbeatRecord:
        return RuntimeWorkerHeartbeatRecord(
            worker_name=str(row[0]),
            component_name=str(row[1]),
            status=row[2],
            pid=None if row[3] is None else int(row[3]),
            error=row[4],
            heartbeat_at=str(row[5]),
            updated_at=str(row[6]),
        )
