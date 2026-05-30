"""日志 API 路由"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, StreamingResponse

from src.logging_config import clear_log_buffer, get_recent_logs, read_log_entries

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("/recent")
def get_recent_logs_endpoint(
    limit: int = Query(100, ge=1, le=1000, description="返回的最大日志条数"),
    level: str | None = Query(None, description="过滤日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)"),
) -> JSONResponse:
    logs = get_recent_logs(limit=limit, level=level)
    return JSONResponse(
        content={"total": len(logs), "logs": logs},
        media_type="application/json; charset=utf-8",
    )


@router.delete("/clear")
def clear_logs_endpoint() -> dict[str, str]:
    clear_log_buffer()
    return {"status": "ok", "message": "日志缓存已清空"}


@router.get("/stream")
async def stream_logs_endpoint() -> StreamingResponse:
    """SSE 实时日志推送（从日志文件读取，跨进程共享）"""

    async def _generate() -> AsyncGenerator[str, None]:
        entries = read_log_entries()
        # 先推送最近 50 条历史
        for entry in entries[-50:]:
            yield f"data: {json.dumps(entry, ensure_ascii=False)}\n\n"
        last_count = len(entries)

        while True:
            await asyncio.sleep(1)
            entries = read_log_entries()
            current_count = len(entries)
            if current_count > last_count:
                for entry in entries[last_count:current_count]:
                    yield f"data: {json.dumps(entry, ensure_ascii=False)}\n\n"
                last_count = current_count
            else:
                # 文件被轮转/清空时重置游标
                if current_count < last_count:
                    last_count = current_count
                yield ": keepalive\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )

