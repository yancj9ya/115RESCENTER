from __future__ import annotations

from typing import Any, Protocol

from src.events import COLLECT_DONE, Event, EventBus

from .base import CoreResult

CORE_NAME = "collector"


class _CollectionService(Protocol):
    def poll_once(self) -> Any:
        ...


class _SubscriptionProcessor(Protocol):
    def process(self, limit: int = ...) -> Any:
        ...


class CollectorCore:
    """收集器核心：抓取频道新消息入 collect_queue，再用订阅中心工具匹配产出 transfer_queue。

    一次成功执行（产出了新的转存任务）后发布 ``COLLECT_DONE`` 触发转存核心。
    订阅中心是工具（不落业务队列由它自己写，落库动作在 processor 内对 transfer_queue），
    收集器持有它来完成匹配——符合"收集器持有订阅中心工具"的架构约束。

    底层复用现有 TelegramCollectionService + SubscriptionProcessor，不重写业务逻辑。
    """

    def __init__(
        self,
        *,
        bus: EventBus,
        collection_services: list[_CollectionService],
        subscription_processor: _SubscriptionProcessor,
        source: str = CORE_NAME,
        limit: int = 100,
    ) -> None:
        self._bus = bus
        self._collection_services = collection_services
        self._subscription_processor = subscription_processor
        self._source = source
        self._limit = limit

    def run(self) -> CoreResult:
        scanned = 0
        enqueued = 0
        failed = 0
        first_error: str | None = None

        for service in self._collection_services:
            result = service.poll_once()
            scanned += int(getattr(result, "scanned", 0))
            enqueued += int(getattr(result, "enqueued", 0))
            error = getattr(result, "error", None)
            if error:
                failed += 1
                if first_error is None:
                    first_error = str(error)

        summary = self._subscription_processor.process(limit=self._limit)
        created = int(getattr(summary, "created", 0))
        skipped = int(getattr(summary, "skipped", 0))
        errors = list(getattr(summary, "errors", []) or [])
        if errors:
            failed += len(errors)
            if first_error is None:
                first_error = str(errors[0])

        triggered: tuple[str, ...] = ()
        if created > 0:
            self._bus.publish(Event(name=COLLECT_DONE, source=self._source))
            triggered = (COLLECT_DONE,)

        return CoreResult(
            core=CORE_NAME,
            status="failed" if first_error else "success",
            processed=scanned,
            succeeded=created,
            skipped=skipped,
            failed=failed,
            error=first_error,
            triggered=triggered,
        )
