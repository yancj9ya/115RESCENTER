from __future__ import annotations

import httpx

from ._http_base import BaseHttpNotifier, NotificationProviderError, _HttpClient, _Response
from .models import NotificationEvent

__all__ = ["TelegramBotNotifier", "NotificationProviderError"]


class TelegramBotNotifier(BaseHttpNotifier):
    """Telegram Bot 渠道：通过 Bot API sendMessage 推送。"""

    def __init__(
        self,
        *,
        name: str,
        bot_token: str,
        chat_id: str,
        client: _HttpClient | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        super().__init__(name=name, client=client, timeout_seconds=timeout_seconds)
        self._bot_token = bot_token
        self._chat_id = chat_id

    def notify(self, event: NotificationEvent) -> None:
        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        text = f"{event.title}\n{event.message}" if event.message else event.title
        self._post(url, {"chat_id": self._chat_id, "text": text})

    def _default_post(self, url: str, payload: dict[str, object]) -> _Response:
        with httpx.Client() as client:
            return client.post(url, json=payload, timeout=self._timeout_seconds)
