from __future__ import annotations

import threading
from collections.abc import Callable

from .types import Event, EventName

Handler = Callable[[Event], None]


class EventBus:
    """进程内同步发布/订阅总线。线程安全，订阅者异常互相隔离。

    设计取舍：``publish`` 同步逐个调用订阅者（不开线程），让事件驱动 worker
    的执行时序可预测、易测试；某个订阅者抛异常不影响其余订阅者，异常被收集后
    在所有订阅者执行完毕再抛出（聚合为 first error），避免一个坏消费者吞掉触发。
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._handlers: dict[EventName, list[Handler]] = {}
        self._errors: list[BaseException] = []

    def subscribe(self, name: EventName, handler: Handler) -> Callable[[], None]:
        """注册订阅者，返回一个取消订阅的回调。"""
        with self._lock:
            self._handlers.setdefault(name, []).append(handler)

        def unsubscribe() -> None:
            with self._lock:
                handlers = self._handlers.get(name)
                if handlers and handler in handlers:
                    handlers.remove(handler)

        return unsubscribe

    def publish(self, event: Event) -> None:
        """同步通知所有订阅者。某订阅者异常不阻断其余订阅者，最后抛出第一个异常。"""
        with self._lock:
            handlers = list(self._handlers.get(event.name, ()))

        first_error: BaseException | None = None
        for handler in handlers:
            try:
                handler(event)
            except BaseException as exc:  # noqa: BLE001 - 隔离订阅者，集中上报
                if first_error is None:
                    first_error = exc
        if first_error is not None:
            raise first_error
