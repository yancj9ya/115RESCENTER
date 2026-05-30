from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from src.cores import CollectorCore, CoreResult, OrganizerCore, TransferCore
from src.events import (
    COLLECT_DONE,
    Event,
    EventBus,
    MANUAL_COLLECT,
    MANUAL_ORGANIZE,
    MANUAL_REFRESH_RANKS,
    MANUAL_TRANSFER,
    TRANSFER_DONE,
)
from src.runtime.factory import RuntimeFactory
from src.runtime.repository import RuntimeControlRepository


class EventDrivenRuntime:
    """事件驱动常驻运行时：事件是触发器，DB 是真相。

    事件链：``manual_collect``/定时 tick → 收集器 → 发 ``collect_done`` → 转存器 →
    发 ``transfer_done`` → 整理器。手动触发事件（前端发起）走同一条总线。

    兜底轮询：每个 tick 末尾无条件跑一次转存+整理，以防事件丢失或进程重启后
    队列里残留 PENDING 任务无人触发——这正是"事件 + 低频兜底轮询"的设计。
    """

    def __init__(
        self,
        *,
        factory: RuntimeFactory,
        bus: EventBus | None = None,
        repository: RuntimeControlRepository | None = None,
        worker_name: str = "event-runtime",
    ) -> None:
        self._factory = factory
        self._bus = bus or EventBus()
        self._repository = repository or factory.build_runtime_control_repository()
        self._worker_name = worker_name
        self._clock = factory.build_clock()
        self._sleeper = factory.build_sleeper()
        self._interval_seconds = 60
        self._sweep_interval_seconds = 3600
        self._last_sweep_at: datetime | None = None
        self._rank_refresh_interval_seconds = 14400
        self._force_rank_refresh = False
        self._results: list[CoreResult] = []
        self._ran: set[str] = set()
        self._wire_events()

    def _wire_events(self) -> None:
        self._bus.subscribe(MANUAL_COLLECT, lambda _e: self._run_collector())
        self._bus.subscribe(COLLECT_DONE, lambda _e: self._run_transfer())
        self._bus.subscribe(MANUAL_TRANSFER, lambda _e: self._run_transfer())
        self._bus.subscribe(TRANSFER_DONE, lambda _e: self._run_organizer())
        self._bus.subscribe(MANUAL_ORGANIZE, lambda _e: self._run_organizer())
        self._bus.subscribe(MANUAL_REFRESH_RANKS, lambda _e: self._mark_force_rank_refresh())

    @property
    def bus(self) -> EventBus:
        return self._bus

    def run_once(self) -> list[CoreResult]:
        """一个 tick：每次都认领手动触发（事件链立即级联处理），
        完整兜底轮询（收集器 + 未被级联的转存/整理）按 ``_sweep_interval_seconds`` 低频执行。"""
        self._results = []
        self._ran = set()
        self._heartbeat("running")
        if self._repository.get_state().desired_state == "stopped":
            self._heartbeat("idle")
            return []

        # 每个 tick 都做：跨进程手动触发认领。拉取 API 入队的待处理触发，
        # 转成进程内事件发布到总线，事件链立即级联跑对应核心（手动触发即时响应）。
        self._drain_manual_triggers()

        # 榜单缓存刷新：冷启动（缓存空）/过期（超过间隔）/手动触发时刷新。
        self._maybe_refresh_ranks()

        # 低频兜底轮询：仅当距上次 sweep 达到间隔时执行，防止纯事件驱动饿死残留 PENDING。
        if self._should_sweep():
            # 事件链：收集器成功 → collect_done → 转存器 → transfer_done → 整理器
            self._run_collector()
            # 兜底：链条未触发到的核心（事件丢失/进程重启后残留 PENDING）补跑一次
            if "transfer" not in self._ran:
                self._run_transfer()
            if "organizer" not in self._ran:
                self._run_organizer()
            self._last_sweep_at = self._now()

        self._heartbeat("success" if not self._has_failure() else "degraded", error=self._first_error())
        return list(self._results)

    def _should_sweep(self) -> bool:
        if self._last_sweep_at is None:
            return True
        elapsed = (self._now() - self._last_sweep_at).total_seconds()
        return elapsed >= self._sweep_interval_seconds

    def run_until_stopped(self, max_ticks: int | None = None) -> list[CoreResult]:
        all_results: list[CoreResult] = []
        ticks = 0
        while max_ticks is None or ticks < max_ticks:
            if self._repository.get_state().desired_state == "stopped":
                break
            all_results.extend(self.run_once())
            ticks += 1
            if max_ticks is not None and ticks >= max_ticks:
                break
            if self._repository.get_state().desired_state == "stopped":
                break
            self._sleeper(float(self._interval_seconds))
        return all_results

    def _drain_manual_triggers(self) -> None:
        claim = getattr(self._repository, "claim_pending_manual_triggers", None)
        if claim is None:
            return
        for _id, event_name, source in claim():
            self._bus.publish(Event(name=event_name, source=source))  # type: ignore[arg-type]

    def _mark_force_rank_refresh(self) -> None:
        self._force_rank_refresh = True

    def _maybe_refresh_ranks(self) -> None:
        """冷启动/过期/手动触发时刷新榜单缓存；任何环节缺失或失败都不影响本 tick 其它工作。"""
        cache_builder = getattr(self._factory, "build_rank_cache_repository", None)
        refresh_builder = getattr(self._factory, "build_rank_refresh_service", None)
        if not callable(cache_builder) or not callable(refresh_builder):
            self._force_rank_refresh = False
            return
        try:
            forced = self._force_rank_refresh
            self._force_rank_refresh = False
            cache = cache_builder()
            if not forced and not self._ranks_due(cache):
                return
            refresh_builder().refresh_all()
        except Exception as exc:  # noqa: BLE001 - 榜单刷新失败不能拖垮 tick
            self._record_blocked("rank_refresh", exc)

    def _ranks_due(self, cache: Any) -> bool:
        if cache.count() == 0:
            return True
        oldest = cache.oldest_refreshed_at()
        if not oldest:
            return True
        last = _parse_db_timestamp(oldest)
        if last is None:
            return True
        elapsed = (self._now() - last).total_seconds()
        return elapsed >= self._rank_refresh_interval_seconds


    def _run_collector(self) -> None:
        self._ran.add("collector")
        try:
            core = self._build_collector()
        except Exception as exc:
            self._record_blocked("collector", exc)
            return
        self._results.append(core.run())

    def _run_transfer(self) -> None:
        self._ran.add("transfer")
        try:
            core = self._build_transfer()
        except Exception as exc:
            self._record_blocked("transfer", exc)
            return
        self._results.append(core.run())

    def _run_organizer(self) -> None:
        self._ran.add("organizer")
        try:
            core = self._build_organizer()
        except Exception as exc:
            self._record_blocked("organizer", exc)
            return
        self._results.append(core.run())

    def _build_collector(self) -> CollectorCore:
        channel_service = self._factory.build_telegram_web_channel_service()
        collection_services = [
            self._factory.build_telegram_collection_service(source_id=str(getattr(channel, "channel")))
            for channel in channel_service.list_channels()
            if bool(getattr(channel, "enabled"))
        ]
        return CollectorCore(
            bus=self._bus,
            collection_services=collection_services,
            subscription_processor=self._factory.build_subscription_processor(),
        )

    def _build_transfer(self) -> TransferCore:
        return TransferCore(
            bus=self._bus,
            processor=self._factory.build_transfer_queue_processor(),
            notifier=self._build_notifier(),
        )

    def _build_organizer(self) -> OrganizerCore:
        return OrganizerCore(
            bus=self._bus,
            service=self._factory.build_organize_run_service(),
            staging_cid=self._factory.settings.transfer_cid,
            notifier=self._build_notifier(),
            item_reader=self._build_item_reader(),
        )

    def _build_notifier(self) -> Any:
        builder = getattr(self._factory, "build_notification_service", None)
        return builder() if callable(builder) else None

    def _build_item_reader(self) -> Any:
        builder = getattr(self._factory, "build_organize_repository", None)
        return builder() if callable(builder) else None

    def _record_blocked(self, core: str, exc: Exception) -> None:
        self._results.append(CoreResult(core=core, status="blocked", error=str(exc)))

    def _has_failure(self) -> bool:
        return any(result.status in {"failed", "blocked"} for result in self._results)

    def _first_error(self) -> str | None:
        for result in self._results:
            if result.error:
                return result.error
        return None

    def _heartbeat(self, status: str, *, error: str | None = None) -> None:
        self._repository.save_worker_heartbeat(
            worker_name=self._worker_name,
            component_name="event_runtime",
            status=status,
            pid=os.getpid(),
            error=error,
        )

    def _now(self) -> datetime:
        return self._clock()


def _parse_db_timestamp(value: str) -> datetime | None:
    """解析 SQLite ``CURRENT_TIMESTAMP``（'YYYY-MM-DD HH:MM:SS' UTC naive）为 tz-aware UTC。

    与运行时时钟（tz-aware UTC）对齐后才能安全做差值；解析失败返回 None（视为需要刷新）。
    """
    text = value.strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        return parsed.replace(tzinfo=timezone.utc)
    return None


__all__ = ["EventDrivenRuntime"]
