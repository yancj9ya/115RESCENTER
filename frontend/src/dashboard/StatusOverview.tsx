import { useEffect, useRef, useState } from 'react'
import { getConnectivity, getRuntimeStatus } from '../api'
import type {
  ConnectivityItem,
  RuntimeComponentStatus,
  RuntimeStatusResponse,
  RuntimeTriggerEvent,
} from '../types'
import { triggerRuntime } from '../api'

type LoadState = { loading: boolean; error: string | null }
type TriggerState = 'idle' | 'loading' | 'success' | 'error'

type CoreConfig = {
  key: string
  title: string
  icon: string
  trigger: RuntimeTriggerEvent
  triggerLabel: string
  componentNames: string[]
}

const CORES: CoreConfig[] = [
  {
    key: 'collector',
    title: '收集核心',
    icon: '🛰️',
    trigger: 'manual_collect',
    triggerLabel: '收集匹配',
    componentNames: ['telegram_collector', 'subscription_processor'],
  },
  {
    key: 'transfer',
    title: '转存核心',
    icon: '🔁',
    trigger: 'manual_transfer',
    triggerLabel: '转存文件',
    componentNames: ['transfer_processor'],
  },
  {
    key: 'organizer',
    title: '整理核心',
    icon: '🗂️',
    trigger: 'manual_organize',
    triggerLabel: '整理文件',
    componentNames: ['organizer'],
  },
]

const STATUS_STYLE: Record<string, { label: string; dot: string; text: string }> = {
  running: { label: '运行中', dot: 'bg-[#53d3ff] shadow-[0_0_0.5rem_rgba(83,211,255,0.8)]', text: 'text-[#53d3ff]' },
  ready: { label: '就绪', dot: 'bg-[#7ee7bf]', text: 'text-[#7ee7bf]' },
  success: { label: '成功', dot: 'bg-[#7dffaa]', text: 'text-[#7dffaa]' },
  idle: { label: '空闲', dot: 'bg-[#667793]', text: 'text-[#91a0bb]' },
  failed: { label: '失败', dot: 'bg-[#ff7d9f]', text: 'text-[#ff7d9f]' },
  blocked: { label: '阻塞', dot: 'bg-[#f5c542]', text: 'text-[#f5c542]' },
  degraded: { label: '降级', dot: 'bg-[#f5c542]', text: 'text-[#f5c542]' },
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function styleFor(status: string) {
  return STATUS_STYLE[status] ?? STATUS_STYLE.idle
}

function aggregateStatus(components: RuntimeComponentStatus[]): string {
  if (components.length === 0) return 'idle'
  if (components.some((c) => c.status === 'failed')) return 'failed'
  if (components.some((c) => c.status === 'blocked')) return 'blocked'
  if (components.some((c) => c.status === 'degraded')) return 'degraded'
  if (components.some((c) => c.status === 'running')) return 'running'
  if (components.every((c) => c.status === 'ready' || c.status === 'success')) return 'ready'
  return components[0].status
}

export default function StatusOverview() {
  const [status, setStatus] = useState<RuntimeStatusResponse | null>(null)
  const [state, setState] = useState<LoadState>({ loading: true, error: null })
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    let mounted = true
    const load = () => {
      getRuntimeStatus()
        .then((response) => {
          if (!mounted) return
          setStatus(response)
          setState({ loading: false, error: null })
        })
        .catch((caught) => {
          if (mounted) setState({ loading: false, error: errorMessage(caught) })
        })
    }
    load()
    timerRef.current = setInterval(load, 5000)
    return () => {
      mounted = false
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [])

  const componentsByName = new Map((status?.components ?? []).map((c) => [c.name, c]))
  const effective = status?.effective_state ?? 'stopped'
  const effectiveStyle =
    effective === 'running' ? STATUS_STYLE.running : effective === 'degraded' ? STATUS_STYLE.degraded : STATUS_STYLE.idle

  return (
    <section className="grid gap-3" aria-label="状态总览">
      <div className="rounded-[0.75rem] border border-[#253552] bg-[linear-gradient(165deg,#0d1b2e,#0a1424)] p-4 shadow-[0_1.25rem_3rem_rgba(0,0,0,0.35)]">
        <div className="flex items-center justify-between gap-2 border-b border-[#1d2a46] pb-3">
          <div>
            <p className="m-0 text-[0.64rem] font-black uppercase tracking-[0.14em] text-[#53d3ff]">运行时</p>
            <h3 className="m-0 mt-0.5 text-[0.98rem] font-black text-white">三大核心状态</h3>
          </div>
          <span className={`flex items-center gap-1.5 rounded-full border border-[#253552] bg-[#07111f] px-2.5 py-1 text-[0.66rem] font-black ${effectiveStyle.text}`}>
            <span className={`h-2 w-2 rounded-full ${effectiveStyle.dot}`} />
            {state.loading ? '加载中' : effectiveStyle.label}
          </span>
        </div>

        {state.error && (
          <p className="m-0 mt-3 rounded-[0.5rem] border border-[#553044] bg-[#1a0e19] px-2.5 py-2 text-[0.72rem] font-semibold text-[#ff9fb4]">
            {state.error}
          </p>
        )}

        <div className="mt-3 grid gap-2.5 lg:grid-cols-3">
          {CORES.map((core) => {
            const comps = core.componentNames
              .map((name) => componentsByName.get(name))
              .filter((c): c is RuntimeComponentStatus => Boolean(c))
            const agg = styleFor(aggregateStatus(comps))
            return (
              <CoreCard key={core.key} core={core} status={agg} components={comps} loading={state.loading} />
            )
          })}
        </div>
      </div>

      <ConnectivitySection />
    </section>
  )
}

const KIND_LABEL: Record<string, string> = {
  netdisk: '网盘',
  tmdb: 'TMDB',
  telegram: 'Telegram',
  bark: 'Bark',
}

function latencyTone(ms: number): string {
  if (ms < 800) return 'text-[#7ee7bf]'
  if (ms < 2500) return 'text-[#f5c542]'
  return 'text-[#ff9f6e]'
}

function formatCheckedAt(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString()
}

const CONNECTIVITY_CACHE_KEY = 'statusOverview.connectivity.v1'

type ConnectivityCache = {
  items: ConnectivityItem[]
  checkedAt: string
}

function readConnectivityCache(): ConnectivityCache | null {
  try {
    const raw = localStorage.getItem(CONNECTIVITY_CACHE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as ConnectivityCache
    if (parsed && Array.isArray(parsed.items)) return parsed
    return null
  } catch {
    return null
  }
}

function ConnectivitySection() {
  const cached = readConnectivityCache()
  const [items, setItems] = useState<ConnectivityItem[] | null>(cached?.items ?? null)
  const [checkedAt, setCheckedAt] = useState<string | null>(cached?.checkedAt ?? null)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const refresh = () => {
    setRefreshing(true)
    setError(null)
    getConnectivity()
      .then((response) => {
        setItems(response.items)
        setCheckedAt(response.checked_at)
        try {
          localStorage.setItem(
            CONNECTIVITY_CACHE_KEY,
            JSON.stringify({ items: response.items, checkedAt: response.checked_at }),
          )
        } catch {
          // localStorage 不可用时忽略缓存写入
        }
      })
      .catch((caught) => setError(errorMessage(caught)))
      .finally(() => setRefreshing(false))
  }

  return (
    <div className="rounded-[0.75rem] border border-[#253552] bg-[linear-gradient(165deg,#0d1b2e,#0a1424)] p-4 shadow-[0_1.25rem_3rem_rgba(0,0,0,0.35)]">
      <div className="flex items-center justify-between gap-2 border-b border-[#1d2a46] pb-3">
        <div>
          <p className="m-0 text-[0.64rem] font-black uppercase tracking-[0.14em] text-[#53d3ff]">外部连接</p>
          <h3 className="m-0 mt-0.5 text-[0.98rem] font-black text-white">连通性与延迟</h3>
          <p className="m-0 mt-0.5 text-[0.62rem] font-semibold text-[#667793]">
            {checkedAt ? `上次检测：${formatCheckedAt(checkedAt)}` : '尚未检测，点击刷新开始'}
          </p>
        </div>
        <button
          type="button"
          onClick={refresh}
          disabled={refreshing}
          className="rounded-full border border-[#253552] bg-[#07111f] px-2.5 py-1 text-[0.66rem] font-black text-[#9aa9c3] transition hover:border-[#3a8bff] hover:text-white disabled:opacity-55"
        >
          {refreshing ? '检测中...' : '刷新'}
        </button>
      </div>

      {error && (
        <p className="m-0 mt-3 rounded-[0.5rem] border border-[#553044] bg-[#1a0e19] px-2.5 py-2 text-[0.72rem] font-semibold text-[#ff9fb4]">
          {error}
        </p>
      )}

      {items && items.length > 0 ? (
        <div className="mt-3 grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {items.map((item) => (
            <ConnectivityCard key={`${item.kind}-${item.name}`} item={item} />
          ))}
        </div>
      ) : items ? (
        <p className="m-0 mt-3 text-[0.72rem] text-[#91a0bb]">没有可检测的连接。</p>
      ) : (
        <p className="m-0 mt-3 text-[0.72rem] text-[#91a0bb]">点击「刷新」检测外部连接状态。</p>
      )}
    </div>
  )
}

function ConnectivityCard({ item }: { item: ConnectivityItem }) {
  const dot = !item.configured
    ? 'bg-[#667793]'
    : item.ok
      ? 'bg-[#7ee7bf]'
      : 'bg-[#ff7d9f] shadow-[0_0_0.4rem_rgba(255,125,159,0.7)]'
  const statusLabel = !item.configured ? '未配置' : item.ok ? '正常' : '异常'
  const statusText = !item.configured ? 'text-[#91a0bb]' : item.ok ? 'text-[#7ee7bf]' : 'text-[#ff7d9f]'
  const detail = item.error ?? item.detail

  return (
    <div className="flex h-full flex-col rounded-[0.625rem] border border-[#1d2a46] bg-[#07111f] p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-1.5 text-[0.8rem] font-black text-[#dbe7ff]">
          <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${dot}`} />
          <span className="truncate">{item.name}</span>
        </span>
        <span className="shrink-0 rounded-full border border-[#253552] bg-[#0d1b2e] px-2 py-0.5 text-[0.6rem] font-black uppercase tracking-[0.08em] text-[#667793]">
          {KIND_LABEL[item.kind] ?? item.kind}
        </span>
      </div>

      <div className="mt-2 flex items-center justify-between gap-2">
        <span className={`text-[0.7rem] font-black ${statusText}`}>{statusLabel}</span>
        {item.latency_ms !== null && (
          <span className={`text-[0.72rem] font-black tabular-nums ${item.ok ? latencyTone(item.latency_ms) : 'text-[#7e8da8]'}`}>
            {item.latency_ms} ms
          </span>
        )}
      </div>

      {detail && (
        <div
          className={`mt-1.5 truncate text-[0.64rem] ${item.error ? 'text-[#ff9fb4]' : 'text-[#7e8da8]'}`}
          title={detail}
        >
          {detail}
        </div>
      )}
    </div>
  )
}

function CoreCard({
  core,
  status,
  components,
  loading,
}: {
  core: CoreConfig
  status: { label: string; dot: string; text: string }
  components: RuntimeComponentStatus[]
  loading: boolean
}) {
  const [triggerState, setTriggerState] = useState<TriggerState>('idle')
  const [message, setMessage] = useState('')

  const fire = async () => {
    setTriggerState('loading')
    setMessage('')
    try {
      const result = await triggerRuntime(core.trigger)
      setTriggerState('success')
      setMessage(`已触发 #${result.trigger_id}`)
      setTimeout(() => setTriggerState('idle'), 3000)
    } catch (error) {
      setTriggerState('error')
      setMessage(error instanceof Error ? error.message : '触发失败')
      setTimeout(() => setTriggerState('idle'), 5000)
    }
  }

  const lastError = components.find((c) => c.last_error)?.last_error
  const isLoading = triggerState === 'loading'
  const isSuccess = triggerState === 'success'
  const isError = triggerState === 'error'

  return (
    <div className="flex h-full flex-col rounded-[0.625rem] border border-[#1d2a46] bg-[#07111f] p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-[0.8rem] font-black text-[#dbe7ff]">
          <span aria-hidden="true">{core.icon}</span>
          {core.title}
        </span>
        <span className={`flex items-center gap-1.5 text-[0.68rem] font-black ${status.text}`}>
          <span className={`h-1.5 w-1.5 rounded-full ${status.dot}`} />
          {loading ? '...' : status.label}
        </span>
      </div>

      <div className="flex-1">
        {!loading && components.length > 0 && (
          <div className="mt-2 grid gap-0.5">
            {components.map((c) => (
              <div key={c.name} className="flex items-center justify-between gap-2 text-[0.66rem] text-[#7e8da8]">
                <span className="truncate">{c.name}</span>
                <span className={styleFor(c.status).text}>{styleFor(c.status).label}</span>
              </div>
            ))}
          </div>
        )}

        {lastError && (
          <div className="mt-1.5 truncate rounded-[0.4rem] bg-[#1a0e19] px-2 py-1 text-[0.64rem] text-[#ff9fb4]" title={lastError}>
            {lastError}
          </div>
        )}
      </div>

      <button
        type="button"
        onClick={fire}
        disabled={isLoading}
        className={`mt-2.5 w-full rounded-[0.45rem] px-3 py-1.5 text-[0.7rem] font-black transition ${
          isLoading
            ? 'cursor-not-allowed border border-[#253552] bg-[#0a1424] text-[#667793]'
            : isSuccess
              ? 'border border-[#2d5a3a] bg-[#1a3d26] text-[#7dffaa]'
              : isError
                ? 'border border-[#5a2d3a] bg-[#3d1a26] text-[#ff7d9f]'
                : 'border border-[#3a8bff] bg-[#122743] text-white hover:bg-[#1a3a5f]'
        }`}
      >
        {isLoading ? '处理中...' : isSuccess ? '✓ 已触发' : isError ? '✗ 失败' : `手动${core.triggerLabel}`}
      </button>
      {message && (
        <div className={`mt-1.5 truncate text-[0.64rem] ${isError ? 'text-[#ff9fb4]' : 'text-[#7dffaa]'}`} title={message}>
          {message}
        </div>
      )}
    </div>
  )
}
