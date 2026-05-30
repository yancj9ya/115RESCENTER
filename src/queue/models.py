from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

PENDING: Final[str] = "PENDING"
RUNNING: Final[str] = "RUNNING"
SUCCESS: Final[str] = "SUCCESS"
SKIPPED: Final[str] = "SKIPPED"
FAILED: Final[str] = "FAILED"

TRANSFER_PENDING: Final[str] = PENDING
TRANSFER_RUNNING: Final[str] = RUNNING
TRANSFER_SUCCESS: Final[str] = SUCCESS
TRANSFER_FAILED: Final[str] = FAILED

COLLECT_QUEUE_STATUSES: Final[tuple[str, ...]] = (PENDING, RUNNING, SUCCESS, SKIPPED, FAILED)
TRANSFER_QUEUE_STATUSES: Final[tuple[str, ...]] = (
    TRANSFER_PENDING,
    TRANSFER_RUNNING,
    TRANSFER_SUCCESS,
    TRANSFER_FAILED,
)


@dataclass(frozen=True)
class CollectorCursor:
    source_type: str
    source_id: str
    last_seen_message_id: str | None
    last_poll_at: str | None
    last_status: str
    last_error: str | None = None


@dataclass(frozen=True)
class ShareLink:
    share_code: str
    receive_code: str
    share_url: str


@dataclass(frozen=True)
class TransferRuleContext:
    rule_id: str
    rule_name: str
    matched_keywords: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TransferSourceMessage:
    collect_id: int
    source_type: str
    source_id: str
    message_id: str
    message_url: str
    published_at: str | None = None


@dataclass(frozen=True)
class CollectQueueRecord:
    id: int
    source_type: str
    source_id: str
    message_id: str
    message_url: str | None
    message_text: str
    published_at: str | None
    shares_json: list[ShareLink] = field(default_factory=list)
    status: str = PENDING
    attempt_count: int = 0
    last_error: str | None = None
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class TransferQueueRecord:
    id: int
    share_code: str
    receive_code: str
    share_url: str
    staging_cid: int
    matched_rules_json: list[TransferRuleContext] = field(default_factory=list)
    source_messages_json: list[TransferSourceMessage] = field(default_factory=list)
    status: str = TRANSFER_PENDING
    attempt_count: int = 0
    last_error: str | None = None
    created_at: str = ""
    updated_at: str = ""
