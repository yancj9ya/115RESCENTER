from __future__ import annotations

import logging
import tempfile
from pathlib import Path as _Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request

from src.api.dependencies import (
    get_app_settings,
    get_collector_polling_service_factory,
    get_organize_repository,
    get_organize_run_service,
    get_queue_repository,
    get_rank_cache_repository,
    get_runtime_control_repository,
    get_runtime_control_service,
    get_storage115_service,
    get_subscription_processor,
    get_subscription_service,
    get_telegram_web_channel_service,
    get_tmdb_discovery_service,
    get_tmdb_movie_resolver,
    get_tmdb_multi_resolver,
    get_transfer_queue_processor,
)
from src.api.schemas import (
    COLLECT_QUEUE_NAME,
    DEFAULT_LIMIT,
    MAX_LIMIT,
    TRANSFER_QUEUE_NAME,
    VALID_COLLECT_STATUSES,
    VALID_ORGANIZE_RUN_STATUSES,
    VALID_ORGANIZE_ITEM_STATUSES,
    VALID_TRANSFER_STATUSES,
    CollectQueueItemResponse,
    CollectQueueListResponse,
    CollectorPollRequest,
    CollectorPollResponse,
    CollectorStatusResponse,
    ConnectivityItemResponse,
    ConnectivityResponse,
    DryRunBackendMessageRequest,
    DryRunBackendRequest,
    DryRunBackendSummaryResponse,
    HealthResponse,
    LogCenterCollectLogListResponse,
    LogCenterOrganizerRunDetailResponse,
    LogCenterOrganizerRunListResponse,
    LogCenterOrganizerItemListResponse,
    LogCenterOrganizerItemDeleteResponse,
    LogCenterOrganizerItemsClearResponse,
    LogCenterOrganizerSummary,
    LogCenterSummaryResponse,
    LogCenterTransferLogListResponse,
    NetdiskSettingsResponse,
    NetdiskSettingsUpdateRequest,
    NetdiskStatusResponse,
    NetdiskTestRequest,
    NetdiskTestResponse,
    NotificationSettingsResponse,
    NotificationSettingsUpdateRequest,
    NotificationProvidersResponse,
    NotificationProvidersUpdateRequest,
    NotificationTestResponse,
    BarkProviderResponse,
    TelegramProviderResponse,
    OrganizeRunDetailResponse,
    OrganizeRunItemResponse,
    OrganizeRunListResponse,
    OrganizeRunOnceRequest,
    OrganizeRunOnceResponse,
    OrganizeRunResponse,
    OrganizeStatusCounts,
    OrganizeStatusResponse,
    OrganizerSettingsResponse,
    OrganizerSettingsUpdateRequest,
    QueueStatusCounts,
    QueueStatusResponse,
    RuntimeComponentStatusResponse,
    RuntimeControlResponse,
    RuntimeOrganizerSummaryResponse,
    RuntimeQueueCountsResponse,
    RuntimeStatusResponse,
    RuntimeTriggerRequest,
    RuntimeTriggerResponse,
    ShareLinkResponse,
    SubscriptionCreateRequest,
    SubscriptionDeleteResponse,
    SubscriptionListResponse,
    SubscriptionProcessRequest,
    SubscriptionProcessResponse,
    SubscriptionResponse,
    SubscriptionTestRequest,
    SubscriptionTestResponse,
    SubscriptionUpdateRequest,
    TelegramWebChannelCreateRequest,
    TelegramWebChannelDeleteResponse,
    TelegramWebChannelListResponse,
    TelegramWebChannelResponse,
    TelegramWebChannelStatusResponse,
    TelegramWebChannelUpdateRequest,
    RankRefreshResponse,
    TencentRankResponse,
    TmdbAliasBundleResponse,
    TmdbDiscoverySearchItem,
    TmdbDiscoverySearchResponse,
    TmdbTrendingResponse,
    TmdbMetadataResponse,
    TmdbMovieSearchResponse,
    TmdbMultiSearchResponse,
    TransferMatchContextResponse,
    TransferQueueItemResponse,
    TransferQueueListResponse,
    TransferQueueProcessRequest,
    TransferQueueProcessResponse,
    TransferQueueStatusCounts,
    TransferSourceMessageResponse,
)
from src.collectors import parse_115_shares
from src.collectors.telegram_web import TelegramWebMessage, parse_telegram_public_channel_html
from src.config.settings import AppSettings
from src.config.yaml_writer import update_yaml_values
from src.notifications import InMemoryNotifier
from src.organizing import (
    TmdbCredentialError,
    TmdbDiscoveryService,
    TmdbError,
    TmdbMovieResolver,
    TmdbMultiResolver,
    TmdbRetryableError,
)
from src.organizing.models import OrganizeRule
from src.organizing.repository import OrganizeRepository
from src.processors.dry_run_backend import DryRunBackendService
from src.processors.fakes import FakeMetadataResolver, FakeOrganizeStorage, FakeTransferStorage
from src.processors.organize_run import OrganizeRunService
from src.processors.subscription_processor import SubscriptionProcessor
from src.processors.transfer_queue import TransferQueueProcessor
from src.queue.repository import QueueRepository
from src.ranks.repository import RankCacheRecord, RankCacheRepository

logger = logging.getLogger(__name__)
from src.resources import TelegramWebChannelRecord, TelegramWebChannelService
from src.runtime import RuntimeControlResult, RuntimeControlService, RuntimeStatus
from src.runtime.repository import RuntimeControlRepository
from src.subscriptions.matcher import SubscriptionMatcher, SubscriptionRule
from src.subscriptions.repository import SubscriptionRuleRecord
from src.subscriptions.service import SubscriptionService

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@router.get("/health/connectivity", response_model=ConnectivityResponse)
def get_connectivity(fastapi_request: Request) -> ConnectivityResponse:
    from datetime import datetime, timezone

    settings: AppSettings = fastapi_request.app.state.settings
    items: list[ConnectivityItemResponse] = [
        _check_netdisk_connectivity(fastapi_request, settings),
        _check_tmdb_connectivity(settings),
    ]
    items.extend(_check_notification_connectivity(fastapi_request))
    return ConnectivityResponse(checked_at=datetime.now(timezone.utc), items=items)


def _elapsed_ms(start: float) -> int:
    import time

    return max(0, int((time.perf_counter() - start) * 1000))


def _check_netdisk_connectivity(fastapi_request: Request, settings: AppSettings) -> ConnectivityItemResponse:
    import time

    if settings.p115 is None:
        return ConnectivityItemResponse(
            name="115 网盘", kind="netdisk", configured=False, ok=False, error="未配置 cookies"
        )

    service = getattr(fastapi_request.app.state, "storage115_service", None)
    if service is None:
        factory = getattr(fastapi_request.app.state, "storage115_service_factory", None)
        try:
            from src.storage import Storage115Service

            service = factory(settings.p115) if factory is not None else Storage115Service(settings.p115)
        except Exception as exc:
            return ConnectivityItemResponse(
                name="115 网盘", kind="netdisk", configured=True, ok=False,
                error=_safe_netdisk_error(exc, settings),
            )

    start = time.perf_counter()
    try:
        items = service.list_folder(0)
    except Exception as exc:
        return ConnectivityItemResponse(
            name="115 网盘", kind="netdisk", configured=True, ok=False,
            latency_ms=_elapsed_ms(start), error=_safe_netdisk_error(exc, settings),
        )
    return ConnectivityItemResponse(
        name="115 网盘", kind="netdisk", configured=True, ok=True,
        latency_ms=_elapsed_ms(start), detail=f"根目录 {len(items)} 项",
    )


def _check_tmdb_connectivity(settings: AppSettings) -> ConnectivityItemResponse:
    import time

    if settings.tmdb is None:
        return ConnectivityItemResponse(
            name="TMDB", kind="tmdb", configured=False, ok=False, error="未配置 bearer_token"
        )

    import httpx

    start = time.perf_counter()
    try:
        with httpx.Client(timeout=settings.tmdb.timeout_seconds, http2=False) as client:
            response = client.get(
                f"{settings.tmdb.base_url.rstrip('/')}/authentication",
                headers={
                    "Authorization": f"Bearer {settings.tmdb.bearer_token}",
                    "Accept": "application/json",
                },
            )
    except Exception as exc:
        return ConnectivityItemResponse(
            name="TMDB", kind="tmdb", configured=True, ok=False,
            latency_ms=_elapsed_ms(start), error=str(exc).splitlines()[0][:200],
        )

    latency = _elapsed_ms(start)
    if response.status_code == 200:
        return ConnectivityItemResponse(
            name="TMDB", kind="tmdb", configured=True, ok=True, latency_ms=latency, detail="令牌有效",
        )
    if response.status_code == 401:
        return ConnectivityItemResponse(
            name="TMDB", kind="tmdb", configured=True, ok=False, latency_ms=latency, error="令牌被拒绝 (401)",
        )
    return ConnectivityItemResponse(
        name="TMDB", kind="tmdb", configured=True, ok=False, latency_ms=latency,
        error=f"HTTP {response.status_code}",
    )


def _check_notification_connectivity(fastapi_request: Request) -> list[ConnectivityItemResponse]:
    try:
        _, raw = _load_notification_yaml(fastapi_request)
    except HTTPException:
        return []

    # 探测器：(method, url, headers) -> 带 status_code 的响应对象。测试可注入。
    probe = getattr(fastapi_request.app.state, "connectivity_http_probe", None) or _default_http_probe

    notification = raw.get("notification", {}) or {}
    providers = notification.get("providers", {}) or {}
    results: list[ConnectivityItemResponse] = []

    for entry in providers.get("telegram") or []:
        if not entry.get("enabled"):
            continue
        name = str(entry.get("name", ""))
        if not entry.get("bot_token"):
            results.append(ConnectivityItemResponse(
                name=name, kind="telegram", configured=False, ok=False, error="缺少 bot_token"
            ))
            continue
        url = f"https://api.telegram.org/bot{entry['bot_token']}/getMe"
        results.append(_probe_http(name, "telegram", probe, url, ok_detail="连接正常"))

    for entry in providers.get("bark") or []:
        if not entry.get("enabled"):
            continue
        name = str(entry.get("name", ""))
        if not entry.get("device_key"):
            results.append(ConnectivityItemResponse(
                name=name, kind="bark", configured=False, ok=False, error="缺少 device_key"
            ))
            continue
        server_url = str(entry.get("server_url", "https://api.day.app")).rstrip("/")
        results.append(_probe_http(name, "bark", probe, f"{server_url}/healthz", ok_detail="服务可达"))

    return results


def _default_http_probe(url: str) -> Any:
    import httpx

    with httpx.Client(timeout=10.0, http2=False) as client:
        return client.get(url)


def _probe_http(name: str, kind: str, probe: Any, url: str, *, ok_detail: str) -> ConnectivityItemResponse:
    import time

    start = time.perf_counter()
    try:
        response = probe(url)
    except Exception as exc:
        return ConnectivityItemResponse(
            name=name, kind=kind, configured=True, ok=False,
            latency_ms=_elapsed_ms(start), error=str(exc).splitlines()[0][:200],
        )
    latency = _elapsed_ms(start)
    status = getattr(response, "status_code", 0)
    # getMe 401 表示令牌无效；Bark 任何 HTTP 响应都代表服务器可达（404 也算可达）。
    if kind == "telegram":
        if status == 200:
            return ConnectivityItemResponse(name=name, kind=kind, configured=True, ok=True, latency_ms=latency, detail=ok_detail)
        if status == 401:
            return ConnectivityItemResponse(name=name, kind=kind, configured=True, ok=False, latency_ms=latency, error="Bot Token 无效 (401)")
        return ConnectivityItemResponse(name=name, kind=kind, configured=True, ok=False, latency_ms=latency, error=f"HTTP {status}")
    if 200 <= status < 500:
        return ConnectivityItemResponse(name=name, kind=kind, configured=True, ok=True, latency_ms=latency, detail=ok_detail)
    return ConnectivityItemResponse(name=name, kind=kind, configured=True, ok=False, latency_ms=latency, error=f"HTTP {status}")


@router.get("/runtime/status", response_model=RuntimeStatusResponse)
def get_runtime_status(service: RuntimeControlService = Depends(get_runtime_control_service)) -> RuntimeStatusResponse:
    return _runtime_status_to_api(service.status())


@router.post("/runtime/start", response_model=RuntimeControlResponse)
def start_runtime(service: RuntimeControlService = Depends(get_runtime_control_service)) -> RuntimeControlResponse:
    return _runtime_control_to_api(service.start())


@router.post("/runtime/stop", response_model=RuntimeControlResponse)
def stop_runtime(service: RuntimeControlService = Depends(get_runtime_control_service)) -> RuntimeControlResponse:
    return _runtime_control_to_api(service.stop())


@router.post("/runtime/trigger", response_model=RuntimeTriggerResponse)
def trigger_runtime(
    request: RuntimeTriggerRequest,
    service: RuntimeControlService = Depends(get_runtime_control_service),
) -> RuntimeTriggerResponse:
    try:
        trigger_id = service.trigger(request.event_name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return RuntimeTriggerResponse(trigger_id=trigger_id, event_name=request.event_name)


@router.get("/netdisk/settings", response_model=NetdiskSettingsResponse)
def get_netdisk_settings(settings: AppSettings = Depends(get_app_settings)) -> NetdiskSettingsResponse:
    return _netdisk_settings_to_api(settings)


@router.patch("/netdisk/settings", response_model=NetdiskSettingsResponse)
def update_netdisk_settings(
    request: NetdiskSettingsUpdateRequest,
    fastapi_request: Request,
) -> NetdiskSettingsResponse:
    updates: dict[str, str] = {}
    yaml_updates: dict[str, object] = {}
    if request.transfer_cid is not None:
        updates["P115_TRANSFER_CID"] = str(request.transfer_cid)
        yaml_updates["p115.transfer_cid"] = int(request.transfer_cid)
    if request.ensure_cookies is not None:
        updates["P115_ENSURE_COOKIES"] = "1" if request.ensure_cookies else "0"
        yaml_updates["p115.ensure_cookies"] = bool(request.ensure_cookies)
    if request.cache_home is not None:
        normalized_cache_home = request.cache_home.strip()
        if normalized_cache_home:
            updates["P115_CACHE_HOME"] = normalized_cache_home
            yaml_updates["p115.cache_home"] = normalized_cache_home
    if request.cookies is not None:
        normalized_cookies = request.cookies.strip()
        if not normalized_cookies:
            raise HTTPException(status_code=422, detail="cookies must not be blank when provided")
        updates["P115_COOKIES"] = normalized_cookies
        yaml_updates["p115.cookies"] = normalized_cookies

    if not updates:
        raise HTTPException(status_code=422, detail="at least one setting must be provided")

    config_dir = _config_dir(fastapi_request)
    try:
        update_yaml_values(config_dir, "netdisk", yaml_updates)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    next_settings = _settings_from_updates(fastapi_request.app.state.settings, updates)
    fastapi_request.app.state.settings = next_settings
    return _netdisk_settings_to_api(next_settings)


@router.get("/netdisk/status", response_model=NetdiskStatusResponse)
def get_netdisk_status(settings: AppSettings = Depends(get_app_settings)) -> NetdiskStatusResponse:
    summary = _netdisk_settings_to_api(settings)
    return NetdiskStatusResponse(**summary.model_dump())


@router.post("/netdisk/test", response_model=NetdiskTestResponse)
def test_netdisk(
    request: NetdiskTestRequest,
    settings: AppSettings = Depends(get_app_settings),
    service: Any = Depends(get_storage115_service),
) -> NetdiskTestResponse:
    if settings.p115 is None:
        raise HTTPException(status_code=503, detail="115 storage is not configured")

    cid = int(request.cid) if request.cid is not None and str(request.cid).strip() else 0
    try:
        items = service.list_folder(cid)
    except Exception as exc:
        return NetdiskTestResponse(
            configured=True,
            status="error",
            ok=False,
            error=_safe_netdisk_error(exc, settings),
        )
    return NetdiskTestResponse(
        configured=True,
        status="ok",
        ok=True,
        item_count=len(items),
    )


@router.get("/subscriptions", response_model=SubscriptionListResponse)
def list_subscriptions(service: SubscriptionService = Depends(get_subscription_service)) -> SubscriptionListResponse:
    return SubscriptionListResponse(items=[_subscription_to_api(rule) for rule in service.list_rules()])


@router.post("/subscriptions", response_model=SubscriptionResponse, status_code=201)
def create_subscription(
    request: SubscriptionCreateRequest,
    service: SubscriptionService = Depends(get_subscription_service),
) -> SubscriptionResponse:
    try:
        rule = service.create_rule(
            name=request.name,
            pattern=request.pattern,
            enabled=request.enabled,
            tmdb_id=request.tmdb_id,
            tmdb_kind=request.tmdb_kind,
            aliases=tuple(request.aliases),
            poster_path=request.poster_path,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _subscription_to_api(rule)


@router.get("/subscriptions/{rule_id}", response_model=SubscriptionResponse)
def get_subscription(
    rule_id: int,
    service: SubscriptionService = Depends(get_subscription_service),
) -> SubscriptionResponse:
    rule = service.get_rule(rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="subscription not found")
    return _subscription_to_api(rule)


@router.patch("/subscriptions/{rule_id}", response_model=SubscriptionResponse)
def update_subscription(
    rule_id: int,
    request: SubscriptionUpdateRequest,
    service: SubscriptionService = Depends(get_subscription_service),
) -> SubscriptionResponse:
    update_fields: dict[str, Any] = {
        "name": request.name,
        "pattern": request.pattern,
        "enabled": request.enabled,
    }
    payload = request.model_dump(exclude_unset=True)
    if "tmdb_id" in payload:
        update_fields["tmdb_id"] = request.tmdb_id
    if "tmdb_kind" in payload:
        update_fields["tmdb_kind"] = request.tmdb_kind
    if "aliases" in payload and request.aliases is not None:
        update_fields["aliases"] = tuple(request.aliases)
    if "poster_path" in payload:
        update_fields["poster_path"] = request.poster_path
    try:
        rule = service.update_rule(rule_id, **update_fields)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if rule is None:
        raise HTTPException(status_code=404, detail="subscription not found")
    return _subscription_to_api(rule)


@router.delete("/subscriptions/{rule_id}", response_model=SubscriptionDeleteResponse)
def delete_subscription(
    rule_id: int,
    service: SubscriptionService = Depends(get_subscription_service),
) -> SubscriptionDeleteResponse:
    if not service.delete_rule(rule_id):
        raise HTTPException(status_code=404, detail="subscription not found")
    return SubscriptionDeleteResponse(deleted=True)


@router.post("/subscriptions/test", response_model=SubscriptionTestResponse)
def test_subscription(
    request: SubscriptionTestRequest,
    service: SubscriptionService = Depends(get_subscription_service),
) -> SubscriptionTestResponse:
    try:
        result = service.test_pattern(pattern=request.pattern, text=request.text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SubscriptionTestResponse(matched=result.matched)


@router.post("/subscriptions/process", response_model=SubscriptionProcessResponse)
def process_subscriptions(
    request: SubscriptionProcessRequest,
    processor: SubscriptionProcessor = Depends(get_subscription_processor),
) -> SubscriptionProcessResponse:
    logger.info(f"手动触发订阅处理: limit={request.limit}")
    summary = processor.process(limit=request.limit)
    if any("P115_TRANSFER_CID" in error for error in summary.errors):
        raise HTTPException(status_code=422, detail="P115_TRANSFER_CID is required")
    logger.info(f"订阅处理完成: 扫描={summary.scanned}, 匹配={summary.matched}, 创建={summary.created}, 跳过={summary.skipped}")
    return SubscriptionProcessResponse(
        scanned=summary.scanned,
        matched=summary.matched,
        created=summary.created,
        skipped=summary.skipped,
        errors=list(summary.errors),
    )


@router.post("/transfer-queue/process", response_model=TransferQueueProcessResponse)
def process_transfer_queue(
    request: TransferQueueProcessRequest,
    processor: TransferQueueProcessor = Depends(get_transfer_queue_processor),
) -> TransferQueueProcessResponse:
    logger.info(f"手动触发转存队列处理: limit={request.limit}")
    processed = 0
    success = 0
    failed = 0
    errors: list[str] = []

    for _ in range(request.limit):
        result = processor.process_next_transfer()
        if not result.claimed:
            break
        processed += 1
        if result.status == "SUCCESS":
            success += 1
        elif result.status == "FAILED":
            failed += 1
            if result.error:
                errors.append(result.error)

    logger.info(f"转存队列处理完成: 处理={processed}, 成功={success}, 失败={failed}")
    return TransferQueueProcessResponse(
        processed=processed,
        success=success,
        failed=failed,
        errors=errors,
    )


@router.get("/resources/telegram-web/channels", response_model=TelegramWebChannelListResponse)
def list_telegram_web_channels(
    service: TelegramWebChannelService = Depends(get_telegram_web_channel_service),
) -> TelegramWebChannelListResponse:
    return TelegramWebChannelListResponse(items=[_telegram_web_channel_to_api(channel) for channel in service.list_channels()])


@router.post("/resources/telegram-web/channels", response_model=TelegramWebChannelResponse, status_code=201)
def create_telegram_web_channel(
    request: TelegramWebChannelCreateRequest,
    service: TelegramWebChannelService = Depends(get_telegram_web_channel_service),
) -> TelegramWebChannelResponse:
    try:
        channel = service.create_channel(
            channel=request.channel,
            display_name=request.display_name,
            enabled=request.enabled,
            poll_interval_seconds=request.poll_interval_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _telegram_web_channel_to_api(channel)


@router.get("/resources/telegram-web/channels/{channel}", response_model=TelegramWebChannelResponse)
def get_telegram_web_channel(
    channel: str,
    service: TelegramWebChannelService = Depends(get_telegram_web_channel_service),
) -> TelegramWebChannelResponse:
    try:
        record = service.get_channel(channel)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="telegram web channel not found")
    return _telegram_web_channel_to_api(record)


@router.patch("/resources/telegram-web/channels/{channel}", response_model=TelegramWebChannelResponse)
def update_telegram_web_channel(
    channel: str,
    request: TelegramWebChannelUpdateRequest,
    service: TelegramWebChannelService = Depends(get_telegram_web_channel_service),
) -> TelegramWebChannelResponse:
    try:
        record = service.update_channel(
            channel,
            display_name=request.display_name,
            enabled=request.enabled,
            poll_interval_seconds=request.poll_interval_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="telegram web channel not found")
    return _telegram_web_channel_to_api(record)


@router.delete("/resources/telegram-web/channels/{channel}", response_model=TelegramWebChannelDeleteResponse)
def delete_telegram_web_channel(
    channel: str,
    service: TelegramWebChannelService = Depends(get_telegram_web_channel_service),
) -> TelegramWebChannelDeleteResponse:
    try:
        deleted = service.delete_channel(channel)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="telegram web channel not found")
    return TelegramWebChannelDeleteResponse(deleted=True)


@router.post("/resources/telegram-web/channels/{channel}/enable", response_model=TelegramWebChannelResponse)
def enable_telegram_web_channel(
    channel: str,
    service: TelegramWebChannelService = Depends(get_telegram_web_channel_service),
) -> TelegramWebChannelResponse:
    try:
        record = service.enable_channel(channel)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="telegram web channel not found")
    return _telegram_web_channel_to_api(record)


@router.post("/resources/telegram-web/channels/{channel}/disable", response_model=TelegramWebChannelResponse)
def disable_telegram_web_channel(
    channel: str,
    service: TelegramWebChannelService = Depends(get_telegram_web_channel_service),
) -> TelegramWebChannelResponse:
    try:
        record = service.disable_channel(channel)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="telegram web channel not found")
    return _telegram_web_channel_to_api(record)


@router.get("/resources/telegram-web/channels/{channel}/status", response_model=TelegramWebChannelStatusResponse)
def get_telegram_web_channel_status(
    channel: str,
    service: TelegramWebChannelService = Depends(get_telegram_web_channel_service),
    repository: QueueRepository = Depends(get_queue_repository),
) -> TelegramWebChannelStatusResponse:
    try:
        record = service.get_channel(channel)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="telegram web channel not found")

    cursor = repository.get_collector_cursor(source_type="telegram_web", source_id=record.channel)
    if cursor is None:
        return TelegramWebChannelStatusResponse(
            channel=_telegram_web_channel_to_api(record),
            cursor=None,
            status="unknown",
            error=None,
        )
    return TelegramWebChannelStatusResponse(
        channel=_telegram_web_channel_to_api(record),
        cursor=_cursor_to_api(cursor.last_seen_message_id),
        status=_status_to_api(cursor.last_status, default="unknown"),
        error=_safe_error(cursor.last_error),
    )


@router.post("/organizer/run-once", response_model=OrganizeRunOnceResponse)
def run_organizer_once(
    request: OrganizeRunOnceRequest,
    service: OrganizeRunService = Depends(get_organize_run_service),
) -> OrganizeRunOnceResponse:
    staging_cid = request.staging_cid
    if staging_cid is None:
        staging_cid = _default_staging_cid_from_service(service)
    if staging_cid is None or staging_cid <= 0:
        raise HTTPException(status_code=422, detail="staging_cid or P115_TRANSFER_CID is required")

    logger.info(f"手动触发整理运行: staging_cid={staging_cid}")
    result = service.run_once(staging_cid)
    logger.info(f"整理运行完成 (run_id={result.run_id}): 扫描={result.scanned_count}, 成功={result.success_count}, 跳过={result.skipped_count}, 失败={result.failed_count}")
    return OrganizeRunOnceResponse(
        run_id=result.run_id,
        status=result.status,
        scanned_count=result.scanned_count,
        planned_count=result.planned_count,
        success_count=result.success_count,
        skipped_count=result.skipped_count,
        failed_count=result.failed_count,
        last_error=result.last_error,
    )


@router.get("/organizer/runs", response_model=OrganizeRunListResponse)
def list_organizer_runs(
    status: str | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    repository: OrganizeRepository = Depends(get_organize_repository),
) -> OrganizeRunListResponse:
    if status is not None and status not in VALID_ORGANIZE_RUN_STATUSES:
        raise HTTPException(status_code=422, detail="invalid organizer run status")
    return OrganizeRunListResponse(items=[_organize_run_to_api(run) for run in repository.list_runs(limit=limit, status=status)])


@router.get("/organizer/runs/{run_id}", response_model=OrganizeRunDetailResponse)
def get_organizer_run(
    run_id: int,
    repository: OrganizeRepository = Depends(get_organize_repository),
) -> OrganizeRunDetailResponse:
    run = repository.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="organizer run not found")
    return OrganizeRunDetailResponse(
        run=_organize_run_to_api(run),
        items=[_organize_run_item_to_api(item) for item in repository.list_run_items(run_id)],
    )


@router.get("/organizer/status", response_model=OrganizeStatusResponse)
def get_organizer_status(repository: OrganizeRepository = Depends(get_organize_repository)) -> OrganizeStatusResponse:
    latest_run = repository.get_latest_run()
    return OrganizeStatusResponse(
        latest_run=_organize_run_to_api(latest_run) if latest_run is not None else None,
        counts=OrganizeStatusCounts(**repository.get_status_counts()),
    )


@router.get("/organizer/settings", response_model=OrganizerSettingsResponse)
def get_organizer_settings(fastapi_request: Request) -> OrganizerSettingsResponse:
    return _organizer_settings_from_state(fastapi_request)


@router.patch("/organizer/settings", response_model=OrganizerSettingsResponse)
def update_organizer_settings(
    request: OrganizerSettingsUpdateRequest,
    fastapi_request: Request,
) -> OrganizerSettingsResponse:
    if request.media_library_root_cid is None:
        raise HTTPException(status_code=422, detail="at least one organizer root must be provided")

    root_cid = int(request.media_library_root_cid)

    config_dir = _config_dir(fastapi_request)
    try:
        update_yaml_values(config_dir, "organize", {"organize.media_library_root_cid": root_cid})
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    state = fastapi_request.app.state
    state.media_library_root_cid = root_cid

    current = state.settings
    state.settings = AppSettings(
        transfer_cid=current.transfer_cid,
        p115=current.p115,
        tmdb=current.tmdb,
        notification_webhook=current.notification_webhook,
        api_cors_origins=current.api_cors_origins,
        media_library_root_cid=root_cid or current.media_library_root_cid,
    )
    return _organizer_settings_from_state(fastapi_request)


def _organizer_settings_from_state(fastapi_request: Request) -> OrganizerSettingsResponse:
    state = fastapi_request.app.state
    media = int(getattr(state, "media_library_root_cid", 0) or 0)
    return OrganizerSettingsResponse(
        media_library_root_cid=str(media),
        configured=media > 0,
    )


@router.get("/notification/settings", response_model=NotificationSettingsResponse)
def get_notification_settings(settings: AppSettings = Depends(get_app_settings)) -> NotificationSettingsResponse:
    return _notification_settings_to_api(settings)


@router.patch("/notification/settings", response_model=NotificationSettingsResponse)
def update_notification_settings(
    request: NotificationSettingsUpdateRequest,
    fastapi_request: Request,
) -> NotificationSettingsResponse:
    import yaml as _yaml

    from src.notifications import WebhookConfig as _WebhookConfig

    config_dir = _config_dir(fastapi_request)
    notification_yml = config_dir / "notification.yml"

    if not notification_yml.exists():
        raise HTTPException(status_code=503, detail="notification config file not found")

    with open(notification_yml, encoding="utf-8") as f:
        raw = _yaml.safe_load(f) or {}

    webhook = raw.setdefault("notification", {}).setdefault("webhook", {})
    if request.enabled is not None:
        webhook["enabled"] = request.enabled
    if request.url is not None:
        webhook["url"] = request.url.strip()
    if request.token is not None:
        webhook["token"] = request.token.strip()
    if request.timeout_seconds is not None:
        webhook["timeout"] = request.timeout_seconds

    with open(notification_yml, "w", encoding="utf-8") as f:
        _yaml.dump(raw, f, allow_unicode=True, default_flow_style=False)

    current = fastapi_request.app.state.settings
    url = webhook.get("url", "")
    enabled = bool(webhook.get("enabled", False))
    token = webhook.get("token", "") or None
    timeout = int(webhook.get("timeout", 10))
    new_webhook = _WebhookConfig(url=url, enabled=enabled, token=token, timeout_seconds=float(timeout)) if url else None
    fastapi_request.app.state.settings = AppSettings(
        transfer_cid=current.transfer_cid,
        p115=current.p115,
        tmdb=current.tmdb,
        notification_webhook=new_webhook,
        api_cors_origins=current.api_cors_origins,
        media_library_root_cid=current.media_library_root_cid,
    )
    return _notification_settings_to_api(fastapi_request.app.state.settings)


@router.post("/notification/test", response_model=NotificationTestResponse)
def test_notification_webhook(settings: AppSettings = Depends(get_app_settings)) -> NotificationTestResponse:
    import httpx as _httpx

    webhook = settings.notification_webhook
    if webhook is None or not webhook.url:
        raise HTTPException(status_code=422, detail="webhook URL is not configured")

    headers: dict[str, str] = {}
    if webhook.token:
        headers["Authorization"] = f"Bearer {webhook.token}"

    try:
        with _httpx.Client() as client:
            resp = client.post(
                webhook.url,
                json={"event_type": "test", "severity": "info", "title": "测试通知", "message": "来自 NDRA 的测试通知", "context": {}},
                headers=headers or None,
                timeout=webhook.timeout_seconds,
            )
        if resp.status_code < 200 or resp.status_code >= 300:
            return NotificationTestResponse(ok=False, status_code=resp.status_code, error=f"HTTP {resp.status_code}")
        return NotificationTestResponse(ok=True, status_code=resp.status_code)
    except Exception as exc:
        return NotificationTestResponse(ok=False, error=str(exc))


def _notification_settings_to_api(settings: AppSettings) -> NotificationSettingsResponse:
    webhook = settings.notification_webhook
    if webhook is None:
        return NotificationSettingsResponse(enabled=False, url="", has_token=False, timeout_seconds=10)
    return NotificationSettingsResponse(
        enabled=webhook.enabled,
        url=webhook.url,
        has_token=bool(webhook.token),
        timeout_seconds=int(webhook.timeout_seconds),
    )


def _load_notification_yaml(fastapi_request: Request):
    import yaml as _yaml

    config_dir = _config_dir(fastapi_request)
    notification_yml = config_dir / "notification.yml"
    if not notification_yml.exists():
        raise HTTPException(status_code=503, detail="notification config file not found")
    with open(notification_yml, encoding="utf-8") as f:
        raw = _yaml.safe_load(f) or {}
    return notification_yml, raw


def _providers_to_api(raw: dict) -> NotificationProvidersResponse:
    notification = raw.get("notification", {}) or {}
    providers = notification.get("providers", {}) or {}
    telegram = [
        TelegramProviderResponse(
            name=str(entry.get("name", "")),
            enabled=bool(entry.get("enabled", False)),
            has_bot_token=bool(entry.get("bot_token")),
            chat_id=str(entry.get("chat_id", "")),
        )
        for entry in (providers.get("telegram") or [])
    ]
    bark = [
        BarkProviderResponse(
            name=str(entry.get("name", "")),
            enabled=bool(entry.get("enabled", False)),
            has_device_key=bool(entry.get("device_key")),
            server_url=str(entry.get("server_url", "https://api.day.app")),
        )
        for entry in (providers.get("bark") or [])
    ]
    routing_raw = notification.get("routing", {}) or {}
    routing = {str(k): [str(n) for n in (v or [])] for k, v in routing_raw.items()}
    return NotificationProvidersResponse(telegram=telegram, bark=bark, routing=routing)


@router.get("/notification/providers", response_model=NotificationProvidersResponse)
def get_notification_providers(fastapi_request: Request) -> NotificationProvidersResponse:
    _, raw = _load_notification_yaml(fastapi_request)
    return _providers_to_api(raw)


@router.patch("/notification/providers", response_model=NotificationProvidersResponse)
def update_notification_providers(
    request: NotificationProvidersUpdateRequest,
    fastapi_request: Request,
) -> NotificationProvidersResponse:
    import yaml as _yaml

    notification_yml, raw = _load_notification_yaml(fastapi_request)
    notification = raw.setdefault("notification", {})
    providers = notification.setdefault("providers", {})

    if request.telegram is not None:
        existing = {str(e.get("name")): e for e in (providers.get("telegram") or [])}
        new_telegram = []
        for item in request.telegram:
            prev = existing.get(item.name, {})
            bot_token = prev.get("bot_token", "") if item.bot_token is None else item.bot_token.strip()
            new_telegram.append(
                {
                    "name": item.name,
                    "enabled": item.enabled,
                    "bot_token": bot_token,
                    "chat_id": item.chat_id.strip(),
                }
            )
        providers["telegram"] = new_telegram

    if request.bark is not None:
        existing = {str(e.get("name")): e for e in (providers.get("bark") or [])}
        new_bark = []
        for item in request.bark:
            prev = existing.get(item.name, {})
            device_key = prev.get("device_key", "") if item.device_key is None else item.device_key.strip()
            new_bark.append(
                {
                    "name": item.name,
                    "enabled": item.enabled,
                    "device_key": device_key,
                    "server_url": item.server_url.strip() or "https://api.day.app",
                }
            )
        providers["bark"] = new_bark

    if request.routing is not None:
        notification["routing"] = {
            str(source): [str(n) for n in (names or [])] for source, names in request.routing.items()
        }

    with open(notification_yml, "w", encoding="utf-8") as f:
        _yaml.dump(raw, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    fastapi_request.app.state.settings = AppSettings.from_yaml(_config_dir(fastapi_request))
    return _providers_to_api(raw)


@router.post("/notification/providers/{name}/test", response_model=NotificationTestResponse)
def test_notification_provider(name: str, fastapi_request: Request) -> NotificationTestResponse:
    from src.notifications import BarkNotifier, NotificationEvent, TelegramBotNotifier

    _, raw = _load_notification_yaml(fastapi_request)
    notification = raw.get("notification", {}) or {}
    providers = notification.get("providers", {}) or {}

    notifier = None
    for entry in providers.get("telegram") or []:
        if str(entry.get("name")) == name:
            if not entry.get("bot_token") or not entry.get("chat_id"):
                raise HTTPException(status_code=422, detail="telegram provider 缺少 bot_token 或 chat_id")
            notifier = TelegramBotNotifier(
                name=name, bot_token=str(entry["bot_token"]), chat_id=str(entry["chat_id"])
            )
            break
    if notifier is None:
        for entry in providers.get("bark") or []:
            if str(entry.get("name")) == name:
                if not entry.get("device_key"):
                    raise HTTPException(status_code=422, detail="bark provider 缺少 device_key")
                notifier = BarkNotifier(
                    name=name,
                    device_key=str(entry["device_key"]),
                    server_url=str(entry.get("server_url", "https://api.day.app")),
                )
                break
    if notifier is None:
        raise HTTPException(status_code=404, detail=f"provider not found: {name}")

    event = NotificationEvent(
        event_type="test", severity="info", title="NDRA 测试通知", message="来自 NDRA 的测试通知"
    )
    try:
        notifier.notify(event)
        return NotificationTestResponse(ok=True, status_code=200)
    except Exception as exc:
        return NotificationTestResponse(ok=False, error=str(exc))


@router.get("/tmdb/search/movie", response_model=TmdbMovieSearchResponse)
def search_tmdb_movie(
    query: Annotated[str, Query(min_length=1)],
    year: int | None = Query(default=None),
    resolver: TmdbMovieResolver = Depends(get_tmdb_movie_resolver),
) -> TmdbMovieSearchResponse:
    try:
        metadata = resolver.resolve_movie(query, year=year)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except TmdbCredentialError as exc:
        raise HTTPException(status_code=401, detail="TMDB credentials were rejected") from exc
    except TmdbRetryableError as exc:
        raise HTTPException(status_code=503, detail="TMDB search is temporarily unavailable") from exc
    except TmdbError as exc:
        raise HTTPException(status_code=502, detail="TMDB search failed") from exc

    return TmdbMovieSearchResponse(
        query=query,
        year=year,
        metadata=_metadata_to_api(metadata),
    )


@router.get("/tmdb/search/multi", response_model=TmdbMultiSearchResponse)
def search_tmdb_multi(
    query: Annotated[str, Query(min_length=1)],
    year: int | None = Query(default=None),
    resolver: TmdbMultiResolver = Depends(get_tmdb_multi_resolver),
) -> TmdbMultiSearchResponse:
    try:
        metadata = resolver.resolve_multi(query, year=year)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except TmdbCredentialError as exc:
        raise HTTPException(status_code=401, detail="TMDB credentials were rejected") from exc
    except TmdbRetryableError as exc:
        raise HTTPException(status_code=503, detail="TMDB search is temporarily unavailable") from exc
    except TmdbError as exc:
        raise HTTPException(status_code=502, detail="TMDB search failed") from exc

    return TmdbMultiSearchResponse(query=query, year=year, metadata=_metadata_to_api(metadata))


@router.get("/tmdb/discovery/search", response_model=TmdbDiscoverySearchResponse)
def discover_tmdb_search(
    query: Annotated[str, Query(min_length=1)],
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
    service: TmdbDiscoveryService = Depends(get_tmdb_discovery_service),
) -> TmdbDiscoverySearchResponse:
    try:
        results = service.search_multi(query, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except TmdbCredentialError as exc:
        raise HTTPException(status_code=401, detail="TMDB credentials were rejected") from exc
    except TmdbRetryableError as exc:
        raise HTTPException(status_code=503, detail="TMDB search is temporarily unavailable") from exc
    except TmdbError as exc:
        raise HTTPException(status_code=502, detail="TMDB search failed") from exc

    return TmdbDiscoverySearchResponse(
        query=query,
        items=[
            TmdbDiscoverySearchItem(
                tmdb_id=item.tmdb_id,
                kind=item.kind,
                title=item.title,
                original_title=item.original_title,
                year=item.year,
                overview=item.overview,
                poster_path=item.poster_path,
            )
            for item in results
        ],
    )


def _rank_cache_items(
    record: RankCacheRecord | None,
    limit: int,
) -> tuple[list[TmdbDiscoverySearchItem], str, str | None]:
    """把缓存记录映射为 API 条目 + 状态。空缓存返回 never_refreshed（前端据此提示尚未刷新）。"""
    if record is None:
        return [], "never_refreshed", None
    items = [
        TmdbDiscoverySearchItem(
            tmdb_id=int(raw.get("tmdb_id")),
            kind=raw.get("kind"),
            title=str(raw.get("title", "")),
            original_title=str(raw.get("original_title", "")),
            year=raw.get("year"),
            overview=str(raw.get("overview", "") or ""),
            poster_path=raw.get("poster_path"),
        )
        for raw in record.items[:limit]
        if isinstance(raw, dict) and raw.get("tmdb_id") and raw.get("kind") in ("movie", "tv")
    ]
    return items, record.status, record.refreshed_at


@router.get("/tmdb/discovery/trending", response_model=TmdbTrendingResponse)
def discover_tmdb_trending(
    list: Literal[
        "tv_on_the_air", "trending_tv_week", "tv_popular", "trending_movie_week"
    ],
    limit: Annotated[int, Query(ge=1, le=20)] = 20,
    cache: RankCacheRepository = Depends(get_rank_cache_repository),
) -> TmdbTrendingResponse:
    record = cache.get(source="tmdb", key=list)
    items, status, refreshed_at = _rank_cache_items(record, limit)
    return TmdbTrendingResponse(list=list, items=items, status=status, refreshed_at=refreshed_at)


@router.get("/tencent/ranks", response_model=TencentRankResponse)
def fetch_tencent_ranks(
    channel: Literal["tv", "movie", "variety", "cartoon"],
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
    cache: RankCacheRepository = Depends(get_rank_cache_repository),
) -> TencentRankResponse:
    record = cache.get(source="tencent", key=channel)
    items, status, refreshed_at = _rank_cache_items(record, limit)
    return TencentRankResponse(channel=channel, items=items, status=status, refreshed_at=refreshed_at)


@router.post("/ranks/refresh", response_model=RankRefreshResponse)
def refresh_ranks(
    repository: RuntimeControlRepository = Depends(get_runtime_control_repository),
) -> RankRefreshResponse:
    trigger_id = repository.enqueue_manual_trigger(event_name="manual_refresh_ranks", source="api")
    return RankRefreshResponse(trigger_id=trigger_id, event_name="manual_refresh_ranks")


@router.get("/tmdb/discovery/aliases/{kind}/{tmdb_id}", response_model=TmdbAliasBundleResponse)
def discover_tmdb_aliases(
    kind: Literal["movie", "tv"],
    tmdb_id: int = Path(ge=1),
    service: TmdbDiscoveryService = Depends(get_tmdb_discovery_service),
) -> TmdbAliasBundleResponse:
    try:
        bundle = service.collect_aliases(kind, tmdb_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except TmdbCredentialError as exc:
        raise HTTPException(status_code=401, detail="TMDB credentials were rejected") from exc
    except TmdbRetryableError as exc:
        raise HTTPException(status_code=503, detail="TMDB search is temporarily unavailable") from exc
    except TmdbError as exc:
        raise HTTPException(status_code=502, detail="TMDB search failed") from exc

    return TmdbAliasBundleResponse(
        tmdb_id=bundle.tmdb_id,
        kind=bundle.kind,
        title=bundle.title,
        original_title=bundle.original_title,
        year=bundle.year,
        aliases=list(bundle.aliases),
    )


def _runtime_status_to_api(status: RuntimeStatus | dict[str, object]) -> RuntimeStatusResponse:
    if isinstance(status, dict):
        return RuntimeStatusResponse(**status)
    return RuntimeStatusResponse(
        desired_state=status.desired_state,
        effective_state=status.effective_state,
        control_plane_only=status.control_plane_only,
        started_at=status.started_at,
        stopped_at=status.stopped_at,
        updated_at=status.updated_at,
        message=status.message,
        components=[
            RuntimeComponentStatusResponse(
                name=component.name,
                desired_state=component.desired_state,
                status=component.status,
                configured=component.configured,
                enabled=component.enabled,
                detail=component.detail,
                last_status=component.last_status,
                last_error=component.last_error,
                tick_count=component.tick_count,
                last_started_at=component.last_started_at,
                last_finished_at=component.last_finished_at,
                last_success=component.last_success,
                last_heartbeat_at=component.last_heartbeat_at,
            )
            for component in status.components
        ],
        queues=RuntimeQueueCountsResponse(
            collect_queue=QueueStatusCounts(**status.queue_counts.collect_queue),
            transfer_queue=TransferQueueStatusCounts(**status.queue_counts.transfer_queue),
        ),
        organizer=RuntimeOrganizerSummaryResponse(
            latest_run=_optional_organize_run_to_api(status.organizer.latest_run),
            counts=OrganizeStatusCounts(**status.organizer.counts),
        ),
    )


def _runtime_control_to_api(result: RuntimeControlResult | dict[str, object]) -> RuntimeControlResponse:
    if isinstance(result, dict):
        return RuntimeControlResponse(**result)
    return RuntimeControlResponse(
        **_runtime_status_to_api(result).model_dump(),
        action=result.action,
        changed=result.changed,
    )


def _config_dir(fastapi_request: Request) -> _Path:
    configured = getattr(fastapi_request.app.state, "config_dir", None)
    if configured is not None:
        return _Path(configured)
    return _Path(__file__).resolve().parents[2] / "config"


def _settings_from_updates(current: AppSettings, updates: dict[str, str]) -> AppSettings:
    from pathlib import Path

    from src.storage import Storage115Config

    transfer_cid = int(updates.get("P115_TRANSFER_CID", current.transfer_cid))
    existing_p115 = current.p115
    cookies = updates.get("P115_COOKIES", existing_p115.cookies if existing_p115 is not None else "")
    ensure_cookies = (
        updates.get("P115_ENSURE_COOKIES", "1" if existing_p115 is not None and existing_p115.ensure_cookies else "0")
        in {"1", "true", "True"}
    )
    cache_home_text = updates.get(
        "P115_CACHE_HOME",
        str(existing_p115.cache_home) if existing_p115 is not None and existing_p115.cache_home is not None else ".p115client.cache.d",
    )
    p115 = None
    if cookies:
        p115 = Storage115Config(
            cookies=cookies,
            ensure_cookies=ensure_cookies,
            cache_home=Path(cache_home_text),
        )
    return AppSettings(
        transfer_cid=transfer_cid,
        p115=p115,
        tmdb=current.tmdb,
        notification_webhook=current.notification_webhook,
        api_cors_origins=current.api_cors_origins,
    )


def _metadata_to_api(metadata: object) -> TmdbMetadataResponse | None:
    if metadata is None:
        return None
    return TmdbMetadataResponse(
        title=metadata.title,
        year=metadata.year,
        kind=metadata.kind,
        region_primary=metadata.region_primary,
        region_candidates=list(metadata.region_candidates),
        region_category=metadata.region_category,
        region_source=metadata.region_source,
        region_confidence=metadata.region_confidence,
    )


@router.post("/dry-run/backend", response_model=DryRunBackendSummaryResponse)
def dry_run_backend(request: DryRunBackendRequest) -> DryRunBackendSummaryResponse:
    shares = _build_dry_run_messages(request.messages)
    with tempfile.TemporaryDirectory() as tmp_dir:
        repository = QueueRepository(f"{tmp_dir}/dry-run.db")
        repository.init_schema()
        summary = DryRunBackendService(
            repository=repository,
            matcher=SubscriptionMatcher(
                [
                    SubscriptionRule(
                        id="dry-run",
                        name="Dry Run",
                        pattern=request.include_keyword,
                    )
                ]
            ),
            transfer_storage=FakeTransferStorage(),
            organize_storage=FakeOrganizeStorage(items=[]),
            metadata_resolver=FakeMetadataResolver({}),
            organize_rule=OrganizeRule(media_library_root_cid=100),
            notifier=InMemoryNotifier(),
            staging_cid=0,
        ).run_messages(shares)

    return DryRunBackendSummaryResponse(
        collect_enqueued=summary.collect_enqueued,
        collect_processed=summary.collect_processed,
        transfer_processed=summary.transfer_processed,
        organize_scanned=summary.organize_scanned,
        organize_planned=summary.organize_planned,
        organize_moved=summary.organize_moved,
        notification_count=summary.notification_count,
        errors=list(summary.errors),
    )


@router.post("/collectors/telegram/{channel}/poll", response_model=CollectorPollResponse)
def poll_telegram_collector(
    channel: str,
    request: CollectorPollRequest,
    repository: QueueRepository = Depends(get_queue_repository),
    service_factory: Any = Depends(get_collector_polling_service_factory),
) -> CollectorPollResponse:
    normalized_channel = _normalize_telegram_channel(channel)
    service = service_factory(
        repository=repository,
        fetcher=_TelegramHtmlFixtureFetcher(request.html, normalized_channel),
        source_type="telegram_web",
        source_id=normalized_channel,
    )
    result = service.poll_once()
    return CollectorPollResponse(
        source_type=result.source_type,
        source_id=result.source_id,
        scanned=result.scanned,
        parsed_shares=result.parsed_shares,
        enqueued=result.enqueued,
        skipped_existing=result.skipped_existing,
        cursor=_cursor_to_api(result.cursor),
        status=_status_to_api(result.status, default="failed"),
        error=_safe_error(result.error),
    )


@router.get("/collectors/telegram/{channel}/status", response_model=CollectorStatusResponse)
def get_telegram_collector_status(
    channel: str,
    repository: QueueRepository = Depends(get_queue_repository),
) -> CollectorStatusResponse:
    normalized_channel = _normalize_telegram_channel(channel)
    cursor = repository.get_collector_cursor(source_type="telegram_web", source_id=normalized_channel)
    if cursor is None:
        return CollectorStatusResponse(
            source_type="telegram_web",
            source_id=normalized_channel,
            cursor=None,
            status="unknown",
            error=None,
        )
    return CollectorStatusResponse(
        source_type=cursor.source_type,
        source_id=cursor.source_id,
        cursor=cursor.last_seen_message_id,
        status=_status_to_api(cursor.last_status, default="unknown"),
        error=_safe_error(cursor.last_error),
    )


@router.get("/log-center/summary", response_model=LogCenterSummaryResponse)
def get_log_center_summary(
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 5,
    queue_repository: QueueRepository = Depends(get_queue_repository),
    organize_repository: OrganizeRepository = Depends(get_organize_repository),
) -> LogCenterSummaryResponse:
    return LogCenterSummaryResponse(
        collect_queue=QueueStatusCounts(**queue_repository.get_collect_status_counts()),
        transfer_queue=TransferQueueStatusCounts(**queue_repository.get_transfer_status_counts()),
        organizer=LogCenterOrganizerSummary(
            latest_run=_optional_organize_run_to_api(organize_repository.get_latest_run()),
            counts=OrganizeStatusCounts(**organize_repository.get_status_counts()),
            recent_runs=[_organize_run_to_api(run) for run in organize_repository.list_runs(limit=limit)],
        ),
    )


@router.get("/log-center/collect/logs", response_model=LogCenterCollectLogListResponse)
def list_log_center_collect_logs(
    status: str | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    repository: QueueRepository = Depends(get_queue_repository),
) -> LogCenterCollectLogListResponse:
    if status is not None and status not in VALID_COLLECT_STATUSES:
        raise HTTPException(status_code=422, detail="invalid collect queue status")
    return LogCenterCollectLogListResponse(
        items=[_collect_queue_item_to_api(item) for item in repository.list_collect_queue(status=status, limit=limit)]
    )


@router.get("/log-center/transfer/logs", response_model=LogCenterTransferLogListResponse)
def list_log_center_transfer_logs(
    status: str | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    repository: QueueRepository = Depends(get_queue_repository),
) -> LogCenterTransferLogListResponse:
    if status is not None and status not in VALID_TRANSFER_STATUSES:
        raise HTTPException(status_code=422, detail="invalid transfer queue status")
    return LogCenterTransferLogListResponse(
        items=[_transfer_queue_item_to_api(item) for item in repository.list_transfer_queue(status=status, limit=limit)]
    )


@router.get("/log-center/organizer/runs", response_model=LogCenterOrganizerRunListResponse)
def list_log_center_organizer_runs(
    status: str | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    repository: OrganizeRepository = Depends(get_organize_repository),
) -> LogCenterOrganizerRunListResponse:
    if status is not None and status not in VALID_ORGANIZE_RUN_STATUSES:
        raise HTTPException(status_code=422, detail="invalid organizer run status")
    return LogCenterOrganizerRunListResponse(items=[_organize_run_to_api(run) for run in repository.list_runs(limit=limit, status=status)])


@router.get("/log-center/organizer/items", response_model=LogCenterOrganizerItemListResponse)
def list_log_center_organizer_items(
    status: str | None = None,
    keyword: str | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    repository: OrganizeRepository = Depends(get_organize_repository),
) -> LogCenterOrganizerItemListResponse:
    if status is not None and status not in VALID_ORGANIZE_ITEM_STATUSES:
        raise HTTPException(status_code=422, detail="invalid organizer item status")
    normalized_keyword = keyword.strip() if keyword else None
    return LogCenterOrganizerItemListResponse(
        items=[
            _organize_run_item_to_api(item)
            for item in repository.list_items(limit=limit, status=status, keyword=normalized_keyword)
        ]
    )


@router.delete("/log-center/organizer/items", response_model=LogCenterOrganizerItemsClearResponse)
def clear_log_center_organizer_items(
    repository: OrganizeRepository = Depends(get_organize_repository),
) -> LogCenterOrganizerItemsClearResponse:
    return LogCenterOrganizerItemsClearResponse(deleted=repository.delete_all_items())


@router.delete("/log-center/organizer/items/{item_id}", response_model=LogCenterOrganizerItemDeleteResponse)
def delete_log_center_organizer_item(
    item_id: int,
    repository: OrganizeRepository = Depends(get_organize_repository),
) -> LogCenterOrganizerItemDeleteResponse:
    if not repository.delete_item(item_id):
        raise HTTPException(status_code=404, detail="organizer item not found")
    return LogCenterOrganizerItemDeleteResponse(deleted=True)


@router.get("/log-center/organizer/runs/{run_id}", response_model=LogCenterOrganizerRunDetailResponse)
def get_log_center_organizer_run(
    run_id: int,
    repository: OrganizeRepository = Depends(get_organize_repository),
) -> LogCenterOrganizerRunDetailResponse:
    run = repository.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="organizer run not found")
    return LogCenterOrganizerRunDetailResponse(
        run=_organize_run_to_api(run),
        items=[_organize_run_item_to_api(item) for item in repository.list_run_items(run_id)],
    )


@router.get("/queues/status", response_model=QueueStatusResponse)
def queue_status(repository: QueueRepository = Depends(get_queue_repository)) -> QueueStatusResponse:
    collect_counts = repository.get_collect_status_counts()
    transfer_counts = repository.get_transfer_status_counts()
    return QueueStatusResponse(
        collect_queue=QueueStatusCounts(**collect_counts),
        transfer_queue=TransferQueueStatusCounts(**transfer_counts),
    )


@router.get("/queues/{queue_name}/items", response_model=CollectQueueListResponse | TransferQueueListResponse)
def list_queue_items(
    queue_name: str,
    status: str | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    repository: QueueRepository = Depends(get_queue_repository),
) -> CollectQueueListResponse | TransferQueueListResponse:
    if queue_name == COLLECT_QUEUE_NAME:
        if status is not None and status not in VALID_COLLECT_STATUSES:
            raise HTTPException(status_code=422, detail="invalid collect queue status")
        collect_items = [_collect_queue_item_to_api(item) for item in repository.list_collect_queue(status=status, limit=limit)]
        return CollectQueueListResponse(items=collect_items)

    if queue_name == TRANSFER_QUEUE_NAME:
        if status is not None and status not in VALID_TRANSFER_STATUSES:
            raise HTTPException(status_code=422, detail="invalid transfer queue status")
        transfer_items = [_transfer_queue_item_to_api(item) for item in repository.list_transfer_queue(status=status, limit=limit)]
        return TransferQueueListResponse(items=transfer_items)

    raise HTTPException(status_code=404, detail="queue not found")


def _collect_queue_item_to_api(item: object) -> CollectQueueItemResponse:
    return CollectQueueItemResponse(
        id=item.id,
        source_type=item.source_type,
        source_id=item.source_id,
        message_id=item.message_id,
        message_url=item.message_url,
        message_text=item.message_text,
        published_at=item.published_at,
        shares=[ShareLinkResponse(**share.__dict__) for share in item.shares_json],
        status=item.status,
        attempt_count=item.attempt_count,
        last_error=item.last_error,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _transfer_queue_item_to_api(item: object) -> TransferQueueItemResponse:
    return TransferQueueItemResponse(
        id=item.id,
        share_code=item.share_code,
        receive_code=item.receive_code,
        share_url=item.share_url,
        staging_cid=item.staging_cid,
        matched_contexts=[TransferMatchContextResponse(**context.__dict__) for context in item.matched_rules_json],
        source_messages=[TransferSourceMessageResponse(**message.__dict__) for message in item.source_messages_json],
        status=item.status,
        attempt_count=item.attempt_count,
        last_error=item.last_error,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _telegram_web_channel_to_api(channel: TelegramWebChannelRecord) -> TelegramWebChannelResponse:
    return TelegramWebChannelResponse(
        channel=channel.channel,
        display_name=channel.display_name,
        enabled=channel.enabled,
        poll_interval_seconds=channel.poll_interval_seconds,
        created_at=channel.created_at,
        updated_at=channel.updated_at,
    )


def _subscription_to_api(rule: SubscriptionRuleRecord) -> SubscriptionResponse:
    return SubscriptionResponse(
        id=rule.id,
        name=rule.name,
        pattern=rule.pattern,
        enabled=rule.enabled,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
        tmdb_id=rule.tmdb_id,
        tmdb_kind=rule.tmdb_kind if rule.tmdb_kind in {"movie", "tv"} else None,
        aliases=list(rule.aliases),
        poster_path=rule.poster_path,
    )


def _netdisk_settings_to_api(settings: AppSettings) -> NetdiskSettingsResponse:
    configured = settings.p115 is not None
    return NetdiskSettingsResponse(
        configured=configured,
        transfer_cid=str(settings.transfer_cid),
        ensure_cookies=bool(settings.p115.ensure_cookies) if settings.p115 is not None else False,
        cache_home_configured=bool(settings.p115.cache_home) if settings.p115 is not None else False,
        status="configured" if configured else "not_configured",
        error=None if configured else "115 storage is not configured",
    )


def _safe_netdisk_error(error: Exception, settings: AppSettings) -> str:
    message = str(error).splitlines()[0].strip() or "115 storage test failed"
    secrets: list[str] = ["P115_COOKIES"]
    if settings.p115 is not None:
        if settings.p115.cookies:
            secrets.append(settings.p115.cookies)
        if settings.p115.cache_home is not None:
            secrets.append(str(settings.p115.cache_home))
    for secret in secrets:
        if secret:
            message = message.replace(secret, "[redacted]")
    return message or "115 storage test failed"


def _optional_organize_run_to_api(run: object | None) -> OrganizeRunResponse | None:
    if run is None:
        return None
    return _organize_run_to_api(run)


def _organize_run_to_api(run: object) -> OrganizeRunResponse:
    return OrganizeRunResponse(
        id=run.id,
        staging_cid=run.staging_cid,
        status=run.status,
        planned_count=run.planned_count,
        success_count=run.success_count,
        skipped_count=run.skipped_count,
        failed_count=run.failed_count,
        last_error=run.last_error,
        started_at=run.started_at,
        finished_at=run.finished_at,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


def _organize_run_item_to_api(item: object) -> OrganizeRunItemResponse:
    return OrganizeRunItemResponse(
        id=item.id,
        run_id=item.run_id,
        file_id=item.file_id,
        file_name=item.file_name,
        is_dir=item.is_dir,
        status=item.status,
        target_cid=item.target_cid,
        target_path=item.target_path,
        new_name=item.new_name,
        reason=item.reason,
        error=item.error,
        metadata_json=item.metadata_json,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _default_staging_cid_from_service(service: object) -> int | None:
    value = getattr(service, "default_staging_cid", None)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class _TelegramHtmlFixtureFetcher:
    def __init__(self, html: str | None, channel: str) -> None:
        self._html = html
        self._channel = channel

    def fetch_messages(self, source_id: str, cursor: int | None = None) -> list[TelegramWebMessage]:
        if self._html is None:
            raise ValueError("html fixture is required for API collector polling")
        return parse_telegram_public_channel_html(self._html, source_id or self._channel)


def _normalize_telegram_channel(channel: str) -> str:
    return channel.strip().lstrip("@")


def _cursor_to_api(cursor: object) -> str | None:
    if cursor in (None, ""):
        return None
    return str(cursor)


def _status_to_api(status: str | None, *, default: str) -> str:
    if not status:
        return default
    normalized = status.lower()
    if normalized in {"success", "failed", "unknown"}:
        return normalized
    return default


def _safe_error(error: str | None) -> str | None:
    if not error:
        return None
    first_line = str(error).splitlines()[0].strip()
    return first_line or "collector polling failed"


def _build_dry_run_messages(messages: list[DryRunBackendMessageRequest]) -> list[dict[str, object]]:
    dry_run_messages: list[dict[str, object]] = []
    for message in messages:
        for share in parse_115_shares(message.message_text):
            dry_run_messages.append(
                {
                    "share_code": share.share_code,
                    "receive_code": share.receive_code,
                    "share_url": share.share_url,
                    "source_type": message.source_type,
                    "source_id": message.source_id,
                    "message_id": message.message_id,
                    "message_text": message.message_text,
                    "published_at": message.published_at,
                }
            )
    return dry_run_messages


def _default_message_url(source_type: str, source_id: str, message_id: str) -> str | None:
    if source_type == "tg_web":
        return f"https://t.me/s/{source_id}/{message_id}"
    return None
