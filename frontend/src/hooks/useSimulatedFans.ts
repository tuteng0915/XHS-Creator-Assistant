import { useCallback, useEffect, useRef, useState } from 'react'
import { simulatedFanApi } from '../api'
import type { SimulatedFan } from '../types'

export function useSimulatedFans(workspaceId: string, completedAnalyses: string) {
  const current = useRef(workspaceId)
  const sequence = useRef(0)
  const [state, setState] = useState<{workspaceId:string; rows:SimulatedFan[]; ids:string[]}>({workspaceId:'',rows:[],ids:[]})
  const [error, setError] = useState('')
  useEffect(() => {
    current.current = workspaceId; setError('')
    return () => {current.current = ''; sequence.current += 1}
  }, [workspaceId])
  const refresh = useCallback(async () => {
    if (!workspaceId || current.current !== workspaceId) return
    const request = ++sequence.current
    try {
      const rows = await simulatedFanApi.list(workspaceId)
      if (current.current !== workspaceId || sequence.current !== request) return
      setState(previous => ({workspaceId, rows, ids: previous.workspaceId === workspaceId && previous.rows.length
        ? previous.ids.filter(id => rows.some(r => r.id === id && r.status === 'active'))
        : rows.filter(r => r.status === 'active').slice(0,3).map(r => r.id)}))
      setError('')
    } catch(e) {if(current.current === workspaceId && sequence.current === request) setError(String(e))}
  }, [workspaceId])
  useEffect(() => {void refresh()}, [refresh, completedAnalyses])
  const rows = state.workspaceId === workspaceId ? state.rows : []
  const ids = state.workspaceId === workspaceId ? state.ids : []
  function toggle(id: string) {
    setState(s => s.workspaceId !== workspaceId || !s.rows.some(row => row.id === id && row.status === 'active') ? s : {...s,ids:s.ids.includes(id) ? s.ids.filter(v => v !== id) : s.ids.length < 3 ? [...s.ids,id] : s.ids})
  }
  return {rows,ids,error,refresh,toggle}
}
