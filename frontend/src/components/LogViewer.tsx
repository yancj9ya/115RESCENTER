import { useCallback, useEffect, useRef, useState } from 'react'
import { apiUrl, clearLogs, getRecentLogs } from '../api'
import type { LogEntry } from '../types'

const LEVEL_COLORS: Record<string, string> = {
  DEBUG: 'text-[#667793]',
  INFO: 'text-[#53d3ff]',
  WARNING: 'text-[#f5c542]',
  ERROR: 'text-[#ff7d9f]',
  CRITICAL: 'text-[#ff4d6d] font-black',
}

const LEVEL_BADGE: Record<string, string> = {
  DEBUG: 'border-[#253552] bg-[#07111f] text-[#667793]',
  INFO: 'border-[#1d4a6a] bg-[#0a2a40] text-[#53d3ff]',
  WARNING: 'border-[#5a4a1a] bg-[#2a2010] text-[#f5c542]',
  ERROR: 'border-[#5a2d3a] bg-[#3d1a26] text-[#ff7d9f]',
  CRITICAL: 'border-[#7d1a2a] bg-[#4d0a14] text-[#ff4d6d]',
}

const LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']

type Props = {
  useSSE?: boolean
  refreshInterval?: number
}

export default function LogViewer({ useSSE = true, refreshInterval = 5000 }: Props) {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [filter, setFilter] = useState('')
  const [levelFilter, setLevelFilter] = useState('')
  const [loading, setLoading] = useState(false)
  const [sseActive, setSseActive] = useState(false)
  const [clearing, setClearing] = useState(false)
  const esRef = useRef<EventSource | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const listRef = useRef<HTMLDivElement | null>(null)
  const pinnedRef = useRef(true)

  const fetchLogs = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getRecentLogs({ limit: 200, level: levelFilter || undefined })
      setLogs(data.logs)
    } catch {
      // silently ignore fetch errors
    } finally {
      setLoading(false)
    }
  }, [levelFilter])

  // SSE connection
  useEffect(() => {
    if (!useSSE) return
    const es = new EventSource(apiUrl('/logs/stream'))
    esRef.current = es
    es.onopen = () => setSseActive(true)
    es.onerror = () => {
      setSseActive(false)
      es.close()
    }
    es.onmessage = (event) => {
      try {
        const entry: LogEntry = JSON.parse(event.data as string)
        setLogs((prev) => {
          const next = [...prev, entry]
          return next.length > 500 ? next.slice(next.length - 500) : next
        })
      } catch {
        // ignore malformed events
      }
    }
    // Initial fetch to populate before SSE catches up
    void fetchLogs()
    return () => {
      es.close()
      esRef.current = null
      setSseActive(false)
    }
  }, [useSSE, fetchLogs])

  // Polling fallback when SSE is not used or unavailable
  useEffect(() => {
    if (useSSE && sseActive) return
    void fetchLogs()
    timerRef.current = setInterval(() => void fetchLogs(), refreshInterval)
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [useSSE, sseActive, fetchLogs, refreshInterval])

  // Re-fetch when level filter changes
  useEffect(() => {
    void fetchLogs()
  }, [levelFilter, fetchLogs])

  async function handleClear() {
    setClearing(true)
    try {
      await clearLogs()
      setLogs([])
    } finally {
      setClearing(false)
    }
  }

  const filtered = logs.filter((log) => {
    if (levelFilter && log.level !== levelFilter) return false
    if (filter && !log.message.toLowerCase().includes(filter.toLowerCase())) return false
    return true
  })

  // Track whether the user is pinned to the bottom of the list
  const handleScroll = useCallback(() => {
    const el = listRef.current
    if (!el) return
    pinnedRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40
  }, [])

  // Auto-scroll to the latest log when pinned to bottom
  useEffect(() => {
    const el = listRef.current
    if (el && pinnedRef.current) {
      el.scrollTop = el.scrollHeight
    }
  }, [filtered.length])

  return (
    <div className="flex flex-col gap-3 p-3">
      {/* toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="search"
          placeholder="搜索日志消息..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="h-9 min-w-[12rem] flex-1 rounded-[0.5rem] border border-[#253552] bg-[#07111f] px-3 text-[0.8rem] font-semibold text-[#dbe7ff] placeholder:text-[#5f6e86] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7c5cff]"
        />
        <select
          value={levelFilter}
          onChange={(e) => setLevelFilter(e.target.value)}
          className="h-9 rounded-[0.5rem] border border-[#253552] bg-[#07111f] px-2 text-[0.8rem] font-semibold text-[#dbe7ff] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7c5cff]"
        >
          <option value="">所有级别</option>
          {LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
        </select>
        <button
          type="button"
          onClick={() => void fetchLogs()}
          disabled={loading}
          className="h-9 rounded-[0.5rem] border border-[#253552] bg-[#0b1829] px-3 text-[0.78rem] font-bold text-[#c5d3ed] transition hover:border-[#3a8bff] disabled:opacity-60"
        >
          {loading ? '刷新中...' : '刷新'}
        </button>
        <button
          type="button"
          onClick={() => void handleClear()}
          disabled={clearing}
          className="h-9 rounded-[0.5rem] border border-[#553044] bg-[#1a0e19] px-3 text-[0.78rem] font-bold text-[#ff9fb4] transition hover:border-[#9b4562] disabled:opacity-60"
        >
          清空
        </button>
        <span className="ml-auto flex items-center gap-1.5 text-[0.72rem] font-semibold text-[#64718b]">
          {sseActive
            ? <><span className="h-2 w-2 rounded-full bg-[#7ee7bf] shadow-[0_0_0.5rem_rgba(126,231,191,0.8)]" />实时</>
            : <><span className="h-2 w-2 rounded-full bg-[#667793]" />轮询</>
          }
        </span>
      </div>

      {/* log list */}
      <div
        ref={listRef}
        onScroll={handleScroll}
        className="h-[calc(100vh-20rem)] min-h-[20rem] overflow-auto rounded-[0.5rem] border border-[#1d2a46] bg-[#050812]"
      >
        {filtered.length === 0 ? (
          <div className="py-10 text-center text-[0.8rem] text-[#64718b]">暂无日志记录</div>
        ) : (
          <div className="divide-y divide-[#0d1b2e]">
            {filtered.map((log, i) => (
              <div key={i} className="flex items-start gap-2.5 px-3 py-2 hover:bg-[#07111f]">
                <span className={`mt-0.5 shrink-0 rounded border px-1.5 py-0.5 text-[0.62rem] font-black ${LEVEL_BADGE[log.level] ?? LEVEL_BADGE.DEBUG}`}>
                  {log.level}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                    <span className="text-[0.68rem] text-[#64718b]">
                      {new Date(log.timestamp).toLocaleTimeString('zh-CN')}
                    </span>
                    <span className="text-[0.68rem] text-[#4a5a72]">
                      {log.module}.{log.function}:{log.line}
                    </span>
                  </div>
                  <div className={`mt-0.5 break-words font-mono text-[0.76rem] ${LEVEL_COLORS[log.level] ?? 'text-[#dbe7ff]'}`}>
                    {log.message}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="text-[0.72rem] text-[#64718b]">
        显示 {filtered.length} / {logs.length} 条
        {!sseActive && <span className="ml-3">· 每 {refreshInterval / 1000}s 自动刷新</span>}
      </div>
    </div>
  )
}
