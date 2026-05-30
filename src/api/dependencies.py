from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from fastapi import Depends, HTTPException, Request

from src.collectors.tencent_ranks import TencentRankCollector
from src.config.settings import AppSettings
from src.organizing import OrganizeRule, TmdbDiscoveryService, TmdbMovieResolver, TmdbMultiResolver, extract_media_title, extract_tmdb_id
from src.organizing.repository import OrganizeRepository
from src.processors.tencent_rank_enrich import TencentRankEnricher
from src.processors.organize_run import OrganizeRunService
from src.processors.subscription_processor import SubscriptionProcessor
from src.processors.transfer_queue import TransferQueueProcessor
from src.queue.repository import QueueRepository
from src.ranks.repository import RankCacheRepository
from src.resources import TelegramWebChannelRepository, TelegramWebChannelService
from src.runtime import RuntimeControlRepository, RuntimeControlService
from src.storage import Storage115Service
from src.subscriptions.repository import SubscriptionRepository
from src.subscriptions.service import SubscriptionService


def get_db_path(request: Request) -> str | Path | None:
    return request.app.state.db_path


def get_app_settings(request: Request) -> AppSettings:
    return request.app.state.settings


def get_storage115_service(
    request: Request,
    settings: AppSettings = Depends(get_app_settings),
) -> Storage115Service:
    if settings.p115 is None:
        raise HTTPException(status_code=503, detail="115 storage is not configured")

    configured_service = getattr(request.app.state, "storage115_service", None)
    if configured_service is not None:
        return configured_service

    configured_factory = getattr(request.app.state, "storage115_service_factory", None)
    if configured_factory is not None:
        return configured_factory(settings.p115)

    return Storage115Service(settings.p115)


def get_queue_repository(request: Request) -> QueueRepository:
    db_path = get_db_path(request)
    if db_path is None:
        raise RuntimeError("Queue API requires app.state.db_path to be set")
    repository = QueueRepository(db_path)
    repository.init_schema()
    return repository


def get_subscription_repository(request: Request) -> SubscriptionRepository:
    db_path = get_db_path(request)
    if db_path is None:
        raise RuntimeError("Subscription API requires app.state.db_path to be set")
    repository = SubscriptionRepository(db_path)
    repository.init_schema()
    return repository


def get_subscription_service(
    repository: SubscriptionRepository = Depends(get_subscription_repository),
) -> SubscriptionService:
    return SubscriptionService(repository)


def get_organize_repository(request: Request) -> OrganizeRepository:
    configured_repository = getattr(request.app.state, "organize_repository", None)
    if configured_repository is not None:
        return configured_repository

    db_path = get_db_path(request)
    if db_path is None:
        raise RuntimeError("Organizer API requires app.state.db_path to be set")
    repository = OrganizeRepository(db_path)
    repository.init_schema()
    return repository


def get_organize_run_service(
    request: Request,
    settings: AppSettings = Depends(get_app_settings),
    repository: OrganizeRepository = Depends(get_organize_repository),
) -> OrganizeRunService:
    configured_service = getattr(request.app.state, "organize_run_service", None)
    if configured_service is not None:
        return configured_service

    if settings.p115 is None:
        raise HTTPException(status_code=503, detail="115 storage is not configured")
    if settings.tmdb is None:
        raise HTTPException(status_code=503, detail="TMDB search is not configured")

    rule = _organize_rule_from_app_state(request)
    resolver = TmdbMultiResolver(settings.tmdb)

    def metadata_resolver(item: Any) -> Any:
        filename = str(getattr(item, "name", "") or "")
        # 优先使用文件名中的 TMDB ID
        tmdb_id = extract_tmdb_id(filename)
        if tmdb_id is not None:
            # 自动尝试 TV 和 Movie 类型
            metadata = resolver.resolve_by_id(tmdb_id)
            if metadata is not None:
                return metadata
        # 回退到标题搜索
        title = extract_media_title(filename)
        return resolver.resolve_multi(title)

    service = OrganizeRunService(
        repository=repository,
        storage=Storage115Service(settings.p115),
        rule=rule,
        metadata_resolver=metadata_resolver,
    )
    service.default_staging_cid = settings.transfer_cid
    return service


def _organize_rule_from_app_state(request: Request) -> OrganizeRule:
    configured_rule = getattr(request.app.state, "organize_rule", None)
    if configured_rule is not None:
        return configured_rule

    media_root_cid = _positive_int_app_state(request, "media_library_root_cid")
    if media_root_cid is None:
        raise HTTPException(
            status_code=503,
            detail="Organizer root cid settings are not configured: media_library_root_cid",
        )
    return OrganizeRule(media_library_root_cid=media_root_cid)


def _positive_int_app_state(request: Request, name: str) -> int | None:
    value = getattr(request.app.state, name, None)
    if value is None:
        return None
    try:
        cid = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"{name} must be a positive integer") from exc
    if cid <= 0:
        raise HTTPException(status_code=422, detail=f"{name} must be a positive integer")
    return cid


def get_subscription_processor(
    settings: AppSettings = Depends(get_app_settings),
    queue_repository: QueueRepository = Depends(get_queue_repository),
    subscription_repository: SubscriptionRepository = Depends(get_subscription_repository),
) -> SubscriptionProcessor:
    staging_cid = settings.transfer_cid if settings.transfer_cid > 0 else None
    return SubscriptionProcessor(
        queue_repository=queue_repository,
        subscription_repository=subscription_repository,
        staging_cid=staging_cid,
    )


def get_transfer_queue_processor(
    settings: AppSettings = Depends(get_app_settings),
    queue_repository: QueueRepository = Depends(get_queue_repository),
    storage: Storage115Service = Depends(get_storage115_service),
) -> TransferQueueProcessor:
    return TransferQueueProcessor(
        repository=queue_repository,
        storage=storage,
        max_attempts=3,
    )


def get_tmdb_movie_resolver(settings: AppSettings = Depends(get_app_settings)) -> TmdbMovieResolver:
    if settings.tmdb is None:
        raise HTTPException(status_code=503, detail="TMDB search is not configured")
    return TmdbMovieResolver(settings.tmdb)


def get_tmdb_multi_resolver(settings: AppSettings = Depends(get_app_settings)) -> TmdbMultiResolver:
    if settings.tmdb is None:
        raise HTTPException(status_code=503, detail="TMDB search is not configured")
    return TmdbMultiResolver(settings.tmdb)


def get_tmdb_discovery_service(
    request: Request,
    settings: AppSettings = Depends(get_app_settings),
) -> TmdbDiscoveryService:
    configured_service = getattr(request.app.state, "tmdb_discovery_service", None)
    if configured_service is not None:
        return configured_service
    if settings.tmdb is None:
        raise HTTPException(status_code=503, detail="TMDB search is not configured")
    return TmdbDiscoveryService(settings.tmdb)


def get_tencent_rank_enricher(
    request: Request,
    discovery: TmdbDiscoveryService = Depends(get_tmdb_discovery_service),
) -> TencentRankEnricher:
    configured = getattr(request.app.state, "tencent_rank_enricher", None)
    if configured is not None:
        return configured
    return TencentRankEnricher(collector=TencentRankCollector(), discovery=discovery)


def get_rank_cache_repository(request: Request) -> RankCacheRepository:
    configured = getattr(request.app.state, "rank_cache_repository", None)
    if configured is not None:
        return configured

    db_path = get_db_path(request)
    if db_path is None:
        raise RuntimeError("Rank cache API requires app.state.db_path to be set")
    repository = RankCacheRepository(db_path)
    repository.init_schema()
    return repository


def get_telegram_web_channel_repository(request: Request) -> TelegramWebChannelRepository:
    configured_repository = getattr(request.app.state, "telegram_web_channel_repository", None)
    if configured_repository is not None:
        return configured_repository

    db_path = get_db_path(request)
    if db_path is None:
        raise RuntimeError("Telegram web channel API requires app.state.db_path to be set")
    repository = TelegramWebChannelRepository(db_path)
    repository.init_schema()
    return repository


def get_telegram_web_channel_service(
    request: Request,
    repository: TelegramWebChannelRepository = Depends(get_telegram_web_channel_repository),
) -> TelegramWebChannelService:
    configured_service = getattr(request.app.state, "telegram_web_channel_service", None)
    if configured_service is not None:
        return configured_service
    return TelegramWebChannelService(repository)


def get_runtime_control_repository(request: Request) -> RuntimeControlRepository:
    configured_repository = getattr(request.app.state, "runtime_control_repository", None)
    if configured_repository is not None:
        return configured_repository

    db_path = get_db_path(request)
    if db_path is None:
        raise RuntimeError("Runtime control API requires app.state.db_path to be set")
    repository = RuntimeControlRepository(db_path)
    repository.init_schema()
    return repository


def get_runtime_control_service(
    request: Request,
    settings: AppSettings = Depends(get_app_settings),
    runtime_repository: RuntimeControlRepository = Depends(get_runtime_control_repository),
    queue_repository: QueueRepository = Depends(get_queue_repository),
    organize_repository: OrganizeRepository = Depends(get_organize_repository),
    telegram_web_channel_service: TelegramWebChannelService = Depends(get_telegram_web_channel_service),
) -> RuntimeControlService:
    configured_service = getattr(request.app.state, "runtime_control_service", None)
    if configured_service is not None:
        return configured_service

    return RuntimeControlService(
        repository=runtime_repository,
        queue_repository=queue_repository,
        organize_repository=organize_repository,
        telegram_web_channel_service=telegram_web_channel_service,
        settings=settings,
    )


CollectorPollingServiceFactory = Callable[..., Any]


def get_collector_polling_service_factory(request: Request) -> CollectorPollingServiceFactory:
    configured_factory = getattr(request.app.state, "collector_polling_service_factory", None)
    if configured_factory is not None:
        return configured_factory

    try:
        from src.processors.telegram_collection import TelegramCollectionService
    except ModuleNotFoundError as exc:
        if exc.name == "src.processors.telegram_collection":
            raise HTTPException(status_code=501, detail="Collector polling service is not implemented") from exc
        raise

    return TelegramCollectionService


def get_collector_polling_service(
    request: Request,
    repository: QueueRepository = Depends(get_queue_repository),
) -> Any:
    configured_service = getattr(request.app.state, "collector_polling_service", None)
    if configured_service is not None:
        return configured_service

    factory = get_collector_polling_service_factory(request)
    return factory(repository=repository)
