import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { getOrganizerSettings, updateOrganizerSettings } from '../api'
import type { OrganizerSettingsResponse } from '../types'
import { useNetdisk } from './useNetdisk'

// 主题对齐 App 深色 shell
const cardClass = 'rounded-[0.625rem] border border-[#1d2a46] bg-[#0a1424] p-5 shadow-[0_0.75rem_2rem_rgba(0,0,0,0.28)]'
const fieldClass = 'w-full rounded-[0.5rem] border border-[#253552] bg-[#07111f] px-3 py-2.5 text-[0.85rem] text-[#dbe7ff] outline-none transition-[border-color,box-shadow] duration-150 placeholder:text-[#5b6a87] focus:border-[#3a8bff] focus:shadow-[0_0_0_0.1875rem_rgba(58,139,255,0.22)] disabled:cursor-not-allowed disabled:opacity-60'
const primaryButtonClass = 'rounded-[0.5rem] bg-[linear-gradient(135deg,#3a8bff,#7c5cff)] px-4 py-2.5 text-[0.82rem] font-black text-white transition duration-150 hover:brightness-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7c5cff]/40 disabled:cursor-not-allowed disabled:opacity-60 disabled:brightness-100'
const quietButtonClass = 'rounded-[0.5rem] border border-[#253552] bg-[#0d1b2e] px-4 py-2.5 text-[0.82rem] font-bold text-[#9aa9c3] transition duration-150 hover:bg-[#122743] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#3a8bff]/35 disabled:cursor-not-allowed disabled:opacity-60'
const tabButtonClass = 'rounded-[0.5rem] px-4 py-2 text-[0.82rem] font-black transition duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#3a8bff]/35'
const tabActiveClass = 'bg-[#122743] text-white shadow-[inset_0_-0.125rem_0_#3a8bff]'
const tabInactiveClass = 'text-[#9aa9c3] hover:bg-[#0d1b2e] hover:text-white'
const labelClass = 'grid gap-1.5 text-[0.82rem] font-bold text-[#9aa9c3]'
const helperClass = 'text-[0.72rem] font-semibold text-[#64718b]'

type TabId = 'basic' | 'advanced' | 'test' | 'status'

const tabs: { id: TabId; label: string }[] = [
  { id: 'basic', label: '基础设置' },
  { id: 'advanced', label: '高级设置' },
  { id: 'test', label: '连接测试' },
  { id: 'status', label: '状态' },
]

export function NetdiskSettings() {
  const { error, loading, refresh, saveSettings, saveState, settings, status, testCid, testResult, testState } = useNetdisk()

  const [activeTab, setActiveTab] = useState<TabId>('basic')

  // 基础：转存中转目录 + Cookie
  const [cidInput, setCidInput] = useState('')
  const [cookiesInput, setCookiesInput] = useState('')

  // 高级
  const [cacheHomeInput, setCacheHomeInput] = useState('')
  const [ensureCookiesInput, setEnsureCookiesInput] = useState(false)

  // 连接测试
  const [testCidInput, setTestCidInput] = useState('')

  // 资源库根目录（organizer 设置，独立接口）
  const [organizer, setOrganizer] = useState<OrganizerSettingsResponse | null>(null)
  const [rootCidInput, setRootCidInput] = useState('')
  const [organizerSaving, setOrganizerSaving] = useState(false)
  const [organizerError, setOrganizerError] = useState<string | null>(null)
  const [savedNote, setSavedNote] = useState<string | null>(null)

  useEffect(() => {
    if (settings?.transfer_cid !== null && settings?.transfer_cid !== undefined) {
      setCidInput((prev) => (prev ? prev : settings.transfer_cid))
      setEnsureCookiesInput(settings.ensure_cookies)
    }
  }, [settings?.transfer_cid, settings?.ensure_cookies])

  const loadOrganizer = useCallback(async () => {
    setOrganizerError(null)
    try {
      const next = await getOrganizerSettings()
      setOrganizer(next)
      setRootCidInput(next.configured ? next.media_library_root_cid : '')
    } catch (caught) {
      setOrganizerError(caught instanceof Error ? caught.message : '加载资源库设置失败')
    }
  }, [])

  useEffect(() => {
    void loadOrganizer()
  }, [loadOrganizer])

  async function handleBasicSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSavedNote(null)
    setOrganizerError(null)

    const trimmedCid = cidInput.trim()
    const trimmedCookies = cookiesInput.trim()
    const trimmedRootCid = rootCidInput.trim()

    if (trimmedRootCid && !/^[1-9]\d*$/.test(trimmedRootCid)) {
      setOrganizerError('资源库根目录 CID 必须为正整数')
      return
    }

    try {
      await saveSettings({
        transfer_cid: trimmedCid || null,
        cookies: trimmedCookies || null,
      })
      setCookiesInput('')

      if (trimmedRootCid && trimmedRootCid !== (organizer?.media_library_root_cid ?? '')) {
        setOrganizerSaving(true)
        const next = await updateOrganizerSettings({ media_library_root_cid: trimmedRootCid })
        setOrganizer(next)
        setRootCidInput(next.configured ? next.media_library_root_cid : '')
      }
      setSavedNote(`已保存 · ${new Date().toLocaleTimeString()}`)
    } catch (caught) {
      setOrganizerError(caught instanceof Error ? caught.message : '保存失败')
    } finally {
      setOrganizerSaving(false)
    }
  }

  async function handleAdvancedSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSavedNote(null)
    try {
      await saveSettings({
        ensure_cookies: ensureCookiesInput,
        cache_home: cacheHomeInput.trim() || null,
      })
      setSavedNote(`已保存 · ${new Date().toLocaleTimeString()}`)
    } catch {
      // hook 持有错误状态
    }
  }

  async function handleTestSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmed = testCidInput.trim()
    try {
      await testCid(trimmed ? Number(trimmed) : undefined)
    } catch {
      // hook 把后端失败转成可见的 testResult
    }
  }

  const configured = settings?.configured ?? false

  return (
    <section className="grid gap-4" aria-labelledby="netdisk-settings-title">
      {/* Tab 栏 + 全局状态 */}
      <div className="flex items-center justify-between gap-3 max-[34rem]:flex-col max-[34rem]:items-stretch">
        <div className="flex flex-wrap gap-2">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={`${tabButtonClass} ${activeTab === tab.id ? tabActiveClass : tabInactiveClass}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <button className={quietButtonClass} type="button" onClick={() => void refresh()} disabled={loading}>
          {loading ? '刷新中...' : '刷新'}
        </button>
      </div>

      {error && <StateNote tone="error" label={error} />}
      {saveState.error && <StateNote tone="error" label={saveState.error} />}
      {organizerError && <StateNote tone="error" label={organizerError} />}
      {savedNote && !error && !saveState.error && !organizerError && <StateNote tone="success" label={savedNote} />}

      {/* 基础设置：转存中转目录 + 资源库根目录 + Cookie */}
      {activeTab === 'basic' && (
        <article className={cardClass}>
          <h2 id="netdisk-settings-title" className="mb-1 mt-0 text-[1.1rem] font-black text-white">基础设置</h2>
          <p className="m-0 mb-4 text-[0.78rem] text-[#91a0bb]">配置 115 转存中转目录、资源库根目录与登录 Cookie。</p>

          <form className="grid gap-4" onSubmit={handleBasicSubmit}>
            <label className={labelClass}>
              <span>转存中转目录 CID（P115_TRANSFER_CID）</span>
              <input
                className={fieldClass}
                name="netdisk-transfer-cid"
                inputMode="numeric"
                value={cidInput}
                onChange={(event) => setCidInput(event.target.value)}
                placeholder="资源转存后暂存的目录 CID"
              />
              <span className={helperClass}>采集到的分享会先转存到此目录，等待整理。</span>
            </label>

            <label className={labelClass}>
              <span>资源库根目录 CID（MEDIA_LIBRARY_ROOT_CID）</span>
              <input
                className={fieldClass}
                name="media-library-root-cid"
                inputMode="numeric"
                value={rootCidInput}
                onChange={(event) => setRootCidInput(event.target.value)}
                placeholder="例如：3438324114378065328"
              />
              <span className={helperClass}>整理后的电影、剧集会按 TMDB 元数据分类落入此目录下。</span>
            </label>

            <label className={labelClass}>
              <span>115 Cookie（P115_COOKIES）</span>
              <input
                className={fieldClass}
                name="netdisk-cookies"
                type="password"
                value={cookiesInput}
                onChange={(event) => setCookiesInput(event.target.value)}
                placeholder="留空则保持现有 Cookie；保存后不再回显"
              />
              <span className={helperClass}>从浏览器登录 115 后复制的 Cookie 字符串；仅写入，不会展示。</span>
            </label>

            <div className="pt-1">
              <button className={primaryButtonClass} type="submit" disabled={saveState.loading || organizerSaving}>
                {saveState.loading || organizerSaving ? '保存中...' : '保存基础设置'}
              </button>
            </div>
          </form>
        </article>
      )}

      {/* 高级设置：ensure_cookies + cache_home */}
      {activeTab === 'advanced' && (
        <article className={cardClass}>
          <h2 className="mb-1 mt-0 text-[1.1rem] font-black text-white">高级设置</h2>
          <p className="m-0 mb-4 text-[0.78rem] text-[#91a0bb]">Cookie 自动校验与 p115client 缓存目录，通常无需改动。</p>

          <form className="grid gap-4" onSubmit={handleAdvancedSubmit}>
            <label className="flex items-center justify-between gap-3 rounded-[0.5rem] border border-[#253552] bg-[#07111f] px-3 py-2.5 text-[0.85rem] font-bold text-[#dbe7ff]">
              <span>
                启用 Cookie 校验/刷新（P115_ENSURE_COOKIES）
                <span className="mt-0.5 block text-[0.72rem] font-semibold text-[#64718b]">每次操作前透传给 P115Client 做有效性校验。</span>
              </span>
              <input
                className="h-4 w-4 shrink-0 accent-[#3a8bff]"
                type="checkbox"
                checked={ensureCookiesInput}
                onChange={(event) => setEnsureCookiesInput(event.target.checked)}
              />
            </label>

            <label className={labelClass}>
              <span>缓存目录（P115_CACHE_HOME）</span>
              <input
                className={fieldClass}
                name="netdisk-cache-home"
                value={cacheHomeInput}
                onChange={(event) => setCacheHomeInput(event.target.value)}
                placeholder="留空保持现有；默认 .p115client.cache.d"
              />
              <span className={helperClass}>p115client 的缓存目录；受限环境下可指向可写路径。</span>
            </label>

            <div className="pt-1">
              <button className={primaryButtonClass} type="submit" disabled={saveState.loading}>
                {saveState.loading ? '保存中...' : '保存高级设置'}
              </button>
            </div>
          </form>
        </article>
      )}

      {/* 连接测试 */}
      {activeTab === 'test' && (
        <article className={cardClass}>
          <h2 className="mb-1 mt-0 text-[1.1rem] font-black text-white">连接测试</h2>
          <p className="m-0 mb-4 text-[0.78rem] text-[#91a0bb]">用指定 CID 列目录，验证 Cookie 与网盘连接是否可用。</p>

          <form className="grid gap-4" onSubmit={handleTestSubmit}>
            <label className={labelClass}>
              <span>测试目录 CID</span>
              <input
                className={fieldClass}
                name="netdisk-test-cid"
                inputMode="numeric"
                value={testCidInput}
                onChange={(event) => setTestCidInput(event.target.value)}
                placeholder="留空使用默认转存中转目录"
              />
            </label>
            <div className="pt-1">
              <button className={primaryButtonClass} type="submit" data-testid="netdisk-test" disabled={testState.loading}>
                {testState.loading ? '测试中...' : '测试连接'}
              </button>
            </div>
          </form>

          {testResult && (
            <div className="mt-4 grid gap-2 rounded-[0.5rem] border border-[#253552] bg-[#07111f] p-4" aria-label="连接测试结果">
              <ResultRow label="连接结果" value={testResult.ok ? '成功' : '失败'} tone={testResult.ok ? 'success' : 'error'} />
              <ResultRow label="目录条目数" value={formatValue(testResult.item_count)} />
              <ResultRow label="错误信息" value={formatValue(testResult.error)} tone={testResult.error ? 'error' : 'neutral'} />
            </div>
          )}
        </article>
      )}

      {/* 状态 */}
      {activeTab === 'status' && (
        <article className={cardClass}>
          <h2 className="mb-1 mt-0 text-[1.1rem] font-black text-white">配置状态</h2>
          <p className="m-0 mb-4 text-[0.78rem] text-[#91a0bb]">当前网盘与资源库配置的只读概览。</p>

          <dl className="m-0 grid grid-cols-2 gap-3 max-[36rem]:grid-cols-1">
            <Metric label="是否已配置 Cookie" value={configured ? '是' : '否'} tone={configured ? 'success' : 'error'} />
            <Metric label="转存中转目录 CID" value={formatValue(settings?.transfer_cid)} />
            <Metric
              label="资源库根目录 CID"
              value={organizer?.configured ? organizer.media_library_root_cid : '未配置'}
              tone={organizer?.configured ? 'success' : 'error'}
            />
            <Metric label="Cookie 自动校验" value={formatBoolean(settings?.ensure_cookies)} />
            <Metric label="缓存目录已配置" value={formatBoolean(settings?.cache_home_configured)} />
            <Metric label="连接状态" value={formatStatus(status)} />
            <Metric label="状态错误" value={formatValue(status?.error)} tone={status?.error ? 'error' : 'neutral'} />
          </dl>
        </article>
      )}
    </section>
  )
}

function Metric({ label, tone = 'neutral', value }: { label: string; tone?: 'error' | 'neutral' | 'success'; value: string }) {
  const valueClass = tone === 'error' ? 'text-[#ff8095]' : tone === 'success' ? 'text-[#5fd3a0]' : 'text-white'
  return (
    <div className="min-w-0 rounded-[0.5rem] border border-[#253552] bg-[#07111f] p-3">
      <dt className="text-[0.68rem] font-bold uppercase tracking-[0.1em] text-[#667793]">{label}</dt>
      <dd className={`m-0 mt-1 break-words text-[0.92rem] font-black ${valueClass}`}>{value}</dd>
    </div>
  )
}

function ResultRow({ label, tone = 'neutral', value }: { label: string; tone?: 'error' | 'neutral' | 'success'; value: string }) {
  const toneClass = tone === 'error' ? 'text-[#ff8095]' : tone === 'success' ? 'text-[#5fd3a0]' : 'text-white'
  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <dt className="text-[0.72rem] font-bold uppercase tracking-[0.1em] text-[#667793]">{label}</dt>
      <dd className={`m-0 break-words text-right text-[0.85rem] font-black ${toneClass}`}>{value}</dd>
    </div>
  )
}

function StateNote({ label, tone = 'neutral' }: { label: string; tone?: 'error' | 'neutral' | 'success' }) {
  const toneClass =
    tone === 'error'
      ? 'border-[#5a2233] bg-[#1a0f16] text-[#ff8095]'
      : tone === 'success'
        ? 'border-[#1f3d2e] bg-[#0e2118] text-[#5fd3a0]'
        : 'border-[#1d2a46] bg-[#0a1424] text-[#91a0bb]'
  return <p className={`mb-0 break-words rounded-[0.5rem] border px-3 py-2.5 text-[0.82rem] ${toneClass}`}>{label}</p>
}

function formatBoolean(value: boolean | null | undefined): string {
  return value === undefined || value === null ? '未知' : value ? '是' : '否'
}

function formatValue(value: number | string | null | undefined): string {
  return value === undefined || value === null || value === '' ? '无' : String(value)
}

function formatStatus(value: unknown): string {
  if (value === undefined || value === null) return '未知'
  if (typeof value === 'string') return value
  if (typeof value === 'object' && 'status' in value && typeof value.status === 'string') return value.status
  if (typeof value === 'object' && 'ok' in value && typeof value.ok === 'boolean') return value.ok ? 'ok' : 'error'
  return 'available'
}
