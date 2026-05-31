import { useEffect, useMemo, useState } from 'react'
import { LogCenterSummary, type LogCenterView } from './dashboard/LogCenterSummary'
import StatusOverview from './dashboard/StatusOverview'
import { NetdiskSettings } from './netdisk/NetdiskSettings'
import { NotificationSettings } from './notifications/NotificationSettings'
import ResourceCenter, { type ResourceCenterTabId } from './resources/ResourceCenter'
import { SubscriptionCenter } from './subscriptions/SubscriptionCenter'
import Toolbox, { type ToolboxTabId } from './toolbox/Toolbox'

type PageId = 'status-overview' | 'resource-center' | 'subscription-center' | 'netdisk-settings' | 'log-center' | 'toolbox' | 'notification-settings'
type SubViewId = ResourceCenterTabId | ToolboxTabId | 'collect' | 'transfer' | 'organize' | 'system' | 'path-tools' | 'global-settings'

type PageWidth = 'standard' | 'wide' | 'full'

type PageConfig = {
  id: PageId
  title: string
  width: PageWidth
}

type NavigationTarget = {
  pageId: PageId
  subViewId?: SubViewId
}

type NavItem = NavigationTarget & {
  icon: string
  label: string
}

const shell = {
  page: 'min-h-screen bg-[#050812] text-[#dbe7ff]',
  sidebar: 'fixed inset-y-0 left-0 z-30 flex w-[16rem] flex-col border-r border-[#1d2a46] bg-[#07111f] px-4 py-4 shadow-[1.25rem_0_4rem_rgba(0,0,0,0.28)] max-[56rem]:static max-[56rem]:h-auto max-[56rem]:w-full max-[56rem]:border-b max-[56rem]:border-r-0',
  topbar: 'fixed left-[16rem] right-0 top-0 z-20 flex min-h-[3.75rem] items-center justify-between gap-3 border-b border-[#1d2a46] bg-[#08111f]/92 px-6 backdrop-blur-xl max-[56rem]:static max-[56rem]:min-h-0 max-[56rem]:flex-wrap max-[56rem]:px-4 max-[56rem]:py-3',
  content: 'ml-[16rem] min-h-screen pt-[3.75rem] max-[56rem]:ml-0 max-[56rem]:pt-0',
  panel: 'mx-auto w-full max-w-[72.5rem] rounded-[0.75rem] border border-[#1d2a46] bg-[#0a1424] p-5 shadow-[0_1.25rem_4rem_rgba(0,0,0,0.32)] max-[44rem]:p-4',
  panelWide: 'mx-auto w-full max-w-[100rem] rounded-[0.75rem] border border-[#1d2a46] bg-[#0a1424] p-5 shadow-[0_1.25rem_4rem_rgba(0,0,0,0.32)] max-[44rem]:p-4',
  panelFull: 'w-full rounded-[0.75rem] border border-[#1d2a46] bg-[#0a1424] p-5 shadow-[0_1.25rem_4rem_rgba(0,0,0,0.32)] max-[44rem]:p-4',
  focus: 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7c5cff] focus-visible:ring-offset-2 focus-visible:ring-offset-[#07111f]',
}

const pages: Record<PageId, PageConfig> = {
  'status-overview': { id: 'status-overview', title: '状态总览', width: 'full' },
  'resource-center': { id: 'resource-center', title: '资源中心', width: 'wide' },
  'subscription-center': { id: 'subscription-center', title: '订阅中心', width: 'wide' },
  'netdisk-settings': { id: 'netdisk-settings', title: '网盘设置', width: 'standard' },
  'log-center': { id: 'log-center', title: '日志中心', width: 'full' },
  toolbox: { id: 'toolbox', title: '实用工具', width: 'standard' },
  'notification-settings': { id: 'notification-settings', title: '通知设置', width: 'wide' },
}

const navGroups: { title: string; items: NavItem[] }[] = [
  {
    title: '核心模块',
    items: [
      { icon: '📊', label: '状态总览', pageId: 'status-overview' },
      { icon: '🛰️', label: '资源中心', pageId: 'resource-center', subViewId: 'telegram-web' },
      { icon: '🧩', label: '订阅中心', pageId: 'subscription-center' },
      { icon: '💾', label: '网盘设置', pageId: 'netdisk-settings', subViewId: 'global-settings' },
      { icon: '📋', label: '日志中心', pageId: 'log-center', subViewId: 'system' },
      { icon: '🔔', label: '通知设置', pageId: 'notification-settings' },
      { icon: '🧰', label: '实用工具', pageId: 'toolbox', subViewId: 'tmdb' },
    ],
  },
  {
    title: '快速入口',
    items: [
      { icon: '📥', label: 'telegram_web', pageId: 'resource-center', subViewId: 'telegram-web' },
      { icon: 'TA', label: 'telegram_app', pageId: 'resource-center', subViewId: 'telegram-app' },
      { icon: 'HD', label: 'hdhive', pageId: 'resource-center', subViewId: 'hdhive' },
      { icon: 'P', label: 'panso', pageId: 'resource-center', subViewId: 'panso' },
      { icon: '🔁', label: '转存队列', pageId: 'log-center', subViewId: 'transfer' },
      { icon: '🗂️', label: '整理记录', pageId: 'log-center', subViewId: 'organize' },
      { icon: '🔎', label: 'TMDB 检索', pageId: 'toolbox', subViewId: 'tmdb' },
      { icon: 'AI', label: 'AI 识别', pageId: 'toolbox', subViewId: 'ai-filename' },
      { icon: '⚙️', label: '全局设置', pageId: 'netdisk-settings', subViewId: 'global-settings' },
      { icon: '🧪', label: '干运行测试', pageId: 'toolbox', subViewId: 'dry-run' },
    ],
  },
]

const resourceCenterTabs: ResourceCenterTabId[] = ['telegram-web', 'telegram-app', 'hdhive', 'panso']
const toolboxTabs: ToolboxTabId[] = ['tmdb', 'ai-filename', 'dry-run']

function toResourceCenterTab(subViewId?: SubViewId): ResourceCenterTabId {
  return resourceCenterTabs.includes(subViewId as ResourceCenterTabId) ? subViewId as ResourceCenterTabId : 'telegram-web'
}

function toToolboxTab(subViewId?: SubViewId): ToolboxTabId {
  return toolboxTabs.includes(subViewId as ToolboxTabId) ? subViewId as ToolboxTabId : 'tmdb'
}

function toLogView(subViewId?: SubViewId): LogCenterView {
  if (subViewId === 'transfer' || subViewId === 'organize' || subViewId === 'collect') {
    return subViewId
  }
  return 'system'
}

function renderPageContent(pageId: PageId, subViewId: SubViewId | undefined, setRoute: (pageId: PageId, subViewId?: SubViewId) => void) {
  if (pageId === 'status-overview') {
    return <StatusOverview />
  }

  if (pageId === 'resource-center') {
    return <ResourceCenter activeTab={toResourceCenterTab(subViewId)} onTabChange={(tabId) => setRoute('resource-center', tabId)} />
  }

  if (pageId === 'subscription-center') {
    return <SubscriptionCenter />
  }

  if (pageId === 'netdisk-settings') {
    return <NetdiskSettings />
  }

  if (pageId === 'log-center') {
    return <LogCenterSummary initialView={toLogView(subViewId)} />
  }

  if (pageId === 'toolbox') {
    return <Toolbox activeTab={toToolboxTab(subViewId)} onTabChange={(tabId) => setRoute('toolbox', tabId)} />
  }

  if (pageId === 'notification-settings') {
    return <NotificationSettings />
  }

  return null
}

function sameTarget(target: NavigationTarget, pageId: PageId, subViewId?: SubViewId) {
  return target.pageId === pageId && target.subViewId === subViewId
}

const DEFAULT_TARGET: NavigationTarget = { pageId: 'status-overview' }

function parseHash(): NavigationTarget {
  const raw = window.location.hash.replace(/^#\/?/, '')
  if (!raw) return DEFAULT_TARGET
  const [pageId, subViewId] = raw.split('/') as [PageId, SubViewId?]
  if (!(pageId in pages)) return DEFAULT_TARGET
  return { pageId, subViewId: subViewId || undefined }
}

function targetToHash(target: NavigationTarget): string {
  return `#/${target.pageId}${target.subViewId ? `/${target.subViewId}` : ''}`
}

function panelClassFor(width: PageWidth): string {
  if (width === 'full') return shell.panelFull
  if (width === 'wide') return shell.panelWide
  return shell.panel
}

function App() {
  const [activeTarget, setActiveTarget] = useState<NavigationTarget>(parseHash)

  useEffect(() => {
    const onHashChange = () => setActiveTarget(parseHash())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  useEffect(() => {
    const next = targetToHash(activeTarget)
    if (window.location.hash !== next) window.location.hash = next
  }, [activeTarget])

  const activePage = pages[activeTarget.pageId]
  const activeNavLabel = useMemo(() => activePage.title, [activePage.title])
  const setRoute = (pageId: PageId, subViewId?: SubViewId) => setActiveTarget({ pageId, subViewId })

  return (
    <div className={shell.page}>
      <aside className={shell.sidebar} aria-label="主导航">
        <div className="rounded-[0.625rem] border border-[#253552] bg-[#0d1b2e] p-3 shadow-[0_0.875rem_2rem_rgba(0,0,0,0.22)]">
          <div className="flex h-10 w-10 items-center justify-center rounded-[0.5rem] bg-[linear-gradient(135deg,#3a8bff,#7c5cff)] text-sm font-black text-white shadow-[0_0.75rem_1.5rem_rgba(93,111,255,0.28)]" aria-hidden="true">
            N
          </div>
          <h1 className="mb-0.5 mt-3 text-[1.15rem] font-black leading-tight text-white">NDRA</h1>
          <p className="m-0 text-[0.72rem] font-semibold text-[#8090ac]">netdisk resource autosave</p>
          <p className="m-0 mt-1 text-[0.72rem] font-semibold text-[#64718b]">v0.0.1</p>
        </div>

        <nav className="mt-5 grid flex-1 gap-5 overflow-y-auto pr-1" aria-label="配置导航">
          {navGroups.map((group) => (
            <section key={group.title} aria-labelledby={`${group.title}-nav-title`}>
              <h2 id={`${group.title}-nav-title`} className="mb-2 px-2 text-[0.68rem] font-bold uppercase tracking-[0.12em] text-[#64718b]">
                {group.title}
              </h2>
              <div className="grid gap-1">
                {group.items.map((item) => {
                  const isActive = sameTarget(activeTarget, item.pageId, item.subViewId)

                  return (
                    <button
                      key={`${group.title}-${item.label}`}
                      type="button"
                      aria-current={isActive ? 'page' : undefined}
                      onClick={() => setRoute(item.pageId, item.subViewId)}
                      className={`${shell.focus} flex min-h-9 w-full items-center justify-between rounded-[0.5rem] px-2.5 text-left text-[0.78rem] font-bold transition duration-150 ${
                        isActive
                          ? 'bg-[#122743] text-white shadow-[inset_0.1875rem_0_0_#3a8bff]'
                          : 'text-[#9aa9c3] hover:bg-[#0d1b2e] hover:text-white'
                      }`}
                    >
                      <span className="flex min-w-0 items-center gap-1.5">
                        <span className="w-4 shrink-0 text-center text-[0.78rem]" aria-hidden="true">{item.icon}</span>
                        <span className="truncate">{item.label}</span>
                      </span>
                      {isActive && <span className="ml-2 h-2 w-2 shrink-0 rounded-full bg-[#53d3ff] shadow-[0_0_1rem_rgba(83,211,255,0.8)]" aria-hidden="true" />}
                    </button>
                  )
                })}
              </div>
            </section>
          ))}
        </nav>
      </aside>

      <header className={shell.topbar}>
        <div className="min-w-0">
          <p className="m-0 text-[0.68rem] font-bold uppercase tracking-[0.14em] text-[#667793]">NDRA 控制台</p>
          <h2 className="m-0 truncate text-[1.05rem] font-black text-white">{activeNavLabel}</h2>
        </div>
      </header>

      <main className={shell.content}>
        <div className="px-7 py-8 max-[56rem]:px-4 max-[44rem]:py-4">
          <section className={panelClassFor(activePage.width)} aria-labelledby="active-page-title">
            <h2 id="active-page-title" className="sr-only">{activePage.title}</h2>
            {activeTarget.pageId === 'subscription-center' && (
              <div className="mb-4 rounded-[0.5rem] border border-[#6d52dd] bg-[#221a4a] px-3 py-2.5 text-[0.8rem] font-semibold leading-5 text-[#ded7ff] shadow-[0_0.75rem_1.5rem_rgba(124,92,255,0.16)]">
                <div className="mb-1 font-black text-white">订阅规则说明</div>
                <div>订阅中心用于把收集到的资源消息转换为候选转存任务；规则会保持独立配置，避免采集、转存与整理逻辑混在一起。</div>
              </div>
            )}

            <div className="min-h-[24rem]">
              {renderPageContent(activeTarget.pageId, activeTarget.subViewId, setRoute)}
            </div>
          </section>
        </div>
      </main>
    </div>
  )
}

export default App
