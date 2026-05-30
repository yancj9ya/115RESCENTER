from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CoreResult:
    """一次核心执行的结果摘要。

    ``triggered`` 列出本次执行后发布的下游事件名（用于诊断/留痕和测试断言）；
    各计数字段语义随核心而异，统一用于运行时上报。
    """

    core: str
    status: str
    processed: int = 0
    succeeded: int = 0
    skipped: int = 0
    failed: int = 0
    error: str | None = None
    triggered: tuple[str, ...] = field(default_factory=tuple)
