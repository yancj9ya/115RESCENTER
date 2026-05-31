"""统一配置管理

从 YAML 配置文件加载所有配置项，替代原有的环境变量方式。
支持配置验证、默认值和环境变量覆盖。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .loader import ConfigLoader, create_default_config_loader


@dataclass
class NetdiskConfig:
    """网盘配置"""

    # 115 网盘 Cookie
    cookies: str = ""
    # 是否确保 Cookie 有效性
    ensure_cookies: bool = False
    # 缓存目录
    cache_home: str = ".p115client.cache.d"
    # 中转目录 CID
    transfer_cid: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NetdiskConfig":
        """从字典创建配置"""
        p115_config = data.get("p115", {})
        return cls(
            cookies=p115_config.get("cookies", ""),
            ensure_cookies=p115_config.get("ensure_cookies", False),
            cache_home=p115_config.get("cache_home", ".p115client.cache.d"),
            transfer_cid=p115_config.get("transfer_cid"),
        )


@dataclass
class TmdbConfig:
    """TMDB 配置"""

    # TMDB Bearer Token
    bearer_token: str = ""
    # 查询语言
    language: str = "zh-CN"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TmdbConfig":
        """从字典创建配置"""
        tmdb_config = data.get("tmdb", {})
        return cls(
            bearer_token=tmdb_config.get("bearer_token", ""),
            language=tmdb_config.get("language", "zh-CN"),
        )


@dataclass
class AiFilenameParserYamlConfig:
    """AI 文件名解析配置"""

    enabled: bool = False
    provider: str = "openai_compatible"
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    timeout_seconds: float = 30.0
    title_similarity_threshold: float = 0.55
    prompt: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AiFilenameParserYamlConfig":
        ai_config = data.get("ai", {})
        parser_config = ai_config.get("filename_parser", {})
        return cls(
            enabled=parser_config.get("enabled", False),
            provider=parser_config.get("provider", "openai_compatible"),
            api_key=parser_config.get("api_key", ""),
            base_url=parser_config.get("base_url", ""),
            model=parser_config.get("model", ""),
            timeout_seconds=parser_config.get("timeout_seconds", 30.0),
            title_similarity_threshold=parser_config.get("title_similarity_threshold", 0.55),
            prompt=parser_config.get("prompt", ""),
        )


@dataclass
class AiConfig:
    """AI 配置"""

    filename_parser: AiFilenameParserYamlConfig = field(default_factory=AiFilenameParserYamlConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AiConfig":
        return cls(filename_parser=AiFilenameParserYamlConfig.from_dict(data))


@dataclass
class OrganizeConfig:
    """整理配置"""

    # 媒体库根目录 CID
    media_library_root_cid: int | None = None
    # 是否启用自动整理
    auto_organize: bool = False
    # 整理间隔（秒）
    interval_seconds: int = 300
    # 重复文件处理策略
    duplicate_strategy: str = "keep_larger"
    # TMDB 解析失败处理
    unmatched_strategy: str = "keep_in_staging"
    # 单文件整理之间的最小间隔（秒），用于规避 115 网盘 QPS 限制
    min_interval_seconds: float = 0.5

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OrganizeConfig":
        """从字典创建配置"""
        organize_config = data.get("organize", {})
        return cls(
            media_library_root_cid=organize_config.get("media_library_root_cid"),
            auto_organize=organize_config.get("auto_organize", False),
            interval_seconds=organize_config.get("interval_seconds", 300),
            duplicate_strategy=organize_config.get("duplicate_strategy", "keep_larger"),
            unmatched_strategy=organize_config.get("unmatched_strategy", "keep_in_staging"),
            min_interval_seconds=organize_config.get("min_interval_seconds", 0.5),
        )


@dataclass
class SubscriptionConfig:
    """订阅配置"""

    # 是否启用自动订阅处理
    auto_process: bool = False
    # 处理间隔（秒）
    interval_seconds: int = 60
    # 每次处理的最大项目数
    max_items_per_tick: int = 10
    # 默认订阅规则
    default_rules: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SubscriptionConfig":
        """从字典创建配置"""
        subscription_config = data.get("subscription", {})
        return cls(
            auto_process=subscription_config.get("auto_process", False),
            interval_seconds=subscription_config.get("interval_seconds", 60),
            max_items_per_tick=subscription_config.get("max_items_per_tick", 10),
            default_rules=subscription_config.get("default_rules", []),
        )


@dataclass
class WebhookConfig:
    """Webhook 配置"""

    # 是否启用
    enabled: bool = False
    # Webhook URL
    url: str = ""
    # 认证 Token
    token: str = ""
    # 请求超时（秒）
    timeout: int = 10
    # 重试次数
    retry_count: int = 3

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WebhookConfig":
        """从字典创建配置"""
        return cls(
            enabled=data.get("enabled", False),
            url=data.get("url", ""),
            token=data.get("token", ""),
            timeout=data.get("timeout", 10),
            retry_count=data.get("retry_count", 3),
        )


@dataclass
class TelegramProviderConfig:
    """Telegram Bot provider 配置"""

    name: str = ""
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TelegramProviderConfig":
        return cls(
            name=data.get("name", ""),
            enabled=data.get("enabled", False),
            bot_token=data.get("bot_token", ""),
            chat_id=data.get("chat_id", ""),
        )


@dataclass
class BarkProviderConfig:
    """iOS Bark provider 配置"""

    name: str = ""
    enabled: bool = False
    device_key: str = ""
    server_url: str = "https://api.day.app"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BarkProviderConfig":
        return cls(
            name=data.get("name", ""),
            enabled=data.get("enabled", False),
            device_key=data.get("device_key", ""),
            server_url=data.get("server_url", "https://api.day.app"),
        )


@dataclass
class NotificationConfig:
    """通知配置"""

    # Webhook 配置
    webhook: WebhookConfig = field(default_factory=WebhookConfig)
    # Telegram provider 列表
    telegram_providers: list[TelegramProviderConfig] = field(default_factory=list)
    # Bark provider 列表
    bark_providers: list[BarkProviderConfig] = field(default_factory=list)
    # 分流路由：核心名 -> provider name 列表
    routing: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NotificationConfig":
        """从字典创建配置"""
        notification_config = data.get("notification", {})
        webhook_data = notification_config.get("webhook", {})
        providers_data = notification_config.get("providers", {}) or {}
        telegram_providers = [
            TelegramProviderConfig.from_dict(entry)
            for entry in providers_data.get("telegram", []) or []
        ]
        bark_providers = [
            BarkProviderConfig.from_dict(entry)
            for entry in providers_data.get("bark", []) or []
        ]
        routing_raw = notification_config.get("routing", {}) or {}
        routing = {
            str(source): [str(name) for name in (names or [])]
            for source, names in routing_raw.items()
        }
        return cls(
            webhook=WebhookConfig.from_dict(webhook_data),
            telegram_providers=telegram_providers,
            bark_providers=bark_providers,
            routing=routing,
        )


@dataclass
class ApiConfig:
    """API 配置"""

    # CORS 允许的源
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # API 服务端口
    port: int = 8000
    # API 服务主机
    host: str = "0.0.0.0"
    # API 文档路径
    docs_url: str | None = "/docs"
    # ReDoc 文档路径
    redoc_url: str | None = "/redoc"
    # 日志级别
    log_level: str = "info"
    # 是否启用热重载
    reload: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApiConfig":
        """从字典创建配置"""
        api_config = data.get("api", {})
        return cls(
            cors_origins=api_config.get("cors_origins", "http://localhost:5173,http://127.0.0.1:5173"),
            port=api_config.get("port", 8000),
            host=api_config.get("host", "0.0.0.0"),
            docs_url=api_config.get("docs_url", "/docs"),
            redoc_url=api_config.get("redoc_url", "/redoc"),
            log_level=api_config.get("log_level", "info"),
            reload=api_config.get("reload", False),
        )


@dataclass
class RuntimeComponentConfig:
    """运行时组件配置"""

    # 是否启用
    enabled: bool = False
    # 间隔（秒）
    interval_seconds: int = 60

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuntimeComponentConfig":
        """从字典创建配置"""
        return cls(
            enabled=data.get("enabled", False),
            interval_seconds=data.get("interval_seconds", 60),
        )


@dataclass
class RuntimeConfig:
    """运行时配置"""

    # 是否启用运行时调度器
    enabled: bool = False
    # 调度间隔（秒）
    interval_seconds: int = 5
    # 每次处理的最大项目数
    max_items_per_tick: int = 3
    # 榜单缓存刷新间隔（秒），默认 4 小时
    rank_refresh_interval_seconds: int = 14400
    # 数据库路径
    db_path: str = "queue.db"
    # 组件配置
    telegram_collector: RuntimeComponentConfig = field(default_factory=RuntimeComponentConfig)
    subscription_processor: RuntimeComponentConfig = field(default_factory=RuntimeComponentConfig)
    transfer_processor: RuntimeComponentConfig = field(default_factory=RuntimeComponentConfig)
    organizer: RuntimeComponentConfig = field(default_factory=RuntimeComponentConfig)
    # 兼容性配置
    dotenv_path: str | None = None
    allow_env_override: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuntimeConfig":
        """从字典创建配置"""
        runtime_config = data.get("runtime", {})
        components = runtime_config.get("components", {})
        compatibility = runtime_config.get("compatibility", {})

        return cls(
            enabled=runtime_config.get("enabled", False),
            interval_seconds=runtime_config.get("interval_seconds", 5),
            max_items_per_tick=runtime_config.get("max_items_per_tick", 3),
            rank_refresh_interval_seconds=runtime_config.get("rank_refresh_interval_seconds", 14400),
            db_path=runtime_config.get("db_path", "queue.db"),
            telegram_collector=RuntimeComponentConfig.from_dict(
                components.get("telegram_collector", {})
            ),
            subscription_processor=RuntimeComponentConfig.from_dict(
                components.get("subscription_processor", {})
            ),
            transfer_processor=RuntimeComponentConfig.from_dict(
                components.get("transfer_processor", {})
            ),
            organizer=RuntimeComponentConfig.from_dict(
                components.get("organizer", {})
            ),
            dotenv_path=compatibility.get("dotenv_path"),
            allow_env_override=compatibility.get("allow_env_override", False),
        )


@dataclass
class AppConfig:
    """应用配置（整合所有配置）"""

    netdisk: NetdiskConfig = field(default_factory=NetdiskConfig)
    tmdb: TmdbConfig = field(default_factory=TmdbConfig)
    organize: OrganizeConfig = field(default_factory=OrganizeConfig)
    subscription: SubscriptionConfig = field(default_factory=SubscriptionConfig)
    notification: NotificationConfig = field(default_factory=NotificationConfig)
    api: ApiConfig = field(default_factory=ApiConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    ai: AiConfig = field(default_factory=AiConfig)

    @classmethod
    def from_yaml(cls, config_dir: str | Path = "config") -> "AppConfig":
        """从 YAML 配置文件加载

        Args:
            config_dir: 配置文件目录路径

        Returns:
            AppConfig 实例

        Raises:
            FileNotFoundError: 配置目录不存在
        """
        loader = ConfigLoader(config_dir)
        all_config = loader.load_all()

        return cls(
            netdisk=NetdiskConfig.from_dict(all_config.get("netdisk", {})),
            tmdb=TmdbConfig.from_dict(all_config.get("tmdb", {})),
            organize=OrganizeConfig.from_dict(all_config.get("organize", {})),
            subscription=SubscriptionConfig.from_dict(all_config.get("subscription", {})),
            notification=NotificationConfig.from_dict(all_config.get("notification", {})),
            api=ApiConfig.from_dict(all_config.get("api", {})),
            runtime=RuntimeConfig.from_dict(all_config.get("runtime", {})),
            ai=AiConfig.from_dict(all_config.get("ai", {})),
        )

    @classmethod
    def from_default_location(cls) -> "AppConfig":
        """从默认位置加载配置

        Returns:
            AppConfig 实例

        Raises:
            FileNotFoundError: 找不到配置目录
        """
        loader = create_default_config_loader()
        all_config = loader.load_all()

        return cls(
            netdisk=NetdiskConfig.from_dict(all_config.get("netdisk", {})),
            tmdb=TmdbConfig.from_dict(all_config.get("tmdb", {})),
            organize=OrganizeConfig.from_dict(all_config.get("organize", {})),
            subscription=SubscriptionConfig.from_dict(all_config.get("subscription", {})),
            notification=NotificationConfig.from_dict(all_config.get("notification", {})),
            api=ApiConfig.from_dict(all_config.get("api", {})),
            runtime=RuntimeConfig.from_dict(all_config.get("runtime", {})),
            ai=AiConfig.from_dict(all_config.get("ai", {})),
        )


__all__ = [
    "AppConfig",
    "AiConfig",
    "AiFilenameParserYamlConfig",
    "NetdiskConfig",
    "TmdbConfig",
    "OrganizeConfig",
    "SubscriptionConfig",
    "NotificationConfig",
    "WebhookConfig",
    "ApiConfig",
    "RuntimeConfig",
    "RuntimeComponentConfig",
]
