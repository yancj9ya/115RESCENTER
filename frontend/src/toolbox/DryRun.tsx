import { useState } from 'react'
import { postDryRunBackend } from '../api'
import type { DryRunBackendSummary } from '../types'

const textareaClass =
  'w-full rounded-[0.5rem] border border-[#253552] bg-[#07111f] px-3 py-2 font-mono text-[0.78rem] text-[#dbe7ff] placeholder:text-[#5f6e86] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7c5cff] resize-y'
const fieldClass =
  'h-9 w-full rounded-[0.5rem] border border-[#253552] bg-[#07111f] px-3 text-[0.82rem] font-semibold text-[#dbe7ff] placeholder:text-[#5f6e86] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7c5cff]'
const btnClass =
  'h-9 rounded-[0.5rem] bg-[linear-gradient(135deg,#3a8bff,#7c5cff)] px-4 text-[0.8rem] font-black text-white transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60'
const labelClass = 'grid gap-1.5 text-[0.78rem] font-bold text-[#9aa9c3]'

const PLACEHOLDER = `115分享链接示例：
https://115.com/s/sw3abc1?password=xy12
https://115.com/s/sw3abc2?password=ab34`

export default function DryRun() {
  const [messageText, setMessageText] = useState('')
  const [keyword, setKeyword] = useState('Movie')
  const [result, setResult] = useState<DryRunBackendSummary | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleRun(e: React.FormEvent) {
    e.preventDefault()
    if (!messageText.trim()) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const data = await postDryRunBackend({
        messages: [
          {
            source_type: 'dry_run',
            source_id: 'dry_run',
            message_id: String(Date.now()),
            message_text: messageText.trim(),
          },
        ],
        include_keyword: keyword.trim() || 'Movie',
      })
      setResult(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : '干运行失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="grid gap-4">
      <div className="rounded-[0.5rem] border border-[#253552] bg-[#0a1424] px-3 py-2 text-[0.78rem] leading-5 text-[#c5d3ed]">
        <span className="font-black text-white">干运行测试</span>
        <span className="ml-2">粘贴包含 115 分享链接的消息文本，模拟完整的收集→匹配→转存→整理流水线（不产生真实副作用）。</span>
      </div>

      <form className="grid gap-3" onSubmit={handleRun}>
        <label className={labelClass}>
          <span>消息文本（包含 115 分享链接）</span>
          <textarea
            className={textareaClass}
            rows={5}
            value={messageText}
            onChange={(e) => setMessageText(e.target.value)}
            placeholder={PLACEHOLDER}
          />
        </label>
        <label className={labelClass}>
          <span>匹配关键词（include_keyword）</span>
          <input
            className={fieldClass}
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="Movie"
          />
        </label>
        <div>
          <button type="submit" className={btnClass} disabled={loading || !messageText.trim()}>
            {loading ? '运行中...' : '执行干运行'}
          </button>
        </div>
      </form>

      {error && (
        <p className="rounded-[0.5rem] border border-[#7d3b58] bg-[#160d18] px-3 py-2 text-[0.78rem] text-[#ff9fb4]">
          {error}
        </p>
      )}

      {result && (
        <div className="rounded-[0.5rem] border border-[#253552] bg-[#0a1424] p-3">
          <div className="mb-2 text-[0.78rem] font-black text-white">运行结果</div>
          <div className="grid gap-1.5 sm:grid-cols-3">
            {[
              ['收集入队', result.collect_enqueued],
              ['收集处理', result.collect_processed],
              ['转存处理', result.transfer_processed],
              ['整理扫描', result.organize_scanned],
              ['整理计划', result.organize_planned],
              ['整理移动', result.organize_moved],
              ['通知发送', result.notification_count],
            ].map(([label, value]) => (
              <div key={label as string} className="rounded-[0.45rem] border border-[#1d2a46] bg-[#07111f] px-2.5 py-2">
                <div className="text-[0.62rem] font-black uppercase tracking-[0.1em] text-[#667793]">{label}</div>
                <div className="mt-0.5 text-[0.9rem] font-black text-[#7ee7bf]">{value}</div>
              </div>
            ))}
          </div>
          {result.errors.length > 0 && (
            <div className="mt-2 rounded-[0.45rem] border border-[#553044] bg-[#1a0e19] p-2">
              <div className="mb-1 text-[0.72rem] font-black text-[#ff9fb4]">错误 ({result.errors.length})</div>
              {result.errors.map((err, i) => (
                <div key={i} className="text-[0.72rem] text-[#ff9fb4]">{err}</div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
