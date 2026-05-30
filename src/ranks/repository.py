from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.db import connect, migrate


@dataclass(frozen=True)
class RankCacheRecord:
    source: str
    key: str
    items: list[dict[str, Any]]
    status: str
    error: str | None
    refreshed_at: str | None


class RankCacheRepository:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)

    def init_schema(self) -> None:
        migrate(self._db_path)

    def upsert(
        self,
        *,
        source: str,
        key: str,
        items: list[dict[str, Any]],
        status: str,
        error: str | None,
    ) -> RankCacheRecord:
        connection = connect(self._db_path)
        try:
            connection.execute(
                """
                INSERT INTO rank_cache (source, key, items_json, status, error, refreshed_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(source, key) DO UPDATE SET
                    items_json = excluded.items_json,
                    status = excluded.status,
                    error = excluded.error,
                    refreshed_at = CURRENT_TIMESTAMP
                """,
                (source, key, json.dumps(items, ensure_ascii=False), status, error),
            )
            connection.commit()
            row = connection.execute(
                """
                SELECT source, key, items_json, status, error, refreshed_at
                FROM rank_cache
                WHERE source = ? AND key = ?
                """,
                (source, key),
            ).fetchone()
            return self._record_from_row(row)
        finally:
            connection.close()

    def get(self, *, source: str, key: str) -> RankCacheRecord | None:
        connection = connect(self._db_path)
        try:
            row = connection.execute(
                """
                SELECT source, key, items_json, status, error, refreshed_at
                FROM rank_cache
                WHERE source = ? AND key = ?
                """,
                (source, key),
            ).fetchone()
            return self._record_from_row(row) if row is not None else None
        finally:
            connection.close()

    def get_all(self) -> list[RankCacheRecord]:
        connection = connect(self._db_path)
        try:
            rows = connection.execute(
                """
                SELECT source, key, items_json, status, error, refreshed_at
                FROM rank_cache
                ORDER BY source ASC, key ASC
                """
            ).fetchall()
            return [self._record_from_row(row) for row in rows]
        finally:
            connection.close()

    def oldest_refreshed_at(self) -> str | None:
        connection = connect(self._db_path)
        try:
            row = connection.execute("SELECT MIN(refreshed_at) FROM rank_cache").fetchone()
            return row[0] if row is not None else None
        finally:
            connection.close()

    def count(self) -> int:
        connection = connect(self._db_path)
        try:
            row = connection.execute("SELECT COUNT(*) FROM rank_cache").fetchone()
            return int(row[0]) if row is not None else 0
        finally:
            connection.close()

    def _record_from_row(self, row: tuple[object, ...]) -> RankCacheRecord:
        return RankCacheRecord(
            source=str(row[0]),
            key=str(row[1]),
            items=json.loads(str(row[2])),
            status=str(row[3]),
            error=row[4] if row[4] is None else str(row[4]),
            refreshed_at=row[5] if row[5] is None else str(row[5]),
        )
