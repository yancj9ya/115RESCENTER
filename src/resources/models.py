from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TelegramWebChannelRecord:
    channel: str
    display_name: str | None
    enabled: bool
    poll_interval_seconds: int
    created_at: str
    updated_at: str
