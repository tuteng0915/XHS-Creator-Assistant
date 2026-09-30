import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { simulatedFanApi } from '../api'
import type { SimulatedFan } from '../types'
import { useSimulatedFans } from './useSimulatedFans'

afterEach(() => {cleanup();vi.restoreAllMocks()})
const fan = (workspaceId:string,id:string):SimulatedFan => ({id,workspaceId,sourceAnalysisId:'a',sourceGroupId:id,original:{},editable:{name:id,profile:'关注点',coreConcern:'',contentPreference:'',expressionStyle:''},status:'active',createdAt:'',updatedAt:''})

it('defaults to three, retains explicit deselection and removes archived selections', async () => {
  const rows = ['1','2','3','4'].map(id=>fan('w',id))
  const list = vi.spyOn(simulatedFanApi,'list').mockResolvedValue(rows)
  const {result} = renderHook(() => useSimulatedFans('w','analysis'))
  await waitFor(() => expect(result.current.ids).toEqual(['1','2','3']))
  act(() => result.current.toggle('2'))
  await act(async () => result.current.refresh())
  expect(result.current.ids).toEqual(['1','3'])
  list.mockResolvedValue(rows.map(row => row.id === '1' ? {...row,status:'archived'} : row))
  await act(async () => result.current.refresh())
  expect(result.current.ids).toEqual(['3'])
})

it('does not show the previous account or accept its late response after switching', async () => {
  let resolve!: (rows:SimulatedFan[])=>void
  vi.spyOn(simulatedFanApi,'list').mockImplementation(async id => id === 'a' ? new Promise(r=>{resolve=r}) : [fan('b','b1')])
  const {result,rerender} = renderHook(({id})=>useSimulatedFans(id,''),{initialProps:{id:'a'}})
  rerender({id:'b'})
  await waitFor(() => expect(result.current.ids).toEqual(['b1']))
  await act(async () => resolve([fan('a','a1')]))
  expect(result.current.rows.map(f=>f.id)).toEqual(['b1'])
})

it('ignores stale responses when switching away and back to the same account', async () => {
  const pending: Array<(rows:SimulatedFan[]) => void> = []
  vi.spyOn(simulatedFanApi,'list').mockImplementation(() => new Promise(resolve => pending.push(resolve)))
  const {result,rerender} = renderHook(({id}) => useSimulatedFans(id,''), {initialProps:{id:'a'}})
  rerender({id:'b'}); rerender({id:'a'})
  await act(async () => pending[2]([fan('a','fresh')]))
  await act(async () => pending[0]([fan('a','stale')]))
  await act(async () => pending[1]([fan('b','other')]))
  expect(result.current.ids).toEqual(['fresh'])
})

it('keeps the latest refresh and rejects unknown or archived selections', async () => {
  const pending: Array<(rows:SimulatedFan[]) => void> = []
  vi.spyOn(simulatedFanApi,'list').mockImplementation(() => new Promise(resolve => pending.push(resolve)))
  const {result} = renderHook(() => useSimulatedFans('a',''))
  let refreshed!: Promise<void>
  act(() => {refreshed = result.current.refresh()})
  await act(async () => {pending[1]([fan('a','fresh'), {...fan('a','archived'),status:'archived'}]); await refreshed})
  await act(async () => pending[0]([fan('a','stale')]))
  act(() => {result.current.toggle('unknown'); result.current.toggle('archived')})
  expect(result.current.ids).toEqual(['fresh'])
})
