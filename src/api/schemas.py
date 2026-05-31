from __future__ import annotations

from datetime import datetime
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.queue.models import COLLECT_QUEUE_STATUSES, TRANSFER_QUEUE_STATUSES
from src.organizing.repository import ORGANIZE_RUN_ITEM_STATUSES, ORGANIZE_RUN_STATUSES

COLLECT_QUEUE_NAME: Final[str] = "collect"
TRANSFER_QUEUE_NAME: Final[str] = "transfer"
QUEUE_NAMES: Final[tuple[str, str]] = (COLLECT_QUEUE_NAME, TRANSFER_QUEUE_NAME)

DEFAULT_LIMIT: Final[int] = 50
MAX_LIMIT: Final[int] = 200

VALID_COLLECT_STATUSES: Final[frozenset[str]] = frozenset(COLLECT_QUEUE_STATUSES)
VALID_TRANSFER_STATUSES: Final[frozenset[str]] = frozenset(TRANSFER_QUEUE_STATUSES)
VALID_ORGANIZE_RUN_STATUSES: Final[frozenset[str]] = frozenset(ORGANIZE_RUN_STATUSES)
VALID_ORGANIZE_ITEM_STATUSES: Final[frozenset[str]] = frozenset(ORGANIZE_RUN_ITEM_STATUSES)


class APIModel(BaseModel):
    model_config = ConfigDict(frozen=True)


def _coerce_cid(value: object, *, minimum: int) -> str | None:
    """Accept int or numeric string CID, return canonical string to preserve precision."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("CID must be a number")
    if isinstance(value, int):
        text = str(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
    else:
        raise ValueError("CID must be an integer or numeric string")
    if not text.isdigit():
        raise ValueError("CID must be a non-negative integer")
    if int(text) < minimum:
        raise ValueError(f"CID must be >= {minimum}")
    return str(int(text))


class HealthResponse(APIModel):
    status: Literal["ok"] = "ok"


class RuntimeComponentStatusResponse(APIModel):
    name: str
    desired_state: str
    status: str
    configured: bool
    enabled: bool
    detail: str
    last_status: str | None = None
    last_error: str | None = None
    tick_count: int | None = None
    last_started_at: str | None = None
    last_finished_at: str | None = None
    last_success: bool | None = None
    last_heartbeat_at: str | None = None


class RuntimeOrganizerSummaryResponse(APIModel):
    latest_run: OrganizeRunResponse | None = None
    counts: OrganizeStatusCounts


class RuntimeQueueCountsResponse(APIModel):
    collect_queue: QueueStatusCounts
    transfer_queue: TransferQueueStatusCounts


class RuntimeStatusResponse(APIModel):
    desired_state: str
    effective_state: str
    control_plane_only: bool
    started_at: str | None = None
    stopped_at: str | None = None
    updated_at: str
    message: str
    components: list[RuntimeComponentStatusResponse]
    queues: RuntimeQueueCountsResponse
    organizer: RuntimeOrganizerSummaryResponse


class RuntimeControlResponse(RuntimeStatusResponse):
    action: str
    changed: bool


class RuntimeTriggerRequest(APIModel):
    event_name: str


class RuntimeTriggerResponse(APIModel):
    trigger_id: int
    event_name: str


class NetdiskSettingsUpdateRequest(APIModel):
    transfer_cid: int | str | None = None
    ensure_cookies: bool | None = None
    cache_home: str | None = None
    cookies: str | None = None

    @field_validator("transfer_cid", mode="before")
    @classmethod
    def _validate_transfer_cid(cls, value: object) -> int | str | None:
        return _coerce_cid(value, minimum=0)


class NetdiskSettingsResponse(APIModel):
    configured: bool
    transfer_cid: str
    ensure_cookies: bool
    cache_home_configured: bool
    status: str
    error: str | None = None


class NetdiskStatusResponse(APIModel):
    configured: bool
    transfer_cid: str
    ensure_cookies: bool
    cache_home_configured: bool
    status: str
    error: str | None = None


class NetdiskTestRequest(APIModel):
    cid: int | str | None = None


class NetdiskTestResponse(APIModel):
    configured: bool
    status: str
    ok: bool
    item_count: int | None = None
    error: str | None = None


class ConnectivityItemResponse(APIModel):
    name: str
    kind: str  # netdisk | tmdb | telegram | bark
    configured: bool
    ok: bool
    latency_ms: int | None = None
    detail: str | None = None
    error: str | None = None


class ConnectivityResponse(APIModel):
    checked_at: datetime
    items: list[ConnectivityItemResponse] = Field(default_factory=list)


class OrganizerSettingsResponse(APIModel):
    media_library_root_cid: str
    configured: bool


class OrganizerSettingsUpdateRequest(APIModel):
    media_library_root_cid: int | str | None = None

    @field_validator("media_library_root_cid", mode="before")
    @classmethod
    def _validate_root_cid(cls, value: object) -> int | str | None:
        return _coerce_cid(value, minimum=1)


class NotificationSettingsResponse(APIModel):
    enabled: bool
    url: str
    has_token: bool
    timeout_seconds: int


class NotificationSettingsUpdateRequest(APIModel):
    enabled: bool | None = None
    url: str | None = None
    token: str | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=120)


class NotificationTestResponse(APIModel):
    ok: bool
    status_code: int | None = None
    error: str | None = None


class TelegramProviderResponse(APIModel):
    name: str
    enabled: bool
    has_bot_token: bool
    chat_id: str


class BarkProviderResponse(APIModel):
    name: str
    enabled: bool
    has_device_key: bool
    server_url: str


class NotificationProvidersResponse(APIModel):
    telegram: list[TelegramProviderResponse] = Field(default_factory=list)
    bark: list[BarkProviderResponse] = Field(default_factory=list)
    routing: dict[str, list[str]] = Field(default_factory=dict)


class TelegramProviderUpdate(APIModel):
    name: str
    enabled: bool = False
    # 留空表示保持现有 bot_token 不变
    bot_token: str | None = None
    chat_id: str = ""


class BarkProviderUpdate(APIModel):
    name: str
    enabled: bool = False
    # 留空表示保持现有 device_key 不变
    device_key: str | None = None
    server_url: str = "https://api.day.app"


class NotificationProvidersUpdateRequest(APIModel):
    telegram: list[TelegramProviderUpdate] | None = None
    bark: list[BarkProviderUpdate] | None = None
    routing: dict[str, list[str]] | None = None


class QueueStatusCounts(APIModel):
    PENDING: int = 0
    RUNNING: int = 0
    SUCCESS: int = 0
    SKIPPED: int = 0
    FAILED: int = 0


class TransferQueueStatusCounts(APIModel):
    PENDING: int = 0
    RUNNING: int = 0
    SUCCESS: int = 0
    FAILED: int = 0


class QueueStatusResponse(APIModel):
    collect_queue: QueueStatusCounts
    transfer_queue: TransferQueueStatusCounts


class ShareLinkResponse(APIModel):
    share_code: str
    receive_code: str
    share_url: str


class TransferMatchContextResponse(APIModel):
    rule_id: str
    rule_name: str
    matched_keywords: list[str]


class TransferSourceMessageResponse(APIModel):
    collect_id: int
    source_type: str
    source_id: str
    message_id: str
    message_url: str
    published_at: str | None = None


class CollectQueueItemResponse(APIModel):
    id: int
    source_type: str
    source_id: str
    message_id: str
    message_url: str | None = None
    message_text: str
    published_at: str | None = None
    shares: list[ShareLinkResponse]
    status: str
    attempt_count: int
    last_error: str | None = None
    created_at: str
    updated_at: str


class TransferQueueItemResponse(APIModel):
    id: int
    share_code: str
    receive_code: str
    share_url: str
    staging_cid: int
    matched_contexts: list[TransferMatchContextResponse]
    source_messages: list[TransferSourceMessageResponse]
    status: str
    attempt_count: int
    last_error: str | None = None
    created_at: str
    updated_at: str


class CollectQueueListResponse(APIModel):
    queue_name: Literal["collect"] = COLLECT_QUEUE_NAME
    items: list[CollectQueueItemResponse]


class TransferQueueListResponse(APIModel):
    queue_name: Literal["transfer"] = TRANSFER_QUEUE_NAME
    items: list[TransferQueueItemResponse]


class CollectorPollRequest(APIModel):
    html: str | None = None


class CollectorPollResponse(APIModel):
    source_type: str
    source_id: str
    scanned: int
    parsed_shares: int
    enqueued: int
    skipped_existing: int
    cursor: str | None = None
    status: str
    error: str | None = None


class CollectorStatusResponse(APIModel):
    source_type: str
    source_id: str
    cursor: str | None = None
    status: str
    error: str | None = None


class DryRunBackendMessageRequest(APIModel):
    source_type: str
    source_id: str
    message_id: str
    message_text: str
    message_url: str | None = None
    published_at: datetime | None = None


class DryRunBackendRequest(APIModel):
    messages: list[DryRunBackendMessageRequest]
    include_keyword: str = "Movie"


class DryRunBackendSummaryResponse(APIModel):
    collect_enqueued: int
    collect_processed: int
    transfer_processed: int
    organize_scanned: int
    organize_planned: int
    organize_moved: int
    notification_count: int
    errors: list[str]


class OrganizeRunOnceRequest(APIModel):
    staging_cid: int | None = None


class OrganizeRunOnceResponse(APIModel):
    run_id: int
    status: str
    scanned_count: int
    planned_count: int
    success_count: int
    skipped_count: int
    failed_count: int
    last_error: str | None = None


class OrganizeRunItemResponse(APIModel):
    id: int
    run_id: int
    file_id: int
    file_name: str
    is_dir: bool
    status: str
    target_cid: int | None = None
    target_path: str | None = None
    new_name: str | None = None
    reason: str | None = None
    error: str | None = None
    metadata_json: str | None = None
    created_at: str
    updated_at: str


class OrganizeRunResponse(APIModel):
    id: int
    staging_cid: int
    status: str
    planned_count: int
    success_count: int
    skipped_count: int
    failed_count: int
    last_error: str | None = None
    started_at: str
    finished_at: str | None = None
    created_at: str
    updated_at: str


class OrganizeRunDetailResponse(APIModel):
    run: OrganizeRunResponse
    items: list[OrganizeRunItemResponse]


class OrganizeRunListResponse(APIModel):
    items: list[OrganizeRunResponse]


class OrganizeStatusCounts(APIModel):
    RUNNING: int = 0
    SUCCESS: int = 0
    PARTIAL_SUCCESS: int = 0
    FAILED: int = 0
    CANCELLED: int = 0


class OrganizeStatusResponse(APIModel):
    latest_run: OrganizeRunResponse | None = None
    counts: OrganizeStatusCounts


class LogCenterOrganizerSummary(APIModel):
    latest_run: OrganizeRunResponse | None = None
    counts: OrganizeStatusCounts
    recent_runs: list[OrganizeRunResponse]


class LogCenterSummaryResponse(APIModel):
    collect_queue: QueueStatusCounts
    transfer_queue: TransferQueueStatusCounts
    organizer: LogCenterOrganizerSummary


class LogCenterCollectLogListResponse(APIModel):
    items: list[CollectQueueItemResponse]


class LogCenterTransferLogListResponse(APIModel):
    items: list[TransferQueueItemResponse]


class LogCenterOrganizerRunListResponse(APIModel):
    items: list[OrganizeRunResponse]


class LogCenterOrganizerRunDetailResponse(APIModel):
    run: OrganizeRunResponse
    items: list[OrganizeRunItemResponse]


class LogCenterOrganizerItemListResponse(APIModel):
    items: list[OrganizeRunItemResponse]


class LogCenterOrganizerItemDeleteResponse(APIModel):
    deleted: bool


class LogCenterOrganizerItemsClearResponse(APIModel):
    deleted: int


class TransferQueueProcessRequest(APIModel):
    limit: int = Field(default=10, ge=1, le=100)


class TransferQueueProcessResponse(APIModel):
    processed: int
    success: int
    failed: int
    errors: list[str]


class TelegramWebChannelResponse(APIModel):
    channel: str
    display_name: str | None = None
    enabled: bool
    poll_interval_seconds: int
    created_at: str
    updated_at: str


class TelegramWebChannelListResponse(APIModel):
    items: list[TelegramWebChannelResponse]


class TelegramWebChannelCreateRequest(APIModel):
    channel: str = Field(min_length=1)
    display_name: str | None = None
    enabled: bool = True
    poll_interval_seconds: int = Field(default=1800, gt=0)


class TelegramWebChannelUpdateRequest(APIModel):
    display_name: str | None = None
    enabled: bool | None = None
    poll_interval_seconds: int | None = Field(default=None, gt=0)


class TelegramWebChannelDeleteResponse(APIModel):
    deleted: bool


class TelegramWebChannelStatusResponse(APIModel):
    channel: TelegramWebChannelResponse
    cursor: str | None = None
    status: str
    error: str | None = None


class SubscriptionResponse(APIModel):
    id: int
    name: str
    pattern: str
    enabled: bool
    created_at: str
    updated_at: str
    tmdb_id: int | None = None
    tmdb_kind: Literal["movie", "tv"] | None = None
    year: int | None = None
    require_year_match: bool = True
    aliases: list[str] = []
    poster_path: str | None = None


class SubscriptionListResponse(APIModel):
    items: list[SubscriptionResponse]


class SubscriptionCreateRequest(APIModel):
    name: str
    pattern: str = ""
    enabled: bool = True
    tmdb_id: int | None = Field(default=None, ge=1)
    tmdb_kind: Literal["movie", "tv"] | None = None
    year: int | None = Field(default=None, ge=1900, le=2099)
    require_year_match: bool = True
    aliases: list[str] = []
    poster_path: str | None = None


class SubscriptionUpdateRequest(APIModel):
    name: str | None = None
    pattern: str | None = None
    enabled: bool | None = None
    tmdb_id: int | None = Field(default=None, ge=1)
    tmdb_kind: Literal["movie", "tv"] | None = None
    year: int | None = Field(default=None, ge=1900, le=2099)
    require_year_match: bool | None = None
    aliases: list[str] | None = None
    poster_path: str | None = None


class SubscriptionDeleteResponse(APIModel):
    deleted: bool


class SubscriptionTestRequest(APIModel):
    pattern: str
    text: str


class SubscriptionTestResponse(APIModel):
    matched: bool


class SubscriptionProcessRequest(APIModel):
    limit: int = 100


class SubscriptionProcessResponse(APIModel):
    scanned: int
    matched: int
    created: int
    skipped: int
    errors: list[str]


class AiModelListRequest(APIModel):
    provider: str = "openai_compatible"
    api_key: str = ""
    base_url: str = ""
    timeout_seconds: float = Field(default=30.0, ge=1.0)


class AiModelListResponse(APIModel):
    models: list[str]


class AiSettingsResponse(APIModel):
    enabled: bool
    provider: str
    base_url: str
    model: str
    timeout_seconds: float
    title_similarity_threshold: float
    prompt: str
    has_api_key: bool


class AiSettingsUpdateRequest(APIModel):
    enabled: bool | None = None
    provider: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    timeout_seconds: float | None = Field(default=None, ge=1.0)
    title_similarity_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    prompt: str | None = None


class AiFilenameParseRequest(APIModel):
    filename: str = Field(min_length=1)
    enabled: bool = True
    provider: str = "openai_compatible"
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    timeout_seconds: float = Field(default=30.0, ge=1.0)
    title_similarity_threshold: float = Field(default=0.55, ge=0.0, le=1.0)
    prompt: str = ""


class AiFilenameParseResultResponse(APIModel):
    type: Literal["movie", "tv"] | None = None
    title: str
    original_title: str | None = None
    year: int | None = None
    season: int | None = None
    episode: int | None = None
    resolution: str | None = None
    source: str | None = None
    release_group: str | None = None
    audio_codec: str | None = None
    video_codec: str | None = None


class AiFilenameParseResponse(APIModel):
    filename: str
    result: AiFilenameParseResultResponse | None = None


class TmdbMetadataResponse(APIModel):
    title: str
    year: int | None = None
    kind: str
    region_primary: str | None = None
    region_candidates: list[str] = []
    region_category: str | None = None
    region_source: str | None = None
    region_confidence: str = "low"


class TmdbMovieSearchResponse(APIModel):
    query: str
    year: int | None = None
    metadata: TmdbMetadataResponse | None = None


class TmdbMultiSearchResponse(APIModel):
    query: str
    year: int | None = None
    metadata: TmdbMetadataResponse | None = None


class TmdbDiscoverySearchItem(APIModel):
    tmdb_id: int
    kind: Literal["movie", "tv"]
    title: str
    original_title: str
    year: int | None = None
    overview: str = ""
    poster_path: str | None = None


class TmdbDiscoverySearchResponse(APIModel):
    query: str
    items: list[TmdbDiscoverySearchItem]


class TmdbTrendingResponse(APIModel):
    list: str
    items: list[TmdbDiscoverySearchItem]
    status: Literal["ok", "error", "never_refreshed"] = "ok"
    refreshed_at: str | None = None


class TencentRankResponse(APIModel):
    channel: str
    items: list[TmdbDiscoverySearchItem]
    status: Literal["ok", "error", "never_refreshed"] = "ok"
    refreshed_at: str | None = None


class RankRefreshResponse(APIModel):
    trigger_id: int
    event_name: str


class TmdbAliasBundleResponse(APIModel):
    tmdb_id: int
    kind: Literal["movie", "tv"]
    title: str
    original_title: str
    year: int | None = None
    aliases: list[str]
