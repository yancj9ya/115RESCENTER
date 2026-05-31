from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Event as ThreadEvent, Thread

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router
from src.api.routes_logs import router as logs_router
from src.config.settings import AppSettings
from src.logging_config import setup_logging
from src.runtime.event_runtime import EventDrivenRuntime
from src.runtime.factory import RuntimeFactory


def _load_app_settings() -> AppSettings:
    """从 YAML 配置加载应用设置。配置目录缺失时返回空设置。"""
    config_dir = Path(__file__).resolve().parents[2] / "config"
    return AppSettings.from_yaml(config_dir)


def create_app(
    db_path: str | Path | None = None,
    settings: AppSettings | None = None,
    *,
    start_runtime: bool = False,
) -> FastAPI:
    app_settings = settings or _load_app_settings()
    api_app = FastAPI(lifespan=_runtime_lifespan if start_runtime else None)
    api_app.state.db_path = db_path
    api_app.state.settings = app_settings
    api_app.state.start_runtime = start_runtime
    _apply_organize_state(api_app, app_settings)
    api_app.add_middleware(
        CORSMiddleware,
        allow_origins=list(app_settings.api_cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
    )
    api_app.include_router(router)
    api_app.include_router(logs_router)
    return api_app


def _apply_organize_state(api_app: FastAPI, settings: AppSettings) -> None:
    api_app.state.media_library_root_cid = settings.media_library_root_cid or None


@asynccontextmanager
async def _runtime_lifespan(api_app: FastAPI) -> AsyncIterator[None]:
    db_path = api_app.state.db_path
    if db_path is None:
        yield
        return

    factory = RuntimeFactory(db_path=db_path, settings=api_app.state.settings)
    control_service = factory.build_runtime_control_service()
    control_service.start()
    runtime = EventDrivenRuntime(factory=factory)
    _apply_runtime_settings(runtime, api_app.state.settings)
    stop_event = ThreadEvent()
    thread = Thread(
        target=_run_api_runtime,
        args=(runtime, stop_event),
        name="api-runtime-worker",
        daemon=True,
    )
    api_app.state.runtime = runtime
    api_app.state.runtime_thread = thread
    thread.start()
    try:
        yield
    finally:
        stop_event.set()
        control_service.stop()
        thread.join(timeout=5)


def _run_api_runtime(runtime: EventDrivenRuntime, stop_event: ThreadEvent) -> None:
    while not stop_event.is_set():
        runtime.run_once()
        stop_event.wait(float(runtime._interval_seconds))


def _apply_runtime_settings(runtime: EventDrivenRuntime, settings: AppSettings) -> None:
    runtime._interval_seconds = settings.runtime_interval_seconds
    runtime._sweep_interval_seconds = settings.runtime_sweep_interval_seconds
    runtime._rank_refresh_interval_seconds = settings.rank_refresh_interval_seconds


# 模块级别：初始化日志系统
setup_logging()

app = create_app(
    db_path=Path(os.getenv("APP_DB_PATH", "queue.db")),
    start_runtime=True,
)
