import { useState } from 'react'
import { discoverTmdbAliases, discoverTmdbSearch } from '../api'
import type { TmdbAliasBundleResponse, TmdbDiscoverySearchItem } from '../types'

const fieldClass =
  'h-9 w-full rounded-[0.5rem] border border-[#253552] bg-[#07111f] px-3 text-[0.82rem] font-semibold text-[#dbe7ff] placeholder:text-[#5f6e86] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7c5cff]'
const btnClass =
  'h-9 rounded-[0.5rem] bg-[linear-gradient(135deg,#3a8bff,#7c5cff)] px-4 text-[0.8rem] font-black text-white transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60'
const quietBtnClass =
  'h-7 rounded-[0.45rem] border border-[#253552] bg-[#0d1b2e] px-2.5 text-[0.72rem] font-black text-[#c5d3ed] transition hover:border-[#3a8bff] hover:text-white disabled:opacity-55'

export default function TmdbSearch() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<TmdbDiscoverySearchItem[]>([])
  const [aliases, setAliases] = useState<TmdbAliasBundleResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [aliasLoading, setAliasLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault()
    if (!query.trim()) return
    setLoading(true)
    setError(null)
    setResults([])
    setAliases(null)
    try {
      const data = await discoverTmdbSearch(query.trim(), 12)
      setResults(data.items)
      if (data.items.length === 0) setError('未找到匹配结果')
    } catch (err) {
      setError(err instanceof Error ? err.message : '搜索失败')
    } finally {
      setLoading(false)
    }
  }

  async function handleLoadAliases(item: TmdbDiscoverySearchItem) {
    setAliasLoading(true)
    setAliases(null)
    try {
      const data = await discoverTmdbAliases(item.kind, item.tmdb_id)
      setAliases(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : '获取别名失败')
    } finally {
      setAliasLoading(false)
    }
  }

  return (
    <div className="grid gap-4">
      <form className="flex gap-2" onSubmit={handleSearch}>
        <input
          className={fieldClass}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="输入电影或剧集名称..."
        />
        <button type="submit" className={btnClass} disabled={loading || !query.trim()}>
          {loading ? '搜索中...' : '搜索'}
        </button>
      </form>

      {error && (
        <p className="rounded-[0.5rem] border border-[#7d3b58] bg-[#160d18] px-3 py-2 text-[0.78rem] text-[#ff9fb4]">
          {error}
        </p>
      )}

      {results.length > 0 && (
        <div className="grid gap-2 sm:grid-cols-2">
          {results.map((item) => (
            <div
              key={`${item.kind}-${item.tmdb_id}`}
              className="rounded-[0.5rem] border border-[#253552] bg-[#07111f] p-3"
            >
              <div className="mb-1 flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <span className="text-[0.82rem] font-black text-white">{item.title}</span>
                  {item.year && <span className="ml-1.5 text-[0.72rem] text-[#64718b]">{item.year}</span>}
                </div>
                <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[0.62rem] font-black ${item.kind === 'movie' ? 'border-[#1d4a6a] bg-[#0a2a40] text-[#53d3ff]' : 'border-[#3a2a6a] bg-[#1a1040] text-[#b09fff]'}`}>
                  {item.kind === 'movie' ? '电影' : '剧集'}
                </span>
              </div>
              {item.original_title !== item.title && (
                <div className="mb-1 text-[0.72rem] text-[#64718b]">{item.original_title}</div>
              )}
              {item.overview && (
                <div className="mb-2 line-clamp-2 text-[0.72rem] leading-4 text-[#91a0bb]">{item.overview}</div>
              )}
              <div className="flex items-center justify-between gap-2">
                <span className="text-[0.68rem] text-[#4a5a72]">TMDB #{item.tmdb_id}</span>
                <button
                  type="button"
                  className={quietBtnClass}
                  onClick={() => void handleLoadAliases(item)}
                  disabled={aliasLoading}
                >
                  {aliasLoading ? '加载中...' : '查看别名'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {aliases && (
        <div className="rounded-[0.5rem] border border-[#253552] bg-[#0a1424] p-3">
          <div className="mb-2 flex items-center gap-2">
            <span className="text-[0.82rem] font-black text-white">{aliases.title}</span>
            {aliases.year && <span className="text-[0.72rem] text-[#64718b]">{aliases.year}</span>}
            <span className="ml-auto text-[0.68rem] text-[#4a5a72]">TMDB #{aliases.tmdb_id}</span>
          </div>
          {aliases.aliases.length === 0 ? (
            <p className="text-[0.78rem] text-[#64718b]">暂无别名数据</p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {aliases.aliases.map((alias) => (
                <span key={alias} className="rounded-[0.4rem] border border-[#253552] bg-[#07111f] px-2 py-0.5 text-[0.72rem] text-[#c5d3ed]">
                  {alias}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
