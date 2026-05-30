from __future__ import annotations

import logging
from typing import Any, Protocol

from src.events import Event, EventBus, TRANSFER_DONE
from src.notifications import build_transfer_summary

from .base import CoreResult

logger = logging.getLogger(__name__)

CORE_NAME = "transfer"


class _TransferProcessor(Protocol):
    def process_next_transfer(self) -> Any:
        ...


class _Notifier(Protocol):
    def notify(self, source: str, event: Any) -> None:
        ...


class TransferCore:
    """转存器核心：消费 transfer_queue，调 115 网盘工具 save_share 转存到中转目录。

    转存失败由底层 processor 重试（最多 3 次，超限标记 FAILED）。一次执行若成功处理了
    至少一条任务，发布 ``TRANSFER_DONE`` 触发整理核心。持有 115 网盘工具——符合
    "转存器持有 115 网盘工具"的架构约束。复用现有 TransferQueueProcessor。
    """

    def __init__(
        self,
        *,
        bus: EventBus,
        processor: _TransferProcessor,
        source: str = CORE_NAME,
        max_items: int = 100,
        notifier: _Notifier | None = None,
    ) -> None:
        self._bus = bus
        self._processor = processor
        self._source = source
        self._max_items = max_items
        self._notifier = notifier

    def run(self) -> CoreResult:
        processed = 0
        succeeded = 0
        failed = 0
        first_error: str | None = None

        for _ in range(max(self._max_items, 0)):
            result = self._processor.process_next_transfer()
            if not getattr(result, "claimed", False):
                break
            processed += 1
            error = getattr(result, "error", None)
            if error:
                failed += 1
                if first_error is None:
                    first_error = str(error)
            else:
                succeeded += 1

        triggered: tuple[str, ...] = ()
        if succeeded > 0:
            self._bus.publish(Event(name=TRANSFER_DONE, source=self._source))
            triggered = (TRANSFER_DONE,)

        self._notify_summary(succeeded=succeeded, failed=failed)

        return CoreResult(
            core=CORE_NAME,
            status="failed" if first_error else "success",
            processed=processed,
            succeeded=succeeded,
            failed=failed,
            error=first_error,
            triggered=triggered,
        )

    def _notify_summary(self, *, succeeded: int, failed: int) -> None:
        if self._notifier is None:
            return
        event = build_transfer_summary(succeeded=succeeded, failed=failed)
        if event is None:
            return
        # 通知是旁路：失败（webhook 超时/token 失效等）不能拖垮转存核心或冒泡出 run()。
        try:
            self._notifier.notify(self._source, event)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"转存通知发送失败（已忽略）: {exc}")
