from __future__ import annotations

import unittest
from dataclasses import dataclass, field

from src.cores import CollectorCore, OrganizerCore, TransferCore
from src.events import (
    COLLECT_DONE,
    ORGANIZE_DONE,
    TRANSFER_DONE,
    Event,
    EventBus,
)


@dataclass
class _FakeCollectionResult:
    scanned: int = 0
    enqueued: int = 0
    error: str | None = None


class _FakeCollectionService:
    def __init__(self, result: _FakeCollectionResult) -> None:
        self._result = result
        self.calls = 0

    def poll_once(self) -> _FakeCollectionResult:
        self.calls += 1
        return self._result


@dataclass
class _FakeSubscriptionSummary:
    created: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


class _FakeSubscriptionProcessor:
    def __init__(self, summary: _FakeSubscriptionSummary) -> None:
        self._summary = summary
        self.limit: int | None = None

    def process(self, limit: int = 100) -> _FakeSubscriptionSummary:
        self.limit = limit
        return self._summary


@dataclass
class _FakeTransferResult:
    claimed: bool
    error: str | None = None


class _FakeTransferProcessor:
    def __init__(self, results: list[_FakeTransferResult]) -> None:
        self._results = list(results)

    def process_next_transfer(self) -> _FakeTransferResult:
        if self._results:
            return self._results.pop(0)
        return _FakeTransferResult(claimed=False)


@dataclass
class _FakeOrganizeResult:
    status: str = "SUCCESS"
    scanned_count: int = 0
    success_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    last_error: str | None = None


class _FakeOrganizeService:
    def __init__(self, result: _FakeOrganizeResult) -> None:
        self._result = result
        self.staging_cid: int | None = None

    def run_once(self, staging_cid: int) -> _FakeOrganizeResult:
        self.staging_cid = staging_cid
        return self._result


def _record(bus: EventBus, name: str) -> list[Event]:
    captured: list[Event] = []
    bus.subscribe(name, captured.append)  # type: ignore[arg-type]
    return captured


class CollectorCoreTests(unittest.TestCase):
    def test_publishes_collect_done_when_transfers_created(self) -> None:
        bus = EventBus()
        events = _record(bus, COLLECT_DONE)
        core = CollectorCore(
            bus=bus,
            collection_services=[_FakeCollectionService(_FakeCollectionResult(scanned=3, enqueued=2))],
            subscription_processor=_FakeSubscriptionProcessor(_FakeSubscriptionSummary(created=2, skipped=1)),
        )

        result = core.run()

        self.assertEqual(result.status, "success")
        self.assertEqual(result.processed, 3)
        self.assertEqual(result.succeeded, 2)
        self.assertEqual(result.triggered, (COLLECT_DONE,))
        self.assertEqual(len(events), 1)

    def test_no_event_when_nothing_created(self) -> None:
        bus = EventBus()
        events = _record(bus, COLLECT_DONE)
        core = CollectorCore(
            bus=bus,
            collection_services=[_FakeCollectionService(_FakeCollectionResult(scanned=1))],
            subscription_processor=_FakeSubscriptionProcessor(_FakeSubscriptionSummary(created=0, skipped=1)),
        )

        result = core.run()

        self.assertEqual(result.triggered, ())
        self.assertEqual(events, [])

    def test_collection_error_marks_failed_but_still_runs_subscription(self) -> None:
        bus = EventBus()
        sub = _FakeSubscriptionProcessor(_FakeSubscriptionSummary(created=1))
        core = CollectorCore(
            bus=bus,
            collection_services=[_FakeCollectionService(_FakeCollectionResult(error="net down"))],
            subscription_processor=sub,
        )

        result = core.run()

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error, "net down")
        self.assertIsNotNone(sub.limit)


class TransferCoreTests(unittest.TestCase):
    def test_publishes_transfer_done_on_success(self) -> None:
        bus = EventBus()
        events = _record(bus, TRANSFER_DONE)
        core = TransferCore(
            bus=bus,
            processor=_FakeTransferProcessor(
                [_FakeTransferResult(claimed=True), _FakeTransferResult(claimed=False)]
            ),
        )

        result = core.run()

        self.assertEqual(result.succeeded, 1)
        self.assertEqual(result.triggered, (TRANSFER_DONE,))
        self.assertEqual(len(events), 1)

    def test_no_event_when_queue_empty(self) -> None:
        bus = EventBus()
        events = _record(bus, TRANSFER_DONE)
        core = TransferCore(bus=bus, processor=_FakeTransferProcessor([]))

        result = core.run()

        self.assertEqual(result.processed, 0)
        self.assertEqual(result.triggered, ())
        self.assertEqual(events, [])

    def test_failed_transfer_does_not_trigger_when_no_success(self) -> None:
        bus = EventBus()
        events = _record(bus, TRANSFER_DONE)
        core = TransferCore(
            bus=bus,
            processor=_FakeTransferProcessor(
                [_FakeTransferResult(claimed=True, error="boom"), _FakeTransferResult(claimed=False)]
            ),
        )

        result = core.run()

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.failed, 1)
        self.assertEqual(events, [])


class OrganizerCoreTests(unittest.TestCase):
    def test_publishes_organize_done(self) -> None:
        bus = EventBus()
        events = _record(bus, ORGANIZE_DONE)
        service = _FakeOrganizeService(_FakeOrganizeResult(success_count=2, scanned_count=2))
        core = OrganizerCore(bus=bus, service=service, staging_cid=12345)

        result = core.run()

        self.assertEqual(result.status, "success")
        self.assertEqual(result.succeeded, 2)
        self.assertEqual(service.staging_cid, 12345)
        self.assertEqual(result.triggered, (ORGANIZE_DONE,))
        self.assertEqual(len(events), 1)

    def test_failed_status_maps_to_failed(self) -> None:
        bus = EventBus()
        core = OrganizerCore(
            bus=bus,
            service=_FakeOrganizeService(_FakeOrganizeResult(status="FAILED", last_error="x")),
            staging_cid=1,
        )

        result = core.run()

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error, "x")

    def test_partial_success_maps_to_degraded(self) -> None:
        bus = EventBus()
        core = OrganizerCore(
            bus=bus,
            service=_FakeOrganizeService(_FakeOrganizeResult(status="PARTIAL_SUCCESS", failed_count=1)),
            staging_cid=1,
        )

        result = core.run()

        self.assertEqual(result.status, "degraded")


if __name__ == "__main__":
    unittest.main()
