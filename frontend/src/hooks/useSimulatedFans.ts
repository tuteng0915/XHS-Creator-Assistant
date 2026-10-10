import { useCallback, useEffect, useRef, useState } from 'react'
import { simulatedFanApi } from '../api'
import type { SimulatedFan } from '../types'

export function useSimulatedFans(workspaceId: string, completedAnalyses: string) {
  const current = useRef(workspaceId)
  const sequence = useRef(0)
  const [state, setState] = useState<{workspaceId:string; rows:SimulatedFan[]; slots:string[]}>({workspaceId:'',rows:[],slots:['','','']})
  const [error, setError] = useState('')
  const [pendingWorkspace, setPendingWorkspace] = useState('')
  useEffect(() => {
    current.current = workspaceId; setError('')
    return () => {current.current = ''; sequence.current += 1}
  }, [workspaceId])
  const refresh = useCallback(async (requireSuccess = false) => {
    if (!workspaceId || current.current !== workspaceId) {
      if (requireSuccess) throw new Error('账号已切换，请重新打开粉丝列表。')
      return
    }
    const request = ++sequence.current
    setPendingWorkspace(workspaceId)
    try {
      const rows = await simulatedFanApi.list(workspaceId)
      if (current.current !== workspaceId || sequence.current !== request) {
        if (requireSuccess) throw new Error('列表刷新已被新的请求替代，请重试刷新。')
        return
      }
      setState(previous => ({workspaceId, rows, slots: previous.workspaceId === workspaceId
        ? previous.slots.map(id => rows.some(r => r.id === id && r.status === 'active') ? id : '')
        : ['','','']}))
      setError('')
    } catch(e) {
      if(current.current === workspaceId && sequence.current === request) setError(String(e))
      if (requireSuccess) throw e
    } finally {
      if(current.current === workspaceId && sequence.current === request) setPendingWorkspace('')
    }
  }, [workspaceId])
  const refreshAfterSave = useCallback(() => refresh(true), [refresh])
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
  function applySelection(selectedIds: string[]) {
    if (!selectedIds.length || new Set(selectedIds).size !== selectedIds.length ||
      selectedIds.some(id => !rows.some(row => row.id === id && row.status === 'active'))) return false
    setState(s => s.workspaceId === workspaceId ? {...s, slots: [
      ...selectedIds, ...Array(Math.max(0, 3 - selectedIds.length)).fill(''),
    ]} : s)
    return true
  }
  const loading = pendingWorkspace === workspaceId && !!workspaceId
  const loaded = state.workspaceId === workspaceId
  return {rows,slots,ids,error,loading,loaded,refresh,refreshAfterSave,setSlot,addSlot,removeSlot,applySelection}
}
