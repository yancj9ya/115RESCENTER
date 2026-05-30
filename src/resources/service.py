from __future__ import annotations

from urllib.parse import urlparse

from .models import TelegramWebChannelRecord
from .repository import TelegramWebChannelRepository


class TelegramWebChannelService:
    def __init__(self, repository: TelegramWebChannelRepository) -> None:
        self._repository = repository

    def init_schema(self) -> None:
        self._repository.init_schema()

    def create_channel(
        self,
        *,
        channel: str,
        display_name: str | None = None,
        enabled: bool = True,
        poll_interval_seconds: int = 1800,
    ) -> TelegramWebChannelRecord:
        normalized_channel = self.normalize_channel(channel)
        normalized_display_name = self._normalize_display_name(display_name)
        validated_interval = self._validate_poll_interval_seconds(poll_interval_seconds)
        return self._repository.create_channel(
            channel=normalized_channel,
            display_name=normalized_display_name,
            enabled=enabled,
            poll_interval_seconds=validated_interval,
        )

    def list_channels(self) -> list[TelegramWebChannelRecord]:
        return self._repository.list_channels()

    def get_channel(self, channel: str) -> TelegramWebChannelRecord | None:
        normalized_channel = self.normalize_channel(channel)
        return self._repository.get_channel(normalized_channel)

    def update_channel(
        self,
        channel: str,
        *,
        display_name: str | None = None,
        enabled: bool | None = None,
        poll_interval_seconds: int | None = None,
    ) -> TelegramWebChannelRecord | None:
        normalized_channel = self.normalize_channel(channel)
        normalized_display_name = self._normalize_display_name(display_name) if display_name is not None else None
        validated_interval = (
            None
            if poll_interval_seconds is None
            else self._validate_poll_interval_seconds(poll_interval_seconds)
        )
        return self._repository.update_channel(
            normalized_channel,
            display_name=normalized_display_name,
            enabled=enabled,
            poll_interval_seconds=validated_interval,
        )

    def delete_channel(self, channel: str) -> bool:
        normalized_channel = self.normalize_channel(channel)
        return self._repository.delete_channel(normalized_channel)

    def enable_channel(self, channel: str) -> TelegramWebChannelRecord | None:
        normalized_channel = self.normalize_channel(channel)
        return self._repository.update_channel(normalized_channel, enabled=True)

    def disable_channel(self, channel: str) -> TelegramWebChannelRecord | None:
        normalized_channel = self.normalize_channel(channel)
        return self._repository.update_channel(normalized_channel, enabled=False)

    def normalize_channel(self, channel: str) -> str:
        normalized = channel.strip()
        if not normalized:
            raise ValueError("channel must not be blank")

        parsed = urlparse(normalized)
        if parsed.scheme and parsed.netloc:
            normalized = parsed.path
        normalized = normalized.strip()
        normalized = normalized.lstrip("/")

        lowercase_normalized = normalized.lower()
        for prefix in ("t.me/", "telegram.me/"):
            if lowercase_normalized.startswith(prefix):
                normalized = normalized[len(prefix) :]
                lowercase_normalized = normalized.lower()
                break

        normalized = normalized.lstrip("/")
        lowercase_normalized = normalized.lower()
        if lowercase_normalized.startswith("s/"):
            normalized = normalized[2:]

        normalized = normalized.lstrip("/")
        if normalized.startswith("@"):
            normalized = normalized[1:]
        normalized = normalized.strip().strip("/")
        if not normalized:
            raise ValueError("channel must not be blank")
        return normalized

    def _normalize_display_name(self, display_name: str | None) -> str | None:
        if display_name is None:
            return None
        normalized_display_name = display_name.strip()
        if not normalized_display_name:
            return None
        return normalized_display_name

    def _validate_poll_interval_seconds(self, poll_interval_seconds: int) -> int:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be greater than 0")
        return poll_interval_seconds
