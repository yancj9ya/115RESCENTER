from __future__ import annotations

import httpx

from ._http_base import BaseHttpNotifier, _HttpClient, _Response
from .models import NotificationEvent

__all__ = ["BarkNotifier"]


class BarkNotifier(BaseHttpNotifier):
    """iOS Bark 渠道：POST 到 <server_url>/<device_key>。"""

    def __init__(
        self,
        *,
        name: str,
        device_key: str,
        server_url: str = "https://api.day.app",
        client: _HttpClient | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        super().__init__(name=name, client=client, timeout_seconds=timeout_seconds)
        self._device_key = device_key
        self._server_url = server_url.rstrip("/")

    def notify(self, event: NotificationEvent) -> None:
        url = f"{self._server_url}/{self._device_key}"
        self._post(url, {"title": event.title, "body": event.message})

    def _default_post(self, url: str, payload: dict[str, object]) -> _Response:
        with httpx.Client() as client:
            return client.post(url, json=payload, timeout=self._timeout_seconds)
