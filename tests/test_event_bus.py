from __future__ import annotations

import threading
import unittest

from src.events import COLLECT_DONE, TRANSFER_DONE, Event, EventBus


class EventBusTests(unittest.TestCase):
    def test_subscriber_receives_published_event(self) -> None:
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(COLLECT_DONE, received.append)

        event = Event(name=COLLECT_DONE, source="test")
        bus.publish(event)

        self.assertEqual(received, [event])

    def test_only_matching_subscribers_are_notified(self) -> None:
        bus = EventBus()
        collect_calls: list[Event] = []
        transfer_calls: list[Event] = []
        bus.subscribe(COLLECT_DONE, collect_calls.append)
        bus.subscribe(TRANSFER_DONE, transfer_calls.append)

        bus.publish(Event(name=COLLECT_DONE))

        self.assertEqual(len(collect_calls), 1)
        self.assertEqual(transfer_calls, [])

    def test_multiple_subscribers_all_run(self) -> None:
        bus = EventBus()
        order: list[str] = []
        bus.subscribe(COLLECT_DONE, lambda _e: order.append("a"))
        bus.subscribe(COLLECT_DONE, lambda _e: order.append("b"))

        bus.publish(Event(name=COLLECT_DONE))

        self.assertEqual(order, ["a", "b"])

    def test_one_subscriber_error_does_not_block_others(self) -> None:
        bus = EventBus()
        ran: list[str] = []

        def boom(_event: Event) -> None:
            raise RuntimeError("boom")

        bus.subscribe(COLLECT_DONE, boom)
        bus.subscribe(COLLECT_DONE, lambda _e: ran.append("second"))

        with self.assertRaises(RuntimeError):
            bus.publish(Event(name=COLLECT_DONE))

        self.assertEqual(ran, ["second"])

    def test_unsubscribe_stops_delivery(self) -> None:
        bus = EventBus()
        received: list[Event] = []
        unsubscribe = bus.subscribe(COLLECT_DONE, received.append)

        unsubscribe()
        bus.publish(Event(name=COLLECT_DONE))

        self.assertEqual(received, [])

    def test_publish_to_no_subscribers_is_noop(self) -> None:
        bus = EventBus()
        bus.publish(Event(name=COLLECT_DONE))  # should not raise

    def test_thread_safe_concurrent_subscribe_and_publish(self) -> None:
        bus = EventBus()
        counter = {"n": 0}
        lock = threading.Lock()

        def handler(_event: Event) -> None:
            with lock:
                counter["n"] += 1

        def worker() -> None:
            for _ in range(50):
                bus.subscribe(COLLECT_DONE, handler)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        bus.publish(Event(name=COLLECT_DONE))
        self.assertEqual(counter["n"], 200)


if __name__ == "__main__":
    unittest.main()
