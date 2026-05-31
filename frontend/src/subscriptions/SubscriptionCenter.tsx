import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { discoverTmdbAliases, discoverTmdbSearch, discoverTmdbTrending, fetchTencentRanks, refreshRanks } from '../api'
import type {
  RankStatus,
  SubscriptionRule,
  TencentRankChannel,
  TmdbAliasBundleResponse,
  TmdbDiscoverySearchItem,
  TmdbTrendingListKey,
} from '../types'
import { useSubscriptions } from './useSubscriptions'

type SelectedTmdb = {
  tmdb_id: number
  kind: 'movie' | 'tv'
  title: string
  year: number | null
  aliases: string[]
  poster_path: string | null
  vote_average: number | null
  overview: string | null
}

// 主题对齐：深蓝面板 + 蓝紫强调色，与 App shell 一致
const cardClass = 'rounded-[0.625rem] border border-[#1d2a46] bg-[#0a1424] shadow-[0_0.75rem_2rem_rgba(0,0,0,0.28)]'
const fieldClass = 'w-full rounded-[0.5rem] border border-[#253552] bg-[#07111f] px-3 py-2.5 text-[0.85rem] text-[#dbe7ff] outline-none transition-[border-color,box-shadow] duration-150 placeholder:text-[#5b6a87] focus:border-[#3a8bff] focus:shadow-[0_0_0_0.1875rem_rgba(58,139,255,0.22)]'
const primaryButtonClass = 'rounded-[0.5rem] bg-[linear-gradient(135deg,#3a8bff,#7c5cff)] px-4 py-2.5 text-[0.82rem] font-black text-white transition duration-150 hover:brightness-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7c5cff]/40 disabled:cursor-not-allowed disabled:opacity-60 disabled:brightness-100'
const quietButtonClass = 'rounded-[0.5rem] border border-[#253552] bg-[#0d1b2e] px-3 py-1.5 text-[0.78rem] font-bold text-[#9aa9c3] transition duration-150 hover:bg-[#122743] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#3a8bff]/35 disabled:cursor-not-allowed disabled:opacity-60'
const dangerButtonClass = 'rounded-[0.5rem] border border-[#5a2233] bg-[#0d1b2e] px-3 py-1.5 text-[0.78rem] font-bold text-[#ff8095] transition duration-150 hover:bg-[#2a1622] hover:text-[#ffb3c0] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#ff8095]/25 disabled:cursor-not-allowed disabled:opacity-60'
const tabButtonClass = 'rounded-[0.5rem] px-4 py-2 text-[0.82rem] font-black transition duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#3a8bff]/35'
const tabActiveClass = 'bg-[#122743] text-white shadow-[inset_0_-0.125rem_0_#3a8bff]'
const tabInactiveClass = 'text-[#9aa9c3] hover:bg-[#0d1b2e] hover:text-white'
const pillClass = 'rounded-full border border-[#253552] bg-[#0d1b2e] px-2.5 py-0.5 text-[0.72rem] text-[#9aa9c3]'

function describeKind(kind: 'movie' | 'tv'): string {
  return kind === 'movie' ? '电影' : '剧集'
}

const TRENDING_LISTS: { key: TmdbTrendingListKey; label: string }[] = [
  { key: 'tv_on_the_air', label: '正在播出' },
  { key: 'trending_tv_week', label: '本周趋势剧集' },
  { key: 'tv_popular', label: '热门剧集' },
  { key: 'trending_movie_week', label: '本周趋势电影' },
]

type TrendingSource = 'tmdb' | 'tencent'

const TRENDING_SOURCES: { key: TrendingSource; label: string }[] = [
  { key: 'tmdb', label: 'TMDB' },
  { key: 'tencent', label: '腾讯视频' },
]

const TENCENT_CHANNELS: { key: TencentRankChannel; label: string }[] = [
  { key: 'tv', label: '电视剧' },
  { key: 'movie', label: '电影' },
  { key: 'variety', label: '综艺' },
  { key: 'cartoon', label: '动漫' },
]

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

// 后端 refreshed_at 是 SQLite CURRENT_TIMESTAMP（UTC naive，'YYYY-MM-DD HH:MM:SS'）。
// 标成 UTC 再转本地时间展示；解析失败则原样返回。
function formatRefreshedAt(value: string): string {
  const isoUtc = value.includes('T') ? value : `${value.replace(' ', 'T')}Z`
  const parsed = new Date(isoUtc)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return parsed.toLocaleString()
}

export function SubscriptionCenter() {
  const {
    rules,
    loading,
    error,
    saveState,
    deleteState,
    toggleState,
    saveRule,
    removeRule,
  } = useSubscriptions()

  const [activeTab, setActiveTab] = useState<'rules' | 'search' | 'trending'>('rules')
  const [tmdbQuery, setTmdbQuery] = useState('')
  const [searchResults, setSearchResults] = useState<TmdbDiscoverySearchItem[] | null>(null)
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)
  const [trendingList, setTrendingList] = useState<TmdbTrendingListKey>('tv_on_the_air')
  const [trendingItems, setTrendingItems] = useState<TmdbDiscoverySearchItem[] | null>(null)
  const [trendingLoading, setTrendingLoading] = useState(false)
  const [trendingError, setTrendingError] = useState<string | null>(null)
  const [trendingSource, setTrendingSource] = useState<TrendingSource>('tmdb')
  const [tencentChannel, setTencentChannel] = useState<TencentRankChannel>('tv')
  const [trendingStatus, setTrendingStatus] = useState<RankStatus | null>(null)
  const [trendingRefreshedAt, setTrendingRefreshedAt] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [refreshNotice, setRefreshNotice] = useState<string | null>(null)
  const [aliasLoading, setAliasLoading] = useState(false)
  const [aliasError, setAliasError] = useState<string | null>(null)
  const [selected, setSelected] = useState<SelectedTmdb | null>(null)
  const [aliasDraft, setAliasDraft] = useState('')
  const [overrideName, setOverrideName] = useState('')
  const [requireYearMatch, setRequireYearMatch] = useState(true)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [showEditModal, setShowEditModal] = useState(false)

  const combinedError = useMemo(() => {
    return [error, saveState.error, deleteState.error, toggleState.error]
      .filter(Boolean)
      .join(' ')
  }, [deleteState.error, error, saveState.error, toggleState.error])

  useEffect(() => {
    if (editingId === null) {
      return
    }
    const current = rules.find((rule) => rule.id === editingId)
    if (!current) {
      return
    }
    if (current.tmdb_id !== null && current.tmdb_kind) {
      setSelected({
        tmdb_id: current.tmdb_id,
        kind: current.tmdb_kind,
        title: current.name,
        year: current.year,
        aliases: current.aliases,
        poster_path: current.poster_path,
        vote_average: null,
        overview: null,
      })
    } else {
      setSelected(null)
    }
    setOverrideName(current.name)
    setRequireYearMatch(current.require_year_match)
  }, [editingId, rules])

  useEffect(() => {
    if (activeTab !== 'trending') {
      return
    }
    let cancelled = false
    setTrendingLoading(true)
    setTrendingError(null)
    const request =
      trendingSource === 'tencent'
        ? fetchTencentRanks(tencentChannel, 20)
        : discoverTmdbTrending(trendingList, 20)
    request
      .then((response) => {
        if (!cancelled) {
          setTrendingItems(response.items)
          setTrendingStatus(response.status)
          setTrendingRefreshedAt(response.refreshed_at)
        }
      })
      .catch((caught) => {
        if (!cancelled) {
          setTrendingError(errorMessage(caught))
          setTrendingItems([])
          setTrendingStatus(null)
          setTrendingRefreshedAt(null)
        }
      })
      .finally(() => {
        if (!cancelled) {
          setTrendingLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [activeTab, trendingList, trendingSource, tencentChannel])

  async function handleRefreshRanks() {
    setRefreshing(true)
    setRefreshNotice(null)
    try {
      await refreshRanks()
      setRefreshNotice('已请求后台刷新榜单，稍后会自动更新（约需 1-2 分钟）')
    } catch (caught) {
      setRefreshNotice(errorMessage(caught))
    } finally {
      setRefreshing(false)
    }
  }

  async function handleSearchSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmed = tmdbQuery.trim()
    if (!trimmed) {
      return
    }
    setSearchLoading(true)
    setSearchError(null)
    try {
      const response = await discoverTmdbSearch(trimmed, 10)
      setSearchResults(response.items)
    } catch (caught) {
      setSearchError(errorMessage(caught))
      setSearchResults([])
    } finally {
      setSearchLoading(false)
    }
  }

  async function handlePickResult(item: TmdbDiscoverySearchItem) {
    setAliasLoading(true)
    setAliasError(null)
    try {
      const bundle: TmdbAliasBundleResponse = await discoverTmdbAliases(item.kind, item.tmdb_id)
      const aliases = bundle.aliases.length > 0 ? bundle.aliases : Array.from(new Set([bundle.title, bundle.original_title].filter(Boolean)))
      setSelected({
        tmdb_id: bundle.tmdb_id,
        kind: bundle.kind,
        title: bundle.title || item.title,
        year: bundle.year ?? item.year,
        aliases,
        poster_path: item.poster_path || null,
        vote_average: item.vote_average || null,
        overview: item.overview || null,
      })
      setOverrideName(bundle.title || item.title)
      setRequireYearMatch(true)
      setShowEditModal(true)
    } catch (caught) {
      setAliasError(errorMessage(caught))
    } finally {
      setAliasLoading(false)
    }
  }

  function handleRemoveAlias(alias: string) {
    if (!selected) return
    setSelected({ ...selected, aliases: selected.aliases.filter((entry) => entry !== alias) })
  }

  function handleAddAlias() {
    const cleaned = aliasDraft.trim()
    if (!cleaned || !selected) return
    if (selected.aliases.includes(cleaned)) {
      setAliasDraft('')
      return
    }
    setSelected({ ...selected, aliases: [...selected.aliases, cleaned] })
    setAliasDraft('')
  }

  function resetEditor() {
    setSelected(null)
    setOverrideName('')
    setRequireYearMatch(true)
    setEditingId(null)
    setAliasDraft('')
    setAliasError(null)
    setShowEditModal(false)
  }

  async function handleSubmitSubscription(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selected) {
      setAliasError('请先选择 TMDB 媒体')
      return
    }
    const name = (overrideName || selected.title).trim()
    if (!name) {
      setAliasError('订阅名称不能为空')
      return
    }
    if (selected.aliases.length === 0) {
      setAliasError('至少需要保留一个别名')
      return
    }
    try {
      if (editingId === null) {
        await saveRule({
          name,
          pattern: '',
          enabled: true,
          tmdb_id: selected.tmdb_id,
          tmdb_kind: selected.kind,
          year: selected.year,
          require_year_match: requireYearMatch,
          aliases: selected.aliases,
          poster_path: selected.poster_path,
        })
      } else {
        await saveRule(
          {
            name,
            pattern: '',
            tmdb_id: selected.tmdb_id,
            tmdb_kind: selected.kind,
            year: selected.year,
            require_year_match: requireYearMatch,
            aliases: selected.aliases,
            poster_path: selected.poster_path,
          },
          editingId,
        )
      }
      resetEditor()
    } catch {
      // useSubscriptions reports the error via saveState.error
    }
  }

  function handleEdit(rule: SubscriptionRule) {
    setEditingId(rule.id)
    setShowEditModal(true)
  }

  async function handleDelete(rule: SubscriptionRule) {
    try {
      await removeRule(rule.id)
      if (editingId === rule.id) {
        resetEditor()
      }
    } catch {
      // Surfaced via deleteState.error
    }
  }

  return (
    <section aria-labelledby="subscription-center-title">
      {/* Tab 栏 + 计数 */}
      <div className="mb-5 flex items-center justify-between gap-3 max-[34rem]:flex-col max-[34rem]:items-stretch">
        <div className="flex gap-2">
          <button
            className={`${tabButtonClass} ${activeTab === 'rules' ? tabActiveClass : tabInactiveClass}`}
            onClick={() => setActiveTab('rules')}
          >
            订阅规则
          </button>
          <button
            className={`${tabButtonClass} ${activeTab === 'search' ? tabActiveClass : tabInactiveClass}`}
            onClick={() => setActiveTab('search')}
          >
            TMDB 搜索
          </button>
          <button
            className={`${tabButtonClass} ${activeTab === 'trending' ? tabActiveClass : tabInactiveClass}`}
            onClick={() => setActiveTab('trending')}
          >
            热门榜单
          </button>
        </div>
        <span className={pillClass}>{rules.length} 条规则</span>
      </div>

      {combinedError && <StateNote tone="error" label={combinedError} />}

      {/* Tab 内容：订阅规则 */}
      {activeTab === 'rules' && (
        <>
          {loading && <StateNote label="加载订阅规则中..." />}
          {!loading && rules.length === 0 && <StateNote label="暂无订阅规则" />}
          {!loading && rules.length > 0 && (
            <div
              className="grid gap-3 grid-cols-1 min-[40rem]:grid-cols-2 min-[68rem]:grid-cols-3 min-[96rem]:grid-cols-4"
              role="list"
              aria-label="订阅规则列表"
            >
              {rules.map((rule) => (
                <SubscriptionRuleCard
                  key={rule.id}
                  rule={rule}
                  busy={deleteState.loading || toggleState.loading}
                  onDelete={handleDelete}
                  onEdit={handleEdit}
                />
              ))}
            </div>
          )}
        </>
      )}

      {/* Tab 内容：TMDB 搜索 */}
      {activeTab === 'search' && (
        <>
          <form className="mb-5 flex gap-2 max-[34rem]:flex-col" onSubmit={handleSearchSubmit}>
            <input
              className={fieldClass}
              name="tmdb-query"
              value={tmdbQuery}
              onChange={(event) => setTmdbQuery(event.target.value)}
              placeholder="搜索 TMDB，例如：三体 / The Three-Body Problem"
              data-testid="tmdb-search-input"
            />
            <button
              className={`${primaryButtonClass} shrink-0`}
              type="submit"
              data-testid="tmdb-search-submit"
              disabled={searchLoading || tmdbQuery.trim().length === 0}
            >
              {searchLoading ? '搜索中...' : '搜索'}
            </button>
          </form>

          {searchError && <StateNote tone="error" label={searchError} />}
          {searchResults && searchResults.length === 0 && !searchLoading && (
            <StateNote label="未找到相关结果" />
          )}

          {searchResults && searchResults.length > 0 && (
            <div
              className="grid gap-3 grid-cols-1 min-[40rem]:grid-cols-2 min-[68rem]:grid-cols-3 min-[96rem]:grid-cols-4"
              role="list"
              aria-label="TMDB 搜索结果"
            >
              {searchResults.map((item) => (
                <TmdbSearchResultCard
                  key={`${item.kind}-${item.tmdb_id}`}
                  item={item}
                  onSubscribe={handlePickResult}
                  disabled={aliasLoading}
                />
              ))}
            </div>
          )}
        </>
      )}

      {/* Tab 内容：热门榜单 */}
      {activeTab === 'trending' && (
        <>
          <div className="mb-3 flex flex-wrap gap-2" role="tablist" aria-label="数据源">
            {TRENDING_SOURCES.map((entry) => (
              <button
                key={entry.key}
                type="button"
                className={`${tabButtonClass} ${
                  trendingSource === entry.key ? tabActiveClass : tabInactiveClass
                }`}
                onClick={() => setTrendingSource(entry.key)}
                data-testid={`trending-source-${entry.key}`}
              >
                {entry.label}
              </button>
            ))}
          </div>

          {trendingSource === 'tmdb' && (
            <div className="mb-5 flex flex-wrap gap-2" role="tablist" aria-label="榜单类型">
              {TRENDING_LISTS.map((entry) => (
                <button
                  key={entry.key}
                  type="button"
                  className={`${tabButtonClass} ${
                    trendingList === entry.key ? tabActiveClass : tabInactiveClass
                  }`}
                  onClick={() => setTrendingList(entry.key)}
                  data-testid={`trending-list-${entry.key}`}
                >
                  {entry.label}
                </button>
              ))}
            </div>
          )}

          {trendingSource === 'tencent' && (
            <div className="mb-5 flex flex-wrap gap-2" role="tablist" aria-label="腾讯频道">
              {TENCENT_CHANNELS.map((entry) => (
                <button
                  key={entry.key}
                  type="button"
                  className={`${tabButtonClass} ${
                    tencentChannel === entry.key ? tabActiveClass : tabInactiveClass
                  }`}
                  onClick={() => setTencentChannel(entry.key)}
                  data-testid={`tencent-channel-${entry.key}`}
                >
                  {entry.label}
                </button>
              ))}
            </div>
          )}

          <div className="mb-4 flex flex-wrap items-center gap-3">
            <button
              type="button"
              className={quietButtonClass}
              onClick={handleRefreshRanks}
              disabled={refreshing}
              data-testid="trending-refresh"
            >
              {refreshing ? '请求中...' : '立即刷新'}
            </button>
            <span className="text-[0.78rem] text-[#7a89a8]" data-testid="trending-refreshed-at">
              {trendingStatus === 'never_refreshed'
                ? '尚未刷新，请点击"立即刷新"'
                : trendingRefreshedAt
                  ? `更新于 ${formatRefreshedAt(trendingRefreshedAt)}`
                  : ''}
            </span>
            {trendingStatus === 'error' && (
              <span className="text-[0.78rem] text-[#ff8095]">上次刷新失败，显示的是上一份缓存</span>
            )}
          </div>
          {refreshNotice && (
            <div className="mb-3 text-[0.78rem] text-[#9aa9c3]" data-testid="trending-refresh-notice">
              {refreshNotice}
            </div>
          )}

          {trendingLoading && <StateNote label="加载榜单中..." />}
          {trendingError && <StateNote tone="error" label={trendingError} />}
          {!trendingLoading && trendingItems && trendingItems.length === 0 && !trendingError && (
            <StateNote label="榜单暂无数据" />
          )}

          {trendingItems && trendingItems.length > 0 && (
            <div
              className="grid gap-3 grid-cols-1 min-[40rem]:grid-cols-2 min-[68rem]:grid-cols-3 min-[96rem]:grid-cols-4"
              role="list"
              aria-label="热门榜单"
            >
              {trendingItems.map((item) => (
                <TmdbSearchResultCard
                  key={`${item.kind}-${item.tmdb_id}`}
                  item={item}
                  onSubscribe={handlePickResult}
                  disabled={aliasLoading}
                />
              ))}
            </div>
          )}
        </>
      )}

      {/* 编辑/订阅弹窗 */}
      {(showEditModal || selected) && (
        <EditModal
          selected={selected}
          editingId={editingId}
          overrideName={overrideName}
          aliasDraft={aliasDraft}
          aliasError={aliasError}
          aliasLoading={aliasLoading}
          requireYearMatch={requireYearMatch}
          saveLoading={saveState.loading}
          onOverrideNameChange={setOverrideName}
          onRequireYearMatchChange={setRequireYearMatch}
          onAliasDraftChange={setAliasDraft}
          onAddAlias={handleAddAlias}
          onRemoveAlias={handleRemoveAlias}
          onSubmit={handleSubmitSubscription}
          onClose={resetEditor}
        />
      )}
    </section>
  )
}

// 海报：小尺寸、固定 2:3 比例，放在卡片左侧
function Poster({ url, alt }: { url: string | null; alt: string }) {
  if (url) {
    return (
      <img
        src={url}
        alt={alt}
        className="aspect-[2/3] w-[5.5rem] shrink-0 rounded-[0.5rem] border border-[#1d2a46] bg-[#07111f] object-cover"
      />
    )
  }
  return (
    <div className="flex aspect-[2/3] w-[5.5rem] shrink-0 items-center justify-center rounded-[0.5rem] border border-[#1d2a46] bg-[#07111f] text-[0.7rem] text-[#5b6a87]">
      无海报
    </div>
  )
}

// 订阅规则卡片：海报左、信息与操作右
function SubscriptionRuleCard({
  busy,
  onDelete,
  onEdit,
  rule,
}: {
  busy: boolean
  onDelete: (rule: SubscriptionRule) => void
  onEdit: (rule: SubscriptionRule) => void
  rule: SubscriptionRule
}) {
  const kindLabel = rule.tmdb_kind ? describeKind(rule.tmdb_kind) : 'Legacy'
  const posterUrl = rule.poster_path
    ? `https://image.tmdb.org/t/p/w185${rule.poster_path}`
    : null

  return (
    <article className={`${cardClass} flex gap-3 p-3`} role="listitem">
      <Poster url={posterUrl} alt={`${rule.name} 海报`} />

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="mb-1.5 flex items-start justify-between gap-2">
          <h3 className="m-0 min-w-0 break-words text-[0.95rem] font-black leading-tight text-white">
            {rule.name}
          </h3>
          <span
            className={`shrink-0 rounded-full px-2 py-0.5 text-[0.68rem] font-bold ${
              rule.enabled
                ? 'border border-[#1f3d2e] bg-[#0e2118] text-[#5fd3a0]'
                : 'border border-[#5a2233] bg-[#2a1622] text-[#ff8095]'
            }`}
          >
            {rule.enabled ? '启用' : '禁用'}
          </span>
        </div>

        <p className="m-0 mb-2 text-[0.7rem] uppercase tracking-[0.06em] text-[#667793]">
          {kindLabel}
          {rule.tmdb_id !== null ? ` · TMDB #${rule.tmdb_id}` : ''}
        </p>

        <div className="mb-2 flex flex-wrap gap-1">
          <span className="inline-flex items-center rounded-[0.375rem] border border-[#253552] bg-[#0d1b2e] px-1.5 py-0.5 text-[0.7rem] text-[#9aa9c3]">
            年份 {rule.year ?? '未设置'}
          </span>
          <span className="inline-flex items-center rounded-[0.375rem] border border-[#253552] bg-[#0d1b2e] px-1.5 py-0.5 text-[0.7rem] text-[#9aa9c3]">
            {rule.require_year_match ? '强制年份' : '年份可选'}
          </span>
        </div>

        {rule.aliases.length > 0 && (
          <div className="mb-2 flex min-w-0 max-w-full flex-nowrap gap-1 overflow-hidden" aria-label="别名">
            {rule.aliases.slice(0, 3).map((alias) => (
              <span
                key={alias}
                title={alias}
                className="inline-flex min-w-0 max-w-[8.5rem] shrink items-center truncate rounded-[0.375rem] border border-[#253552] bg-[#0d1b2e] px-1.5 py-0.5 text-[0.7rem] text-[#9aa9c3]"
              >
                {alias}
              </span>
            ))}
            {rule.aliases.length > 3 && (
              <span className="inline-flex shrink-0 items-center rounded-[0.375rem] border border-[#253552] bg-[#0d1b2e] px-1.5 py-0.5 text-[0.7rem] text-[#667793]">
                +{rule.aliases.length - 3}
              </span>
            )}
          </div>
        )}

        <div className="mt-auto flex gap-2 pt-1">
          <button className={quietButtonClass} type="button" onClick={() => onEdit(rule)} disabled={busy}>
            编辑
          </button>
          <button className={dangerButtonClass} type="button" onClick={() => onDelete(rule)} disabled={busy}>
            删除
          </button>
        </div>
      </div>
    </article>
  )
}

// TMDB 搜索结果卡片：海报左、信息与订阅按钮右
function TmdbSearchResultCard({
  item,
  onSubscribe,
  disabled,
}: {
  item: TmdbDiscoverySearchItem
  onSubscribe: (item: TmdbDiscoverySearchItem) => void
  disabled: boolean
}) {
  const posterUrl = item.poster_path
    ? `https://image.tmdb.org/t/p/w185${item.poster_path}`
    : null

  return (
    <article className={`${cardClass} flex gap-3 p-3`} role="listitem">
      <Poster url={posterUrl} alt={`${item.title} 海报`} />

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="mb-1 flex items-start justify-between gap-2">
          <h3 className="m-0 min-w-0 break-words text-[0.95rem] font-black leading-tight text-white">
            {item.title || item.original_title}
          </h3>
          {item.vote_average !== null && item.vote_average > 0 && (
            <span className="shrink-0 rounded-full border border-[#253552] bg-[#0d1b2e] px-2 py-0.5 text-[0.7rem] font-bold text-[#ffd166]">
              ⭐ {item.vote_average.toFixed(1)}
            </span>
          )}
        </div>

        <p className="m-0 mb-1.5 text-[0.7rem] uppercase tracking-[0.06em] text-[#667793]">
          {describeKind(item.kind)} · TMDB #{item.tmdb_id}
          {item.year ? ` · ${item.year}` : ''}
        </p>

        {item.overview && (
          <p className="m-0 mb-2 line-clamp-2 text-[0.75rem] leading-4 text-[#91a0bb]">
            {item.overview}
          </p>
        )}

        <div className="mt-auto pt-1">
          <button className={primaryButtonClass} type="button" onClick={() => onSubscribe(item)} disabled={disabled}>
            {disabled ? '加载中...' : '订阅'}
          </button>
        </div>
      </div>
    </article>
  )
}

// 编辑/订阅弹窗
function EditModal({
  selected,
  editingId,
  overrideName,
  aliasDraft,
  aliasError,
  aliasLoading,
  requireYearMatch,
  saveLoading,
  onOverrideNameChange,
  onRequireYearMatchChange,
  onAliasDraftChange,
  onAddAlias,
  onRemoveAlias,
  onSubmit,
  onClose,
}: {
  selected: SelectedTmdb | null
  editingId: number | null
  overrideName: string
  aliasDraft: string
  aliasError: string | null
  aliasLoading: boolean
  requireYearMatch: boolean
  saveLoading: boolean
  onOverrideNameChange: (value: string) => void
  onRequireYearMatchChange: (value: boolean) => void
  onAliasDraftChange: (value: string) => void
  onAddAlias: () => void
  onRemoveAlias: (alias: string) => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
  onClose: () => void
}) {
  if (!selected) return null

  const posterUrl = selected.poster_path
    ? `https://image.tmdb.org/t/p/w342${selected.poster_path}`
    : null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(3,6,16,0.78)] p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className={`${cardClass} max-h-[90vh] w-full max-w-2xl overflow-y-auto p-5`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <p className="m-0 text-[0.68rem] font-black uppercase tracking-[0.14em] text-[#53d3ff]">
              {editingId === null ? '新建订阅' : '编辑订阅'}
            </p>
            <h2 className="mb-0 mt-1 text-[1.2rem] font-black text-white">订阅设置</h2>
          </div>
          <button className={quietButtonClass} type="button" onClick={onClose} aria-label="关闭">
            ✕
          </button>
        </div>

        {aliasLoading && <StateNote label="加载别名中..." />}
        {aliasError && <StateNote tone="error" label={aliasError} />}

        <form className="grid gap-4" onSubmit={onSubmit}>
          {/* 媒体信息卡片 */}
          <div className="flex gap-4 rounded-[0.5rem] border border-[#1d2a46] bg-[#07111f] p-4 max-[34rem]:flex-col">
            {posterUrl && (
              <img
                src={posterUrl}
                alt={`${selected.title} 海报`}
                className="aspect-[2/3] w-[7.5rem] shrink-0 rounded-[0.5rem] border border-[#1d2a46] object-cover"
              />
            )}
            <div className="flex-1">
              <h3 className="mb-1 mt-0 text-[1.05rem] font-black leading-tight text-white">
                {selected.title}
              </h3>
              <p className="m-0 mb-2 text-[0.72rem] uppercase tracking-[0.06em] text-[#667793]">
                {describeKind(selected.kind)} · TMDB #{selected.tmdb_id}
                {selected.year ? ` · ${selected.year}` : ''}
              </p>
              {selected.vote_average !== null && selected.vote_average > 0 && (
                <p className="m-0 mb-2 text-[0.8rem] text-[#ffd166]">
                  ⭐ {selected.vote_average.toFixed(1)}
                </p>
              )}
              {selected.overview && (
                <p className="m-0 line-clamp-4 text-[0.78rem] leading-5 text-[#91a0bb]">
                  {selected.overview}
                </p>
              )}
            </div>
          </div>

          {/* 订阅名称 */}
          <label className="grid gap-1.5 text-[0.82rem] font-bold text-[#9aa9c3]">
            <span>订阅名称</span>
            <input
              className={fieldClass}
              name="subscription-name"
              value={overrideName}
              onChange={(event) => onOverrideNameChange(event.target.value)}
              required
            />
          </label>

          <label className="flex items-center justify-between gap-3 rounded-[0.5rem] border border-[#1d2a46] bg-[#07111f] px-3 py-2.5 text-[0.82rem] font-bold text-[#dbe7ff]">
            <span>强制年份匹配</span>
            <input
              type="checkbox"
              checked={requireYearMatch}
              onChange={(event) => onRequireYearMatchChange(event.target.checked)}
              className="h-4 w-4 accent-[#3a8bff]"
            />
          </label>

          {/* 别名管理 */}
          <div className="grid gap-1.5 text-[0.82rem] font-bold text-[#9aa9c3]">
            <span>别名（任一命中即匹配）</span>
            <div className="flex flex-wrap gap-1.5">
              {selected.aliases.map((alias) => (
                <span
                  key={alias}
                  className="inline-flex items-center gap-1.5 rounded-[0.375rem] border border-[#253552] bg-[#0d1b2e] px-2 py-1 text-[0.78rem] font-semibold text-[#dbe7ff]"
                >
                  {alias}
                  <button
                    type="button"
                    className="text-[#ff8095] hover:text-[#ffb3c0]"
                    aria-label={`删除 ${alias}`}
                    onClick={() => onRemoveAlias(alias)}
                  >
                    ×
                  </button>
                </span>
              ))}
              {selected.aliases.length === 0 && (
                <span className="text-[#ff8095]">至少保留一个别名</span>
              )}
            </div>
            <div className="mt-1 flex gap-2">
              <input
                className={`${fieldClass} flex-1`}
                name="alias-draft"
                value={aliasDraft}
                onChange={(event) => onAliasDraftChange(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault()
                    onAddAlias()
                  }
                }}
                placeholder="新增别名"
              />
              <button className={`${quietButtonClass} shrink-0`} type="button" onClick={onAddAlias}>
                添加
              </button>
            </div>
          </div>

          {/* 操作按钮 */}
          <div className="flex gap-2">
            <button className={primaryButtonClass} type="submit" disabled={saveLoading}>
              {saveLoading ? '保存中...' : editingId === null ? '保存订阅' : '保存修改'}
            </button>
            <button className={quietButtonClass} type="button" onClick={onClose}>
              取消
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function StateNote({ label, tone = 'neutral' }: { label: string; tone?: 'neutral' | 'error' }) {
  const toneClass = tone === 'error' ? 'border-[#5a2233] bg-[#1a0f16] text-[#ff8095]' : 'border-[#1d2a46] bg-[#0a1424] text-[#91a0bb]'

  return (
    <p className={`mb-3 break-words rounded-[0.5rem] border px-3 py-2.5 text-[0.82rem] ${toneClass}`}>{label}</p>
  )
}
