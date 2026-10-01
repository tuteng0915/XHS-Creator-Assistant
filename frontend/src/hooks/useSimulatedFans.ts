import { useCallback, useEffect, useRef, useState } from 'react'
import { simulatedFanApi } from '../api'
import type { SimulatedFan } from '../types'

export function useSimulatedFans(workspaceId: string, completedAnalyses: string) {
  const current = useRef(workspaceId)
  const sequence = useRef(0)
  const [state, setState] = useState<{workspaceId:string; rows:SimulatedFan[]; slots:string[]}>({workspaceId:'',rows:[],slots:['','','']})
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
      setState(previous => ({workspaceId, rows, slots: previous.workspaceId === workspaceId && previous.rows.length
        ? previous.slots.map(id => rows.some(r => r.id === id && r.status === 'active') ? id : '')
        : Array.from({length:3},(_,index) => rows.filter(r => r.status === 'active')[index]?.id || '')}))
      setError('')
    } catch(e) {if(current.current === workspaceId && sequence.current === request) setError(String(e))}
  }, [workspaceId])
  useEffect(() => {void refresh()}, [refresh, completedAnalyses])
  const rows = state.workspaceId === workspaceId ? state.rows : []
  const slots = state.workspaceId === workspaceId ? state.slots : ['','','']
  const ids = slots.filter(Boolean)
  function setSlot(index: number, id: string) {
    setState(s => {
      if (s.workspaceId !== workspaceId || index < 0 || index >= s.slots.length ||
        (id && (!s.rows.some(row => row.id === id && row.status === 'active') || s.slots.some((value, i) => i !== index && value === id)))) return s
      return {...s, slots:s.slots.map((value, i) => i === index ? id : value)}
    })
  }
  function addSlot() {
    setState(s => s.workspaceId === workspaceId ? {...s,slots:[...s.slots,'']} : s)
  }
  function removeSlot(index:number) {
    setState(s => s.workspaceId === workspaceId && index >= 3 && index < s.slots.length
      ? {...s,slots:s.slots.filter((_,i) => i !== index)} : s)
  }
  return {rows,slots,ids,error,refresh,setSlot,addSlot,removeSlot}
}
