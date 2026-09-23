import { useCallback, useEffect, useState } from 'react'
import { audienceAnalysisApi } from '../api'
import type { AudienceAnalysis } from '../types'

export function useAudienceAnalyses(workspaceId: string) {
  const [rows, setRows] = useState<AudienceAnalysis[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [error, setError] = useState('')
  const refresh = useCallback(async () => {
    if (!workspaceId) return
    const loaded = await audienceAnalysisApi.list(workspaceId)
    setRows(loaded)
    setError('')
  }, [workspaceId])
  useEffect(() => {
    let active = true
    let timer: ReturnType<typeof setTimeout>
    setRows([]); setSelectedId(''); setError('')
    async function load() {
      try {const loaded = await audienceAnalysisApi.list(workspaceId); if (active) {setRows(loaded); setError('')}}
      catch (e) {if(active) setError(e instanceof Error ? e.message : String(e))}
      if(active) timer = setTimeout(() => void load(), 2000)
    }
    if(workspaceId) void load()
    return () => {active=false; clearTimeout(timer)}
  }, [workspaceId])
  const safeRows = rows.filter(row => row.workspaceId === workspaceId)
  const selected = safeRows.find(row => row.id === selectedId) || safeRows.find(row => row.status === 'completed')
  return {rows:safeRows, selectedId, setSelectedId, selected, refresh, error}
}
