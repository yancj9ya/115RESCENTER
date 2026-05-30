from __future__ import annotations

from typing import Protocol

from .models import NotificationEvent


class NotificationProviderError(RuntimeError):
    pass


class _Response(Protocol):
    status_code: int


class _HttpClient(Protocol):
    def post(self, url: str, **kwargs: object) -> _Response:
        ...


class BaseHttpNotifier:
    """渠道 provider 基类：注入 client 时用注入的；否则由子类提供默认发送。"""

    def __init__(self, *, name: str, client: _HttpClient | None, timeout_seconds: float) -> None:
        self.name = name
        self._client = client
        self._timeout_seconds = timeout_seconds

    def _post(self, url: str, payload: dict[str, object]) -> None:
        response = self._do_post(url, payload)
        if response.status_code < 200 or response.status_code >= 300:
            raise NotificationProviderError(
                f"{self.name} notification failed with status {response.status_code}"
            )

    def _do_post(self, url: str, payload: dict[str, object]) -> _Response:
        if self._client is not None:
            return self._client.post(url, json=payload, timeout=self._timeout_seconds)
        return self._default_post(url, payload)

    def _default_post(self, url: str, payload: dict[str, object]) -> _Response:  # pragma: no cover
        raise NotImplementedError

    def notify(self, event: NotificationEvent) -> None:  # pragma: no cover
        raise NotImplementedError
