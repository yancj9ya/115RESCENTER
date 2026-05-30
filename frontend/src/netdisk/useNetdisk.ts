import { useCallback, useEffect, useState } from 'react'
import { getNetdiskSettings, getNetdiskStatus, testNetdisk, updateNetdiskSettings } from '../api'

type ActionState = {
  error: string | null
  loading: boolean
}

type NetdiskSettings = Awaited<ReturnType<typeof getNetdiskSettings>>
type NetdiskStatus = Awaited<ReturnType<typeof getNetdiskStatus>>
type NetdiskTestSuccess = Awaited<ReturnType<typeof testNetdisk>>

type NetdiskTestResult = NetdiskTestSuccess & {
  error: string | null
  item_count: number | null
}

const idleActionState: ActionState = { error: null, loading: false }

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

async function loadNetdisk() {
  const [settings, status] = await Promise.all([
    getNetdiskSettings(),
    getNetdiskStatus(),
  ])

  return { settings, status }
}

export function useNetdisk() {
  const [settings, setSettings] = useState<NetdiskSettings | null>(null)
  const [status, setStatus] = useState<NetdiskStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saveState, setSaveState] = useState<ActionState>(idleActionState)
  const [testState, setTestState] = useState<ActionState>(idleActionState)
  const [testResult, setTestResult] = useState<NetdiskTestResult | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)

    try {
      const response = await loadNetdisk()
      setSettings(response.settings)
      setStatus(response.status)
      return response
    } catch (caught) {
      const message = errorMessage(caught)
      setError(message)
      throw caught
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    let mounted = true

    setLoading(true)
    setError(null)
    loadNetdisk()
      .then((response) => {
        if (mounted) {
          setSettings(response.settings)
          setStatus(response.status)
          setLoading(false)
        }
      })
      .catch((caught) => {
        if (mounted) {
          setError(errorMessage(caught))
          setLoading(false)
        }
      })

    return () => {
      mounted = false
    }
  }, [])

  const saveSettings = useCallback(async (payload: Parameters<typeof updateNetdiskSettings>[0]) => {
    setSaveState({ error: null, loading: true })

    try {
      const response = await updateNetdiskSettings(payload)
      setSettings(response)
      await refresh()
      return response
    } catch (caught) {
      const message = errorMessage(caught)
      setSaveState({ error: message, loading: false })
      throw caught
    } finally {
      setSaveState((current) => ({ ...current, loading: false }))
    }
  }, [refresh])

  const testCid = useCallback(async (cid?: number) => {
    setTestState({ error: null, loading: true })
    setTestResult(null)

    try {
      const response = await testNetdisk(cid === undefined ? {} : { cid })
      const result: NetdiskTestResult = {
        ...response,
        error: response.error,
        item_count: response.item_count,
      }
      setTestResult(result)
      return result
    } catch (caught) {
      const message = errorMessage(caught)
      const result: NetdiskTestResult = {
        configured: false,
        error: message,
        item_count: null,
        ok: false,
        status: 'error',
      }
      setTestState({ error: message, loading: false })
      setTestResult(result)
      return result
    } finally {
      setTestState((current) => ({ ...current, loading: false }))
    }
  }, [])

  return {
    saveSettings,
    saveState,
    settings,
    status,
    loading,
    error,
    testState,
    testResult,
    refresh,
    testCid,
  }
}
