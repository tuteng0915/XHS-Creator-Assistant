import { useCallback, useEffect, useRef, useState } from 'react'
import { audienceAnalysisApi } from '../api'
import type { AudienceAnalysis } from '../types'

export function useAudienceAnalyses(workspaceId: string) {
  const [rows, setRows] = useState<AudienceAnalysis[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [error, setError] = useState('')
  const current = useRef(workspaceId)
  const sequence = useRef(0)
  const refresh = useCallback(async () => {
    if (!workspaceId || current.current !== workspaceId) return
    const request = ++sequence.current
    try {
      const loaded = await audienceAnalysisApi.list(workspaceId)
      if (current.current !== workspaceId || sequence.current !== request) return
      setRows(loaded); setError('')
    } catch(e) {
      if (current.current === workspaceId && sequence.current === request) {
        setError(e instanceof Error ? e.message : String(e))
        throw e
      }
    }
  }, [workspaceId])
  useEffect(() => {
    current.current = workspaceId
    setRows([]); setSelectedId(''); setError('')
    if(workspaceId) void refresh().catch(() => { /* refresh owns the visible error state. */ })
    return () => {current.current=''; sequence.current += 1}
  }, [workspaceId, refresh])
  const safeRows = rows.filter(row => row.workspaceId === workspaceId)
  const running = safeRows.some(row => row.status === 'pending' || row.status === 'running')
  useEffect(() => {
    if (!workspaceId || !running) return
    let active = true
    let timer: ReturnType<typeof setTimeout>
    async function poll() {
      try {await refresh()} catch { /* Preserve the last visible result and retry active work. */ }
      if (active) timer = setTimeout(() => void poll(), 2000)
    }
    timer = setTimeout(() => void poll(), 2000)
    return () => {active = false; clearTimeout(timer)}
  }, [workspaceId, running, refresh])
  const selected = safeRows.find(row => row.id === selectedId) || safeRows.find(row => ['completed', 'partially_completed'].includes(row.status))
  return {rows:safeRows, selectedId, setSelectedId, selected, refresh, error}
}
