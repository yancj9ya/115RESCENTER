export type QueueName = 'collect' | 'transfer'

export type HealthResponse = {
  status: 'ok'
}

export type CollectQueueStatusCounts = {
  PENDING: number
  RUNNING: number
  SUCCESS: number
  SKIPPED: number
  FAILED: number
}

export type TransferQueueStatusCounts = {
  PENDING: number
  RUNNING: number
  SUCCESS: number
  FAILED: number
}

export type QueueStatusResponse = {
  collect_queue: CollectQueueStatusCounts
  transfer_queue: TransferQueueStatusCounts
}

export type ShareLink = {
  share_code: string
  receive_code: string
  share_url: string
}

export type CollectQueueItem = {
  id: number
  source_type: string
  source_id: string
  message_id: string
  message_url: string | null
  message_text: string
  published_at: string | null
  shares: ShareLink[]
  status: string
  attempt_count: number
  last_error: string | null
  created_at: string
  updated_at: string
}

export type TransferMatchContext = {
  rule_id: string
  rule_name: string
  matched_keywords: string[]
}

export type TransferSourceMessage = {
  collect_id: number
  source_type: string
  source_id: string
  message_id: string
  message_url: string
  published_at: string | null
}

export type TransferQueueItem = {
  id: number
  share_code: string
  receive_code: string
  share_url: string
  staging_cid: number
  matched_contexts: TransferMatchContext[]
  source_messages: TransferSourceMessage[]
  status: string
  attempt_count: number
  last_error: string | null
  created_at: string
  updated_at: string
}

export type CollectQueueListResponse = {
  queue_name: 'collect'
  items: CollectQueueItem[]
}

export type TransferQueueListResponse = {
  queue_name: 'transfer'
  items: TransferQueueItem[]
}

export type QueueItemsResponse = CollectQueueListResponse | TransferQueueListResponse

export type SubscriptionRule = {
  id: number
  name: string
  pattern: string
  enabled: boolean
  created_at: string
  updated_at: string
  tmdb_id: number | null
  tmdb_kind: 'movie' | 'tv' | null
  aliases: string[]
  poster_path: string | null
}

export type SubscriptionListResponse = {
  items: SubscriptionRule[]
}

export type SubscriptionCreateRequest = {
  name: string
  pattern?: string
  enabled: boolean
  tmdb_id?: number | null
  tmdb_kind?: 'movie' | 'tv' | null
  aliases?: string[]
  poster_path?: string | null
}

export type SubscriptionUpdateRequest = {
  name?: string | null
  pattern?: string | null
  enabled?: boolean | null
  tmdb_id?: number | null
  tmdb_kind?: 'movie' | 'tv' | null
  aliases?: string[] | null
  poster_path?: string | null
}

export type SubscriptionDeleteResponse = {
  deleted: boolean
}

export type SubscriptionTestRequest = {
  pattern: string
  text: string
}

export type SubscriptionTestResponse = {
  matched: boolean
}

export type SubscriptionProcessRequest = {
  limit: number
}

export type SubscriptionProcessResponse = {
  scanned: number
  matched: number
  created: number
  skipped: number
  errors: string[]
}

export type TransferQueueProcessRequest = {
  limit: number
}

export type TransferQueueProcessResponse = {
  processed: number
  success: number
  failed: number
  errors: string[]
}

export type DryRunBackendRequest = {
  messages: Array<{
    source_type: string
    source_id: string
    message_id: string
    message_text: string
    message_url?: string | null
    published_at?: string | null
  }>
  include_keyword: string
}

export type DryRunBackendSummary = {
  collect_enqueued: number
  collect_processed: number
  transfer_processed: number
  organize_scanned: number
  organize_planned: number
  organize_moved: number
  notification_count: number
  errors: string[]
}

export type OrganizerRunStatus = 'RUNNING' | 'SUCCESS' | 'PARTIAL_SUCCESS' | 'FAILED' | 'CANCELLED'

export type OrganizerRun = {
  id: number
  staging_cid: number
  status: OrganizerRunStatus
  planned_count: number
  success_count: number
  skipped_count: number
  failed_count: number
  last_error: string | null
  started_at: string
  finished_at: string | null
  created_at: string
  updated_at: string
}

export type OrganizerRunItem = {
  id: number
  run_id: number
  file_id: string
  file_name: string
  is_dir: boolean
  target_cid: number
  target_path: string | null
  new_name: string | null
  reason: string | null
  status: string
  metadata_json: string | null
  error: string | null
  created_at: string
  updated_at: string
}

export type OrganizerRunDetailResponse = {
  run: OrganizerRun
  items: OrganizerRunItem[]
}

export type OrganizerStatusCounts = Record<OrganizerRunStatus, number>

export type OrganizerStatusResponse = {
  latest_run: OrganizerRun | null
  counts: OrganizerStatusCounts
}

export type OrganizerRunsResponse = {
  items: OrganizerRun[]
}

export type LogCenterOrganizerSummary = {
  latest_run: OrganizerRun | null
  counts: OrganizerStatusCounts
  recent_runs: OrganizerRun[]
}

export type LogCenterSummaryResponse = {
  collect_queue: CollectQueueStatusCounts
  transfer_queue: TransferQueueStatusCounts
  organizer: LogCenterOrganizerSummary
}

export type LogCenterCollectLogsResponse = {
  items: CollectQueueItem[]
}

export type LogCenterTransferLogsResponse = {
  items: TransferQueueItem[]
}

export type LogCenterOrganizerRunsResponse = {
  items: OrganizerRun[]
}

export type LogCenterOrganizerRunDetailResponse = {
  run: OrganizerRun
  items: OrganizerRunItem[]
}

export type LogCenterOrganizerItemsResponse = {
  items: OrganizerRunItem[]
}

export type LogCenterOrganizerItemDeleteResponse = {
  deleted: boolean
}

export type LogCenterOrganizerItemsClearResponse = {
  deleted: number
}

export type TmdbMetadata = {
  title: string
  year: number | null
  kind: string
}

export type TmdbMovieSearchResponse = {
  query: string
  year: number | null
  metadata: TmdbMetadata | null
}

export type RuntimeDesiredState = 'running' | 'stopped'

export type RuntimeEffectiveState = 'running' | 'stopped' | 'degraded'

export type RuntimeComponentStatus = {
  name: string
  desired_state: RuntimeDesiredState
  status: 'idle' | 'ready' | 'running' | 'success' | 'failed' | 'blocked' | 'degraded'
  configured: boolean
  enabled: boolean
  detail: string
  last_status?: string | null
  last_error?: string | null
  tick_count?: number | null
  last_started_at?: string | null
  last_finished_at?: string | null
  last_success?: boolean | null
  last_heartbeat_at?: string | null
}

export type RuntimeQueueCounts = {
  collect_queue: CollectQueueStatusCounts
  transfer_queue: TransferQueueStatusCounts
}

export type RuntimeOrganizerSummary = {
  latest_run: OrganizerRun | null
  counts: OrganizerStatusCounts
}

export type RuntimeStatusResponse = {
  desired_state: RuntimeDesiredState
  effective_state: RuntimeEffectiveState
  control_plane_only: boolean
  started_at: string | null
  stopped_at: string | null
  updated_at: string
  message: string
  components: RuntimeComponentStatus[]
  queues: RuntimeQueueCounts
  organizer: RuntimeOrganizerSummary
}

export type RuntimeControlResponse = RuntimeStatusResponse & {
  action: 'start' | 'stop'
  changed: boolean
}

export type RuntimeTriggerEvent = 'manual_collect' | 'manual_transfer' | 'manual_organize'

export type RuntimeTriggerResponse = {
  trigger_id: number
  event_name: string
}

export type NetdiskSettingsResponse = {
  configured: boolean
  transfer_cid: string
  ensure_cookies: boolean
  cache_home_configured: boolean
  status: string
  error: string | null
}

export type NetdiskSettingsUpdateRequest = {
  transfer_cid?: string | null
  ensure_cookies?: boolean | null
  cache_home?: string | null
  cookies?: string | null
}

export type NetdiskStatusResponse = {
  configured: boolean
  transfer_cid: string
  ensure_cookies: boolean
  cache_home_configured: boolean
  status: string
  error: string | null
}

export type NetdiskTestRequest = {
  cid?: number | string | null
}

export type NetdiskTestResponse = {
  configured: boolean
  status: string
  ok: boolean
  item_count: number | null
  error: string | null
}

export type OrganizerSettingsResponse = {
  media_library_root_cid: string
  configured: boolean
}

export type OrganizerSettingsUpdateRequest = {
  media_library_root_cid?: string | null
}

export type TelegramWebChannel = {
  channel: string
  display_name: string | null
  enabled: boolean
  poll_interval_seconds: number
  created_at: string
  updated_at: string
}

export type TelegramWebChannelListResponse = {
  items: TelegramWebChannel[]
}

export type TelegramWebChannelCreateRequest = {
  channel: string
  display_name?: string | null
  enabled: boolean
  poll_interval_seconds?: number | null
}

export type TelegramWebChannelUpdateRequest = {
  channel?: string | null
  display_name?: string | null
  enabled?: boolean | null
  poll_interval_seconds?: number | null
}

export type TelegramWebChannelDeleteResponse = {
  deleted: boolean
}

export type TelegramWebChannelStatusResponse = {
  channel: TelegramWebChannel
  cursor: string | null
  status: string
  error: string | null
}

export type TmdbDiscoveryKind = 'movie' | 'tv'

export type TmdbDiscoverySearchItem = {
  tmdb_id: number
  kind: TmdbDiscoveryKind
  title: string
  original_title: string
  year: number | null
  overview: string
  poster_path: string | null
  vote_average: number | null
}

export type TmdbDiscoverySearchResponse = {
  query: string
  items: TmdbDiscoverySearchItem[]
}

export type TmdbTrendingListKey =
  | 'tv_on_the_air'
  | 'trending_tv_week'
  | 'tv_popular'
  | 'trending_movie_week'

export type RankStatus = 'ok' | 'error' | 'never_refreshed'

export type TmdbTrendingResponse = {
  list: TmdbTrendingListKey
  items: TmdbDiscoverySearchItem[]
  status: RankStatus
  refreshed_at: string | null
}

export type TencentRankChannel = 'tv' | 'movie' | 'variety' | 'cartoon'

export type TencentRankResponse = {
  channel: TencentRankChannel
  items: TmdbDiscoverySearchItem[]
  status: RankStatus
  refreshed_at: string | null
}

export type RankRefreshResponse = {
  trigger_id: number
  event_name: string
}

export type TmdbAliasBundleResponse = {
  tmdb_id: number
  kind: TmdbDiscoveryKind
  title: string
  original_title: string
  year: number | null
  aliases: string[]
}

export type LogEntry = {
  timestamp: string
  level: string
  logger: string
  message: string
  module: string
  function: string
  line: number
}

export type RecentLogsResponse = {
  total: number
  logs: LogEntry[]
}

export type NotificationSettingsResponse = {
  enabled: boolean
  url: string
  has_token: boolean
  timeout_seconds: number
}

export type NotificationSettingsUpdateRequest = {
  enabled?: boolean | null
  url?: string | null
  token?: string | null
  timeout_seconds?: number | null
}

export type NotificationTestResponse = {
  ok: boolean
  status_code: number | null
  error: string | null
}

export type TelegramProviderResponse = {
  name: string
  enabled: boolean
  has_bot_token: boolean
  chat_id: string
}

export type BarkProviderResponse = {
  name: string
  enabled: boolean
  has_device_key: boolean
  server_url: string
}

export type NotificationProvidersResponse = {
  telegram: TelegramProviderResponse[]
  bark: BarkProviderResponse[]
  routing: Record<string, string[]>
}

export type TelegramProviderUpdate = {
  name: string
  enabled: boolean
  bot_token?: string | null
  chat_id: string
}

export type BarkProviderUpdate = {
  name: string
  enabled: boolean
  device_key?: string | null
  server_url: string
}

export type NotificationProvidersUpdateRequest = {
  telegram?: TelegramProviderUpdate[] | null
  bark?: BarkProviderUpdate[] | null
  routing?: Record<string, string[]> | null
}

export type ConnectivityItem = {
  name: string
  kind: string
  configured: boolean
  ok: boolean
  latency_ms: number | null
  detail: string | null
  error: string | null
}

export type ConnectivityResponse = {
  checked_at: string
  items: ConnectivityItem[]
}
