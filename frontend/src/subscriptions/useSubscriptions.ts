import { useCallback, useEffect, useState } from 'react'
import {
  createSubscription,
  deleteSubscription,
  getSubscriptions,
  processSubscriptions,
  testSubscription,
  updateSubscription,
} from '../api'
import type {
  SubscriptionCreateRequest,
  SubscriptionProcessRequest,
  SubscriptionProcessResponse,
  SubscriptionRule,
  SubscriptionTestRequest,
  SubscriptionTestResponse,
  SubscriptionUpdateRequest,
} from '../types'

type ActionState = {
  error: string | null
  loading: boolean
}

type SaveRule = {
  (payload: SubscriptionCreateRequest): Promise<SubscriptionRule>
  (payload: SubscriptionUpdateRequest, id: number): Promise<SubscriptionRule>
}

const idleActionState: ActionState = { error: null, loading: false }

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

export function useSubscriptions() {
  const [rules, setRules] = useState<SubscriptionRule[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saveState, setSaveState] = useState<ActionState>(idleActionState)
  const [deleteState, setDeleteState] = useState<ActionState>(idleActionState)
  const [toggleState, setToggleState] = useState<ActionState>(idleActionState)
  const [testState, setTestState] = useState<ActionState>(idleActionState)
  const [processState, setProcessState] = useState<ActionState>(idleActionState)
  const [testResult, setTestResult] = useState<SubscriptionTestResponse | null>(null)
  const [processSummary, setProcessSummary] = useState<SubscriptionProcessResponse | null>(null)

  const loadRules = useCallback(async () => {
    setLoading(true)
    setError(null)

    try {
      const response = await getSubscriptions()
      setRules(response.items)
      return response.items
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
    getSubscriptions()
      .then((response) => {
        if (mounted) {
          setRules(response.items)
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

  const createRule = useCallback(async (payload: SubscriptionCreateRequest) => {
    setSaveState({ error: null, loading: true })

    try {
      const rule = await createSubscription(payload)
      const refreshedRules = await loadRules()
      return refreshedRules.find((item) => item.id === rule.id) ?? rule
    } catch (caught) {
      const message = errorMessage(caught)
      setSaveState({ error: message, loading: false })
      throw caught
    } finally {
      setSaveState((current) => ({ ...current, loading: false }))
    }
  }, [loadRules])

  const updateRule = useCallback(async (id: number, payload: SubscriptionUpdateRequest) => {
    setSaveState({ error: null, loading: true })

    try {
      const rule = await updateSubscription(id, payload)
      const refreshedRules = await loadRules()
      return refreshedRules.find((item) => item.id === rule.id) ?? rule
    } catch (caught) {
      const message = errorMessage(caught)
      setSaveState({ error: message, loading: false })
      throw caught
    } finally {
      setSaveState((current) => ({ ...current, loading: false }))
    }
  }, [loadRules])

  const saveRule = useCallback<SaveRule>((payload: SubscriptionCreateRequest | SubscriptionUpdateRequest, id?: number) => {
    return id === undefined ? createRule(payload as SubscriptionCreateRequest) : updateRule(id, payload)
  }, [createRule, updateRule])

  const removeRule = useCallback(async (id: number) => {
    setDeleteState({ error: null, loading: true })

    try {
      const response = await deleteSubscription(id)
      if (response.deleted) {
        setRules((current) => current.filter((rule) => rule.id !== id))
      }
      return response
    } catch (caught) {
      const message = errorMessage(caught)
      setDeleteState({ error: message, loading: false })
      throw caught
    } finally {
      setDeleteState((current) => ({ ...current, loading: false }))
    }
  }, [])

  const setRuleEnabled = useCallback(async (id: number, enabled: boolean) => {
    setToggleState({ error: null, loading: true })

    try {
      const rule = await updateSubscription(id, { enabled })
      setRules((current) => current.map((item) => (item.id === id ? rule : item)))
      return rule
    } catch (caught) {
      const message = errorMessage(caught)
      setToggleState({ error: message, loading: false })
      throw caught
    } finally {
      setToggleState((current) => ({ ...current, loading: false }))
    }
  }, [])

  const runTest = useCallback(async (payload: SubscriptionTestRequest) => {
    setTestState({ error: null, loading: true })
    setTestResult(null)

    try {
      const response = await testSubscription(payload)
      setTestResult(response)
      return response
    } catch (caught) {
      const message = errorMessage(caught)
      setTestState({ error: message, loading: false })
      throw caught
    } finally {
      setTestState((current) => ({ ...current, loading: false }))
    }
  }, [])

  const runProcess = useCallback(async (payload: SubscriptionProcessRequest) => {
    setProcessState({ error: null, loading: true })
    setProcessSummary(null)

    try {
      const response = await processSubscriptions(payload)
      setProcessSummary(response)
      return response
    } catch (caught) {
      const message = errorMessage(caught)
      setProcessState({ error: message, loading: false })
      throw caught
    } finally {
      setProcessState((current) => ({ ...current, loading: false }))
    }
  }, [])

  return {
    rules,
    loading,
    error,
    saveState,
    deleteState,
    toggleState,
    testState,
    processState,
    testResult,
    processSummary,
    loadRules,
    createRule,
    updateRule,
    saveRule,
    removeRule,
    setRuleEnabled,
    runTest,
    runProcess,
  }
}
