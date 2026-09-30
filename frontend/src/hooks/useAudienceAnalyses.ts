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
    let active = true
    let timer: ReturnType<typeof setTimeout>
    current.current = workspaceId
    setRows([]); setSelectedId(''); setError('')
    async function load() {
      try {await refresh()} catch { /* refresh owns the visible error state. */ }
      if(active) timer = setTimeout(() => void load(), 2000)
    }
    if(workspaceId) void load()
    return () => {active=false; current.current=''; sequence.current += 1; clearTimeout(timer)}
  }, [workspaceId, refresh])
  const safeRows = rows.filter(row => row.workspaceId === workspaceId)
  const selected = safeRows.find(row => row.id === selectedId) || safeRows.find(row => ['completed', 'partially_completed'].includes(row.status))
  return {rows:safeRows, selectedId, setSelectedId, selected, refresh, error}
}
