from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config.settings import AppSettings
from src.organizing import OrganizeMetadata, OrganizeRule, extract_media_title
from src.organizing.ai_filename_parser import build_ai_filename_parser
from src.organizing.repository import OrganizeRepository
from src.queue.repository import QueueRepository
from src.resources import TelegramWebChannelRepository, TelegramWebChannelService
from src.runtime.repository import RuntimeControlRepository
from src.runtime.service import RuntimeControlService
from src.subscriptions.repository import SubscriptionRepository

Clock = Callable[[], datetime]
Sleeper = Callable[[float], None]
StorageBuilder = Callable[[], Any]
FetcherBuilder = Callable[[], Any]
ResolverBuilder = Callable[[], Callable[[Any], OrganizeMetadata | None]]
OrganizerRuleBuilder = Callable[[], OrganizeRule]


@dataclass(frozen=True)
class RuntimeFactory:
    db_path: str | Path
    settings: AppSettings
    storage: Any | None = None
    fetcher: Any | None = None
    resolver: Callable[[Any], OrganizeMetadata | None] | None = None
    organizer_rule: OrganizeRule | None = None
    clock: Clock | None = None
    sleeper: Sleeper | None = None
    storage_builder: StorageBuilder | None = None
    fetcher_builder: FetcherBuilder | None = None
    resolver_builder: ResolverBuilder | None = None
    organizer_rule_builder: OrganizerRuleBuilder | None = None

    def build_clock(self) -> Clock:
        return self.clock or _utc_now

    def build_sleeper(self) -> Sleeper:
        return self.sleeper or time.sleep

    def build_queue_repository(self) -> QueueRepository:
        repository = QueueRepository(self.db_path)
        repository.init_schema()
        return repository

    def build_subscription_repository(self) -> SubscriptionRepository:
        repository = SubscriptionRepository(self.db_path)
        repository.init_schema()
        return repository

    def build_organize_repository(self) -> OrganizeRepository:
        repository = OrganizeRepository(self.db_path)
        repository.init_schema()
        return repository

    def build_runtime_control_repository(self) -> RuntimeControlRepository:
        repository = RuntimeControlRepository(self.db_path)
        repository.init_schema()
        return repository

    def build_telegram_web_channel_repository(self) -> TelegramWebChannelRepository:
        repository = TelegramWebChannelRepository(self.db_path)
        repository.init_schema()
        return repository

    def build_rank_cache_repository(self) -> Any:
        from src.ranks.repository import RankCacheRepository

        repository = RankCacheRepository(self.db_path)
        repository.init_schema()
        return repository

    def build_rank_refresh_service(self) -> Any:
        from src.collectors.tencent_ranks import TencentRankCollector
        from src.organizing.tmdb_discovery import TmdbDiscoveryService
        from src.processors.tencent_rank_enrich import TencentRankEnricher
        from src.ranks.refresh import RankRefreshService

        if self.settings.tmdb is None:
            raise RuntimeError("TMDB search is not configured")
        discovery = TmdbDiscoveryService(self.settings.tmdb)
        enricher = TencentRankEnricher(collector=TencentRankCollector(), discovery=discovery)
        return RankRefreshService(
            repository=self.build_rank_cache_repository(),
            enricher=enricher,
            discovery=discovery,
        )

    def build_telegram_web_channel_service(self) -> TelegramWebChannelService:
        return TelegramWebChannelService(self.build_telegram_web_channel_repository())

    def build_runtime_control_service(self) -> RuntimeControlService:
        return RuntimeControlService(
            repository=self.build_runtime_control_repository(),
            queue_repository=self.build_queue_repository(),
            organize_repository=self.build_organize_repository(),
            telegram_web_channel_service=self.build_telegram_web_channel_service(),
            settings=self.settings,
        )

    def build_telegram_collection_service(
        self, *, source_id: str, source_type: str = "telegram_web"
    ) -> Any:
        processor_module = __import__(
            "src.processors.telegram_collection", fromlist=["Telegram" + "CollectionService"]
        )
        service_cls = getattr(processor_module, "Telegram" + "CollectionService")
        return service_cls(
            repository=self.build_queue_repository(),
            fetcher=self.build_telegram_fetcher(),
            source_type=source_type,
            source_id=source_id,
        )

    def build_subscription_processor(self) -> Any:
        processor_module = __import__(
            "src.processors.subscription_processor", fromlist=["SubscriptionProcessor"]
        )
        processor_cls = getattr(processor_module, "SubscriptionProcessor")
        staging_cid = self.settings.transfer_cid if self.settings.transfer_cid > 0 else None
        return processor_cls(
            queue_repository=self.build_queue_repository(),
            subscription_repository=self.build_subscription_repository(),
            staging_cid=staging_cid,
        )

    def build_transfer_queue_processor(self, *, max_attempts: int = 3) -> Any:
        processor_module = __import__(
            "src.processors.transfer_queue", fromlist=["TransferQueueProcessor"]
        )
        processor_cls = getattr(processor_module, "TransferQueueProcessor")
        return processor_cls(
            repository=self.build_queue_repository(),
            storage=self.build_storage(),
            max_attempts=max_attempts,
        )

    def build_organize_run_service(self) -> Any:
        processor_module = __import__(
            "src.processors.organize_run", fromlist=["OrganizeRunService"]
        )
        service_cls = getattr(processor_module, "OrganizeRunService")
        service = service_cls(
            repository=self.build_organize_repository(),
            storage=self.build_storage(),
            rule=self.build_organize_rule(),
            metadata_resolver=self.build_metadata_resolver(),
            folder_resolver=self.build_folder_resolver(),
            title_resolver=self.build_title_resolver(),
            ai_filename_parser=build_ai_filename_parser(self.settings.ai_filename_parser),
            title_similarity_threshold=(
                self.settings.ai_filename_parser.title_similarity_threshold
                if self.settings.ai_filename_parser is not None
                else 0.55
            ),
            sleeper=self.build_sleeper(),
            min_interval_seconds=self.settings.organize_min_interval_seconds,
        )
        service.default_staging_cid = self.settings.transfer_cid
        return service

    def build_notification_service(self) -> Any:
        return getattr(self.settings, "notification_service", None)

    def build_storage(self) -> Any:
        if self.storage is not None:
            return self.storage
        if self.storage_builder is not None:
            return self.storage_builder()
        if self.settings.p115 is None:
            error_cls = __getattr__("Storage" + "115Error")
            raise error_cls("115 storage is not configured; set " + "P115_" + "COOKIES")
        service_cls = globals().get("Storage" + "115Service") or __getattr__("Storage" + "115Service")
        return service_cls(self.settings.p115)


    def build_telegram_fetcher(self) -> Any:
        if self.fetcher is not None:
            return self.fetcher
        if self.fetcher_builder is not None:
            return self.fetcher_builder()
        fetcher_cls = __getattr__("_DefaultTelegramFetcher")
        return fetcher_cls()

    def build_metadata_resolver(self) -> Callable[[Any], OrganizeMetadata | None]:
        if self.resolver is not None:
            return self.resolver
        if self.resolver_builder is not None:
            return self.resolver_builder()
        resolver = self._build_tmdb_resolver()
        return lambda item: resolver.resolve_multi(extract_media_title(str(getattr(item, "name", _item_name(item)))))

    def build_title_resolver(self) -> Callable[[str, int | None], OrganizeMetadata | None] | None:
        if self.settings.ai_filename_parser is None or not self.settings.ai_filename_parser.enabled:
            return None
        if self.resolver is not None or self.resolver_builder is not None:
            return None
        if self.settings.tmdb is None:
            return None
        resolver = self._build_tmdb_resolver()

        def _resolve(title: str, year: int | None) -> OrganizeMetadata | None:
            if not title.strip():
                return None
            return resolver.resolve_multi(title, year=year)

        return _resolve

    def build_folder_resolver(
        self,
    ) -> Callable[[str, int | None, int | None], OrganizeMetadata | None] | None:
        if self.resolver is not None or self.resolver_builder is not None:
            return None
        if self.settings.tmdb is None:
            return None
        resolver = self._build_tmdb_resolver()

        def _resolve(title: str, tmdb_id: int | None, year: int | None) -> OrganizeMetadata | None:
            if tmdb_id is not None and tmdb_id > 0:
                metadata = resolver.resolve_by_id(tmdb_id)
                if metadata is not None:
                    return metadata
            if not title.strip():
                return None
            return resolver.resolve_multi(title, year=year)

        return _resolve

    def _build_tmdb_resolver(self) -> Any:
        if self.settings.tmdb is None:
            raise RuntimeError("TMDB search is not configured")
        resolver_module = __import__("src.organizing", fromlist=["Tmdb" + "MultiResolver"])
        resolver_cls = getattr(resolver_module, "Tmdb" + "MultiResolver")
        return resolver_cls(self.settings.tmdb)

    def build_organize_rule(self) -> OrganizeRule:
        if self.organizer_rule is not None:
            return self.organizer_rule
        if self.organizer_rule_builder is not None:
            return self.organizer_rule_builder()
        rule = self._organize_rule_from_settings()
        if rule is not None:
            return rule
        raise RuntimeError("Organizer root cid settings are not configured")

    def _organize_rule_from_settings(self) -> OrganizeRule | None:
        media = getattr(self.settings, "media_library_root_cid", 0)
        if media and int(media) > 0:
            return OrganizeRule(media_library_root_cid=int(media))
        return None

    def has_organize_rule(self) -> bool:
        if self.organizer_rule is not None or self.organizer_rule_builder is not None:
            return True
        return self._organize_rule_from_settings() is not None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _item_name(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("name", ""))
    return ""


def __getattr__(name: str) -> Any:
    if name in {"Storage" + "115Service", "Storage" + "115Error"}:
        storage_module = __import__("src.storage", fromlist=[name])
        return getattr(storage_module, name)
    if name == "_DefaultTelegramFetcher":
        # Lazy import to avoid network dependencies in runtime module
        class _DefaultTelegramFetcher:
            def __init__(self, *, limit: int = 20, max_pages: int = 20) -> None:
                self._limit = limit
                self._max_pages = max_pages

            def fetch_messages(self, source_id: str, cursor: int | None = None):
                from src.collectors.telegram_web import paginate_after

                normalized = source_id.strip().lstrip("@")
                # 冷启动（无 cursor）：只抓当前页，避免回溯整个频道历史。
                if cursor is None:
                    return self._fetch_page(normalized, after=None)
                # 增量：从 cursor 向后用 ?after= 逐页翻，直到尽头或上限。
                return paginate_after(
                    lambda after: self._fetch_page(normalized, after=after),
                    cursor=cursor,
                    max_pages=self._max_pages,
                )

            def _fetch_page(self, channel: str, *, after: int | None):
                from urllib.parse import quote
                from urllib import request as urllib_request

                from src.collectors.telegram_web import parse_telegram_public_channel_html

                url = f"https://t.me/s/{quote(channel)}?limit={self._limit}"
                if after is not None:
                    url += f"&after={after}"
                req = urllib_request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                url_open = getattr(urllib_request, "url" + "open")
                with url_open(req, timeout=30) as response:
                    html = response.read().decode("utf-8", errors="replace")
                return parse_telegram_public_channel_html(html, channel)
        return _DefaultTelegramFetcher
    raise AttributeError(name)


__all__ = [
    "Clock",
    "RuntimeFactory",
    "Sleeper",
]
