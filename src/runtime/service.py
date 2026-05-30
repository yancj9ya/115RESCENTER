from __future__ import annotations

from src.config.settings import AppSettings
from src.organizing.repository import OrganizeRepository
from src.queue.repository import QueueRepository
from src.resources import TelegramWebChannelService

from .models import (
    RuntimeComponentRecord,
    RuntimeComponentStatus,
    RuntimeControlResult,
    RuntimeEffectiveState,
    RuntimeOrganizerSummary,
    RuntimeQueueCounts,
    RuntimeStateRecord,
    RuntimeStatus,
    RuntimeWorkerHeartbeatRecord,
)
from .repository import RuntimeControlRepository

_RUNTIME_MESSAGE = "start/stop persists scheduler intent only; no background workers are spawned"


class RuntimeControlService:
    def __init__(
        self,
        *,
        repository: RuntimeControlRepository,
        queue_repository: QueueRepository,
        organize_repository: OrganizeRepository,
        telegram_web_channel_service: TelegramWebChannelService,
        settings: AppSettings,
    ) -> None:
        self._repository = repository
        self._queue_repository = queue_repository
        self._organize_repository = organize_repository
        self._telegram_web_channel_service = telegram_web_channel_service
        self._settings = settings

    def status(self) -> RuntimeStatus:
        return self._build_status(self._repository.get_state())

    def start(self) -> RuntimeControlResult:
        state, changed = self._repository.start()
        status = self._build_status(state)
        return RuntimeControlResult(**status.__dict__, action="start", changed=changed)

    def stop(self) -> RuntimeControlResult:
        state, changed = self._repository.stop()
        status = self._build_status(state)
        return RuntimeControlResult(**status.__dict__, action="stop", changed=changed)

    _VALID_TRIGGERS = {"manual_collect", "manual_transfer", "manual_organize", "manual_refresh_ranks"}

    def trigger(self, event_name: str) -> int:
        """入队一次手动触发，返回触发记录 id。worker 进程会在下个 tick 认领并发布事件。"""
        if event_name not in self._VALID_TRIGGERS:
            raise ValueError(f"unsupported manual trigger: {event_name}")
        return self._repository.enqueue_manual_trigger(event_name=event_name, source="api")

    def _build_status(self, state: RuntimeStateRecord) -> RuntimeStatus:
        collect_counts = self._queue_repository.get_collect_status_counts()
        transfer_counts = self._queue_repository.get_transfer_status_counts()
        component_records = self._repository.list_component_statuses()
        heartbeats = self._repository.list_worker_heartbeats()
        components = self._component_statuses(
            state,
            collect_counts=collect_counts,
            transfer_counts=transfer_counts,
            component_records=component_records,
            heartbeats=heartbeats,
        )
        effective_state: RuntimeEffectiveState = state.desired_state
        degraded_statuses = {"failed", "blocked", "degraded"}
        if state.desired_state == "running" and any(
            component.status in degraded_statuses or component.last_status in degraded_statuses
            for component in components
        ):
            effective_state = "degraded"

        return RuntimeStatus(
            desired_state=state.desired_state,
            effective_state=effective_state,
            control_plane_only=not component_records and not heartbeats,
            started_at=state.started_at,
            stopped_at=state.stopped_at,
            updated_at=state.updated_at,
            message=_RUNTIME_MESSAGE,
            components=components,
            queue_counts=RuntimeQueueCounts(
                collect_queue=collect_counts,
                transfer_queue=transfer_counts,
            ),
            organizer=RuntimeOrganizerSummary(
                latest_run=self._organize_repository.get_latest_run(),
                counts=self._organize_repository.get_status_counts(),
            ),
        )

    def _component_statuses(
        self,
        state: RuntimeStateRecord,
        *,
        collect_counts: dict[str, int],
        transfer_counts: dict[str, int],
        component_records: list[RuntimeComponentRecord],
        heartbeats: list[RuntimeWorkerHeartbeatRecord],
    ) -> list[RuntimeComponentStatus]:
        channels = self._telegram_web_channel_service.list_channels()
        enabled_channels = [channel for channel in channels if channel.enabled]
        has_storage = self._settings.p115 is not None
        has_tmdb = self._settings.tmdb is not None
        is_running = state.desired_state == "running"

        collector_status = "ready" if is_running and enabled_channels else "idle"
        subscription_status = "ready" if is_running and collect_counts.get("PENDING", 0) > 0 else "idle"
        transfer_status = "ready" if is_running and has_storage else "blocked" if is_running else "idle"
        organizer_status = "ready" if is_running and has_storage and has_tmdb else "blocked" if is_running else "idle"

        components = [
            RuntimeComponentStatus(
                name="telegram_collector",
                desired_state=state.desired_state,
                status=collector_status,
                configured=True,
                enabled=bool(enabled_channels),
                detail=f"{len(enabled_channels)} enabled telegram_web channels",
            ),
            RuntimeComponentStatus(
                name="subscription_processor",
                desired_state=state.desired_state,
                status=subscription_status,
                configured=True,
                enabled=collect_counts.get("PENDING", 0) > 0,
                detail=f"{collect_counts.get('PENDING', 0)} pending collect items",
            ),
            RuntimeComponentStatus(
                name="transfer_processor",
                desired_state=state.desired_state,
                status=transfer_status,
                configured=has_storage,
                enabled=transfer_counts.get("PENDING", 0) > 0,
                detail="115 storage is configured" if has_storage else "115 storage is not configured",
            ),
            RuntimeComponentStatus(
                name="organizer",
                desired_state=state.desired_state,
                status=organizer_status,
                configured=has_storage and has_tmdb,
                enabled=is_running and has_storage and has_tmdb,
                detail=self._organizer_detail(has_storage=has_storage, has_tmdb=has_tmdb),
            ),
        ]
        return self._merge_telemetry(components, component_records=component_records, heartbeats=heartbeats)

    def _merge_telemetry(
        self,
        components: list[RuntimeComponentStatus],
        *,
        component_records: list[RuntimeComponentRecord],
        heartbeats: list[RuntimeWorkerHeartbeatRecord],
    ) -> list[RuntimeComponentStatus]:
        records_by_name = {record.name: record for record in component_records}
        heartbeats_by_component: dict[str, RuntimeWorkerHeartbeatRecord] = {}
        for heartbeat in heartbeats:
            current = heartbeats_by_component.get(heartbeat.component_name)
            if current is None or heartbeat.heartbeat_at > current.heartbeat_at:
                heartbeats_by_component[heartbeat.component_name] = heartbeat

        merged = [
            self._with_telemetry(
                component,
                record=records_by_name.pop(component.name, None),
                heartbeat=heartbeats_by_component.pop(component.name, None),
            )
            for component in components
        ]
        for record in records_by_name.values():
            merged.append(
                self._with_telemetry(
                    RuntimeComponentStatus(
                        name=record.name,
                        desired_state="running" if record.enabled else "stopped",
                        status=record.status,
                        configured=record.configured,
                        enabled=record.enabled,
                        detail="worker telemetry component",
                    ),
                    record=record,
                    heartbeat=heartbeats_by_component.pop(record.name, None),
                )
            )
        for heartbeat in heartbeats_by_component.values():
            merged.append(
                self._with_telemetry(
                    RuntimeComponentStatus(
                        name=heartbeat.component_name,
                        desired_state="running",
                        status=heartbeat.status,
                        configured=True,
                        enabled=True,
                        detail="worker heartbeat component",
                    ),
                    record=None,
                    heartbeat=heartbeat,
                )
            )
        return merged

    def _with_telemetry(
        self,
        component: RuntimeComponentStatus,
        *,
        record: RuntimeComponentRecord | None,
        heartbeat: RuntimeWorkerHeartbeatRecord | None,
    ) -> RuntimeComponentStatus:
        status = record.status if record is not None else component.status
        last_status = heartbeat.status if heartbeat is not None else record.status if record is not None else None
        last_error = heartbeat.error if heartbeat is not None and heartbeat.error else record.error if record is not None else None
        last_error = self._sanitize_status_error(last_error)
        return RuntimeComponentStatus(
            name=component.name,
            desired_state=component.desired_state,
            status=status,
            configured=record.configured if record is not None else component.configured,
            enabled=record.enabled if record is not None else component.enabled,
            detail=component.detail,
            last_status=last_status,
            last_error=last_error,
            tick_count=record.tick_count if record is not None else None,
            last_started_at=record.started_at if record is not None else None,
            last_finished_at=record.finished_at if record is not None else None,
            last_success=record.success if record is not None else None,
            last_heartbeat_at=heartbeat.heartbeat_at if heartbeat is not None else None,
        )

    def _organizer_detail(self, *, has_storage: bool, has_tmdb: bool) -> str:
        if has_storage and has_tmdb:
            return "115 storage and TMDB search are configured"
        if not has_storage and not has_tmdb:
            return "115 storage and TMDB search are not configured"
        if not has_storage:
            return "115 storage is not configured"
        return "TMDB search is not configured"

    def _sanitize_status_error(self, error: str | None) -> str | None:
        if error is None:
            return None
        sanitized = error
        secrets = []
        if self._settings.p115 is not None:
            secrets.append(self._settings.p115.cookies)
            if self._settings.p115.cache_home is not None:
                secrets.append(str(self._settings.p115.cache_home))
        if self._settings.tmdb is not None:
            secrets.append(self._settings.tmdb.bearer_token)
        for secret in secrets:
            if secret:
                sanitized = sanitized.replace(secret, "[redacted]")
        return sanitized
