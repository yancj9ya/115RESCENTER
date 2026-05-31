from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.notifications import (
    BarkNotifier,
    NotificationService,
    TelegramBotNotifier,
    WebhookConfig,
)
from src.organizing.ai_filename_parser import AiFilenameParserConfig, DEFAULT_AI_FILENAME_PROMPT
from src.organizing.tmdb import TmdbConfig
from src.storage import Storage115Config

_DEFAULT_API_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


@dataclass(frozen=True)
class AppSettings:
    transfer_cid: int = 0
    p115: Storage115Config | None = None
    tmdb: TmdbConfig | None = None
    notification_webhook: WebhookConfig | None = None
    notification_service: NotificationService | None = None
    ai_filename_parser: AiFilenameParserConfig | None = None
    api_cors_origins: tuple[str, ...] = _DEFAULT_API_CORS_ORIGINS
    media_library_root_cid: int = 0
    organize_min_interval_seconds: float = 0.5
    runtime_interval_seconds: int = 5
    runtime_sweep_interval_seconds: int = 300
    rank_refresh_interval_seconds: int = 14400

    @classmethod
    def from_yaml(cls, config_dir: str | Path = "config") -> "AppSettings":
        """从 YAML 配置文件加载设置

        Args:
            config_dir: 配置文件目录路径

        Returns:
            AppSettings 实例
        """
        from src.config.yaml_settings import AppConfig

        config_path = Path(config_dir)
        if not config_path.exists():
            return cls()

        app_config = AppConfig.from_yaml(config_dir)

        # 转换为 AppSettings
        p115 = None
        if app_config.netdisk.cookies:
            p115 = Storage115Config(
                cookies=app_config.netdisk.cookies,
                ensure_cookies=app_config.netdisk.ensure_cookies,
                cache_home=Path(app_config.netdisk.cache_home),
            )

        tmdb = None
        if app_config.tmdb.bearer_token:
            tmdb = TmdbConfig(
                bearer_token=app_config.tmdb.bearer_token,
                language=app_config.tmdb.language,
            )

        notification_webhook = None
        if app_config.notification.webhook.enabled and app_config.notification.webhook.url:
            notification_webhook = WebhookConfig(
                url=app_config.notification.webhook.url,
                enabled=app_config.notification.webhook.enabled,
                token=app_config.notification.webhook.token or None,
            )

        notification_service = _build_notification_service(app_config.notification)

        api_cors_origins = tuple(
            origin.strip()
            for origin in app_config.api.cors_origins.split(",")
            if origin.strip()
        ) or _DEFAULT_API_CORS_ORIGINS

        prompt = app_config.ai.filename_parser.prompt.strip() or DEFAULT_AI_FILENAME_PROMPT
        ai_filename_parser = AiFilenameParserConfig(
            enabled=app_config.ai.filename_parser.enabled,
            provider=app_config.ai.filename_parser.provider,
            api_key=app_config.ai.filename_parser.api_key,
            base_url=app_config.ai.filename_parser.base_url,
            model=app_config.ai.filename_parser.model,
            timeout_seconds=app_config.ai.filename_parser.timeout_seconds,
            title_similarity_threshold=app_config.ai.filename_parser.title_similarity_threshold,
            prompt=prompt,
        )

        transfer_cid = app_config.netdisk.transfer_cid or 0
        media_library_root_cid = app_config.organize.media_library_root_cid or 0

        return cls(
            transfer_cid=transfer_cid,
            p115=p115,
            tmdb=tmdb,
            notification_webhook=notification_webhook,
            notification_service=notification_service,
            ai_filename_parser=ai_filename_parser,
            api_cors_origins=api_cors_origins,
            media_library_root_cid=media_library_root_cid,
            organize_min_interval_seconds=app_config.organize.min_interval_seconds,
            runtime_interval_seconds=app_config.runtime.interval_seconds,
            runtime_sweep_interval_seconds=app_config.runtime.telegram_collector.interval_seconds,
            rank_refresh_interval_seconds=app_config.runtime.rank_refresh_interval_seconds,
        )


def _build_notification_service(notification_config: object) -> NotificationService | None:
    providers: list[object] = []
    for entry in getattr(notification_config, "telegram_providers", []):
        if entry.enabled and entry.bot_token and entry.chat_id and entry.name:
            providers.append(
                TelegramBotNotifier(name=entry.name, bot_token=entry.bot_token, chat_id=entry.chat_id)
            )
    for entry in getattr(notification_config, "bark_providers", []):
        if entry.enabled and entry.device_key and entry.name:
            providers.append(
                BarkNotifier(name=entry.name, device_key=entry.device_key, server_url=entry.server_url)
            )

    routing = getattr(notification_config, "routing", {}) or {}
    if not providers or not routing:
        return None
    return NotificationService(providers=providers, routing=routing)
