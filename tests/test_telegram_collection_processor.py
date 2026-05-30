from __future__ import annotations

import importlib
import inspect
import unittest
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime

from src.queue import ShareLink


@dataclass(frozen=True)
class FakeTelegramMessage:
    message_id: int
    text: str
    message_url: str = ""
    published_at: datetime | None = None


class FakeTelegramFetcher:
    def __init__(self, messages: list[FakeTelegramMessage] | None = None, error: Exception | None = None) -> None:
        self.messages = messages or []
        self.error = error
        self.calls: list[tuple[str, int | None]] = []

    def fetch_messages(self, source_id: str, cursor: int | None = None) -> list[FakeTelegramMessage]:
        self.calls.append((source_id, cursor))
        if self.error is not None:
            raise self.error
        return list(self.messages)


class FakeCollectorCursorRepository:
    def __init__(self, cursor: int | None = None, enqueue_error_at: str | None = None) -> None:
        self.cursor = cursor
        self.enqueue_error_at = enqueue_error_at
        self.enqueued: dict[tuple[str, str, str], dict[str, object]] = {}
        self.cursor_updates: list[tuple[str, str, int, str, str | None]] = []

    def get_collector_cursor(self, source_type: str, source_id: str) -> int | None:
        return self.cursor

    def upsert_collector_cursor(
        self,
        source_type: str,
        source_id: str,
        cursor: int,
        *,
        status: str,
        error: str | None = None,
    ) -> None:
        self.cursor = cursor
        self.cursor_updates.append((source_type, source_id, cursor, status, error))

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
    ) -> object:
        if message_id == self.enqueue_error_at:
            raise RuntimeError(f"enqueue exploded at {message_id}")
        key = (source_type, source_id, message_id)
        if key in self.enqueued:
            return self.enqueued[key]
        record = {
            "source_type": source_type,
            "source_id": source_id,
            "message_id": message_id,
            "message_url": message_url,
            "message_text": message_text,
            "published_at": published_at,
            "shares": shares,
        }
        self.enqueued[key] = record
        return record


def message(message_id: int, text: str) -> FakeTelegramMessage:
    return FakeTelegramMessage(
        message_id=message_id,
        text=text,
        message_url=f"https://t.me/s/movie_channel/{message_id}",
        published_at=datetime(2026, 5, 26, 10, message_id % 60, 0),
    )


def share_text(code: str) -> str:
    return f"movie release https://115.com/s/{code}?password=r1"


class TelegramCollectionProcessorContractTest(unittest.TestCase):
    def test_result_dataclass_contract(self) -> None:
        from src.processors.telegram_collection import TelegramCollectionResult

        self.assertTrue(is_dataclass(TelegramCollectionResult))
        self.assertEqual(
            [field.name for field in fields(TelegramCollectionResult)],
            [
                "source_type",
                "source_id",
                "scanned",
                "parsed_shares",
                "enqueued",
                "skipped_existing",
                "cursor",
                "status",
                "error",
            ],
        )
        result = TelegramCollectionResult(
            source_type="telegram_web",
            source_id="movie_channel",
            scanned=0,
            parsed_shares=0,
            enqueued=0,
            skipped_existing=0,
            cursor=None,
            status="SUCCESS",
        )
        self.assertEqual(result.source_type, "telegram_web")
        self.assertEqual(result.source_id, "movie_channel")
        self.assertEqual(result.scanned, 0)
        self.assertEqual(result.parsed_shares, 0)
        self.assertEqual(result.enqueued, 0)
        self.assertEqual(result.skipped_existing, 0)
        self.assertIsNone(result.cursor)
        self.assertEqual(result.status, "SUCCESS")
        self.assertIsNone(result.error)

    def test_processor_module_import_is_side_effect_free(self) -> None:
        module = importlib.import_module("src.processors.telegram_collection")

        self.assertTrue(hasattr(module, "TelegramCollectionService"))
        self.assertTrue(hasattr(module, "TelegramCollectionResult"))

    def test_module_has_no_forbidden_runtime_dependencies(self) -> None:
        import src.processors.telegram_collection as telegram_collection

        source = inspect.getsource(telegram_collection)
        forbidden = [
            "Storage115Service",
            "save_share",
            "TransferQueueProcessor",
            "SubscriptionMatcher",
            "tmdb",
            "notification",
            "Telethon",
            "scheduler",
            "daemon",
            "P115_COOKIES",
        ]
        for text in forbidden:
            self.assertNotIn(text, source)


class TelegramCollectionProcessorBehaviorTest(unittest.TestCase):
    def make_service(
        self,
        *,
        messages: list[FakeTelegramMessage],
        cursor: int | None = None,
        fetch_error: Exception | None = None,
        enqueue_error_at: str | None = None,
    ):
        from src.processors.telegram_collection import TelegramCollectionService

        repository = FakeCollectorCursorRepository(cursor=cursor, enqueue_error_at=enqueue_error_at)
        fetcher = FakeTelegramFetcher(messages=messages, error=fetch_error)
        service = TelegramCollectionService(
            repository=repository,
            fetcher=fetcher,
            source_type="telegram_web",
            source_id="movie_channel",
        )
        return service, repository, fetcher

    def test_first_run_scans_three_messages_enqueues_two_shares_and_advances_cursor(self) -> None:
        service, repository, fetcher = self.make_service(
            messages=[message(100, share_text("a100")), message(101, "no share here"), message(102, share_text("a102"))]
        )

        result = service.poll_once()

        self.assertEqual(fetcher.calls, [("movie_channel", None)])
        self.assertEqual(result.source_type, "telegram_web")
        self.assertEqual(result.source_id, "movie_channel")
        self.assertEqual(result.scanned, 3)
        self.assertEqual(result.parsed_shares, 2)
        self.assertEqual(result.enqueued, 2)
        self.assertEqual(result.skipped_existing, 0)
        self.assertEqual(result.cursor, 102)
        self.assertEqual(result.status, "SUCCESS")
        self.assertIsNone(result.error)
        self.assertEqual(sorted(key[2] for key in repository.enqueued), ["100", "102"])
        self.assertEqual(repository.cursor, 102)
        self.assertEqual(repository.cursor_updates[-1], ("telegram_web", "movie_channel", 102, "SUCCESS", None))

    def test_idempotent_second_run_skips_existing_share_messages_and_keeps_cursor(self) -> None:
        service, repository, _fetcher = self.make_service(
            messages=[message(100, share_text("a100")), message(101, "no share here"), message(102, share_text("a102"))]
        )
        first = service.poll_once()
        self.assertEqual(first.status, "SUCCESS")

        second = service.poll_once()

        self.assertEqual(second.scanned, 3)
        self.assertEqual(second.parsed_shares, 2)
        self.assertEqual(second.enqueued, 0)
        self.assertEqual(second.skipped_existing, 2)
        self.assertEqual(second.cursor, 102)
        self.assertEqual(second.status, "SUCCESS")
        self.assertIsNone(second.error)
        self.assertEqual(len(repository.enqueued), 2)
        self.assertEqual(repository.cursor, 102)

    def test_existing_cursor_only_enqueues_newer_messages_and_advances_to_newest_seen(self) -> None:
        service, repository, fetcher = self.make_service(
            cursor=102,
            messages=[message(101, share_text("a101")), message(102, share_text("a102")), message(103, share_text("a103"))],
        )

        result = service.poll_once()

        self.assertEqual(fetcher.calls, [("movie_channel", 102)])
        self.assertEqual(result.scanned, 1)
        self.assertEqual(result.parsed_shares, 1)
        self.assertEqual(result.enqueued, 1)
        self.assertEqual(result.skipped_existing, 0)
        self.assertEqual(result.cursor, 103)
        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(sorted(key[2] for key in repository.enqueued), ["103"])
        self.assertEqual(repository.cursor, 103)

    def test_messages_without_shares_are_scanned_and_can_advance_cursor(self) -> None:
        service, repository, _fetcher = self.make_service(cursor=102, messages=[message(103, "still no share")])

        result = service.poll_once()

        self.assertEqual(result.scanned, 1)
        self.assertEqual(result.parsed_shares, 0)
        self.assertEqual(result.enqueued, 0)
        self.assertEqual(result.skipped_existing, 0)
        self.assertEqual(result.cursor, 103)
        self.assertEqual(result.status, "SUCCESS")
        self.assertIsNone(result.error)
        self.assertEqual(repository.enqueued, {})
        self.assertEqual(repository.cursor, 103)

    def test_fetch_failure_records_failed_status_error_and_preserves_prior_cursor(self) -> None:
        service, repository, _fetcher = self.make_service(cursor=102, messages=[], fetch_error=RuntimeError("channel exploded"))

        result = service.poll_once()

        self.assertEqual(result.scanned, 0)
        self.assertEqual(result.parsed_shares, 0)
        self.assertEqual(result.enqueued, 0)
        self.assertEqual(result.skipped_existing, 0)
        self.assertEqual(result.cursor, 102)
        self.assertEqual(result.status, "FAILED")
        self.assertIn("channel exploded", result.error or "")
        self.assertEqual(repository.cursor, 102)
        self.assertEqual(repository.cursor_updates[-1], ("telegram_web", "movie_channel", 102, "FAILED", "channel exploded"))

    def test_enqueue_failure_does_not_advance_cursor_beyond_last_fully_reconciled_message(self) -> None:
        service, repository, _fetcher = self.make_service(
            cursor=100,
            messages=[message(101, share_text("a101")), message(102, share_text("a102")), message(103, share_text("a103"))],
            enqueue_error_at="102",
        )

        result = service.poll_once()

        self.assertEqual(result.scanned, 2)
        self.assertEqual(result.parsed_shares, 2)
        self.assertEqual(result.enqueued, 1)
        self.assertEqual(result.skipped_existing, 0)
        self.assertEqual(result.cursor, 101)
        self.assertEqual(result.status, "FAILED")
        self.assertIn("enqueue exploded at 102", result.error or "")
        self.assertEqual(sorted(key[2] for key in repository.enqueued), ["101"])
        self.assertEqual(repository.cursor, 101)
        self.assertEqual(repository.cursor_updates[-1], ("telegram_web", "movie_channel", 101, "FAILED", "enqueue exploded at 102"))

    def test_poll_once_logs_start_and_completion_summary(self) -> None:
        service, _repository, _fetcher = self.make_service(
            messages=[message(100, share_text("a100")), message(101, "no share"), message(102, share_text("a102"))]
        )

        with self.assertLogs("src.processors.telegram_collection", level="INFO") as captured:
            service.poll_once()

        joined = "\n".join(captured.output)
        self.assertIn("movie_channel", joined)
        self.assertIn("scanned=3", joined)
        self.assertIn("enqueued=2", joined)

    def test_poll_once_logs_error_on_fetch_failure(self) -> None:
        service, _repository, _fetcher = self.make_service(
            messages=[], fetch_error=RuntimeError("boom fetch")
        )

        with self.assertLogs("src.processors.telegram_collection", level="ERROR") as captured:
            result = service.poll_once()

        self.assertEqual(result.status, "FAILED")
        self.assertIn("boom fetch", "\n".join(captured.output))


if __name__ == "__main__":
    unittest.main()
