from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

RUNTIME_COMPONENT_TELEGRAM_COLLECTOR = "telegram_collector"
RUNTIME_COMPONENT_SUBSCRIPTION_PROCESSOR = "subscription_processor"
RUNTIME_COMPONENT_TRANSFER_PROCESSOR = "transfer_processor"
RUNTIME_COMPONENT_ORGANIZER = "organizer"

RUNTIME_COMPONENTS = (
    RUNTIME_COMPONENT_TELEGRAM_COLLECTOR,
    RUNTIME_COMPONENT_SUBSCRIPTION_PROCESSOR,
    RUNTIME_COMPONENT_TRANSFER_PROCESSOR,
    RUNTIME_COMPONENT_ORGANIZER,
)

RuntimeComponentName = Literal[
    "telegram_collector",
    "subscription_processor",
    "transfer_processor",
    "organizer",
]
RuntimeExecutionStatus = Literal[
    "idle",
    "ready",
    "running",
    "success",
    "failed",
    "blocked",
    "degraded",
]
RuntimeDesiredState = Literal["running", "stopped"]
RuntimeEffectiveState = Literal["running", "stopped", "degraded"]
RuntimeComponentState = Literal["idle", "ready", "running", "success", "failed", "blocked", "degraded"]


@dataclass(frozen=True)
class RuntimeStateRecord:
    desired_state: RuntimeDesiredState
    started_at: str | None
    stopped_at: str | None
    updated_at: str


@dataclass(frozen=True)
class RuntimeQueueCounts:
    collect_queue: dict[str, int]
    transfer_queue: dict[str, int]


@dataclass(frozen=True)
class RuntimeOrganizerSummary:
    latest_run: object | None
    counts: dict[str, int]


@dataclass(frozen=True)
class RuntimeComponentStatus:
    name: str
    desired_state: RuntimeDesiredState
    status: RuntimeComponentState
    configured: bool
    enabled: bool
    detail: str
    last_status: str | None = None
    last_error: str | None = None
    tick_count: int | None = None
    last_started_at: str | None = None
    last_finished_at: str | None = None
    last_success: bool | None = None
    last_heartbeat_at: str | None = None


@dataclass(frozen=True)
class RuntimeComponentTelemetry:
    component: RuntimeComponentName
    status: RuntimeExecutionStatus = "idle"
    checked_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    detail: str = ""
    last_error: str | None = None
    counters: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeComponentRecord:
    name: str
    status: RuntimeExecutionStatus
    enabled: bool
    configured: bool
    started_at: str | None
    finished_at: str | None
    success: bool | None
    error: str | None
    tick_count: int
    updated_at: str


@dataclass(frozen=True)
class RuntimeWorkerHeartbeatRecord:
    worker_name: str
    component_name: str
    status: RuntimeExecutionStatus
    pid: int | None
    error: str | None
    heartbeat_at: str
    updated_at: str


@dataclass(frozen=True)
class RuntimeStatus:
    desired_state: RuntimeDesiredState
    effective_state: RuntimeEffectiveState
    control_plane_only: bool
    started_at: str | None
    stopped_at: str | None
    updated_at: str
    message: str
    components: list[RuntimeComponentStatus]
    queue_counts: RuntimeQueueCounts
    organizer: RuntimeOrganizerSummary


@dataclass(frozen=True)
class RuntimeControlResult(RuntimeStatus):
    action: Literal["start", "stop"]
    changed: bool
