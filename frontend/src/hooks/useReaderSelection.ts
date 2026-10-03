import { useEffect, useRef, useState } from 'react'
import { readerSelectionApi } from '../api'
import type { ReaderSelection } from '../readerSelection'

type Receipt = {requestKey: string; desiredCount: number; id?: string}
type View = {key: string; revision: string; record: ReaderSelection | null; busy: boolean; error: string}
export const readerSelectionStorageKey = (workspaceId: string, topicId: string) =>
  `reader-selection:${workspaceId}:${topicId}`

function read(key: string): Receipt | null {
  try {
    const value = JSON.parse(window.localStorage.getItem(key) || 'null')
    return value && typeof value.requestKey === 'string' && Number.isInteger(value.desiredCount)
      && value.desiredCount > 0 && (value.id === undefined || typeof value.id === 'string') ? value : null
  } catch { return null }
}

export function useReaderSelection(workspaceId: string, topicId: string, revision: string) {
  const key = readerSelectionStorageKey(workspaceId, topicId)
  const epoch = useRef(0)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const locked = useRef(false)
  const [view, setView] = useState<View>({key: '', revision: '', record: null, busy: false, error: ''})

  function cancelTimer() { clearTimeout(timer.current) }
  async function observe(receipt: Receipt, turn: number): Promise<ReaderSelection | null> {
    if (!receipt.id) return null
    try {
      const record = await readerSelectionApi.get(workspaceId, receipt.id)
      if (turn !== epoch.current) return null
      if (record.workspaceId !== workspaceId || record.id !== receipt.id) throw new Error('推荐不属于当前账号')
      const busy = ['pending', 'running'].includes(record.status)
      setView({key, revision, record, busy, error: ''})
      locked.current = busy
      if (busy) timer.current = setTimeout(() => { void observe(receipt, turn) }, 1000)
      return record
    } catch (error) {
      if (turn === epoch.current) {
        locked.current = false
        setView(current => ({...current, key, revision, busy: false, error: String(error)}))
      }
      return null
    }
  }

  async function refresh() {
    cancelTimer()
    const turn = ++epoch.current
    const receipt = read(key)
    if (!receipt?.id) return null
    locked.current = true
    setView(current => ({...current, key, revision, busy: true, error: ''}))
    return observe(receipt, turn)
  }

  useEffect(() => {
    const generation = epoch
    const turn = ++epoch.current
    locked.current = false
    setView({key, revision, record: null, busy: false, error: ''})
    const receipt = read(key)
    if (workspaceId && topicId && receipt?.id) {
      locked.current = true
      setView({key, revision, record: null, busy: true, error: ''})
      void observe(receipt, turn)
    } else if (receipt) {
      setView({key, revision, record: null, busy: false, error: '上次请求尚未确认，可重试原请求。'})
    }
    return () => { ++generation.current; locked.current = false; cancelTimer() }
    // The epoch binds each observer to this account, topic and asset revision.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, revision])

  async function recommend(desiredCount: number) {
    if (!workspaceId || !topicId || locked.current) return
    cancelTimer()
    const turn = ++epoch.current
    locked.current = true
    setView({key, revision, record: null, busy: true, error: ''})
    const previous = read(key)
    const receipt: Receipt = previous && !previous.id ? previous : {
      requestKey: crypto.randomUUID(), desiredCount,
    }
    try {
      // Persist before sending, so a lost response can be retried with the same key.
      window.localStorage.setItem(key, JSON.stringify(receipt))
      const record = await readerSelectionApi.create(workspaceId, {
        requestKey: receipt.requestKey, desiredCount: receipt.desiredCount, topicId,
      })
      if (record.workspaceId !== workspaceId) throw new Error('推荐不属于当前账号')
      const confirmed = {...receipt, id: record.id}
      // A late response may update its own receipt, never another request's or account's view.
      if (read(key)?.requestKey === receipt.requestKey) window.localStorage.setItem(key, JSON.stringify(confirmed))
      if (turn !== epoch.current) return
      await observe(confirmed, turn)
    } catch (error) {
      if (turn === epoch.current) {
        locked.current = false
        setView({key, revision, record: null, busy: false, error: String(error)})
      }
    }
  }
  const current = view.key === key && view.revision === revision
    ? view : {key, revision, record: null, busy: true, error: ''}
  return {...current, recommend, refresh, hasReceipt: Boolean(read(key)?.id)}
}
