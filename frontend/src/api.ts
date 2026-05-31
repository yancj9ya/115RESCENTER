import type {
  DryRunBackendRequest,
  AiFilenameParseRequest,
  AiFilenameParseResponse,
  AiModelListRequest,
  AiModelListResponse,
  AiSettingsResponse,
  AiSettingsUpdateRequest,
  DryRunBackendSummary,
  ConnectivityResponse,
  HealthResponse,
  LogCenterCollectLogsResponse,
  LogCenterOrganizerRunDetailResponse,
  LogCenterOrganizerItemsResponse,
  LogCenterOrganizerItemDeleteResponse,
  LogCenterOrganizerItemsClearResponse,
  LogCenterOrganizerRunsResponse,
  LogCenterSummaryResponse,
  LogCenterTransferLogsResponse,
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
  OrganizerRunDetailResponse,
  OrganizerRunsResponse,
  OrganizerSettingsResponse,
  OrganizerSettingsUpdateRequest,
  OrganizerStatusResponse,
  QueueItemsResponse,
  QueueName,
  QueueStatusResponse,
  RecentLogsResponse,
  RuntimeControlResponse,
  RuntimeStatusResponse,
  RuntimeTriggerEvent,
  RuntimeTriggerResponse,
  SubscriptionCreateRequest,
  SubscriptionDeleteResponse,
  SubscriptionListResponse,
  SubscriptionProcessRequest,
  SubscriptionProcessResponse,
  SubscriptionRule,
  SubscriptionTestRequest,
  SubscriptionTestResponse,
  SubscriptionUpdateRequest,
  TelegramWebChannel,
  TelegramWebChannelCreateRequest,
  TelegramWebChannelDeleteResponse,
  TelegramWebChannelListResponse,
  TelegramWebChannelStatusResponse,
  TelegramWebChannelUpdateRequest,
  TmdbAliasBundleResponse,
  TmdbDiscoveryKind,
  TmdbDiscoverySearchResponse,
  TmdbTrendingListKey,
  TmdbTrendingResponse,
  TencentRankChannel,
  TencentRankResponse,
  RankRefreshResponse,
  TmdbMovieSearchResponse,
  TransferQueueProcessRequest,
  TransferQueueProcessResponse,
} from './types'

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL?.replace(/\/+$/, '') ?? ''

export function apiUrl(path: string): string {
  return apiBaseUrl ? `${apiBaseUrl}${path}` : path
}

function extractErrorDetail(payload: unknown): string | null {
  if (typeof payload === 'string') {
    return payload
  }

  if (!payload || typeof payload !== 'object' || !('detail' in payload)) {
    return null
  }

  const { detail } = payload
  if (typeof detail === 'string') {
    return detail
  }

  if (Array.isArray(detail)) {
    const messages = detail
      .map((entry) => {
        if (typeof entry === 'string') {
          return entry
        }
        if (entry && typeof entry === 'object' && 'msg' in entry && typeof entry.msg === 'string') {
          return entry.msg
        }
        return null
      })
      .filter((message): message is string => message !== null)

    return messages.length > 0 ? messages.join('; ') : null
  }

  return null
}

async function responseErrorMessage(response: Response): Promise<string> {
  const fallback = `Request failed with ${response.status}`
  const contentType = response.headers.get('content-type') ?? ''

  if (contentType.includes('application/json')) {
    try {
      const payload: unknown = await response.json()
      return extractErrorDetail(payload) ?? fallback
    } catch {
      return fallback
    }
  }

  const detail = await response.text()
  return detail || fallback
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), {
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
    ...init,
  })

  if (!response.ok) {
    throw new Error(await responseErrorMessage(response))
  }

  return response.json() as Promise<T>
}

export function getHealth() {
  return requestJson<HealthResponse>('/health')
}

export function getConnectivity() {
  return requestJson<ConnectivityResponse>('/health/connectivity')
}

export function getQueueStatus() {
  return requestJson<QueueStatusResponse>('/queues/status')
}

export function getQueueItems(queue: QueueName) {
  return requestJson<QueueItemsResponse>(`/queues/${queue}/items`)
}

export function getRuntimeStatus() {
  return requestJson<RuntimeStatusResponse>('/runtime/status')
}

export function startRuntime() {
  return requestJson<RuntimeControlResponse>('/runtime/start', {
    method: 'POST',
  })
}

export function stopRuntime() {
  return requestJson<RuntimeControlResponse>('/runtime/stop', {
    method: 'POST',
  })
}

export function triggerRuntime(eventName: RuntimeTriggerEvent) {
  return requestJson<RuntimeTriggerResponse>('/runtime/trigger', {
    method: 'POST',
    body: JSON.stringify({ event_name: eventName }),
  })
}

export function getLogCenterSummary(limit = 5) {
  const params = new URLSearchParams({ limit: String(limit) })
  return requestJson<LogCenterSummaryResponse>(`/log-center/summary?${params.toString()}`)
}

export function getLogCenterCollectLogs(params?: { status?: string; limit?: number }) {
  const query = new URLSearchParams()
  if (params?.status) {
    query.set('status', params.status)
  }
  if (params?.limit !== undefined) {
    query.set('limit', String(params.limit))
  }
  const suffix = query.toString()
  return requestJson<LogCenterCollectLogsResponse>(`/log-center/collect/logs${suffix ? `?${suffix}` : ''}`)
}

export function getLogCenterTransferLogs(params?: { status?: string; limit?: number }) {
  const query = new URLSearchParams()
  if (params?.status) {
    query.set('status', params.status)
  }
  if (params?.limit !== undefined) {
    query.set('limit', String(params.limit))
  }
  const suffix = query.toString()
  return requestJson<LogCenterTransferLogsResponse>(`/log-center/transfer/logs${suffix ? `?${suffix}` : ''}`)
}

export function getLogCenterOrganizerRuns(params?: { status?: string; limit?: number }) {
  const query = new URLSearchParams()
  if (params?.status) {
    query.set('status', params.status)
  }
  if (params?.limit !== undefined) {
    query.set('limit', String(params.limit))
  }
  const suffix = query.toString()
  return requestJson<LogCenterOrganizerRunsResponse>(`/log-center/organizer/runs${suffix ? `?${suffix}` : ''}`)
}

export function getLogCenterOrganizerItems(params?: { status?: string; keyword?: string; limit?: number }) {
  const query = new URLSearchParams()
  if (params?.status) {
    query.set('status', params.status)
  }
  if (params?.keyword) {
    query.set('keyword', params.keyword)
  }
  if (params?.limit !== undefined) {
    query.set('limit', String(params.limit))
  }
  const suffix = query.toString()
  return requestJson<LogCenterOrganizerItemsResponse>(`/log-center/organizer/items${suffix ? `?${suffix}` : ''}`)
}

export function getLogCenterOrganizerRunDetail(id: number) {
  return requestJson<LogCenterOrganizerRunDetailResponse>(`/log-center/organizer/runs/${id}`)
}

export function deleteLogCenterOrganizerItem(id: number) {
  return requestJson<LogCenterOrganizerItemDeleteResponse>(`/log-center/organizer/items/${id}`, {
    method: 'DELETE',
  })
}

export function clearLogCenterOrganizerItems() {
  return requestJson<LogCenterOrganizerItemsClearResponse>('/log-center/organizer/items', {
    method: 'DELETE',
  })
}

export function getNetdiskSettings() {
  return requestJson<NetdiskSettingsResponse>('/netdisk/settings')
}

export function updateNetdiskSettings(payload: NetdiskSettingsUpdateRequest) {
  return requestJson<NetdiskSettingsResponse>('/netdisk/settings', {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function getNetdiskStatus() {
  return requestJson<NetdiskStatusResponse>('/netdisk/status')
}

export function testNetdisk(payload: NetdiskTestRequest) {
  return requestJson<NetdiskTestResponse>('/netdisk/test', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function getTelegramWebChannels() {
  return requestJson<TelegramWebChannelListResponse>('/resources/telegram-web/channels')
}

export function createTelegramWebChannel(payload: TelegramWebChannelCreateRequest) {
  return requestJson<TelegramWebChannel>('/resources/telegram-web/channels', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateTelegramWebChannel(channel: string | number, payload: TelegramWebChannelUpdateRequest) {
  return requestJson<TelegramWebChannel>(`/resources/telegram-web/channels/${encodeURIComponent(String(channel))}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function deleteTelegramWebChannel(channel: string | number) {
  return requestJson<TelegramWebChannelDeleteResponse>(
    `/resources/telegram-web/channels/${encodeURIComponent(String(channel))}`,
    {
      method: 'DELETE',
    },
  )
}

export function enableTelegramWebChannel(channel: string | number) {
  return requestJson<TelegramWebChannel>(
    `/resources/telegram-web/channels/${encodeURIComponent(String(channel))}/enable`,
    {
      method: 'POST',
    },
  )
}

export function disableTelegramWebChannel(channel: string | number) {
  return requestJson<TelegramWebChannel>(
    `/resources/telegram-web/channels/${encodeURIComponent(String(channel))}/disable`,
    {
      method: 'POST',
    },
  )
}

export function getTelegramWebChannelStatus(channel: string | number) {
  return requestJson<TelegramWebChannelStatusResponse>(
    `/resources/telegram-web/channels/${encodeURIComponent(String(channel))}/status`,
  )
}

export function getSubscriptions() {
  return requestJson<SubscriptionListResponse>('/subscriptions')
}

export function createSubscription(payload: SubscriptionCreateRequest) {
  return requestJson<SubscriptionRule>('/subscriptions', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function getSubscription(id: number) {
  return requestJson<SubscriptionRule>(`/subscriptions/${id}`)
}

export function updateSubscription(id: number, payload: SubscriptionUpdateRequest) {
  return requestJson<SubscriptionRule>(`/subscriptions/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function deleteSubscription(id: number) {
  return requestJson<SubscriptionDeleteResponse>(`/subscriptions/${id}`, {
    method: 'DELETE',
  })
}

export function testSubscription(payload: SubscriptionTestRequest) {
  return requestJson<SubscriptionTestResponse>('/subscriptions/test', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function processSubscriptions(payload: SubscriptionProcessRequest) {
  return requestJson<SubscriptionProcessResponse>('/subscriptions/process', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function processTransferQueue(payload: TransferQueueProcessRequest) {
  return requestJson<TransferQueueProcessResponse>('/transfer-queue/process', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function runOrganizerOnce(stagingCid?: number) {
  return requestJson<any>('/organizer/run-once', {
    method: 'POST',
    body: JSON.stringify({ staging_cid: stagingCid ?? null }),
  })
}

export function getOrganizerStatus() {
  return requestJson<OrganizerStatusResponse>('/organizer/status')
}

export function getOrganizerSettings() {
  return requestJson<OrganizerSettingsResponse>('/organizer/settings')
}

export function updateOrganizerSettings(payload: OrganizerSettingsUpdateRequest) {
  return requestJson<OrganizerSettingsResponse>('/organizer/settings', {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function getOrganizerRuns(limit = 8) {
  const params = new URLSearchParams({ limit: String(limit) })
  return requestJson<OrganizerRunsResponse>(`/organizer/runs?${params.toString()}`)
}

export function getOrganizerRunDetail(id: number) {
  return requestJson<OrganizerRunDetailResponse>(`/organizer/runs/${id}`)
}

export function postDryRunBackend(payload: DryRunBackendRequest) {
  return requestJson<DryRunBackendSummary>('/dry-run/backend', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function getTmdbMovie(query: string, year?: number | null) {
  const params = new URLSearchParams({ query })

  if (year !== null && year !== undefined) {
    params.set('year', String(year))
  }

  return requestJson<TmdbMovieSearchResponse>(`/tmdb/search/movie?${params.toString()}`)
}

export function getAiSettings() {
  return requestJson<AiSettingsResponse>('/ai/settings')
}

export function updateAiSettings(payload: AiSettingsUpdateRequest) {
  return requestJson<AiSettingsResponse>('/ai/settings', {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function listAiModels(payload: AiModelListRequest) {
  return requestJson<AiModelListResponse>('/ai/models', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function parseAiFilename(payload: AiFilenameParseRequest) {
  return requestJson<AiFilenameParseResponse>('/ai/filename/parse', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function discoverTmdbSearch(query: string, limit = 10) {
  const params = new URLSearchParams({ query, limit: String(limit) })
  return requestJson<TmdbDiscoverySearchResponse>(`/tmdb/discovery/search?${params.toString()}`)
}

export function discoverTmdbTrending(list: TmdbTrendingListKey, limit = 20) {
  const params = new URLSearchParams({ list, limit: String(limit) })
  return requestJson<TmdbTrendingResponse>(`/tmdb/discovery/trending?${params.toString()}`)
}

export function fetchTencentRanks(channel: TencentRankChannel, limit = 10) {
  const params = new URLSearchParams({ channel, limit: String(limit) })
  return requestJson<TencentRankResponse>(`/tencent/ranks?${params.toString()}`)
}

export function refreshRanks() {
  return requestJson<RankRefreshResponse>('/ranks/refresh', { method: 'POST' })
}

export function discoverTmdbAliases(kind: TmdbDiscoveryKind, tmdbId: number) {
  return requestJson<TmdbAliasBundleResponse>(`/tmdb/discovery/aliases/${kind}/${tmdbId}`)
}

export function getRecentLogs(params?: { limit?: number; level?: string }) {
  const query = new URLSearchParams()
  if (params?.limit !== undefined) query.set('limit', String(params.limit))
  if (params?.level) query.set('level', params.level)
  const suffix = query.toString()
  return requestJson<RecentLogsResponse>(`/logs/recent${suffix ? `?${suffix}` : ''}`)
}

export function clearLogs() {
  return requestJson<{ status: string; message: string }>('/logs/clear', { method: 'DELETE' })
}

export function getNotificationSettings() {
  return requestJson<NotificationSettingsResponse>('/notification/settings')
}

export function updateNotificationSettings(payload: NotificationSettingsUpdateRequest) {
  return requestJson<NotificationSettingsResponse>('/notification/settings', {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function testNotificationWebhook() {
  return requestJson<NotificationTestResponse>('/notification/test', { method: 'POST' })
}

export function getNotificationProviders() {
  return requestJson<NotificationProvidersResponse>('/notification/providers')
}

export function updateNotificationProviders(payload: NotificationProvidersUpdateRequest) {
  return requestJson<NotificationProvidersResponse>('/notification/providers', {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function testNotificationProvider(name: string) {
  return requestJson<NotificationTestResponse>(
    `/notification/providers/${encodeURIComponent(name)}/test`,
    { method: 'POST' },
  )
}
