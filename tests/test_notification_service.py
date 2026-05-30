from __future__ import annotations

import unittest

from src.notifications import (
    NotificationEvent,
    NotificationService,
    OrganizeItemSummary,
    build_organize_summary,
    build_transfer_summary,
)


class _RecordingProvider:
    def __init__(self, name: str, *, fail: bool = False) -> None:
        self.name = name
        self._fail = fail
        self.events: list[NotificationEvent] = []

    def notify(self, event: NotificationEvent) -> None:
        if self._fail:
            raise RuntimeError(f"{self.name} boom")
        self.events.append(event)


class NotificationServiceRoutingTest(unittest.TestCase):
    def test_routes_event_to_providers_for_source_core(self) -> None:
        tg1 = _RecordingProvider("tg1")
        tg2 = _RecordingProvider("tg2")
        bark1 = _RecordingProvider("bark1")
        service = NotificationService(
            providers=[tg1, tg2, bark1],
            routing={"transfer": ["tg1"], "organize": ["tg2", "bark1"]},
        )

        event = NotificationEvent(event_type="organize_success", severity="info", title="t", message="m")
        service.notify("organize", event)

        self.assertEqual(tg1.events, [])
        self.assertEqual(len(tg2.events), 1)
        self.assertEqual(len(bark1.events), 1)

    def test_unknown_source_routes_to_nobody(self) -> None:
        tg1 = _RecordingProvider("tg1")
        service = NotificationService(providers=[tg1], routing={"transfer": ["tg1"]})

        service.notify("organize", NotificationEvent(event_type="x", severity="info", title="t", message="m"))

        self.assertEqual(tg1.events, [])

    def test_single_provider_failure_is_isolated(self) -> None:
        bad = _RecordingProvider("tg2", fail=True)
        good = _RecordingProvider("bark1")
        service = NotificationService(
            providers=[bad, good],
            routing={"organize": ["tg2", "bark1"]},
        )

        # must not raise even though tg2 fails
        service.notify("organize", NotificationEvent(event_type="x", severity="info", title="t", message="m"))

        self.assertEqual(len(good.events), 1)

    def test_routing_to_unknown_provider_name_is_ignored(self) -> None:
        tg1 = _RecordingProvider("tg1")
        service = NotificationService(providers=[tg1], routing={"transfer": ["tg1", "ghost"]})

        service.notify("transfer", NotificationEvent(event_type="x", severity="info", title="t", message="m"))

        self.assertEqual(len(tg1.events), 1)


class OrganizeSummaryTest(unittest.TestCase):
    def test_merges_same_tmdb_id_episodes_into_one_line(self) -> None:
        items = [
            OrganizeItemSummary(tmdb_id=111, title="逐玉", season=1, episode=1),
            OrganizeItemSummary(tmdb_id=111, title="逐玉", season=1, episode=2),
            OrganizeItemSummary(tmdb_id=111, title="逐玉", season=1, episode=3),
        ]
        event = build_organize_summary(items)

        self.assertIsNotNone(event)
        assert event is not None
        self.assertIn("逐玉", event.message)
        self.assertIn("E1-E3", event.message)
        # only one logical line for one tmdb_id
        self.assertEqual(event.message.count("逐玉"), 1)

    def test_groups_distinct_tmdb_ids_separately(self) -> None:
        items = [
            OrganizeItemSummary(tmdb_id=111, title="逐玉", season=1, episode=1),
            OrganizeItemSummary(tmdb_id=222, title="他乡", season=1, episode=5),
        ]
        event = build_organize_summary(items)

        assert event is not None
        self.assertIn("逐玉", event.message)
        self.assertIn("他乡", event.message)

    def test_non_contiguous_episodes_listed(self) -> None:
        items = [
            OrganizeItemSummary(tmdb_id=111, title="逐玉", season=1, episode=1),
            OrganizeItemSummary(tmdb_id=111, title="逐玉", season=1, episode=3),
        ]
        event = build_organize_summary(items)

        assert event is not None
        self.assertIn("E1", event.message)
        self.assertIn("E3", event.message)

    def test_empty_items_returns_none(self) -> None:
        self.assertIsNone(build_organize_summary([]))


class TransferSummaryTest(unittest.TestCase):
    def test_summarizes_count(self) -> None:
        event = build_transfer_summary(succeeded=3, failed=1)
        assert event is not None
        self.assertIn("3", event.message)

    def test_zero_returns_none(self) -> None:
        self.assertIsNone(build_transfer_summary(succeeded=0, failed=0))


if __name__ == "__main__":
    unittest.main()
