from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

INFO: Final[str] = "info"
WARNING: Final[str] = "warning"
ERROR: Final[str] = "error"

TRANSFER_SUCCESS: Final[str] = "transfer_success"
TRANSFER_FAILED: Final[str] = "transfer_failed"
ORGANIZE_SUCCESS: Final[str] = "organize_success"
ORGANIZE_FAILED: Final[str] = "organize_failed"
TMDB_UNRESOLVED: Final[str] = "tmdb_unresolved"


@dataclass(frozen=True)
class NotificationEvent:
    event_type: str
    severity: str
    title: str
    message: str
    context: dict[str, object] = field(default_factory=dict)
