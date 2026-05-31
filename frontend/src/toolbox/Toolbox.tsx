import AiFilenameParse from './AiFilenameParse'
import DryRun from './DryRun'
import TmdbSearch from './TmdbSearch'

export type ToolboxTabId = 'tmdb' | 'ai-filename' | 'dry-run'

type Props = {
  activeTab: ToolboxTabId
  onTabChange: (tabId: ToolboxTabId) => void
}

const tabs: Array<{ id: ToolboxTabId; label: string }> = [
  { id: 'tmdb', label: 'TMDB 搜索' },
  { id: 'ai-filename', label: 'AI 识别' },
  { id: 'dry-run', label: '干运行测试' },
]

const focusClass = 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7c5cff] focus-visible:ring-offset-2 focus-visible:ring-offset-[#0a1424]'

export default function Toolbox({ activeTab, onTabChange }: Props) {
  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap gap-1 rounded-[0.625rem] border border-[#253552] bg-[#07111f] p-1">
        {tabs.map((tab) => {
          const active = tab.id === activeTab
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => onTabChange(tab.id)}
              className={`${focusClass} h-9 rounded-[0.5rem] px-3 text-[0.78rem] font-black transition ${
                active
                  ? 'bg-[#173254] text-white shadow-[inset_0_-0.125rem_0_#53d3ff]'
                  : 'text-[#8fa0bb] hover:bg-[#0d1b2e] hover:text-white'
              }`}
            >
              {tab.label}
            </button>
          )
        })}
      </div>

      {activeTab === 'tmdb' && <TmdbSearch />}
      {activeTab === 'ai-filename' && <AiFilenameParse />}
      {activeTab === 'dry-run' && <DryRun />}
    </div>
  )
}
