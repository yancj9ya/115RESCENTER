from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.events import EventBus
from src.runtime.event_runtime import EventDrivenRuntime


@dataclass
class _State:
    desired_state: str = "running"


class _FakeRepo:
    def __init__(self, state: _State) -> None:
        self._state = state
        self.pending_triggers: list[tuple[int, str, str]] = []

    def get_state(self) -> _State:
        return self._state

    def save_worker_heartbeat(self, **kwargs: object) -> None:
        pass

    def claim_pending_manual_triggers(self) -> list[tuple[int, str, str]]:
        claimed = list(self.pending_triggers)
        self.pending_triggers = []
        return claimed


class _FakeRankCacheRepo:
    def __init__(self, *, count: int = 0, oldest: str | None = None) -> None:
        self._count = count
        self._oldest = oldest

    def count(self) -> int:
        return self._count

    def oldest_refreshed_at(self) -> str | None:
        return self._oldest


class _FakeRefreshService:
    def __init__(self) -> None:
        self.calls = 0

    def refresh_all(self) -> None:
        self.calls += 1


@dataclass
class _Settings:
    transfer_cid: int = 99


class _MinimalFactory:
    """只装配榜单刷新相关依赖；其它核心构建在本测试里不触发（sweep 间隔设很大）。"""

    def __init__(self, *, cache_repo: _FakeRankCacheRepo, refresh: _FakeRefreshService, clock) -> None:
        self.settings = _Settings()
        self._cache_repo = cache_repo
        self._refresh = refresh
        self._clock = clock

    def build_clock(self):
        return self._clock

    def build_sleeper(self):
        return lambda _s: None

    def build_runtime_control_repository(self):
        raise NotImplementedError

    def build_rank_cache_repository(self) -> _FakeRankCacheRepo:
        return self._cache_repo

    def build_rank_refresh_service(self) -> _FakeRefreshService:
        return self._refresh


def _runtime(factory, repo, *, clock) -> EventDrivenRuntime:
    runtime = EventDrivenRuntime(factory=factory, bus=EventBus(), repository=repo)  # type: ignore[arg-type]
    # 把三核心兜底 sweep 推到很久以后，隔离出榜单刷新行为
    runtime._sweep_interval_seconds = 10**9
    runtime._last_sweep_at = clock()
    return runtime


class RankRefreshIntegrationTest(unittest.TestCase):
    def test_cold_start_empty_cache_refreshes_immediately(self) -> None:
        now = datetime(2026, 5, 30, tzinfo=timezone.utc)
        cache = _FakeRankCacheRepo(count=0, oldest=None)
        refresh = _FakeRefreshService()
        factory = _MinimalFactory(cache_repo=cache, refresh=refresh, clock=lambda: now)
        runtime = _runtime(factory, _FakeRepo(_State("running")), clock=lambda: now)
        runtime._rank_refresh_interval_seconds = 14400

        runtime.run_once()

        self.assertEqual(refresh.calls, 1)

    def test_fresh_cache_is_not_refreshed(self) -> None:
        now = datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc)
        # 1 小时前刷新过，间隔 4h 未到
        oldest = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        cache = _FakeRankCacheRepo(count=8, oldest=oldest)
        refresh = _FakeRefreshService()
        factory = _MinimalFactory(cache_repo=cache, refresh=refresh, clock=lambda: now)
        runtime = _runtime(factory, _FakeRepo(_State("running")), clock=lambda: now)
        runtime._rank_refresh_interval_seconds = 14400

        runtime.run_once()

        self.assertEqual(refresh.calls, 0)

    def test_stale_cache_is_refreshed(self) -> None:
        now = datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc)
        # 5 小时前刷新过，超过 4h 间隔
        oldest = (now - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S")
        cache = _FakeRankCacheRepo(count=8, oldest=oldest)
        refresh = _FakeRefreshService()
        factory = _MinimalFactory(cache_repo=cache, refresh=refresh, clock=lambda: now)
        runtime = _runtime(factory, _FakeRepo(_State("running")), clock=lambda: now)
        runtime._rank_refresh_interval_seconds = 14400

        runtime.run_once()

        self.assertEqual(refresh.calls, 1)

    def test_manual_refresh_trigger_forces_refresh_even_when_fresh(self) -> None:
        now = datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc)
        oldest = (now - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
        cache = _FakeRankCacheRepo(count=8, oldest=oldest)
        refresh = _FakeRefreshService()
        factory = _MinimalFactory(cache_repo=cache, refresh=refresh, clock=lambda: now)
        repo = _FakeRepo(_State("running"))
        repo.pending_triggers = [(1, "manual_refresh_ranks", "api")]
        runtime = _runtime(factory, repo, clock=lambda: now)
        runtime._rank_refresh_interval_seconds = 14400

        runtime.run_once()

        self.assertEqual(refresh.calls, 1)

    def test_refresh_failure_does_not_crash_tick(self) -> None:
        now = datetime(2026, 5, 30, tzinfo=timezone.utc)
        cache = _FakeRankCacheRepo(count=0, oldest=None)

        class _Boom:
            def refresh_all(self) -> None:
                raise RuntimeError("boom")

        factory = _MinimalFactory(cache_repo=cache, refresh=_Boom(), clock=lambda: now)  # type: ignore[arg-type]
        runtime = _runtime(factory, _FakeRepo(_State("running")), clock=lambda: now)
        runtime._rank_refresh_interval_seconds = 14400

        # 不应抛出
        runtime.run_once()


if __name__ == "__main__":
    unittest.main()
