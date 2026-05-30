import { useCallback, useEffect, useState } from 'react'
import {
  createTelegramWebChannel,
  deleteTelegramWebChannel,
  disableTelegramWebChannel,
  enableTelegramWebChannel,
  getTelegramWebChannels,
  getTelegramWebChannelStatus,
  updateTelegramWebChannel,
} from '../api'
import type {
  TelegramWebChannel,
  TelegramWebChannelCreateRequest,
  TelegramWebChannelDeleteResponse,
  TelegramWebChannelListResponse,
  TelegramWebChannelStatusResponse,
  TelegramWebChannelUpdateRequest,
} from '../types'

type ActionState = {
  error: string | null
  loading: boolean
}

type SaveChannel = {
  (payload: TelegramWebChannelCreateRequest): Promise<TelegramWebChannel>
  (payload: TelegramWebChannelUpdateRequest, channel: string): Promise<TelegramWebChannel>
}

const idleActionState: ActionState = { error: null, loading: false }

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function listItems(response: TelegramWebChannelListResponse): TelegramWebChannel[] {
  return response.items
}

export function useTelegramWebChannels() {
  const [channels, setChannels] = useState<TelegramWebChannel[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saveState, setSaveState] = useState<ActionState>(idleActionState)
  const [deleteState, setDeleteState] = useState<ActionState>(idleActionState)
  const [toggleState, setToggleState] = useState<ActionState>(idleActionState)
  const [statusState, setStatusState] = useState<ActionState>(idleActionState)
  const [statusByChannel, setStatusByChannel] = useState<Record<string, TelegramWebChannelStatusResponse>>({})

  const loadChannels = useCallback(async () => {
    setLoading(true)
    setError(null)

    try {
      const response = await getTelegramWebChannels()
      const items = listItems(response)
      setChannels(items)
      return items
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
    getTelegramWebChannels()
      .then((response) => {
        if (mounted) {
          setChannels(listItems(response))
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

  function storeChannel(channel: TelegramWebChannel) {
    setChannels((current) => {
      const existing = current.some((item) => item.channel === channel.channel)
      return existing
        ? current.map((item) => (item.channel === channel.channel ? channel : item))
        : [...current, channel]
    })
  }

  const createChannel = useCallback(async (payload: TelegramWebChannelCreateRequest) => {
    setSaveState({ error: null, loading: true })

    try {
      const channel = await createTelegramWebChannel(payload)
      storeChannel(channel)
      return channel
    } catch (caught) {
      const message = errorMessage(caught)
      setSaveState({ error: message, loading: false })
      throw caught
    } finally {
      setSaveState((current) => ({ ...current, loading: false }))
    }
  }, [])

  const updateChannel = useCallback(async (channelName: string, payload: TelegramWebChannelUpdateRequest) => {
    setSaveState({ error: null, loading: true })

    try {
      const channel = await updateTelegramWebChannel(channelName, payload)
      storeChannel(channel)
      return channel
    } catch (caught) {
      const message = errorMessage(caught)
      setSaveState({ error: message, loading: false })
      throw caught
    } finally {
      setSaveState((current) => ({ ...current, loading: false }))
    }
  }, [])

  const saveChannel = useCallback<SaveChannel>((payload: TelegramWebChannelCreateRequest | TelegramWebChannelUpdateRequest, channelName?: string) => {
    return channelName === undefined ? createChannel(payload as TelegramWebChannelCreateRequest) : updateChannel(channelName, payload)
  }, [createChannel, updateChannel])

  const removeChannel = useCallback(async (channelName: string): Promise<TelegramWebChannelDeleteResponse> => {
    setDeleteState({ error: null, loading: true })

    try {
      const response = await deleteTelegramWebChannel(channelName)
      if (response.deleted) {
        setChannels((current) => current.filter((channel) => channel.channel !== channelName))
        setStatusByChannel((current) => {
          const next = { ...current }
          delete next[channelName]
          return next
        })
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

  const setChannelEnabled = useCallback(async (channelName: string, enabled: boolean) => {
    setToggleState({ error: null, loading: true })

    try {
      const channel = enabled ? await enableTelegramWebChannel(channelName) : await disableTelegramWebChannel(channelName)
      setChannels((current) => current.map((item) => (item.channel === channelName ? channel : item)))
      return channel
    } catch (caught) {
      const message = errorMessage(caught)
      setToggleState({ error: message, loading: false })
      throw caught
    } finally {
      setToggleState((current) => ({ ...current, loading: false }))
    }
  }, [])

  const checkChannelStatus = useCallback(async (channelName: string) => {
    setStatusState({ error: null, loading: true })

    try {
      const response = await getTelegramWebChannelStatus(channelName)
      setStatusByChannel((current) => ({ ...current, [channelName]: response }))
      return response
    } catch (caught) {
      const message = errorMessage(caught)
      setStatusState({ error: message, loading: false })
      throw caught
    } finally {
      setStatusState((current) => ({ ...current, loading: false }))
    }
  }, [])

  return {
    channels,
    loading,
    error,
    saveState,
    deleteState,
    toggleState,
    statusState,
    statusByChannel,
    loadChannels,
    createChannel,
    updateChannel,
    saveChannel,
    removeChannel,
    setChannelEnabled,
    checkChannelStatus,
  }
}
