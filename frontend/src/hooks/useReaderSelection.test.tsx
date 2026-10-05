import {act, cleanup, renderHook, waitFor} from '@testing-library/react'
import {afterEach, beforeEach, expect, it, vi} from 'vitest'
import {memoryStorage} from '../test/storage'
import {readerSelectionApi} from '../api'
import type {ReaderSelection} from '../readerSelection'
import type {PanelTask} from '../types'
import {readerSelectionStorageKey, useReaderSelection} from './useReaderSelection'

const record: ReaderSelection = {id:'r', workspaceId:'w', inputHash:'a'.repeat(64), status:'completed',
  inputSnapshot:{target:{title:'题目'},candidates:[]},result:{proposedReaders:[],unmatchedReason:'无匹配'},
  errorCode:null,freshness:{status:'current',reasons:[]}}
function receipt(id?:string) {
  window.localStorage.setItem(readerSelectionStorageKey('w','t'), JSON.stringify({requestKey:'original',desiredCount:5,id}))
}
beforeEach(()=>vi.stubGlobal('localStorage',memoryStorage()))
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks();vi.useRealTimers()})

it('does not create a paid request when opening an empty page', () => {
  const create=vi.spyOn(readerSelectionApi,'create')
  const get=vi.spyOn(readerSelectionApi,'get')
  const {result}=renderHook(()=>useReaderSelection('w','t','v1'))
  expect(create).not.toHaveBeenCalled(); expect(get).not.toHaveBeenCalled()
  expect(result.current.busy).toBe(false)
})

it('restores saved receipts through observation only', async () => {
  receipt('r')
  const create=vi.spyOn(readerSelectionApi,'create')
  const get=vi.spyOn(readerSelectionApi,'get').mockResolvedValue(record)
  const {result}=renderHook(()=>useReaderSelection('w','t','v1'))
  await waitFor(()=>expect(result.current.record?.id).toBe('r'))
  expect(get).toHaveBeenCalledWith('w','r');expect(create).not.toHaveBeenCalled()
})

it('retries a lost POST response with the original key and count, not on remount', async () => {
  const create=vi.spyOn(readerSelectionApi,'create').mockRejectedValueOnce(new Error('断网')).mockResolvedValue(record)
  vi.spyOn(readerSelectionApi,'get').mockResolvedValue(record)
  const first=renderHook(()=>useReaderSelection('w','t','v1'))
  await act(async()=>first.result.current.recommend(5))
  const original=create.mock.calls[0][1]
  first.unmount()
  const next=renderHook(()=>useReaderSelection('w','t','v1'))
  expect(create).toHaveBeenCalledTimes(1)
  expect(next.result.current.error).toContain('尚未确认')
  await act(async()=>next.result.current.recommend(3))
  expect(create.mock.calls[1][1]).toEqual(original)
  expect(next.result.current.record?.id).toBe('r')
})

it('locks duplicate clicks and ignores late creation after topic switches', async () => {
  let finish!:(value:ReaderSelection)=>void
  const create=vi.spyOn(readerSelectionApi,'create').mockImplementation(()=>new Promise(resolve=>{finish=resolve}))
  const get=vi.spyOn(readerSelectionApi,'get').mockResolvedValue(record)
  const {result,rerender}=renderHook(({topic})=>useReaderSelection('w',topic,'v1'),{initialProps:{topic:'t'}})
  let request!:Promise<void>
  act(()=>{request=result.current.recommend(3);void result.current.recommend(3)})
  expect(create).toHaveBeenCalledTimes(1)
  rerender({topic:'other'})
  await act(async()=>{finish(record);await request})
  expect(result.current.record).toBeNull();expect(get).not.toHaveBeenCalled()
  expect(JSON.parse(window.localStorage.getItem(readerSelectionStorageKey('w','t'))!).id).toBe('r')
})

it('does not accept an old observation after changing the input revision', async () => {
  receipt('r')
  let old!:(value:ReaderSelection)=>void
  vi.spyOn(readerSelectionApi,'get').mockImplementationOnce(()=>new Promise(resolve=>{old=resolve}))
    .mockResolvedValue({...record,freshness:{status:'stale',reasons:['target_changed']}})
  const {result,rerender}=renderHook(({revision})=>useReaderSelection('w','t',revision),{initialProps:{revision:'v1'}})
  rerender({revision:'v2'})
  await waitFor(()=>expect(result.current.record?.freshness?.status).toBe('stale'))
  await act(async()=>old(record))
  expect(result.current.record?.freshness?.status).toBe('stale')
})

it('polls pending runs, stops at terminal results, and never POSTs during observation', async () => {
  vi.useFakeTimers();receipt('r')
  const get=vi.spyOn(readerSelectionApi,'get').mockResolvedValueOnce({...record,status:'running',result:null}).mockResolvedValue(record)
  const create=vi.spyOn(readerSelectionApi,'create')
  const {result}=renderHook(()=>useReaderSelection('w','t','v1'))
  await act(async()=>{})
  expect(result.current.busy).toBe(true)
  await act(async()=>vi.advanceTimersByTimeAsync(1000))
  expect(result.current.busy).toBe(false)
  await act(async()=>vi.advanceTimersByTimeAsync(10000))
  expect(get).toHaveBeenCalledTimes(2);expect(create).not.toHaveBeenCalled()
})

it('recovers GET errors without another POST', async () => {
  receipt('r')
  const get=vi.spyOn(readerSelectionApi,'get').mockRejectedValueOnce(new Error('暂时断网')).mockResolvedValue(record)
  const create=vi.spyOn(readerSelectionApi,'create')
  const {result,unmount}=renderHook(()=>useReaderSelection('w','t','v1'))
  await waitFor(()=>expect(result.current.error).toContain('断网'))
  await act(async()=>result.current.refresh())
  expect(result.current.error).toBe('');expect(result.current.record).toEqual(record)
  expect(get).toHaveBeenCalledTimes(2)
  unmount();expect(create).not.toHaveBeenCalled()
})

it('cancels pending observation timers on unmount', async()=>{
  vi.useFakeTimers();receipt('r')
  const get=vi.spyOn(readerSelectionApi,'get').mockResolvedValue({...record,status:'running',result:null})
  const {unmount}=renderHook(()=>useReaderSelection('w','t','v1'))
  await act(async()=>{})
  unmount()
  await act(async()=>vi.advanceTimersByTimeAsync(5000))
  expect(get).toHaveBeenCalledTimes(1)
})

it('rejects observations from another account', async () => {
  receipt('r')
  vi.spyOn(readerSelectionApi,'get').mockResolvedValue({...record,workspaceId:'other'})
  const {result}=renderHook(()=>useReaderSelection('w','t','v1'))
  await waitFor(()=>expect(result.current.error).toContain('不属于'))
  expect(result.current.record).toBeNull()
})

it('isolates lost receipts by task and retries with the original task key', async()=>{
  const task:PanelTask={protocolVersion:'panel/v1',readingMode:'natural',discussionEnabled:true,focusQuestions:[]}
  const create=vi.spyOn(readerSelectionApi,'create').mockRejectedValue(new Error('断网'))
  const {result,rerender}=renderHook(({task})=>useReaderSelection('w','t','v1',task),{initialProps:{task}})
  await act(async()=>result.current.recommend(3))
  const original=create.mock.calls[0][1]
  rerender({task:{...task,discussionEnabled:false}})
  await act(async()=>result.current.recommend(3))
  expect(create.mock.calls[1][1].requestKey).not.toBe(original.requestKey)
  expect(create.mock.calls[1][1].panelTask?.discussionEnabled).toBe(false)
  rerender({task})
  await act(async()=>result.current.recommend(5))
  expect(create.mock.calls[2][1]).toEqual(original)
})

it('ignores late results after a task change and rejects mismatched task snapshots', async()=>{
  const task:PanelTask={protocolVersion:'panel/v1',readingMode:'natural',discussionEnabled:true,focusQuestions:[]}
  let finish!:(value:ReaderSelection)=>void
  vi.spyOn(readerSelectionApi,'create').mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve})).mockResolvedValue(record)
  vi.spyOn(readerSelectionApi,'get').mockResolvedValue(record)
  const {result,rerender}=renderHook(({task})=>useReaderSelection('w','t','v1',task),{initialProps:{task}})
  let pending!:Promise<void>
  act(()=>{pending=result.current.recommend(3)})
  rerender({task:{...task,discussionEnabled:false}})
  await act(async()=>{finish({...record,inputSnapshot:{...record.inputSnapshot,panelTask:task}});await pending})
  expect(result.current.record).toBeNull()
  await act(async()=>result.current.recommend(3))
  expect(result.current.error).toContain('试读设置不一致')
})
