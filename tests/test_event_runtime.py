from __future__ import annotations

import unittest
from dataclasses import dataclass, field

from src.events import EventBus
from src.runtime.event_runtime import EventDrivenRuntime


@dataclass
class _State:
    desired_state: str = "running"


class _FakeRepo:
    def __init__(self, state: _State) -> None:
        self._state = state
        self.heartbeats: list[str] = []
        self.pending_triggers: list[tuple[int, str, str]] = []

    def get_state(self) -> _State:
        return self._state

    def save_worker_heartbeat(self, **kwargs: object) -> None:
        self.heartbeats.append(str(kwargs.get("status")))

    def claim_pending_manual_triggers(self) -> list[tuple[int, str, str]]:
        claimed = list(self.pending_triggers)
        self.pending_triggers = []
        return claimed


@dataclass
class _CollectResult:
    scanned: int = 0
    enqueued: int = 0
    error: str | None = None


class _CollectionService:
    def __init__(self, result: _CollectResult) -> None:
        self._result = result

    def poll_once(self) -> _CollectResult:
        return self._result


@dataclass
class _SubSummary:
    created: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


class _SubProcessor:
    def __init__(self, summary: _SubSummary) -> None:
        self._summary = summary

    def process(self, limit: int = 100) -> _SubSummary:
        return self._summary


@dataclass
class _TransferResult:
    claimed: bool
    error: str | None = None


class _TransferProcessor:
    def __init__(self, results: list[_TransferResult]) -> None:
        self._results = list(results)

    def process_next_transfer(self) -> _TransferResult:
        return self._results.pop(0) if self._results else _TransferResult(claimed=False)


@dataclass
class _OrganizeResult:
    status: str = "SUCCESS"
    scanned_count: int = 0
    success_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    last_error: str | None = None


class _OrganizeService:
    def __init__(self, result: _OrganizeResult) -> None:
        self._result = result
        self.calls = 0

    def run_once(self, staging_cid: int) -> _OrganizeResult:
        self.calls += 1
        return self._result


@dataclass
class _Channel:
    channel: str
    enabled: bool = True


class _ChannelService:
    def __init__(self, channels: list[_Channel]) -> None:
        self._channels = channels

    def list_channels(self) -> list[_Channel]:
        return self._channels


@dataclass
class _Settings:
    transfer_cid: int = 99


class _FakeFactory:
    """最小 RuntimeFactory 替身，注入各核心需要的 fake 工具/processor。"""

    def __init__(
        self,
        *,
        collect_result: _CollectResult,
        sub_summary: _SubSummary,
        transfer_results: list[_TransferResult],
        organize_result: _OrganizeResult,
        channels: list[_Channel] | None = None,
        transfer_buildable: bool = True,
    ) -> None:
        self.settings = _Settings()
        self._collect_result = collect_result
        self._sub_summary = sub_summary
        self._transfer_results = transfer_results
        self.organize_service = _OrganizeService(organize_result)
        self._channels = channels if channels is not None else [_Channel("ch1")]
        self._transfer_buildable = transfer_buildable

    def build_clock(self):
        from datetime import datetime, timezone

        return lambda: datetime.now(timezone.utc)

    def build_sleeper(self):
        return lambda _s: None

    def build_runtime_control_repository(self):  # not used; repo injected in tests
        raise NotImplementedError

    def build_telegram_web_channel_service(self) -> _ChannelService:
        return _ChannelService(self._channels)

    def build_telegram_collection_service(self, *, source_id: str) -> _CollectionService:
        return _CollectionService(self._collect_result)

    def build_subscription_processor(self) -> _SubProcessor:
        return _SubProcessor(self._sub_summary)

    def build_transfer_queue_processor(self) -> _TransferProcessor:
        if not self._transfer_buildable:
            raise RuntimeError("115 storage is not configured")
        return _TransferProcessor(self._transfer_results)

    def build_organize_run_service(self) -> _OrganizeService:
        return self.organize_service


def _runtime(factory: _FakeFactory, repo: _FakeRepo) -> EventDrivenRuntime:
    return EventDrivenRuntime(factory=factory, bus=EventBus(), repository=repo)  # type: ignore[arg-type]


class EventDrivenRuntimeTests(unittest.TestCase):
    def test_collect_cascades_to_transfer_and_organize(self) -> None:
        factory = _FakeFactory(
            collect_result=_CollectResult(scanned=2, enqueued=2),
            sub_summary=_SubSummary(created=2),
            transfer_results=[_TransferResult(claimed=True), _TransferResult(claimed=False)],
            organize_result=_OrganizeResult(success_count=1, scanned_count=1),
        )
        repo = _FakeRepo(_State("running"))
        runtime = _runtime(factory, repo)

        results = runtime.run_once()
        cores = [r.core for r in results]

        # 收集器触发 collect_done → 转存；转存成功触发 transfer_done → 整理。
        # 同步级联是嵌套的，结果追加顺序为最内层先入，故按集合断言。
        self.assertEqual(sorted(cores), ["collector", "organizer", "transfer"])
        self.assertEqual(factory.organize_service.calls, 1)

    def test_fallback_runs_transfer_and_organizer_when_no_cascade(self) -> None:
        # 收集器无新增 → 不发 collect_done；兜底轮询仍应跑转存+整理
        factory = _FakeFactory(
            collect_result=_CollectResult(scanned=0),
            sub_summary=_SubSummary(created=0),
            transfer_results=[_TransferResult(claimed=False)],
            organize_result=_OrganizeResult(),
        )
        repo = _FakeRepo(_State("running"))
        runtime = _runtime(factory, repo)

        results = runtime.run_once()
        cores = [r.core for r in results]

        self.assertEqual(sorted(cores), ["collector", "organizer", "transfer"])

    def test_transfer_not_double_run_within_tick(self) -> None:
        # 级联触发转存后，兜底不应再跑一次转存
        factory = _FakeFactory(
            collect_result=_CollectResult(scanned=1),
            sub_summary=_SubSummary(created=1),
            transfer_results=[_TransferResult(claimed=True), _TransferResult(claimed=False)],
            organize_result=_OrganizeResult(),
        )
        repo = _FakeRepo(_State("running"))
        runtime = _runtime(factory, repo)

        results = runtime.run_once()
        transfer_runs = [r for r in results if r.core == "transfer"]
        organizer_runs = [r for r in results if r.core == "organizer"]

        self.assertEqual(len(transfer_runs), 1)
        self.assertEqual(len(organizer_runs), 1)

    def test_stopped_state_returns_empty(self) -> None:
        factory = _FakeFactory(
            collect_result=_CollectResult(),
            sub_summary=_SubSummary(),
            transfer_results=[],
            organize_result=_OrganizeResult(),
        )
        repo = _FakeRepo(_State("stopped"))
        runtime = _runtime(factory, repo)

        self.assertEqual(runtime.run_once(), [])

    def test_transfer_build_failure_is_blocked_not_crash(self) -> None:
        factory = _FakeFactory(
            collect_result=_CollectResult(scanned=0),
            sub_summary=_SubSummary(created=0),
            transfer_results=[],
            organize_result=_OrganizeResult(),
            transfer_buildable=False,
        )
        repo = _FakeRepo(_State("running"))
        runtime = _runtime(factory, repo)

        results = runtime.run_once()
        transfer = next(r for r in results if r.core == "transfer")
        self.assertEqual(transfer.status, "blocked")

    def test_pending_manual_trigger_is_drained_and_runs_organizer(self) -> None:
        # 跨进程手动触发：DB 里有待处理的 manual_organize，tick 应认领并触发整理
        factory = _FakeFactory(
            collect_result=_CollectResult(scanned=0),
            sub_summary=_SubSummary(created=0),
            transfer_results=[_TransferResult(claimed=False)],
            organize_result=_OrganizeResult(success_count=1),
        )
        repo = _FakeRepo(_State("running"))
        repo.pending_triggers = [(1, "manual_organize", "api")]
        runtime = _runtime(factory, repo)

        runtime.run_once()

        # manual_organize 触发整理 + 兜底也跑整理；以服务调用次数确认至少跑了
        self.assertGreaterEqual(factory.organize_service.calls, 1)

    def test_run_until_stopped_honors_max_ticks(self) -> None:
        factory = _FakeFactory(
            collect_result=_CollectResult(),
            sub_summary=_SubSummary(),
            transfer_results=[],
            organize_result=_OrganizeResult(),
        )
        repo = _FakeRepo(_State("running"))
        runtime = _runtime(factory, repo)
        # sweep 间隔设 0 使每个 tick 都跑完整兜底，从而用 collector 运行次数验证 tick 数
        runtime._sweep_interval_seconds = 0

        results = runtime.run_until_stopped(max_ticks=2)
        collector_runs = [r for r in results if r.core == "collector"]
        self.assertEqual(len(collector_runs), 2)

    def test_sweep_skipped_when_interval_not_elapsed(self) -> None:
        factory = _FakeFactory(
            collect_result=_CollectResult(),
            sub_summary=_SubSummary(),
            transfer_results=[],
            organize_result=_OrganizeResult(),
        )
        repo = _FakeRepo(_State("running"))
        runtime = _runtime(factory, repo)
        runtime._sweep_interval_seconds = 3600

        # 第一个 tick：首次 sweep 必跑收集器
        first = runtime.run_once()
        # 第二个 tick：间隔未到，跳过完整兜底，不再跑收集器
        second = runtime.run_once()

        self.assertEqual([r.core for r in first if r.core == "collector"], ["collector"])
        self.assertEqual([r.core for r in second if r.core == "collector"], [])

    def test_manual_trigger_drained_every_tick_even_without_sweep(self) -> None:
        factory = _FakeFactory(
            collect_result=_CollectResult(),
            sub_summary=_SubSummary(),
            transfer_results=[_TransferResult(claimed=False)],
            organize_result=_OrganizeResult(success_count=1),
        )
        repo = _FakeRepo(_State("running"))
        runtime = _runtime(factory, repo)
        runtime._sweep_interval_seconds = 3600

        # 先消耗掉首次 sweep
        runtime.run_once()
        before = factory.organize_service.calls
        # 后续 tick 不再 sweep，但手动触发仍应被认领并跑整理
        repo.pending_triggers = [(1, "manual_organize", "api")]
        runtime.run_once()

        self.assertGreater(factory.organize_service.calls, before)


if __name__ == "__main__":
    unittest.main()
