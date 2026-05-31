import { useEffect, useMemo, useState, type FormEvent } from 'react'
import type { TelegramWebChannel, TelegramWebChannelStatusResponse } from '../types'
import { useTelegramWebChannels } from './useTelegramWebChannels'

export type ResourceCenterTabId = 'telegram-web' | 'telegram-app' | 'hdhive' | 'panso'

type ResourceCenterProps = {
  activeTab: ResourceCenterTabId
  onTabChange: (tabId: ResourceCenterTabId) => void
}

type ChannelFormState = {
  original_channel: string | null
  channel: string
  display_name: string
  enabled: boolean
  poll_interval_seconds: string
}

type ResourceTab = {
  id: ResourceCenterTabId
  label: string
  title: string
  description: string
  status: string
}

const resourceTabs: ResourceTab[] = [
  {
    id: 'telegram-web',
    label: 'telegram_web',
    title: 'Telegram Web 来源',
    description: '维护公开 t.me/s 频道采集器，用于 NDRA 资源接入。',
    status: '已接入',
  },
  {
    id: 'telegram-app',
    label: 'telegram_app',
    title: 'Telegram App 来源',
    description: '预留 Telegram 客户端采集渠道，后续可接入账号态或应用侧采集能力。',
    status: '未实现',
  },
  {
    id: 'hdhive',
    label: 'hdhive',
    title: 'HDHive 来源',
    description: '预留 HDHive 资源渠道，用于后续扩展站点型资源接入。',
    status: '未实现',
  },
  {
    id: 'panso',
    label: 'panso',
    title: 'Panso 来源',
    description: '预留 Panso 搜索渠道，用于后续扩展聚合搜索资源接入。',
    status: '未实现',
  },
]

const panelClass = 'rounded-[0.75rem] border border-[#1d2a46] bg-[#0a1424] p-4 shadow-[0_1rem_2.5rem_rgba(0,0,0,0.24)]'
const surfaceClass = 'rounded-[0.625rem] border border-[#253552] bg-[#07111f]'
const focusClass = 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#53d3ff] focus-visible:ring-offset-2 focus-visible:ring-offset-[#07111f]'
const labelClass = 'grid gap-1.5 text-[0.72rem] font-black uppercase tracking-[0.1em] text-[#71829f]'
const fieldClass = `${focusClass} h-9 rounded-[0.5rem] border border-[#253552] bg-[#07111f] px-2.5 text-[0.8rem] font-semibold text-[#dbe7ff] placeholder:text-[#52627d]`
const primaryButtonClass = `${focusClass} h-9 rounded-[0.5rem] bg-[linear-gradient(135deg,#3a8bff,#7c5cff)] px-3 text-[0.78rem] font-black text-white shadow-[0_0.75rem_1.5rem_rgba(58,139,255,0.18)] transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60 disabled:brightness-100`
const quietButtonClass = `${focusClass} h-8 rounded-[0.45rem] border border-[#253552] bg-[#0d1b2e] px-2.5 text-[0.72rem] font-black text-[#c5d3ed] transition hover:border-[#3a8bff] hover:text-white disabled:cursor-not-allowed disabled:opacity-55`
const dangerButtonClass = `${focusClass} h-8 rounded-[0.45rem] border border-[#553044] bg-[#1a0e19] px-2.5 text-[0.72rem] font-black text-[#ff9fb4] transition hover:border-[#9b4562] hover:text-[#ffd7e0] disabled:cursor-not-allowed disabled:opacity-55`
const pillClass = 'rounded-full border border-[#253552] bg-[#07111f] px-2.5 py-0.5 text-[0.68rem] font-black text-[#aebdd6]'

const emptyChannelForm: ChannelFormState = {
  original_channel: null,
  channel: '',
  display_name: '',
  enabled: true,
  poll_interval_seconds: '1800',
}

export function ResourceCenter({ activeTab, onTabChange }: ResourceCenterProps) {
  const activeResource = resourceTabs.find((tab) => tab.id === activeTab) ?? resourceTabs[0]

  return (
    <section className="grid gap-3" aria-labelledby="resource-center-title">
      <div className="flex items-start justify-between gap-3 border-b border-[#1d2a46] pb-3 max-[42rem]:flex-col">
        <div className="min-w-0">
          <p className="m-0 text-[0.66rem] font-black uppercase tracking-[0.14em] text-[#53d3ff]">{activeResource.label}</p>
          <h2 id="resource-center-title" className="mb-1 mt-1 text-[1.05rem] font-black text-white">资源中心</h2>
          <p className="m-0 max-w-3xl text-[0.78rem] leading-5 text-[#91a0bb]">{activeResource.description}</p>
        </div>
        <span className={pillClass}>{activeResource.status}</span>
      </div>

      <div className="flex flex-wrap gap-2 border-b border-[#1d2a46] pb-3" role="tablist" aria-label="资源来源">
        {resourceTabs.map((tab) => {
          const selected = tab.id === activeTab
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={selected}
              className={`${focusClass} min-h-9 rounded-[0.5rem] border px-3 text-[0.76rem] font-black transition ${
                selected
                  ? 'border-[#3a8bff] bg-[#122743] text-white shadow-[inset_0_0_0_0.0625rem_rgba(83,211,255,0.22)]'
                  : 'border-[#253552] bg-[#07111f] text-[#9aa9c3] hover:border-[#3a8bff] hover:text-white'
              }`}
              onClick={() => onTabChange(tab.id)}
            >
              {tab.label}
            </button>
          )
        })}
      </div>

      {activeTab === 'telegram-web' ? <TelegramWebResourcePanel /> : <ResourcePlaceholderPanel tab={activeResource} />}
    </section>
  )
}

function TelegramWebResourcePanel() {
  const {
    channels,
    loading,
    error,
    saveState,
    deleteState,
    toggleState,
    statusState,
    statusByChannel,
    saveChannel,
    removeChannel,
    setChannelEnabled,
    checkChannelStatus,
  } = useTelegramWebChannels()
  const [channelForm, setChannelForm] = useState<ChannelFormState>(emptyChannelForm)
  const combinedError = useMemo(() => {
    return [error, saveState.error, deleteState.error, toggleState.error, statusState.error].filter(Boolean).join(' ')
  }, [deleteState.error, error, saveState.error, statusState.error, toggleState.error])

  useEffect(() => {
    if (channelForm.original_channel === null) {
      return
    }

    const currentChannel = channels.find((channel) => channel.channel === channelForm.original_channel)
    if (currentChannel) {
      setChannelForm(toFormState(currentChannel))
    }
  }, [channelForm.original_channel, channels])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    const payload = {
      channel: normalizeChannel(channelForm.channel),
      display_name: channelForm.display_name.trim() || null,
      enabled: channelForm.enabled,
      poll_interval_seconds: Number(channelForm.poll_interval_seconds),
    }

    try {
      if (channelForm.original_channel === null) {
        await saveChannel(payload)
      } else {
        await saveChannel({
          display_name: payload.display_name,
          enabled: payload.enabled,
          poll_interval_seconds: payload.poll_interval_seconds,
        }, channelForm.original_channel)
      }
      setChannelForm(emptyChannelForm)
    } catch {
      return
    }
  }

  async function handleDelete(channel: TelegramWebChannel) {
    try {
      await removeChannel(channel.channel)
      if (channelForm.original_channel === channel.channel) {
        setChannelForm(emptyChannelForm)
      }
    } catch {
      return
    }
  }

  async function handleToggle(channel: TelegramWebChannel) {
    try {
      await setChannelEnabled(channel.channel, !channel.enabled)
    } catch {
      return
    }
  }

  async function handleStatus(channel: TelegramWebChannel) {
    try {
      await checkChannelStatus(channel.channel)
    } catch {
      return
    }
  }

  return (
    <div className="grid gap-3">
      {combinedError && <StateNote tone="error" label={combinedError} />}

      <div className="grid grid-cols-[minmax(0,1fr)_minmax(20rem,0.38fr)] gap-3 max-[64rem]:grid-cols-1">
        <article className={panelClass} aria-label="Telegram web channel list">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <p className="m-0 text-[0.66rem] font-black uppercase tracking-[0.14em] text-[#71829f]">频道列表</p>
              <h3 className="m-0 mt-1 text-[0.98rem] font-black text-white">telegram_web</h3>
            </div>
            <span className={pillClass}>{channels.length} 个频道</span>
          </div>

          {loading && <StateNote label="加载 telegram_web 频道..." />}
          {!loading && channels.length === 0 && <StateNote label="暂无配置的 telegram_web 频道。" />}
          {!loading && channels.length > 0 && (
            <div className="grid max-h-[36rem] gap-2 overflow-auto pr-1" role="list" aria-label="Telegram web channels">
              {channels.map((channel) => (
                <ChannelRow
                  key={channel.channel}
                  busy={deleteState.loading || toggleState.loading || statusState.loading}
                  channel={channel}
                  status={statusByChannel[channel.channel]}
                  onDelete={handleDelete}
                  onEdit={(selected) => setChannelForm(toFormState(selected))}
                  onStatus={handleStatus}
                  onToggle={handleToggle}
                />
              ))}
            </div>
          )}
        </article>

        <article className={panelClass} aria-labelledby="telegram-web-channel-form-title">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <p className="m-0 text-[0.66rem] font-black uppercase tracking-[0.14em] text-[#71829f]">{channelForm.original_channel === null ? '创建' : '编辑'}</p>
              <h3 id="telegram-web-channel-form-title" className="m-0 mt-1 text-[0.98rem] font-black text-white">频道来源</h3>
            </div>
            {channelForm.original_channel !== null && <span className={pillClass}>{channelForm.original_channel}</span>}
          </div>

          <form className="grid gap-3" onSubmit={handleSubmit}>
            <label className={labelClass}>
              <span>频道</span>
              <input
                className={fieldClass}
                name="telegram-web-channel"
                value={channelForm.channel}
                onChange={(event) => setChannelForm((current) => ({ ...current, channel: event.target.value }))}
                placeholder="movie_channel 或 @movie_channel"
                required
              />
            </label>

            <label className={labelClass}>
              <span>显示名称</span>
              <input
                className={fieldClass}
                name="telegram-web-display-name"
                value={channelForm.display_name}
                onChange={(event) => setChannelForm((current) => ({ ...current, display_name: event.target.value }))}
                placeholder="电影频道"
              />
            </label>

            <label className={labelClass}>
              <span>轮询间隔（秒）</span>
              <input
                className={fieldClass}
                name="telegram-web-poll-interval-seconds"
                type="number"
                min="60"
                inputMode="numeric"
                value={channelForm.poll_interval_seconds}
                onChange={(event) => setChannelForm((current) => ({ ...current, poll_interval_seconds: event.target.value }))}
                required
              />
            </label>

            <label className={`${surfaceClass} flex min-h-10 items-center justify-between gap-3 px-3 text-[0.78rem] font-black text-[#c5d3ed]`}>
              <span>已启用</span>
              <input
                className="h-4 w-4 accent-[#53d3ff]"
                type="checkbox"
                checked={channelForm.enabled}
                onChange={(event) => setChannelForm((current) => ({ ...current, enabled: event.target.checked }))}
              />
            </label>

            <div className="flex flex-wrap gap-2">
              <button className={primaryButtonClass} type="submit" data-testid="telegram-web-channel-save" disabled={saveState.loading}>
                {saveState.loading ? '保存中...' : channelForm.original_channel === null ? '保存频道' : '保存更改'}
              </button>
              {channelForm.original_channel !== null && (
                <button className={quietButtonClass} type="button" onClick={() => setChannelForm(emptyChannelForm)}>
                  取消
                </button>
              )}
            </div>
          </form>
        </article>
      </div>
    </div>
  )
}

function ResourcePlaceholderPanel({ tab }: { tab: ResourceTab }) {
  return (
    <article className={`${panelClass} min-h-[18rem]`} aria-labelledby={`${tab.id}-placeholder-title`}>
      <div className="grid h-full min-h-[15rem] place-items-center rounded-[0.625rem] border border-dashed border-[#253552] bg-[#07111f] px-4 py-8 text-center">
        <div className="max-w-[34rem]">
          <p className="m-0 text-[0.66rem] font-black uppercase tracking-[0.14em] text-[#53d3ff]">{tab.label}</p>
          <h3 id={`${tab.id}-placeholder-title`} className="mb-2 mt-2 text-[1rem] font-black text-white">{tab.title}</h3>
          <p className="m-0 text-[0.8rem] font-semibold leading-6 text-[#91a0bb]">{tab.description}</p>
          <p className="m-0 mt-3 text-[0.72rem] font-black uppercase tracking-[0.12em] text-[#71829f]">未实现</p>
        </div>
      </div>
    </article>
  )
}

function ChannelRow({
  busy,
  channel,
  onDelete,
  onEdit,
  onStatus,
  onToggle,
  status,
}: {
  busy: boolean
  channel: TelegramWebChannel
  onDelete: (channel: TelegramWebChannel) => void
  onEdit: (channel: TelegramWebChannel) => void
  onStatus: (channel: TelegramWebChannel) => void
  onToggle: (channel: TelegramWebChannel) => void
  status?: TelegramWebChannelStatusResponse
}) {
  const title = channel.display_name?.trim() || channel.channel

  return (
    <article className={`${surfaceClass} overflow-hidden shadow-[inset_0_0_0_0.0625rem_rgba(83,211,255,0.04)]`} role="listitem">
      <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3 p-3 max-[42rem]:grid-cols-1">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <h3 className="m-0 break-words text-[0.98rem] font-black leading-tight text-white">{title}</h3>
            <span className={channel.enabled ? 'rounded-full border border-[#275d48] bg-[#0c2a22] px-2 py-0.5 text-[0.65rem] font-black text-[#7ee7bf]' : 'rounded-full border border-[#553044] bg-[#1a0e19] px-2 py-0.5 text-[0.65rem] font-black text-[#ff9fb4]'}>
              {channel.enabled ? '已启用' : '已禁用'}
            </span>
          </div>
          <code className="block break-all rounded-[0.45rem] border border-[#1d2a46] bg-[#050812] px-2 py-1.5 text-[0.76rem] text-[#b9c7df]">{channel.channel}</code>
        </div>
        <div className="flex flex-wrap justify-end gap-1.5 max-[42rem]:justify-start">
          <button className={quietButtonClass} type="button" data-testid="telegram-web-channel-status" onClick={() => onStatus(channel)} disabled={busy}>
            状态
          </button>
          <button className={quietButtonClass} type="button" data-testid="telegram-web-channel-toggle" aria-pressed={!channel.enabled} onClick={() => onToggle(channel)} disabled={busy}>
            {channel.enabled ? '禁用' : '启用'}
          </button>
          <button className={quietButtonClass} type="button" data-testid="telegram-web-channel-edit" onClick={() => onEdit(channel)} disabled={busy}>
            编辑
          </button>
          <button className={dangerButtonClass} type="button" data-testid="telegram-web-channel-delete" onClick={() => onDelete(channel)} disabled={busy}>
            删除
          </button>
        </div>
      </div>

      <dl className="m-0 grid grid-cols-3 gap-px border-t border-[#1d2a46] bg-[#1d2a46] text-[0.72rem] max-[42rem]:grid-cols-1">
        <MetaCell label="轮询" value={`${channel.poll_interval_seconds}秒`} />
        <MetaCell label="创建时间" value={channel.created_at} />
        <MetaCell label="更新时间" value={channel.updated_at} />
      </dl>

      {status && <StatusPanel status={status} />}
    </article>
  )
}

function MetaCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 bg-[#0a1424] px-3 py-2">
      <dt className="text-[0.62rem] font-black uppercase tracking-[0.1em] text-[#667793]">{label}</dt>
      <dd className="m-0 mt-1 truncate text-[#c5d3ed]">{value}</dd>
    </div>
  )
}

function StatusPanel({ status }: { status: TelegramWebChannelStatusResponse }) {
  const entries = Object.entries(status).filter(([, value]) => value !== undefined)

  return (
    <section className="border-t border-[#1d2a46] bg-[#08111f] p-3" aria-label="Telegram web channel status">
      <div className="grid gap-1.5 sm:grid-cols-2">
        {entries.map(([key, value]) => (
          <div key={key} className="min-w-0 rounded-[0.45rem] border border-[#1d2a46] bg-[#050812] px-2.5 py-2">
            <div className="text-[0.62rem] font-black uppercase tracking-[0.1em] text-[#667793]">{formatLabel(key)}</div>
            <div className={key === 'error' && value ? 'mt-1 break-words text-[0.76rem] font-bold text-[#ff9fb4]' : 'mt-1 break-words text-[0.76rem] font-bold text-[#dbe7ff]'}>
              {formatStatusValue(value)}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

function StateNote({ label, tone = 'neutral' }: { label: string; tone?: 'neutral' | 'error' }) {
  const toneClass = tone === 'error' ? 'border-[#553044] bg-[#1a0e19] text-[#ff9fb4]' : 'border-[#253552] bg-[#07111f] text-[#91a0bb]'

  return <p className={`m-0 rounded-[0.5rem] border px-3 py-2 text-[0.78rem] font-semibold leading-5 ${toneClass}`}>{label}</p>
}

function toFormState(channel: TelegramWebChannel): ChannelFormState {
  return {
    original_channel: channel.channel,
    channel: channel.channel,
    display_name: channel.display_name ?? '',
    enabled: channel.enabled,
    poll_interval_seconds: String(channel.poll_interval_seconds),
  }
}

function normalizeChannel(channel: string): string {
  return channel.trim().replace(/^@/, '')
}

function formatLabel(key: string): string {
  return key.replace(/_/g, ' ')
}

function formatStatusValue(value: unknown): string {
  if (value === null) {
    return 'null'
  }

  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }

  return JSON.stringify(value)
}

export default ResourceCenter
