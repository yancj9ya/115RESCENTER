from __future__ import annotations

from pathlib import Path

from src.db import connect, migrate

from .models import TelegramWebChannelRecord


class TelegramWebChannelRepository:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)

    def init_schema(self) -> None:
        migrate(self._db_path)

    def create_channel(
        self,
        *,
        channel: str,
        display_name: str | None = None,
        enabled: bool = True,
        poll_interval_seconds: int = 1800,
    ) -> TelegramWebChannelRecord:
        connection = connect(self._db_path)
        try:
            connection.execute(
                """
                INSERT INTO telegram_web_channels (
                    channel,
                    display_name,
                    enabled,
                    poll_interval_seconds
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    channel,
                    display_name,
                    self._enabled_to_int(enabled),
                    poll_interval_seconds,
                ),
            )
            connection.commit()
            row = connection.execute(
                """
                SELECT channel, display_name, enabled, poll_interval_seconds, created_at, updated_at
                FROM telegram_web_channels
                WHERE channel = ?
                """,
                (channel,),
            ).fetchone()
            return self._channel_from_row(row)
        finally:
            connection.close()

    def list_channels(self) -> list[TelegramWebChannelRecord]:
        connection = connect(self._db_path)
        try:
            rows = connection.execute(
                """
                SELECT channel, display_name, enabled, poll_interval_seconds, created_at, updated_at
                FROM telegram_web_channels
                ORDER BY channel ASC
                """
            ).fetchall()
            return [self._channel_from_row(row) for row in rows]
        finally:
            connection.close()

    def get_channel(self, channel: str) -> TelegramWebChannelRecord | None:
        connection = connect(self._db_path)
        try:
            row = connection.execute(
                """
                SELECT channel, display_name, enabled, poll_interval_seconds, created_at, updated_at
                FROM telegram_web_channels
                WHERE channel = ?
                """,
                (channel,),
            ).fetchone()
            if row is None:
                return None
            return self._channel_from_row(row)
        finally:
            connection.close()

    def update_channel(
        self,
        channel: str,
        *,
        display_name: str | None = None,
        enabled: bool | None = None,
        poll_interval_seconds: int | None = None,
    ) -> TelegramWebChannelRecord | None:
        current = self.get_channel(channel)
        if current is None:
            return None

        next_display_name = current.display_name if display_name is None else display_name
        next_enabled = current.enabled if enabled is None else enabled
        next_poll_interval_seconds = (
            current.poll_interval_seconds if poll_interval_seconds is None else poll_interval_seconds
        )

        connection = connect(self._db_path)
        try:
            connection.execute(
                """
                UPDATE telegram_web_channels
                SET display_name = ?,
                    enabled = ?,
                    poll_interval_seconds = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE channel = ?
                """,
                (
                    next_display_name,
                    self._enabled_to_int(next_enabled),
                    next_poll_interval_seconds,
                    channel,
                ),
            )
            connection.commit()
            row = connection.execute(
                """
                SELECT channel, display_name, enabled, poll_interval_seconds, created_at, updated_at
                FROM telegram_web_channels
                WHERE channel = ?
                """,
                (channel,),
            ).fetchone()
            return self._channel_from_row(row)
        finally:
            connection.close()

    def delete_channel(self, channel: str) -> bool:
        connection = connect(self._db_path)
        try:
            cursor = connection.execute(
                """
                DELETE FROM telegram_web_channels
                WHERE channel = ?
                """,
                (channel,),
            )
            connection.commit()
            return cursor.rowcount > 0
        finally:
            connection.close()

    def _channel_from_row(self, row: tuple[object, ...]) -> TelegramWebChannelRecord:
        return TelegramWebChannelRecord(
            channel=row[0],
            display_name=row[1],
            enabled=bool(row[2]),
            poll_interval_seconds=row[3],
            created_at=row[4],
            updated_at=row[5],
        )

    def _enabled_to_int(self, enabled: bool) -> int:
        return 1 if enabled else 0
