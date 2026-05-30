from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx

from .models import NotificationEvent


@dataclass(frozen=True)
class WebhookConfig:
    url: str
    enabled: bool = False
    token: str | None = None
    timeout_seconds: float = 10.0

    def __init__(
        self,
        url: str,
        enabled: bool = False,
        token: str | None = None,
        timeout_seconds: float = 10.0,
        timeout: float | None = None,
    ) -> None:
        object.__setattr__(self, "url", url)
        object.__setattr__(self, "enabled", enabled)
        object.__setattr__(self, "token", token)
        object.__setattr__(self, "timeout_seconds", timeout_seconds if timeout is None else timeout)


class WebhookNotificationError(RuntimeError):
    pass


class _WebhookResponse(Protocol):
    status_code: int


class _WebhookClient(Protocol):
    def post(self, url: str, **kwargs: object) -> _WebhookResponse:
        pass


class WebhookNotifier:
    def __init__(self, config: WebhookConfig, client: _WebhookClient | None = None) -> None:
        self._config = config
        self._client = client

    def notify(self, event: NotificationEvent) -> None:
        if not self._config.enabled:
            return

        headers = None
        if self._config.token:
            headers = {"Authorization": f"Bearer {self._config.token}"}

        response = self._post(
            json={
                "event_type": event.event_type,
                "severity": event.severity,
                "title": event.title,
                "message": event.message,
                "context": event.context,
            },
            headers=headers,
        )
        if response.status_code < 200 or response.status_code >= 300:
            raise WebhookNotificationError(f"Webhook notification failed with status {response.status_code}")

    def _post(self, json: dict[str, object], headers: dict[str, str] | None) -> _WebhookResponse:
        kwargs: dict[str, object] = {
            "json": json,
            "timeout": self._config.timeout_seconds,
        }
        if headers is not None:
            kwargs["headers"] = headers

        if self._client is not None:
            return self._client.post(self._config.url, **kwargs)

        with httpx.Client() as client:
            return client.post(self._config.url, **kwargs)
