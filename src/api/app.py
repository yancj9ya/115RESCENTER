from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router
from src.api.routes_logs import router as logs_router
from src.config.settings import AppSettings
from src.logging_config import setup_logging


def _load_app_settings() -> AppSettings:
    """从 YAML 配置加载应用设置。配置目录缺失时返回空设置。"""
    config_dir = Path(__file__).resolve().parents[2] / "config"
    return AppSettings.from_yaml(config_dir)


def create_app(db_path: str | Path | None = None, settings: AppSettings | None = None) -> FastAPI:
    app_settings = settings or _load_app_settings()
    api_app = FastAPI()
    api_app.state.db_path = db_path
    api_app.state.settings = app_settings
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


# 模块级别：初始化日志系统
setup_logging()

app = create_app(
    db_path=Path(os.getenv("APP_DB_PATH", "queue.db")),
)
