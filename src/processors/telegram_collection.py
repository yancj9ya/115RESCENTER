from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.collectors.shares import parse_115_shares
from src.queue import FAILED, SUCCESS, ShareLink

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TelegramCollectionResult:
    source_type: str
    source_id: str
    scanned: int
    parsed_shares: int
    enqueued: int
    skipped_existing: int
    cursor: int | None
    status: str
    error: str | None = None


class TelegramCollectionService:
    def __init__(self, *, repository: Any, fetcher: Any, source_type: str, source_id: str) -> None:
        self._repository = repository
        self._fetcher = fetcher
        self._source_type = source_type
        self._source_id = source_id

    def poll_once(self) -> TelegramCollectionResult:
        prior_cursor = self._get_cursor()
        safe_cursor = prior_cursor
        scanned = 0
        parsed_shares = 0
        enqueued = 0
        skipped_existing = 0

        logger.info(f"开始采集: source_id={self._source_id}, cursor={prior_cursor}")

        try:
            messages = self._fetch_messages(prior_cursor)
            existing_keys = self._existing_message_keys()
            process_all = bool(existing_keys)
            pending_messages = [
                message
                for message in sorted(messages, key=lambda item: self._message_id_as_int(item))
                if process_all or prior_cursor is None or self._message_id_as_int(message) > prior_cursor
            ]

            for message in pending_messages:
                message_id = self._message_id_as_int(message)
                scanned += 1
                shares = parse_115_shares(str(getattr(message, "text", "")))
                parsed_shares += len(shares)

                if shares:
                    key = (self._source_type, self._source_id, str(message_id))
                    existed_before = key in existing_keys
                    self._enqueue_message(message, shares)
                    if existed_before:
                        skipped_existing += 1
                    else:
                        enqueued += 1
                        existing_keys.add(key)

                safe_cursor = message_id

            self._upsert_cursor(safe_cursor, SUCCESS, None)
            logger.info(
                f"采集完成: source_id={self._source_id}, scanned={scanned}, "
                f"parsed_shares={parsed_shares}, enqueued={enqueued}, "
                f"skipped_existing={skipped_existing}, cursor={safe_cursor}"
            )
            return TelegramCollectionResult(
                source_type=self._source_type,
                source_id=self._source_id,
                scanned=scanned,
                parsed_shares=parsed_shares,
                enqueued=enqueued,
                skipped_existing=skipped_existing,
                cursor=safe_cursor,
                status=SUCCESS,
            )
        except Exception as exc:
            error = str(exc)
            logger.error(f"采集失败: source_id={self._source_id}, error={error}")
            self._upsert_cursor(safe_cursor, FAILED, error)
            return TelegramCollectionResult(
                source_type=self._source_type,
                source_id=self._source_id,
                scanned=scanned,
                parsed_shares=parsed_shares,
                enqueued=enqueued,
                skipped_existing=skipped_existing,
                cursor=safe_cursor,
                status=FAILED,
                error=error,
            )

    def _fetch_messages(self, cursor: int | None) -> list[Any]:
        if hasattr(self._fetcher, "fetch_messages"):
            return list(self._fetcher.fetch_messages(self._source_id, cursor=cursor))
        if hasattr(self._fetcher, "collect_history"):
            collected = self._fetcher.collect_history(self._source_id)
            if inspect.isawaitable(collected):
                raise RuntimeError("async collection requires an async caller")
            return list(collected)
        raise TypeError("fetcher must provide fetch_messages")

    def _get_cursor(self) -> int | None:
        try:
            cursor = self._repository.get_collector_cursor(source_type=self._source_type, source_id=self._source_id)
        except TypeError:
            cursor = self._repository.get_collector_cursor(self._source_type, self._source_id)

        if cursor is None:
            return None
        if isinstance(cursor, int):
            return cursor
        value = getattr(cursor, "last_seen_message_id", None)
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _upsert_cursor(self, cursor: int | None, status: str, error: str | None) -> None:
        stored_cursor = 0 if cursor is None else cursor
        try:
            self._repository.upsert_collector_cursor(
                source_type=self._source_type,
                source_id=self._source_id,
                last_seen_message_id=None if cursor is None else str(cursor),
                last_poll_at=datetime.now(timezone.utc).isoformat(),
                last_status=status,
                last_error=error,
            )
        except TypeError:
            self._repository.upsert_collector_cursor(
                self._source_type,
                self._source_id,
                stored_cursor,
                status=status,
                error=error,
            )

    def _enqueue_message(self, message: Any, shares: list[Any]) -> Any:
        return self._repository.enqueue_collected_message(
            source_type=self._source_type,
            source_id=self._source_id,
            message_id=str(self._message_id_as_int(message)),
            message_url=getattr(message, "message_url", None),
            message_text=str(getattr(message, "text", "")),
            published_at=self._format_published_at(getattr(message, "published_at", None)),
            shares=[
                ShareLink(
                    share_code=share.share_code,
                    receive_code=share.receive_code,
                    share_url=share.share_url,
                )
                for share in shares
            ],
        )

    def _existing_message_keys(self) -> set[tuple[str, str, str]]:
        enqueued = getattr(self._repository, "enqueued", None)
        if isinstance(enqueued, dict):
            return {key for key in enqueued if key[0] == self._source_type and key[1] == self._source_id}
        return set()

    @staticmethod
    def _message_id_as_int(message: Any) -> int:
        return int(getattr(message, "message_id"))

    @staticmethod
    def _format_published_at(value: Any) -> str | None:
        if value is None:
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)
