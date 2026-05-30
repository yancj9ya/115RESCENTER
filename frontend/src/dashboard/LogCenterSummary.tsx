import { useEffect, useMemo, useState } from 'react'
import { getLogCenterCollectLogs, getLogCenterOrganizerItems, getLogCenterSummary, deleteLogCenterOrganizerItem, clearLogCenterOrganizerItems } from '../api'
import type { CollectQueueItem, LogCenterSummaryResponse, OrganizerRunItem } from '../types'
import LogViewer from '../components/LogViewer'

export type LogCenterView = 'overview' | 'collect' | 'transfer' | 'organize' | 'system'

type LoadState = {
  loading: boolean
  error: string | null
}

const cardClass = 'rounded-[0.625rem] border border-[#253552] bg-[#07111f] px-3 py-2.5'
const labelClass = 'text-[0.64rem] font-black uppercase tracking-[0.1em] text-[#667793]'
const valueClass = 'mt-1 text-[0.86rem] font-black text-[#dbe7ff]'

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function queueTotal(counts: Record<string, number>): number {
  return Object.values(counts).reduce((total, count) => total + count, 0)
}

function statusRows(counts: Record<string, number>) {
  return Object.entries(counts).map(([status, count]) => ({ label: status, value: String(count) }))
}

export function LogCenterSummary({ initialView = 'system' }: { initialView?: LogCenterView }) {
  const [activeView, setActiveView] = useState<LogCenterView>(initialView)
  const [summary, setSummary] = useState<LogCenterSummaryResponse | null>(null)
  const [state, setState] = useState<LoadState>({ loading: true, error: null })

  useEffect(() => {
    setActiveView(initialView)
  }, [initialView])

  useEffect(() => {
    let mounted = true

    setState({ loading: true, error: null })
    getLogCenterSummary(5)
      .then((response) => {
        if (!mounted) {
          return
        }
        setSummary(response)
        setState({ loading: false, error: null })
      })
      .catch((caught) => {
        if (mounted) {
          setState({ loading: false, error: errorMessage(caught) })
        }
      })

    return () => {
      mounted = false
    }
  }, [])

  const metrics = useMemo(() => {
    return [
      {
        label: '收集队列',
        value: summary ? `${queueTotal(summary.collect_queue)} 总计` : '未知',
      },
      {
        label: '转存队列',
        value: summary ? `${queueTotal(summary.transfer_queue)} 总计` : '未知',
      },
      {
        label: '最新整理',
        value: summary?.organizer.latest_run?.status ?? '无',
      },
    ]
  }, [summary])

  return (
    <section className="grid gap-3" aria-label="日志中心视图">
      <div className="flex flex-wrap items-center gap-1.5">
        {[
          ['overview', '总览'],
          ['collect', '资源收集'],
          ['transfer', '转存队列'],
          ['organize', '整理记录'],
          ['system', '系统日志'],
        ].map(([view, label]) => {
          const active = activeView === view
          return (
            <button
              key={view}
              type="button"
              onClick={() => setActiveView(view as LogCenterView)}
              className={`h-8 rounded-[0.45rem] border px-2.5 text-[0.72rem] font-black transition ${active ? 'border-[#3a8bff] bg-[#122743] text-white' : 'border-[#253552] bg-[#07111f] text-[#9aa9c3] hover:text-white'}`}
            >
              {label}
            </button>
          )
        })}
      </div>

      {state.error && <p className="m-0 rounded-[0.5rem] border border-[#553044] bg-[#1a0e19] px-3 py-2 text-[0.78rem] font-semibold text-[#ff9fb4]">{state.error}</p>}

      {activeView === 'overview' && (
        <div className="grid gap-2.5 sm:grid-cols-3">
          {metrics.map((metric) => (
            <div key={metric.label} className={cardClass}>
              <div className={labelClass}>{metric.label}</div>
              <div className={valueClass}>{state.loading ? '加载中...' : metric.value}</div>
            </div>
          ))}
        </div>
      )}

      {activeView === 'collect' && <CollectLogTable />}
      {activeView === 'transfer' && <StatusGrid title="转存队列" rows={summary ? statusRows(summary.transfer_queue) : []} loading={state.loading} />}
      {activeView === 'organize' && <OrganizeItemTable />}
      {activeView === 'system' && (
        <div className="rounded-[0.625rem] border border-[#253552] bg-[#0a1424] p-0 overflow-hidden">
          <LogViewer useSSE={true} refreshInterval={3000} />
        </div>
      )}
    </section>
  )
}

function StatusGrid({ loading, rows, title }: { loading: boolean; rows: { label: string; value: string }[]; title: string }) {
  return (
    <div className="rounded-[0.625rem] border border-[#253552] bg-[#0a1424] p-3">
      <h3 className="m-0 mb-2 text-[0.82rem] font-black text-white">{title}</h3>
      <div className="grid gap-2 sm:grid-cols-4">
        {(loading ? [{ label: '加载中', value: '...' }] : rows).map((row) => (
          <div key={row.label} className={cardClass}>
            <div className={labelClass}>{row.label}</div>
            <div className={valueClass}>{row.value}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

const COLLECT_STATUS_STYLE: Record<string, { label: string; cls: string }> = {
  pending: { label: '待处理', cls: 'border-[#3a4a6a] bg-[#16223a] text-[#9aa9c3]' },
  running: { label: '处理中', cls: 'border-[#2d5a7a] bg-[#0f2a3d] text-[#53d3ff]' },
  success: { label: '转存成功', cls: 'border-[#2d5a3a] bg-[#0c2a1c] text-[#7dffaa]' },
  skipped: { label: '过滤', cls: 'border-[#3a4a6a] bg-[#16223a] text-[#9aa9c3]' },
  failed: { label: '失败', cls: 'border-[#5a2d3a] bg-[#2a0e16] text-[#ff7d9f]' },
}

function collectStatusStyle(status: string) {
  return COLLECT_STATUS_STYLE[status] ?? { label: status, cls: 'border-[#3a4a6a] bg-[#16223a] text-[#9aa9c3]' }
}

function formatDateTime(iso: string): string {
  if (!iso) return '-'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}/${date.getMonth() + 1}/${date.getDate()} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

function messageHref(item: CollectQueueItem): string | null {
  if (item.message_url) {
    // 把 t.me/s/<channel>/<id> 预览页链接转成直达消息链接
    return item.message_url.replace('https://t.me/s/', 'https://t.me/')
  }
  if (item.source_type.startsWith('tg') || item.source_type.startsWith('telegram')) {
    if (item.source_id && item.message_id) {
      return `https://t.me/${item.source_id}/${item.message_id}`
    }
  }
  return null
}

const COLLECT_PAGE_SIZE = 30

function CollectLogTable() {
  const [items, setItems] = useState<CollectQueueItem[] | null>(null)
  const [state, setState] = useState<LoadState>({ loading: true, error: null })
  const [page, setPage] = useState(0)

  useEffect(() => {
    let mounted = true
    setState({ loading: true, error: null })
    getLogCenterCollectLogs({ limit: 200 })
      .then((response) => {
        if (!mounted) return
        setItems(response.items)
        setState({ loading: false, error: null })
      })
      .catch((caught) => {
        if (mounted) setState({ loading: false, error: errorMessage(caught) })
      })
    return () => {
      mounted = false
    }
  }, [])

  const total = items?.length ?? 0
  const pageCount = Math.max(1, Math.ceil(total / COLLECT_PAGE_SIZE))
  const start = page * COLLECT_PAGE_SIZE
  const visible = (items ?? []).slice(start, start + COLLECT_PAGE_SIZE)

  return (
    <div className="rounded-[0.625rem] border border-[#253552] bg-[#0a1424] p-3">
      <div className="mb-2.5 flex flex-wrap items-center justify-between gap-2">
        <h3 className="m-0 text-[0.98rem] font-black text-white">资源收集</h3>
        <span className="text-[0.7rem] font-bold text-[#667793]">
          {state.loading
            ? '加载中...'
            : `总记录 ${total} 条 · 当前显示 ${visible.length} 条（第 ${total === 0 ? 0 : start + 1}-${start + visible.length} 条，每页 ${COLLECT_PAGE_SIZE} 条）`}
        </span>
      </div>

      {state.loading ? (
        <p className="m-0 text-[0.76rem] font-semibold text-[#91a0bb]">加载收集记录...</p>
      ) : total === 0 ? (
        <p className="m-0 text-[0.76rem] font-semibold text-[#91a0bb]">暂无收集记录。</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-[0.78rem]">
            <thead>
              <tr className="border-b border-[#1d2a46] text-[0.7rem] font-black uppercase tracking-[0.06em] text-[#667793]">
                <th className="px-2.5 py-2 font-black">时间</th>
                <th className="px-2.5 py-2 font-black">来源</th>
                <th className="px-2.5 py-2 font-black">状态</th>
                <th className="px-2.5 py-2 font-black">原始消息</th>
                <th className="px-2.5 py-2 font-black">消息链接</th>
                <th className="px-2.5 py-2 font-black">分享链接</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((item) => {
                const style = collectStatusStyle(item.status)
                const msgHref = messageHref(item)
                const shareUrl = item.shares[0]?.share_url ?? null
                return (
                  <tr key={item.id} className="border-b border-[#121f36] hover:bg-[#0d1b2e]">
                    <td className="whitespace-nowrap px-2.5 py-2.5 font-semibold text-[#c5d3ed]">{formatDateTime(item.created_at)}</td>
                    <td className="whitespace-nowrap px-2.5 py-2.5 font-bold text-[#9aa9c3]">{item.source_id || item.source_type}</td>
                    <td className="px-2.5 py-2.5">
                      <span className={`inline-block rounded-[0.4rem] border px-2 py-0.5 text-[0.66rem] font-black ${style.cls}`}>{style.label}</span>
                    </td>
                    <td className="max-w-[28rem] px-2.5 py-2.5">
                      <span className="block truncate font-semibold text-[#dbe7ff]" title={item.message_text}>{item.message_text || '-'}</span>
                    </td>
                    <td className="whitespace-nowrap px-2.5 py-2.5">
                      {msgHref ? (
                        <a href={msgHref} target="_blank" rel="noreferrer" className="font-black text-[#7c8cff] transition hover:text-[#a3b0ff]">查看</a>
                      ) : (
                        <span className="text-[0.72rem] text-[#3f4d68]">-</span>
                      )}
                    </td>
                    <td className="whitespace-nowrap px-2.5 py-2.5">
                      {shareUrl ? (
                        <a href={shareUrl} target="_blank" rel="noreferrer" className="font-black text-[#7c8cff] transition hover:text-[#a3b0ff]">打开</a>
                      ) : (
                        <span className="text-[0.72rem] text-[#3f4d68]">-</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {!state.loading && pageCount > 1 && (
        <div className="mt-3 flex items-center justify-end gap-2 text-[0.72rem] font-bold text-[#9aa9c3]">
          <button
            type="button"
            disabled={page === 0}
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            className="h-7 rounded-[0.4rem] border border-[#253552] bg-[#07111f] px-2.5 transition hover:border-[#3a8bff] hover:text-white disabled:opacity-40"
          >
            上一页
          </button>
          <span className="tabular-nums">{page + 1} / {pageCount}</span>
          <button
            type="button"
            disabled={page >= pageCount - 1}
            onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
            className="h-7 rounded-[0.4rem] border border-[#253552] bg-[#07111f] px-2.5 transition hover:border-[#3a8bff] hover:text-white disabled:opacity-40"
          >
            下一页
          </button>
        </div>
      )}
    </div>
  )
}

const ORGANIZE_ITEM_STATUS_STYLE: Record<string, { label: string; cls: string }> = {
  PLANNED: { label: 'planned', cls: 'border-[#3a4a6a] bg-[#16223a] text-[#9aa9c3]' },
  SUCCESS: { label: 'success', cls: 'border-[#2d5a3a] bg-[#0c2a1c] text-[#7dffaa]' },
  FAILED: { label: 'failed', cls: 'border-[#5a2d3a] bg-[#2a0e16] text-[#ff7d9f]' },
  SKIPPED_DIR: { label: 'skipped', cls: 'border-[#6a5a2a] bg-[#2a240e] text-[#f5c542]' },
  SKIPPED_UNMATCHED: { label: 'skipped', cls: 'border-[#6a5a2a] bg-[#2a240e] text-[#f5c542]' },
  SKIPPED_DUPLICATE: { label: 'skipped', cls: 'border-[#6a5a2a] bg-[#2a240e] text-[#f5c542]' },
}

function organizeItemStatusStyle(status: string) {
  return ORGANIZE_ITEM_STATUS_STYLE[status] ?? { label: status.toLowerCase(), cls: 'border-[#3a4a6a] bg-[#16223a] text-[#9aa9c3]' }
}

const ORGANIZE_STATUS_FILTERS: { value: string; label: string }[] = [
  { value: '', label: '全部状态' },
  { value: 'SUCCESS', label: '成功' },
  { value: 'FAILED', label: '失败' },
  { value: 'SKIPPED_DUPLICATE', label: '跳过-重复' },
  { value: 'SKIPPED_UNMATCHED', label: '跳过-未识别' },
  { value: 'PLANNED', label: '计划中' },
]

function organizeItemTitle(item: OrganizerRunItem): string {
  if (item.metadata_json) {
    try {
      const meta = JSON.parse(item.metadata_json) as { title?: string; year?: number | string }
      if (meta.title) {
        return meta.year ? `${meta.title} (${meta.year})` : meta.title
      }
    } catch {
      // 忽略解析失败，回退到文件名
    }
  }
  return item.new_name || item.file_name
}

function organizeItemTarget(item: OrganizerRunItem): string {
  if (item.target_path && item.new_name) return `${item.target_path} / ${item.new_name}`
  return item.new_name || item.target_path || '-'
}

const ORGANIZE_PAGE_SIZE = 20

function OrganizeItemTable() {
  const [items, setItems] = useState<OrganizerRunItem[] | null>(null)
  const [state, setState] = useState<LoadState>({ loading: true, error: null })
  const [status, setStatus] = useState('')
  const [keyword, setKeyword] = useState('')
  const [appliedKeyword, setAppliedKeyword] = useState('')
  const [page, setPage] = useState(0)
  const [reloadToken, setReloadToken] = useState(0)
  const [selected, setSelected] = useState<OrganizerRunItem | null>(null)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [clearing, setClearing] = useState(false)

  const handleDeleteItem = async (item: OrganizerRunItem) => {
    if (!window.confirm(`确定删除该整理记录？\n${organizeItemTitle(item)}`)) return
    setDeletingId(item.id)
    try {
      await deleteLogCenterOrganizerItem(item.id)
      setItems((prev) => (prev ? prev.filter((it) => it.id !== item.id) : prev))
      setSelected((prev) => (prev?.id === item.id ? null : prev))
    } catch (caught) {
      window.alert(`删除失败：${errorMessage(caught)}`)
    } finally {
      setDeletingId(null)
    }
  }

  const handleClearAll = async () => {
    if (!window.confirm('确定删除全部整理记录？此操作不可恢复。')) return
    setClearing(true)
    try {
      await clearLogCenterOrganizerItems()
      setItems([])
      setSelected(null)
      setPage(0)
    } catch (caught) {
      window.alert(`删除失败：${errorMessage(caught)}`)
    } finally {
      setClearing(false)
    }
  }

  useEffect(() => {
    let mounted = true
    setState({ loading: true, error: null })
    getLogCenterOrganizerItems({ limit: 200, status: status || undefined, keyword: appliedKeyword || undefined })
      .then((response) => {
        if (!mounted) return
        setItems(response.items)
        setPage(0)
        setState({ loading: false, error: null })
      })
      .catch((caught) => {
        if (mounted) setState({ loading: false, error: errorMessage(caught) })
      })
    return () => {
      mounted = false
    }
  }, [status, appliedKeyword, reloadToken])

  const total = items?.length ?? 0
  const pageCount = Math.max(1, Math.ceil(total / ORGANIZE_PAGE_SIZE))
  const start = page * ORGANIZE_PAGE_SIZE
  const visible = (items ?? []).slice(start, start + ORGANIZE_PAGE_SIZE)

  return (
    <div className="rounded-[0.625rem] border border-[#253552] bg-[#0a1424] p-3">
      <div className="mb-2.5 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="m-0 text-[0.98rem] font-black text-white">网盘整理历史</h3>
          <p className="m-0 mt-0.5 text-[0.7rem] font-semibold text-[#667793]">保留关键信息：状态 / 标题 / 来源 / 目标</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setReloadToken((t) => t + 1)}
            className="h-8 rounded-[0.45rem] border border-[#253552] bg-[#07111f] px-3 text-[0.72rem] font-black text-[#9aa9c3] transition hover:border-[#3a8bff] hover:text-white"
          >
            刷新
          </button>
          <button
            type="button"
            onClick={handleClearAll}
            disabled={clearing || (items?.length ?? 0) === 0}
            className="h-8 rounded-[0.45rem] border border-[#553044] bg-[#1a0e19] px-3 text-[0.72rem] font-black text-[#ff9fb4] transition hover:border-[#ff7d9f] hover:text-white disabled:opacity-45"
          >
            {clearing ? '删除中...' : '删除全部'}
          </button>
        </div>
      </div>

      <div className="mb-2.5 flex flex-wrap items-center gap-2">
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="h-8 rounded-[0.45rem] border border-[#253552] bg-[#07111f] px-2.5 text-[0.74rem] font-bold text-[#dbe7ff] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#3a8bff]/35"
        >
          {ORGANIZE_STATUS_FILTERS.map((f) => (
            <option key={f.value} value={f.value}>{f.label}</option>
          ))}
        </select>
        <form
          className="flex flex-1 items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            setAppliedKeyword(keyword.trim())
          }}
        >
          <input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="按 文件名 / 路径 / 错误信息 搜索"
            className="h-8 min-w-[12rem] flex-1 rounded-[0.45rem] border border-[#253552] bg-[#07111f] px-2.5 text-[0.74rem] font-semibold text-[#dbe7ff] placeholder:text-[#5f6e86] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#3a8bff]/35"
          />
          <button type="submit" className="h-8 rounded-[0.45rem] border border-[#3a8bff] bg-[#122743] px-3 text-[0.72rem] font-black text-white transition hover:bg-[#1a3a5f]">
            搜索
          </button>
        </form>
      </div>

      <div className="mb-2.5 flex items-center justify-between gap-2">
        <span className="text-[0.82rem] font-black text-white">115 网盘</span>
        <span className="text-[0.7rem] font-bold text-[#667793]">
          {state.loading
            ? '加载中...'
            : `总记录 ${total} 条 · 当前显示 ${visible.length} 条（第 ${total === 0 ? 0 : start + 1}-${start + visible.length} 条，每页 ${ORGANIZE_PAGE_SIZE} 条）`}
        </span>
      </div>

      {state.error && <p className="m-0 mb-2.5 rounded-[0.5rem] border border-[#553044] bg-[#1a0e19] px-3 py-2 text-[0.76rem] font-semibold text-[#ff9fb4]">{state.error}</p>}

      {state.loading ? (
        <p className="m-0 text-[0.76rem] font-semibold text-[#91a0bb]">加载整理记录...</p>
      ) : total === 0 ? (
        <p className="m-0 text-[0.76rem] font-semibold text-[#91a0bb]">暂无整理记录。</p>
      ) : (
        <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
          {visible.map((item) => {
            const style = organizeItemStatusStyle(item.status)
            return (
              <div
                key={item.id}
                role="button"
                tabIndex={0}
                onClick={() => setSelected(item)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    setSelected(item)
                  }
                }}
                className="cursor-pointer rounded-[0.5rem] border border-[#1d2a46] bg-[#07111f] p-3 transition hover:border-[#3a8bff] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#3a8bff]/40"
              >
                <div className="mb-1.5 flex items-center justify-between gap-2">
                  <span className={`inline-block rounded-[0.4rem] border px-2 py-0.5 text-[0.66rem] font-black ${style.cls}`}>{style.label}</span>
                  <div className="flex items-center gap-1.5">
                    <span className="text-[0.7rem] font-semibold text-[#91a0bb]">{formatDateTime(item.created_at)}</span>
                    <button
                      type="button"
                      title="删除该记录"
                      disabled={deletingId === item.id}
                      onClick={(e) => {
                        e.stopPropagation()
                        void handleDeleteItem(item)
                      }}
                      className="rounded-[0.35rem] border border-[#3a2230] bg-[#1a0e19] px-1.5 py-0.5 text-[0.64rem] font-black text-[#ff9fb4] transition hover:border-[#ff7d9f] hover:text-white disabled:opacity-45"
                    >
                      {deletingId === item.id ? '...' : '删除'}
                    </button>
                  </div>
                </div>
                <div className="mb-1.5 truncate text-[0.86rem] font-black text-[#dbe7ff]" title={organizeItemTitle(item)}>
                  {organizeItemTitle(item)}
                </div>
                <div className="text-[0.72rem] leading-5 text-[#9aa9c3]">
                  <span className="font-bold text-[#667793]">来源：</span>
                  <span className="break-all">{item.file_name}</span>
                </div>
                <div className="mt-0.5 text-[0.72rem] leading-5 text-[#9aa9c3]">
                  <span className="font-bold text-[#667793]">目标：</span>
                  <span className="break-all">{organizeItemTarget(item)}</span>
                </div>
                {item.error && (
                  <div className="mt-1.5 truncate rounded-[0.4rem] bg-[#1a0e19] px-2 py-1 text-[0.66rem] text-[#ff9fb4]" title={item.error}>
                    {item.error}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {!state.loading && pageCount > 1 && (
        <div className="mt-3 flex items-center justify-end gap-2 text-[0.72rem] font-bold text-[#9aa9c3]">
          <button
            type="button"
            disabled={page === 0}
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            className="h-7 rounded-[0.4rem] border border-[#253552] bg-[#07111f] px-2.5 transition hover:border-[#3a8bff] hover:text-white disabled:opacity-40"
          >
            上一页
          </button>
          <span className="tabular-nums">{page + 1} / {pageCount}</span>
          <button
            type="button"
            disabled={page >= pageCount - 1}
            onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
            className="h-7 rounded-[0.4rem] border border-[#253552] bg-[#07111f] px-2.5 transition hover:border-[#3a8bff] hover:text-white disabled:opacity-40"
          >
            下一页
          </button>
        </div>
      )}

      {selected && <OrganizeItemDetailModal item={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}

const ORGANIZE_DETAIL_FIELDS: { key: keyof OrganizerRunItem; label: string }[] = [
  { key: 'id', label: '记录 ID' },
  { key: 'run_id', label: '整理批次' },
  { key: 'file_id', label: '文件 ID' },
  { key: 'file_name', label: '原始文件名' },
  { key: 'new_name', label: '重命名为' },
  { key: 'target_path', label: '目标路径' },
  { key: 'target_cid', label: '目标目录 CID' },
  { key: 'reason', label: '处理原因' },
  { key: 'created_at', label: '创建时间' },
  { key: 'updated_at', label: '更新时间' },
]

function formatDetailValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '-'
  return String(value)
}

function organizeItemMetadata(item: OrganizerRunItem): Record<string, unknown> | null {
  if (!item.metadata_json) return null
  try {
    const parsed = JSON.parse(item.metadata_json) as unknown
    return parsed && typeof parsed === 'object' ? (parsed as Record<string, unknown>) : null
  } catch {
    return null
  }
}

function OrganizeItemDetailModal({ item, onClose }: { item: OrganizerRunItem; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const style = organizeItemStatusStyle(item.status)
  const metadata = organizeItemMetadata(item)

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="max-h-[88vh] w-full max-w-[56rem] overflow-y-auto rounded-[0.75rem] border border-[#253552] bg-[#0a1424] p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="mb-1.5 flex items-center gap-2">
              <span className={`inline-block rounded-[0.4rem] border px-2 py-0.5 text-[0.66rem] font-black ${style.cls}`}>{style.label}</span>
              <span className="text-[0.7rem] font-semibold text-[#91a0bb]">{item.status}</span>
            </div>
            <h3 className="m-0 break-all text-[1.02rem] font-black text-white">{organizeItemTitle(item)}</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="h-8 shrink-0 rounded-[0.45rem] border border-[#253552] bg-[#07111f] px-3 text-[0.72rem] font-black text-[#9aa9c3] transition hover:border-[#3a8bff] hover:text-white"
          >
            关闭
          </button>
        </div>

        <dl className="grid grid-cols-1 gap-x-5 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
          {ORGANIZE_DETAIL_FIELDS.map((field) => (
            <div key={field.key} className="min-w-0">
              <dt className="text-[0.66rem] font-black uppercase tracking-wide text-[#667793]">{field.label}</dt>
              <dd className="m-0 break-all text-[0.78rem] font-semibold text-[#dbe7ff]">{formatDetailValue(item[field.key])}</dd>
            </div>
          ))}
        </dl>

        {item.error && (
          <div className="mt-3">
            <div className="mb-1 text-[0.66rem] font-black uppercase tracking-wide text-[#ff9fb4]">错误信息</div>
            <pre className="m-0 max-h-40 overflow-auto whitespace-pre-wrap break-all rounded-[0.5rem] border border-[#553044] bg-[#1a0e19] px-3 py-2 text-[0.72rem] text-[#ff9fb4]">{item.error}</pre>
          </div>
        )}

        {metadata && (
          <div className="mt-3">
            <div className="mb-1 text-[0.66rem] font-black uppercase tracking-wide text-[#667793]">TMDB 元数据</div>
            <pre className="m-0 max-h-48 overflow-auto whitespace-pre-wrap break-all rounded-[0.5rem] border border-[#253552] bg-[#07111f] px-3 py-2 text-[0.72rem] text-[#9aa9c3]">{JSON.stringify(metadata, null, 2)}</pre>
          </div>
        )}
      </div>
    </div>
  )
}
