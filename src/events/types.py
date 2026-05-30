from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

EventName = Literal[
    "collect_done",
    "transfer_done",
    "organize_done",
    "manual_collect",
    "manual_transfer",
    "manual_organize",
    "manual_refresh_ranks",
]

COLLECT_DONE: EventName = "collect_done"
TRANSFER_DONE: EventName = "transfer_done"
ORGANIZE_DONE: EventName = "organize_done"
MANUAL_COLLECT: EventName = "manual_collect"
MANUAL_TRANSFER: EventName = "manual_transfer"
MANUAL_ORGANIZE: EventName = "manual_organize"
MANUAL_REFRESH_RANKS: EventName = "manual_refresh_ranks"


@dataclass(frozen=True)
class Event:
    """进程内事件。事件是触发器，不携带业务数据——消费者从 DB 读真相。

    ``source`` 仅用于诊断/留痕（谁发布的），``emitted_at`` 用于排查时序。
    """

    name: EventName
    source: str = "system"
    emitted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
