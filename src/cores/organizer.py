from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from src.events import Event, EventBus, ORGANIZE_DONE
from src.notifications import OrganizeItemSummary, build_organize_summary

from .base import CoreResult

logger = logging.getLogger(__name__)

CORE_NAME = "organizer"


class _OrganizeRunService(Protocol):
    def run_once(self, staging_cid: int) -> Any:
        ...


class _OrganizeItemReader(Protocol):
    def list_run_items(self, run_id: int) -> list[Any]:
        ...


class _Notifier(Protocol):
    def notify(self, source: str, event: Any) -> None:
        ...


class OrganizerCore:
    """整理器核心：扫中转目录，用 TMDB 工具解析元数据 + 115 工具重命名/移动到媒体库。

    整理失败的文件记录并跳过等待人工处理（底层 OrganizeRunService 已实现，并落
    organize_runs/organize_run_items 留痕）。一次执行后发布 ``ORGANIZE_DONE``
    （供通知等下游订阅）。持有 TMDB + 115 网盘工具——符合架构约束。
    """

    def __init__(
        self,
        *,
        bus: EventBus,
        service: _OrganizeRunService,
        staging_cid: int,
        source: str = CORE_NAME,
        notifier: _Notifier | None = None,
        item_reader: _OrganizeItemReader | None = None,
    ) -> None:
        self._bus = bus
        self._service = service
        self._staging_cid = staging_cid
        self._source = source
        self._notifier = notifier
        self._item_reader = item_reader

    def run(self) -> CoreResult:
        result = self._service.run_once(self._staging_cid)
        status_text = str(getattr(result, "status", ""))
        error = getattr(result, "last_error", None)
        if status_text == "FAILED":
            status = "failed"
        elif status_text == "PARTIAL_SUCCESS":
            status = "degraded"
        else:
            status = "success"

        # 先发事件再发通知：通知是旁路，其失败不能阻止 ORGANIZE_DONE 级联。
        self._bus.publish(Event(name=ORGANIZE_DONE, source=self._source))
        self._notify_summary(result)

        return CoreResult(
            core=CORE_NAME,
            status=status,
            processed=int(getattr(result, "scanned_count", 0)),
            succeeded=int(getattr(result, "success_count", 0)),
            skipped=int(getattr(result, "skipped_count", 0)),
            failed=int(getattr(result, "failed_count", 0)),
            error=error,
            triggered=(ORGANIZE_DONE,),
        )

    def _notify_summary(self, result: Any) -> None:
        if self._notifier is None or self._item_reader is None:
            return
        if int(getattr(result, "success_count", 0)) <= 0:
            return
        run_id = getattr(result, "run_id", None)
        if run_id is None:
            return
        # 整个通知旁路（读 run items + 构建 + 发送）失败都不能拖垮整理核心或冒泡出 run()。
        try:
            summaries = _success_item_summaries(self._item_reader.list_run_items(int(run_id)))
            event = build_organize_summary(summaries)
            if event is None:
                return
            self._notifier.notify(self._source, event)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"整理通知发送失败（已忽略）: {exc}")


def _success_item_summaries(items: list[Any]) -> list[OrganizeItemSummary]:
    summaries: list[OrganizeItemSummary] = []
    for item in items:
        if str(getattr(item, "status", "")) != "SUCCESS":
            continue
        metadata = _parse_metadata(getattr(item, "metadata_json", None))
        title = str(metadata.get("title") or getattr(item, "new_name", None) or getattr(item, "file_name", ""))
        tmdb_id = metadata.get("tmdb_id")
        summaries.append(
            OrganizeItemSummary(
                tmdb_id=int(tmdb_id) if isinstance(tmdb_id, int) else None,
                title=title,
                season=metadata.get("season") if isinstance(metadata.get("season"), int) else None,
                episode=metadata.get("episode") if isinstance(metadata.get("episode"), int) else None,
            )
        )
    return summaries


def _parse_metadata(metadata_json: str | None) -> dict[str, Any]:
    if not metadata_json:
        return {}
    try:
        parsed = json.loads(metadata_json)
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
