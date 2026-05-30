import { useEffect, useState } from 'react'
import {
  getNotificationProviders,
  getNotificationSettings,
  testNotificationProvider,
  testNotificationWebhook,
  updateNotificationProviders,
  updateNotificationSettings,
} from '../api'
import type {
  BarkProviderResponse,
  NotificationProvidersResponse,
  NotificationSettingsResponse,
  TelegramProviderResponse,
} from '../types'

const cardClass = 'rounded-[0.625rem] border border-[#1d2a46] bg-[#0a1424] shadow-[0_0.75rem_2rem_rgba(0,0,0,0.28)]'
const fieldClass =
  'h-9 w-full rounded-[0.5rem] border border-[#253552] bg-[#07111f] px-3 text-[0.82rem] font-semibold text-[#dbe7ff] placeholder:text-[#5f6e86] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7c5cff]'
const labelClass = 'grid gap-1.5 text-[0.78rem] font-bold text-[#9aa9c3]'
const btnClass =
  'h-9 rounded-[0.5rem] bg-[linear-gradient(135deg,#3a8bff,#7c5cff)] px-4 text-[0.8rem] font-black text-white transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60'
const quietBtnClass =
  'h-9 rounded-[0.5rem] border border-[#253552] bg-[#0d1b2e] px-3 text-[0.78rem] font-black text-[#c5d3ed] transition hover:border-[#3a8bff] hover:text-white disabled:opacity-55'
const dangerBtnClass =
  'h-9 rounded-[0.5rem] border border-[#5a2233] bg-[#0d1b2e] px-3 text-[0.78rem] font-black text-[#ff8095] transition hover:bg-[#2a1622] hover:text-[#ffb3c0] disabled:opacity-55'
const tabButtonClass = 'rounded-[0.5rem] px-4 py-2 text-[0.82rem] font-black transition duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#3a8bff]/35'
const tabActiveClass = 'bg-[#122743] text-white shadow-[inset_0_-0.125rem_0_#3a8bff]'
const tabInactiveClass = 'text-[#9aa9c3] hover:bg-[#0d1b2e] hover:text-white'
const pillClass = 'rounded-full border border-[#253552] bg-[#0d1b2e] px-2.5 py-0.5 text-[0.72rem] font-bold text-[#9aa9c3]'

const ROUTE_SOURCES: { key: string; label: string }[] = [
  { key: 'transfer', label: '转存核心' },
  { key: 'organize', label: '整理核心' },
]

type ProviderKind = 'telegram' | 'bark'

type TgDraft = { name: string; enabled: boolean; chat_id: string; bot_token: string; has_bot_token: boolean }
type BarkDraft = { name: string; enabled: boolean; server_url: string; device_key: string; has_device_key: boolean }

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

function tgToDraft(p: TelegramProviderResponse): TgDraft {
  return { name: p.name, enabled: p.enabled, chat_id: p.chat_id, bot_token: '', has_bot_token: p.has_bot_token }
}

function barkToDraft(p: BarkProviderResponse): BarkDraft {
  return { name: p.name, enabled: p.enabled, server_url: p.server_url, device_key: '', has_device_key: p.has_device_key }
}

export function NotificationSettings() {
  const [activeTab, setActiveTab] = useState<'providers' | 'routing' | 'webhook'>('providers')
  const [data, setData] = useState<NotificationProvidersResponse | null>(null)
  const [tg, setTg] = useState<TgDraft[]>([])
  const [bark, setBark] = useState<BarkDraft[]>([])
  const [routing, setRouting] = useState<Record<string, string[]>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saveMsg, setSaveMsg] = useState<string | null>(null)
  const [testState, setTestState] = useState<Record<string, { ok: boolean; msg: string }>>({})

  const [editing, setEditing] = useState<{ kind: ProviderKind; index: number | null } | null>(null)

  function hydrate(d: NotificationProvidersResponse) {
    setData(d)
    setTg(d.telegram.map(tgToDraft))
    setBark(d.bark.map(barkToDraft))
    setRouting(Object.fromEntries(ROUTE_SOURCES.map((s) => [s.key, d.routing[s.key] ?? []])))
  }

  useEffect(() => {
    getNotificationProviders()
      .then(hydrate)
      .catch((e) => setError(errorMessage(e)))
      .finally(() => setLoading(false))
  }, [])

  const allNames = [...tg.map((p) => p.name), ...bark.map((p) => p.name)].filter(Boolean)
  const providerCount = tg.length + bark.length

  function toggleRoute(source: string, name: string) {
    setRouting((prev) => {
      const current = prev[source] ?? []
      const next = current.includes(name) ? current.filter((n) => n !== name) : [...current, name]
      return { ...prev, [source]: next }
    })
  }

  async function persist(nextTg: TgDraft[], nextBark: BarkDraft[], nextRouting: Record<string, string[]>) {
    setSaving(true)
    setError(null)
    setSaveMsg(null)
    try {
      const updated = await updateNotificationProviders({
        telegram: nextTg.map((p) => ({
          name: p.name,
          enabled: p.enabled,
          chat_id: p.chat_id.trim(),
          bot_token: p.bot_token.trim() ? p.bot_token.trim() : null,
        })),
        bark: nextBark.map((p) => ({
          name: p.name,
          enabled: p.enabled,
          server_url: p.server_url.trim() || 'https://api.day.app',
          device_key: p.device_key.trim() ? p.device_key.trim() : null,
        })),
        routing: nextRouting,
      })
      hydrate(updated)
      setSaveMsg('已保存')
      window.setTimeout(() => setSaveMsg(null), 2000)
      return true
    } catch (e) {
      setError(errorMessage(e))
      return false
    } finally {
      setSaving(false)
    }
  }

  function handleSaveRouting() {
    void persist(tg, bark, routing)
  }

  async function handleSaveProvider(kind: ProviderKind, index: number | null, draft: TgDraft | BarkDraft) {
    let nextTg = tg
    let nextBark = bark
    if (kind === 'telegram') {
      const d = draft as TgDraft
      nextTg = index === null ? [...tg, d] : tg.map((x, i) => (i === index ? d : x))
    } else {
      const d = draft as BarkDraft
      nextBark = index === null ? [...bark, d] : bark.map((x, i) => (i === index ? d : x))
    }
    const ok = await persist(nextTg, nextBark, routing)
    if (ok) setEditing(null)
  }

  async function handleDeleteProvider(kind: ProviderKind, index: number) {
    const removedName = kind === 'telegram' ? tg[index]?.name : bark[index]?.name
    const nextTg = kind === 'telegram' ? tg.filter((_, i) => i !== index) : tg
    const nextBark = kind === 'bark' ? bark.filter((_, i) => i !== index) : bark
    const nextRouting = removedName
      ? Object.fromEntries(Object.entries(routing).map(([k, v]) => [k, v.filter((n) => n !== removedName)]))
      : routing
    await persist(nextTg, nextBark, nextRouting)
  }

  async function handleTest(name: string) {
    setTestState((prev) => ({ ...prev, [name]: { ok: false, msg: '测试中...' } }))
    try {
      const result = await testNotificationProvider(name)
      setTestState((prev) => ({
        ...prev,
        [name]: result.ok ? { ok: true, msg: '成功' } : { ok: false, msg: result.error ?? '失败' },
      }))
    } catch (e) {
      setTestState((prev) => ({ ...prev, [name]: { ok: false, msg: errorMessage(e) } }))
    }
  }

  if (loading) {
    return <p className="text-[0.78rem] text-[#91a0bb]">加载中...</p>
  }
  if (!data) {
    return error ? (
      <p className="rounded-[0.5rem] border border-[#7d3b58] bg-[#160d18] px-3 py-2 text-[0.78rem] text-[#ff9fb4]">{error}</p>
    ) : null
  }

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className={`${tabButtonClass} ${activeTab === 'providers' ? tabActiveClass : tabInactiveClass}`} onClick={() => setActiveTab('providers')}>
          渠道管理 <span className={`ml-1.5 ${pillClass}`}>{providerCount}</span>
        </button>
        <button type="button" className={`${tabButtonClass} ${activeTab === 'routing' ? tabActiveClass : tabInactiveClass}`} onClick={() => setActiveTab('routing')}>
          路由设置
        </button>
        <button type="button" className={`${tabButtonClass} ${activeTab === 'webhook' ? tabActiveClass : tabInactiveClass}`} onClick={() => setActiveTab('webhook')}>
          Webhook
        </button>
        {saveMsg && <span className="ml-auto text-[0.78rem] font-black text-[#7ee7bf]">{saveMsg}</span>}
      </div>

      {error && (
        <p className="rounded-[0.5rem] border border-[#7d3b58] bg-[#160d18] px-3 py-2 text-[0.78rem] text-[#ff9fb4]">{error}</p>
      )}

      {activeTab === 'providers' && (
        <ProvidersTab
          tg={tg}
          bark={bark}
          testState={testState}
          saving={saving}
          onAdd={(kind) => setEditing({ kind, index: null })}
          onEdit={(kind, index) => setEditing({ kind, index })}
          onDelete={handleDeleteProvider}
          onToggle={(kind, index) => {
            if (kind === 'telegram') {
              const next = tg.map((x, i) => (i === index ? { ...x, enabled: !x.enabled } : x))
              setTg(next)
              void persist(next, bark, routing)
            } else {
              const next = bark.map((x, i) => (i === index ? { ...x, enabled: !x.enabled } : x))
              setBark(next)
              void persist(tg, next, routing)
            }
          }}
          onTest={handleTest}
        />
      )}

      {activeTab === 'routing' && (
        <div className="grid gap-4">
          <div className="rounded-[0.5rem] border border-[#253552] bg-[#0a1424] px-3 py-2 text-[0.78rem] leading-5 text-[#c5d3ed]">
            <span className="font-black text-white">分流路由</span>
            <span className="ml-2">勾选每个核心整批跑完后要通知的渠道。仅显示已添加的渠道。</span>
          </div>
          <div className="grid gap-3 grid-cols-1 min-[60rem]:grid-cols-2">
            {ROUTE_SOURCES.map((source) => (
              <div key={source.key} className={`${cardClass} p-4`}>
                <div className="mb-2.5 text-[0.85rem] font-black text-[#dbe7ff]">{source.label}</div>
                <div className="flex flex-wrap gap-2">
                  {allNames.length === 0 && <span className="text-[0.74rem] text-[#667793]">暂无可用渠道，请先在「渠道管理」添加。</span>}
                  {allNames.map((name) => {
                    const active = (routing[source.key] ?? []).includes(name)
                    return (
                      <button key={name} type="button" onClick={() => toggleRoute(source.key, name)}
                        className={`h-8 rounded-[0.45rem] border px-2.5 text-[0.74rem] font-black transition ${active ? 'border-[#3a8bff] bg-[#122743] text-white' : 'border-[#253552] bg-[#0d1b2e] text-[#9aa9c3] hover:text-white'}`}>
                        {active ? '✓ ' : ''}{name}
                      </button>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <button type="button" className={btnClass} disabled={saving} onClick={handleSaveRouting}>
              {saving ? '保存中...' : '保存路由'}
            </button>
          </div>
        </div>
      )}

      {activeTab === 'webhook' && <WebhookTab />}

      {editing && (
        <ProviderModal
          kind={editing.kind}
          initial={
            editing.kind === 'telegram'
              ? editing.index !== null
                ? tg[editing.index]
                : null
              : editing.index !== null
                ? bark[editing.index]
                : null
          }
          existingNames={allNames}
          editingIndex={editing.index}
          saving={saving}
          onClose={() => setEditing(null)}
          onSubmit={(draft) => handleSaveProvider(editing.kind, editing.index, draft)}
        />
      )}
    </div>
  )
}

function ProvidersTab({
  tg,
  bark,
  testState,
  saving,
  onAdd,
  onEdit,
  onDelete,
  onToggle,
  onTest,
}: {
  tg: TgDraft[]
  bark: BarkDraft[]
  testState: Record<string, { ok: boolean; msg: string }>
  saving: boolean
  onAdd: (kind: ProviderKind) => void
  onEdit: (kind: ProviderKind, index: number) => void
  onDelete: (kind: ProviderKind, index: number) => void
  onToggle: (kind: ProviderKind, index: number) => void
  onTest: (name: string) => void
}) {
  const cards: { kind: ProviderKind; index: number; name: string; enabled: boolean; detail: string; configured: boolean }[] = [
    ...tg.map((p, index) => ({
      kind: 'telegram' as const,
      index,
      name: p.name,
      enabled: p.enabled,
      detail: `Chat ID: ${p.chat_id || '未设置'}`,
      configured: p.has_bot_token || !!p.bot_token,
    })),
    ...bark.map((p, index) => ({
      kind: 'bark' as const,
      index,
      name: p.name,
      enabled: p.enabled,
      detail: p.server_url || 'https://api.day.app',
      configured: p.has_device_key || !!p.device_key,
    })),
  ]

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[0.78rem] text-[#91a0bb]">添加 Telegram / Bark 渠道，可自定义名称。</span>
        <div className="ml-auto flex gap-2">
          <button type="button" className={quietBtnClass} disabled={saving} onClick={() => onAdd('telegram')}>+ Telegram</button>
          <button type="button" className={quietBtnClass} disabled={saving} onClick={() => onAdd('bark')}>+ Bark</button>
        </div>
      </div>

      {cards.length === 0 ? (
        <div className={`${cardClass} px-4 py-8 text-center text-[0.8rem] text-[#91a0bb]`}>
          还没有任何渠道，点击右上角按钮添加。
        </div>
      ) : (
        <div className="grid gap-3 grid-cols-1 min-[40rem]:grid-cols-2 min-[68rem]:grid-cols-3">
          {cards.map((c) => {
            const result = testState[c.name]
            return (
              <div key={`${c.kind}-${c.index}`} className={`${cardClass} p-3.5`}>
                <div className="mb-2 flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="truncate text-[0.88rem] font-black text-[#dbe7ff]">{c.name || '(未命名)'}</div>
                    <div className="mt-0.5 text-[0.68rem] font-black uppercase tracking-[0.08em] text-[#53d3ff]">{c.kind}</div>
                  </div>
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-[0.66rem] font-black ${c.enabled ? 'bg-[#0c2a22] text-[#7ee7bf]' : 'bg-[#1a1320] text-[#8a7686]'}`}>
                    {c.enabled ? '已启用' : '已禁用'}
                  </span>
                </div>
                <p className="m-0 mb-1 truncate text-[0.74rem] text-[#9aa9c3]">{c.detail}</p>
                <p className="m-0 mb-3 text-[0.72rem] font-bold text-[#667793]">{c.configured ? '凭据已配置' : '凭据未配置'}</p>
                <div className="flex flex-wrap items-center gap-1.5">
                  <button type="button" className={quietBtnClass} onClick={() => onEdit(c.kind, c.index)}>编辑</button>
                  <button type="button" className={quietBtnClass} onClick={() => onToggle(c.kind, c.index)} disabled={saving}>
                    {c.enabled ? '停用' : '启用'}
                  </button>
                  <button type="button" className={quietBtnClass} onClick={() => onTest(c.name)} disabled={!c.name}>测试</button>
                  <button type="button" className={dangerBtnClass} onClick={() => onDelete(c.kind, c.index)} disabled={saving}>删除</button>
                </div>
                {result && (
                  <div className={`mt-2 text-[0.72rem] font-bold ${result.ok ? 'text-[#7ee7bf]' : 'text-[#ff9fb4]'}`}>
                    {result.ok ? '测试成功' : `测试：${result.msg}`}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function ProviderModal({
  kind,
  initial,
  existingNames,
  editingIndex,
  saving,
  onClose,
  onSubmit,
}: {
  kind: ProviderKind
  initial: TgDraft | BarkDraft | null
  existingNames: string[]
  editingIndex: number | null
  saving: boolean
  onClose: () => void
  onSubmit: (draft: TgDraft | BarkDraft) => void
}) {
  const tgInit = kind === 'telegram' ? (initial as TgDraft | null) : null
  const barkInit = kind === 'bark' ? (initial as BarkDraft | null) : null

  const [name, setName] = useState(initial?.name ?? '')
  const [enabled, setEnabled] = useState(initial?.enabled ?? false)
  const [chatId, setChatId] = useState(tgInit?.chat_id ?? '')
  const [botToken, setBotToken] = useState('')
  const [serverUrl, setServerUrl] = useState(barkInit?.server_url ?? 'https://api.day.app')
  const [deviceKey, setDeviceKey] = useState('')
  const [localError, setLocalError] = useState<string | null>(null)

  const hasBotToken = tgInit?.has_bot_token ?? false
  const hasDeviceKey = barkInit?.has_device_key ?? false

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) {
      setLocalError('请填写渠道名称')
      return
    }
    if (editingIndex === null && existingNames.includes(trimmed)) {
      setLocalError('该名称已存在，请换一个')
      return
    }
    if (kind === 'telegram') {
      onSubmit({ name: trimmed, enabled, chat_id: chatId, bot_token: botToken, has_bot_token: hasBotToken })
    } else {
      onSubmit({ name: trimmed, enabled, server_url: serverUrl, device_key: deviceKey, has_device_key: hasDeviceKey })
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(3,6,16,0.78)] p-4 backdrop-blur-sm" onClick={onClose}>
      <div className={`${cardClass} w-full max-w-lg overflow-y-auto p-5`} onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <p className="m-0 text-[0.68rem] font-black uppercase tracking-[0.14em] text-[#53d3ff]">{kind}</p>
            <h2 className="mb-0 mt-1 text-[1.15rem] font-black text-white">{editingIndex === null ? '添加渠道' : '编辑渠道'}</h2>
          </div>
          <button type="button" className={quietBtnClass} onClick={onClose} aria-label="关闭">✕</button>
        </div>

        {localError && (
          <p className="mb-3 rounded-[0.5rem] border border-[#7d3b58] bg-[#160d18] px-3 py-2 text-[0.76rem] text-[#ff9fb4]">{localError}</p>
        )}

        <form className="grid gap-3" onSubmit={handleSubmit}>
          <label className={labelClass}>
            <span>渠道名称{editingIndex !== null && <span className="ml-2 text-[0.68rem] text-[#667793]">（不可修改）</span>}</span>
            <input className={fieldClass} value={name} placeholder="例如 tg1 / 我的Bark" disabled={editingIndex !== null}
              onChange={(e) => setName(e.target.value)} />
          </label>

          {kind === 'telegram' ? (
            <>
              <label className={labelClass}>
                <span>Chat ID</span>
                <input className={fieldClass} value={chatId} placeholder="会话 / 群组 / 频道 ID"
                  onChange={(e) => setChatId(e.target.value)} />
              </label>
              <label className={labelClass}>
                <span>Bot Token{hasBotToken && !botToken && <span className="ml-2 text-[0.68rem] text-[#7ee7bf]">（已配置，留空保持不变）</span>}</span>
                <input className={fieldClass} type="password" value={botToken}
                  placeholder={hasBotToken ? '留空保持现有 Token' : '从 @BotFather 获取'}
                  onChange={(e) => setBotToken(e.target.value)} />
              </label>
            </>
          ) : (
            <>
              <label className={labelClass}>
                <span>Device Key{hasDeviceKey && !deviceKey && <span className="ml-2 text-[0.68rem] text-[#7ee7bf]">（已配置，留空保持不变）</span>}</span>
                <input className={fieldClass} type="password" value={deviceKey}
                  placeholder={hasDeviceKey ? '留空保持现有 Key' : 'Bark App 提供的设备 key'}
                  onChange={(e) => setDeviceKey(e.target.value)} />
              </label>
              <label className={labelClass}>
                <span>服务器地址</span>
                <input className={fieldClass} value={serverUrl} placeholder="https://api.day.app"
                  onChange={(e) => setServerUrl(e.target.value)} />
              </label>
            </>
          )}

          <div className="flex items-center gap-3">
            <button type="button" role="switch" aria-checked={enabled} onClick={() => setEnabled((v) => !v)}
              className={`relative h-6 w-11 rounded-full border transition ${enabled ? 'border-[#3a8bff] bg-[#122743]' : 'border-[#253552] bg-[#07111f]'}`}>
              <span className={`absolute top-0.5 h-5 w-5 rounded-full transition-all ${enabled ? 'left-[calc(100%-1.375rem)] bg-[#53d3ff] shadow-[0_0_0.75rem_rgba(83,211,255,0.7)]' : 'left-0.5 bg-[#4a5a72]'}`} />
            </button>
            <span className="text-[0.78rem] font-bold text-[#9aa9c3]">{enabled ? '已启用' : '已禁用'}</span>
          </div>

          <div className="mt-1 flex items-center gap-2">
            <button type="submit" className={btnClass} disabled={saving}>{saving ? '保存中...' : '保存'}</button>
            <button type="button" className={quietBtnClass} onClick={onClose}>取消</button>
          </div>
        </form>
      </div>
    </div>
  )
}

function WebhookTab() {
  const [settings, setSettings] = useState<NotificationSettingsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saveMsg, setSaveMsg] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null)

  const [url, setUrl] = useState('')
  const [token, setToken] = useState('')
  const [enabled, setEnabled] = useState(false)
  const [timeout, setTimeout_] = useState(10)

  useEffect(() => {
    getNotificationSettings()
      .then((s) => {
        setSettings(s)
        setUrl(s.url)
        setEnabled(s.enabled)
        setTimeout_(s.timeout_seconds)
      })
      .catch((e) => setError(errorMessage(e)))
      .finally(() => setLoading(false))
  }, [])

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    setSaveMsg(null)
    try {
      const updated = await updateNotificationSettings({
        enabled,
        url: url.trim(),
        token: token.trim() || null,
        timeout_seconds: timeout,
      })
      setSettings(updated)
      setToken('')
      setSaveMsg('已保存')
      window.setTimeout(() => setSaveMsg(null), 2000)
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setSaving(false)
    }
  }

  async function handleTest() {
    setTesting(true)
    setTestResult(null)
    try {
      const result = await testNotificationWebhook()
      setTestResult(result.ok ? { ok: true, msg: `成功 (HTTP ${result.status_code})` } : { ok: false, msg: result.error ?? `HTTP ${result.status_code}` })
    } catch (e) {
      setTestResult({ ok: false, msg: errorMessage(e) })
    } finally {
      setTesting(false)
    }
  }

  if (loading) {
    return <p className="text-[0.78rem] text-[#91a0bb]">加载中...</p>
  }

  return (
    <div className="grid gap-4">
      <div className="rounded-[0.5rem] border border-[#253552] bg-[#0a1424] px-3 py-2 text-[0.78rem] leading-5 text-[#c5d3ed]">
        <span className="font-black text-white">Webhook 通知</span>
        <span className="ml-2">配置 HTTP Webhook，在转存成功、整理完成等事件发生时向指定地址发送 POST 请求。</span>
      </div>

      {error && (
        <p className="rounded-[0.5rem] border border-[#7d3b58] bg-[#160d18] px-3 py-2 text-[0.78rem] text-[#ff9fb4]">{error}</p>
      )}

      <form className="grid gap-4" onSubmit={handleSave}>
        <div className={`${cardClass} p-4`}>
          <h3 className="m-0 mb-3 text-[0.82rem] font-black text-white">Webhook 配置</h3>
          <div className="grid gap-3 min-[60rem]:grid-cols-2">
            <label className={labelClass}>
              <span>Webhook 地址</span>
              <input className={fieldClass} type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://your-server.com/webhook" />
            </label>

            <label className={labelClass}>
              <span>
                认证令牌
                {settings?.has_token && !token && (
                  <span className="ml-2 text-[0.68rem] font-semibold text-[#7ee7bf]">（已配置，留空保持不变）</span>
                )}
              </span>
              <input className={fieldClass} type="password" value={token} onChange={(e) => setToken(e.target.value)}
                placeholder={settings?.has_token ? '留空保持现有令牌' : '可选，用于 Authorization: Bearer <token>'} />
            </label>

            <label className={labelClass}>
              <span>请求超时（秒）</span>
              <input className={fieldClass} type="number" min={1} max={120} value={timeout} onChange={(e) => setTimeout_(Number(e.target.value))} />
            </label>

            <div className="flex items-center gap-3 min-[60rem]:items-end min-[60rem]:pb-1">
              <button type="button" role="switch" aria-checked={enabled} onClick={() => setEnabled((v) => !v)}
                className={`relative h-6 w-11 rounded-full border transition ${enabled ? 'border-[#3a8bff] bg-[#122743]' : 'border-[#253552] bg-[#07111f]'}`}>
                <span className={`absolute top-0.5 h-5 w-5 rounded-full transition-all ${enabled ? 'left-[calc(100%-1.375rem)] bg-[#53d3ff] shadow-[0_0_0.75rem_rgba(83,211,255,0.7)]' : 'left-0.5 bg-[#4a5a72]'}`} />
              </button>
              <span className="text-[0.78rem] font-bold text-[#9aa9c3]">{enabled ? '已启用' : '已禁用'}</span>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button type="submit" className={btnClass} disabled={saving}>{saving ? '保存中...' : '保存配置'}</button>
          <button type="button" className={quietBtnClass} onClick={handleTest} disabled={testing || !url.trim()}>
            {testing ? '测试中...' : '发送测试通知'}
          </button>
          {saveMsg && <span className="text-[0.78rem] font-black text-[#7ee7bf]">{saveMsg}</span>}
        </div>
      </form>

      {testResult && (
        <div className={`rounded-[0.5rem] border px-3 py-2 text-[0.78rem] font-semibold ${testResult.ok ? 'border-[#275d48] bg-[#0c2a22] text-[#7ee7bf]' : 'border-[#7d3b58] bg-[#160d18] text-[#ff9fb4]'}`}>
          {testResult.ok ? '测试成功：' : '测试失败：'}{testResult.msg}
        </div>
      )}

      {settings && (
        <div className={`${cardClass} p-3`}>
          <h3 className="m-0 mb-2 text-[0.82rem] font-black text-white">当前状态</h3>
          <div className="grid gap-1.5 sm:grid-cols-4">
            {[
              ['状态', settings.enabled ? '已启用' : '已禁用'],
              ['地址', settings.url || '未配置'],
              ['令牌', settings.has_token ? '已配置' : '未配置'],
              ['超时', `${settings.timeout_seconds} 秒`],
            ].map(([label, value]) => (
              <div key={label} className="rounded-[0.45rem] border border-[#1d2a46] bg-[#07111f] px-2.5 py-2">
                <div className="text-[0.62rem] font-black uppercase tracking-[0.1em] text-[#667793]">{label}</div>
                <div className="mt-0.5 truncate text-[0.82rem] font-black text-[#dbe7ff]">{value}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
