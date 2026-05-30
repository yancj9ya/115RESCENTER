from __future__ import annotations

from typing import Protocol

from .models import NotificationEvent


class Notifier(Protocol):
    def notify(self, event: NotificationEvent) -> None:
        pass


class InMemoryNotifier:
    def __init__(self) -> None:
        self._events: list[NotificationEvent] = []

    def notify(self, event: NotificationEvent) -> None:
        self._events.append(event)

    @property
    def events(self) -> list[NotificationEvent]:
        return list(self._events)
