from __future__ import annotations

import unittest

from src.cores.organizer import OrganizerCore
from src.cores.transfer import TransferCore
from src.events import EventBus, ORGANIZE_DONE, TRANSFER_DONE
from src.notifications import NotificationEvent


class _Bus(EventBus):
    pass


class _RecordingNotifier:
    def __init__(self) -> None:
        self.calls: list[tuple[str, NotificationEvent]] = []

    def notify(self, source: str, event: NotificationEvent) -> None:
        self.calls.append((source, event))


class _ThrowingNotifier:
    def __init__(self) -> None:
        self.calls = 0

    def notify(self, source: str, event: NotificationEvent) -> None:
        self.calls += 1
        raise RuntimeError("webhook 超时")


class _EventCapturingBus(EventBus):
    def __init__(self) -> None:
        super().__init__()
        self.published: list[str] = []

    def publish(self, event: object) -> None:  # type: ignore[override]
        self.published.append(str(getattr(event, "name", "")))
        super().publish(event)  # type: ignore[arg-type]


class _Result:
    def __init__(self, **kwargs: object) -> None:
        self.__dict__.update(kwargs)


class _OrganizeService:
    def __init__(self, result: object) -> None:
        self._result = result

    def run_once(self, staging_cid: int) -> object:
        return self._result


class _ItemReader:
    def __init__(self, items: list[object]) -> None:
        self._items = items

    def list_run_items(self, run_id: int) -> list[object]:
        return self._items


class _TransferProcessor:
    def __init__(self, results: list[object]) -> None:
        self._results = list(results)

    def process_next_transfer(self) -> object:
        if self._results:
            return self._results.pop(0)
        return _Result(claimed=False)


class OrganizerCoreNotificationTest(unittest.TestCase):
    def test_aggregates_same_tmdb_episodes_into_single_notification(self) -> None:
        items = [
            _Result(status="SUCCESS", metadata_json='{"tmdb_id": 111, "title": "逐玉", "season": 1, "episode": 1}', new_name="a", file_name="a"),
            _Result(status="SUCCESS", metadata_json='{"tmdb_id": 111, "title": "逐玉", "season": 1, "episode": 2}', new_name="b", file_name="b"),
            _Result(status="SKIPPED_DUPLICATE", metadata_json='{"tmdb_id": 111, "title": "逐玉", "season": 1, "episode": 3}', new_name="c", file_name="c"),
        ]
        notifier = _RecordingNotifier()
        core = OrganizerCore(
            bus=EventBus(),
            service=_OrganizeService(_Result(status="SUCCESS", run_id=7, scanned_count=3, success_count=2, skipped_count=1, failed_count=0, last_error=None)),
            staging_cid=999,
            notifier=notifier,
            item_reader=_ItemReader(items),
        )

        core.run()

        self.assertEqual(len(notifier.calls), 1)
        source, event = notifier.calls[0]
        self.assertEqual(source, "organizer")
        self.assertIn("逐玉", event.message)
        self.assertIn("E1-E2", event.message)
        self.assertNotIn("E3", event.message)  # skipped item excluded

    def test_no_notification_when_zero_success(self) -> None:
        notifier = _RecordingNotifier()
        core = OrganizerCore(
            bus=EventBus(),
            service=_OrganizeService(_Result(status="SUCCESS", run_id=7, scanned_count=0, success_count=0, skipped_count=0, failed_count=0, last_error=None)),
            staging_cid=999,
            notifier=notifier,
            item_reader=_ItemReader([]),
        )

        core.run()

        self.assertEqual(notifier.calls, [])


class TransferCoreNotificationTest(unittest.TestCase):
    def test_sends_summary_after_batch(self) -> None:
        notifier = _RecordingNotifier()
        processor = _TransferProcessor([
            _Result(claimed=True, error=None),
            _Result(claimed=True, error=None),
        ])
        core = TransferCore(bus=EventBus(), processor=processor, notifier=notifier)

        core.run()

        self.assertEqual(len(notifier.calls), 1)
        source, event = notifier.calls[0]
        self.assertEqual(source, "transfer")
        self.assertIn("2", event.message)

    def test_notifier_failure_does_not_break_run_or_event(self) -> None:
        bus = _EventCapturingBus()
        processor = _TransferProcessor([_Result(claimed=True, error=None)])
        core = TransferCore(bus=bus, processor=processor, notifier=_ThrowingNotifier())

        result = core.run()  # 不应抛出

        self.assertEqual(result.status, "success")
        self.assertEqual(result.succeeded, 1)
        self.assertIn(TRANSFER_DONE, bus.published)


class OrganizerCoreNotificationFailureTest(unittest.TestCase):
    def test_notifier_failure_does_not_break_run_and_event_still_published(self) -> None:
        bus = _EventCapturingBus()
        items = [
            _Result(status="SUCCESS", metadata_json='{"tmdb_id": 111, "title": "逐玉"}', new_name="a", file_name="a"),
        ]
        core = OrganizerCore(
            bus=bus,
            service=_OrganizeService(
                _Result(status="SUCCESS", run_id=7, scanned_count=1, success_count=1, skipped_count=0, failed_count=0, last_error=None)
            ),
            staging_cid=999,
            notifier=_ThrowingNotifier(),
            item_reader=_ItemReader(items),
        )

        result = core.run()  # 不应抛出

        self.assertEqual(result.status, "success")
        # 通知失败不能阻止 ORGANIZE_DONE 发布
        self.assertIn(ORGANIZE_DONE, bus.published)


if __name__ == "__main__":
    unittest.main()
