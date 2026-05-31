import { useEffect, useState } from 'react'
import { getAiSettings, listAiModels, parseAiFilename, updateAiSettings } from '../api'
import type { AiFilenameParseResult } from '../types'

const fieldClass =
  'h-9 w-full rounded-[0.5rem] border border-[#253552] bg-[#07111f] px-3 text-[0.82rem] font-semibold text-[#dbe7ff] placeholder:text-[#5f6e86] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7c5cff]'
const textareaClass =
  'w-full rounded-[0.5rem] border border-[#253552] bg-[#07111f] px-3 py-2 text-[0.78rem] font-semibold leading-5 text-[#dbe7ff] placeholder:text-[#5f6e86] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7c5cff] resize-y'
const btnClass =
  'h-9 rounded-[0.5rem] bg-[linear-gradient(135deg,#3a8bff,#7c5cff)] px-4 text-[0.8rem] font-black text-white transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60'
const labelClass = 'grid gap-1.5 text-[0.78rem] font-bold text-[#9aa9c3]'

const DEFAULT_PROMPT = ''

function resultRows(result: AiFilenameParseResult): Array<[string, string]> {
  const rows: Array<[string, string]> = [
    ['类型', result.type === 'movie' ? '电影' : result.type === 'tv' ? '剧集' : '未识别'],
    ['标题', result.title],
    ['原始标题', result.original_title ?? ''],
    ['年份', result.year?.toString() ?? ''],
    ['季', result.season?.toString() ?? ''],
    ['集', result.episode?.toString() ?? ''],
    ['分辨率', result.resolution ?? ''],
    ['来源', result.source ?? ''],
    ['发布组', result.release_group ?? ''],
    ['音频编码', result.audio_codec ?? ''],
    ['视频编码', result.video_codec ?? ''],
  ]
  return rows.filter(([, value]) => value.trim().length > 0)
}

export default function AiFilenameParse() {
  const [filename, setFilename] = useState('')
  const [enabled, setEnabled] = useState(true)
  const [provider, setProvider] = useState('openai_compatible')
  const [baseUrl, setBaseUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [model, setModel] = useState('')
  const [models, setModels] = useState<string[]>([])
  const [modelsLoading, setModelsLoading] = useState(false)
  const [modelsError, setModelsError] = useState<string | null>(null)
  const [timeoutSeconds, setTimeoutSeconds] = useState('30')
  const [threshold, setThreshold] = useState('0.55')
  const [prompt, setPrompt] = useState(DEFAULT_PROMPT)
  const [hasSavedApiKey, setHasSavedApiKey] = useState(false)
  const [settingsLoading, setSettingsLoading] = useState(true)
  const [settingsSaving, setSettingsSaving] = useState(false)
  const [settingsMessage, setSettingsMessage] = useState<string | null>(null)
  const [result, setResult] = useState<AiFilenameParseResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function loadSettings() {
      setSettingsLoading(true)
      setSettingsMessage(null)
      try {
        const data = await getAiSettings()
        if (cancelled) return
        setEnabled(data.enabled)
        setProvider(data.provider || 'openai_compatible')
        setBaseUrl(data.base_url)
        setModel(data.model)
        setTimeoutSeconds(String(data.timeout_seconds))
        setThreshold(String(data.title_similarity_threshold))
        setPrompt(data.prompt)
        setHasSavedApiKey(data.has_api_key)
      } catch (err) {
        if (!cancelled) setSettingsMessage(err instanceof Error ? err.message : '读取 AI 设置失败')
      } finally {
        if (!cancelled) setSettingsLoading(false)
      }
    }
    void loadSettings()
    return () => {
      cancelled = true
    }
  }, [])

  async function handleSaveSettings() {
    setSettingsSaving(true)
    setSettingsMessage(null)
    try {
      const data = await updateAiSettings({
        enabled,
        provider: provider.trim() || 'openai_compatible',
        api_key: apiKey.trim() || null,
        base_url: baseUrl.trim(),
        model: model.trim(),
        timeout_seconds: Number(timeoutSeconds) || 30,
        title_similarity_threshold: Number(threshold) || 0.55,
        prompt,
      })
      setEnabled(data.enabled)
      setProvider(data.provider || 'openai_compatible')
      setBaseUrl(data.base_url)
      setModel(data.model)
      setTimeoutSeconds(String(data.timeout_seconds))
      setThreshold(String(data.title_similarity_threshold))
      setPrompt(data.prompt)
      setHasSavedApiKey(data.has_api_key)
      setApiKey('')
      setSettingsMessage('已保存 AI 设置')
    } catch (err) {
      setSettingsMessage(err instanceof Error ? err.message : '保存 AI 设置失败')
    } finally {
      setSettingsSaving(false)
    }
  }

  async function handleLoadModels() {
    setModelsLoading(true)
    setModelsError(null)
    setModels([])
    try {
      const data = await listAiModels({
        provider: provider.trim() || 'openai_compatible',
        api_key: apiKey,
        base_url: baseUrl.trim(),
        timeout_seconds: Number(timeoutSeconds) || 30,
      })
      setModels(data.models)
      if (data.models.length > 0 && !model.trim()) setModel(data.models[0])
      if (data.models.length === 0) setModelsError('未获取到可用模型')
    } catch (err) {
      setModelsError(err instanceof Error ? err.message : '获取模型失败')
    } finally {
      setModelsLoading(false)
    }
  }

  async function handleParse(e: React.FormEvent) {
    e.preventDefault()
    if (!filename.trim()) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const data = await parseAiFilename({
        filename: filename.trim(),
        enabled: true,
        provider: provider.trim() || 'openai_compatible',
        api_key: apiKey,
        base_url: baseUrl.trim(),
        model: model.trim(),
        timeout_seconds: Number(timeoutSeconds) || 30,
        title_similarity_threshold: Number(threshold) || 0.55,
        prompt,
      })
      setResult(data.result)
      if (!data.result) setError('AI 未返回可用解析结果')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'AI 识别失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="grid gap-4">
      <form className="grid gap-4" onSubmit={handleParse}>
        <label className={labelClass}>
          <span>文件名</span>
          <input
            className={fieldClass}
            value={filename}
            onChange={(e) => setFilename(e.target.value)}
            placeholder="主角.2026.S01E38.2160p.WEB-DL.H.265-XH.mkv"
          />
        </label>

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="flex items-center gap-2 text-[0.78rem] font-bold text-[#9aa9c3]">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
              className="h-4 w-4 accent-[#3a8bff]"
            />
            <span>启用 AI 兜底</span>
          </label>
          <label className={labelClass}>
            <span>Provider</span>
            <input className={fieldClass} value={provider} onChange={(e) => setProvider(e.target.value)} />
          </label>
          <label className={labelClass}>
            <span>Model</span>
            <div className="flex gap-2">
              <select className={fieldClass} value={model} onChange={(e) => setModel(e.target.value)}>
                <option value="">手动输入或选择模型</option>
                {models.map((item) => (
                  <option key={item} value={item}>{item}</option>
                ))}
              </select>
              <button
                type="button"
                className="h-9 shrink-0 rounded-[0.5rem] border border-[#253552] bg-[#0d1b2e] px-3 text-[0.75rem] font-black text-[#c5d3ed] transition hover:border-[#3a8bff] hover:text-white disabled:opacity-55"
                onClick={() => void handleLoadModels()}
                disabled={modelsLoading || !baseUrl.trim() || (!apiKey.trim() && !hasSavedApiKey)}
              >
                {modelsLoading ? '获取中' : '获取模型'}
              </button>
            </div>
            <input className={fieldClass} value={model} onChange={(e) => setModel(e.target.value)} placeholder="model name" />
            {modelsError && <span className="text-[0.72rem] font-semibold text-[#ff9fb4]">{modelsError}</span>}
          </label>
          <label className={labelClass}>
            <span>Base URL</span>
            <input className={fieldClass} value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://api.example.com/v1" />
          </label>
          <label className={labelClass}>
            <span>API Key</span>
            <input
              className={fieldClass}
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={hasSavedApiKey ? '已保存，留空不修改' : 'sk-...'}
            />
          </label>
          <label className={labelClass}>
            <span>Timeout Seconds</span>
            <input className={fieldClass} type="number" min="1" step="0.5" value={timeoutSeconds} onChange={(e) => setTimeoutSeconds(e.target.value)} />
          </label>
          <label className={labelClass}>
            <span>Title Similarity Threshold</span>
            <input className={fieldClass} type="number" min="0" max="1" step="0.01" value={threshold} onChange={(e) => setThreshold(e.target.value)} />
          </label>
        </div>

        <label className={labelClass}>
          <span>Prompt</span>
          <textarea
            className={textareaClass}
            rows={8}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="留空使用后端内置默认提示词"
          />
        </label>

        <div className="flex flex-wrap gap-2">
          <button type="submit" className={btnClass} disabled={loading || !filename.trim() || settingsLoading}>
            {loading ? '识别中...' : '开始识别'}
          </button>
          <button
            type="button"
            className="h-9 rounded-[0.5rem] border border-[#253552] bg-[#0d1b2e] px-4 text-[0.8rem] font-black text-[#c5d3ed] transition hover:border-[#3a8bff] hover:text-white disabled:opacity-55"
            onClick={() => void handleSaveSettings()}
            disabled={settingsSaving || settingsLoading || !baseUrl.trim() || !model.trim() || (!apiKey.trim() && !hasSavedApiKey)}
          >
            {settingsSaving ? '保存中' : '保存设置'}
          </button>
        </div>
      </form>

      {settingsMessage && (
        <p className="rounded-[0.5rem] border border-[#253552] bg-[#0a1424] px-3 py-2 text-[0.78rem] text-[#c5d3ed]">
          {settingsMessage}
        </p>
      )}

      {error && (
        <p className="rounded-[0.5rem] border border-[#7d3b58] bg-[#160d18] px-3 py-2 text-[0.78rem] text-[#ff9fb4]">
          {error}
        </p>
      )}

      {result && (
        <div className="rounded-[0.5rem] border border-[#253552] bg-[#0a1424] p-3">
          <div className="mb-2 text-[0.78rem] font-black text-white">识别结果</div>
          <div className="grid gap-1.5 sm:grid-cols-2">
            {resultRows(result).map(([label, value]) => (
              <div key={label} className="rounded-[0.45rem] border border-[#1d2a46] bg-[#07111f] px-2.5 py-2">
                <div className="text-[0.62rem] font-black uppercase tracking-[0.1em] text-[#667793]">{label}</div>
                <div className="mt-0.5 break-words text-[0.82rem] font-black text-[#dbe7ff]">{value}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
