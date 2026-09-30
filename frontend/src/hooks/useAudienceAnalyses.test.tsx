import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { audienceAnalysisApi } from '../api'
import type { AudienceAnalysis } from '../types'
import { useAudienceAnalyses } from './useAudienceAnalyses'

afterEach(() => {cleanup(); vi.restoreAllMocks()})
const run = (workspaceId:string, id:string):AudienceAnalysis => ({id,workspaceId,sourceMaterialId:'p',status:'completed',result:{},inputSnapshot:{scope:{scope:'all',selectedNoteCount:1}},createdAt:'',error:''})

it('ignores old refresh results after switching accounts away and back', async () => {
  const pending: Array<(rows:AudienceAnalysis[])=>void> = []
  vi.spyOn(audienceAnalysisApi,'list').mockImplementation(() => new Promise(resolve => pending.push(resolve)))
  const {result,rerender} = renderHook(({id}) => useAudienceAnalyses(id),{initialProps:{id:'a'}})
  let refreshed!: Promise<void>
  act(() => {refreshed = result.current.refresh()})
  rerender({id:'b'}); rerender({id:'a'})
  await act(async () => pending[3]([run('a','fresh')]))
  await act(async () => {pending[1]([run('a','old-manual')]); await refreshed})
  await act(async () => pending[0]([run('a','old-poll')]))
  await act(async () => pending[2]([run('b','other')]))
  expect(result.current.rows.map(row=>row.id)).toEqual(['fresh'])
})

it('does not replace a newer refresh with an older poll or its error', async () => {
  const pending: Array<{resolve:(rows:AudienceAnalysis[])=>void; reject:(error:Error)=>void}> = []
  vi.spyOn(audienceAnalysisApi,'list').mockImplementation(() => new Promise((resolve,reject) => pending.push({resolve,reject})))
  const {result} = renderHook(() => useAudienceAnalyses('a'))
  let refreshed!: Promise<void>
  act(() => {refreshed = result.current.refresh()})
  await act(async () => {pending[1].resolve([run('a','fresh')]); await refreshed})
  await act(async () => pending[0].reject(new Error('旧请求失败')))
  expect(result.current.rows[0].id).toBe('fresh')
  expect(result.current.error).toBe('')
  let failed!: Promise<void>
  act(() => {failed = result.current.refresh()})
  await act(async () => {
    const assertion = expect(failed).rejects.toThrow('网络中断')
    pending[2].reject(new Error('网络中断')); await assertion
  })
  expect(result.current.error).toBe('网络中断')
  expect(result.current.rows[0].id).toBe('fresh')
})
