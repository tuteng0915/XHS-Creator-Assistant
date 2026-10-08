import {act, cleanup, fireEvent, render, screen} from '@testing-library/react'
import {afterEach, expect, it, vi} from 'vitest'
import {simulationRunApi} from '../api'
import type {SimulationRun} from '../types'
import {RetestProgress} from './RetestProgress'
import {SimulationHistoryPage} from './SimulationHistoryPage'

afterEach(() => {cleanup(); vi.useRealTimers(); vi.restoreAllMocks()})
const run = {id:'child',parentSimulationId:'old',workspaceId:'w',topicId:'t',draftId:null,
  status:'pending',inputSnapshot:{},personaDefinitions:[],reactionResults:[],debateResults:[],
  synthesis:{},stageErrors:{},modelMetadata:{},userNotes:'',reviewStatus:'unreviewed',
  createdAt:'2026-10-05T00:00:00Z',updatedAt:'2026-10-05T00:00:00Z',startedAt:null,completedAt:null} as SimulationRun

it('polls one run until terminal and does not create another simulation',async () => {
  vi.useFakeTimers()
  const get=vi.spyOn(simulationRunApi,'get').mockResolvedValueOnce({...run,status:'running'}).mockResolvedValue({...run,status:'completed'})
  const create=vi.spyOn(simulationRunApi,'createRetest'), update=vi.fn()
  render(<RetestProgress run={run} onObserved={update}/>)
  await act(async () => {await vi.advanceTimersByTimeAsync(500)})
  expect(update).toHaveBeenLastCalledWith(expect.objectContaining({status:'running'}))
  await act(async () => {await vi.advanceTimersByTimeAsync(1500)})
  expect(update).toHaveBeenLastCalledWith(expect.objectContaining({status:'completed'}))
  await act(async () => {await vi.advanceTimersByTimeAsync(10000)})
  expect(get).toHaveBeenCalledTimes(2)
  expect(create).not.toHaveBeenCalled()
})

it('retains failure and only retries progress reading when requested',async () => {
  vi.useFakeTimers()
  const get=vi.spyOn(simulationRunApi,'get').mockRejectedValueOnce(new Error('连接中断')).mockResolvedValue({...run,status:'completed'})
  const update=vi.fn()
  render(<RetestProgress run={run} onObserved={update}/>)
  await act(async () => {await vi.advanceTimersByTimeAsync(500)})
  expect(screen.getByRole('alert')).toHaveTextContent('无需再次创建')
  await act(async () => {await vi.advanceTimersByTimeAsync(10000)})
  expect(get).toHaveBeenCalledOnce()
  fireEvent.click(screen.getByRole('button',{name:'重新读取进度'}))
  await act(async () => {await vi.advanceTimersByTimeAsync(500)})
  expect(update).toHaveBeenCalledOnce()
})

it('does not deliver delayed progress to an unmounted selection',async () => {
  vi.useFakeTimers()
  let resolve!:(value:SimulationRun)=>void
  vi.spyOn(simulationRunApi,'get').mockReturnValue(new Promise(yes => {resolve=yes}))
  const update=vi.fn()
  const page=render(<RetestProgress run={run} onObserved={update}/>)
  await act(async () => {await vi.advanceTimersByTimeAsync(500)})
  page.unmount()
  await act(async () => resolve({...run,status:'completed'}))
  expect(update).not.toHaveBeenCalled()
})

it('rejects an unrelated progress receipt',async () => {
  vi.useFakeTimers()
  vi.spyOn(simulationRunApi,'get').mockResolvedValue({...run,workspaceId:'other'})
  const update=vi.fn()
  render(<RetestProgress run={run} onObserved={update}/>)
  await act(async () => {await vi.advanceTimersByTimeAsync(500)})
  expect(screen.getByRole('alert')).toHaveTextContent('不匹配')
  expect(update).not.toHaveBeenCalled()
})

it('history distinguishes retests and opens the original without mixing its results',() => {
  const open=vi.fn()
  render(<SimulationHistoryPage publicMode simulationRuns={[{...run,id:'old',parentSimulationId:null},run]}
    selectedSimulationRun={{...run,status:'completed'}} simulationReviewDraft={{userNotes:'',reviewStatus:'unreviewed'}}
    simulationReviewSaveState={{phase:'idle'}} reviewStatusLabel={s => s} onOpenSimulationRun={open}
    onSimulationReviewDraftChange={vi.fn()} onSaveSimulationRunReview={vi.fn()} stageSeedFromSimulation={() => []} renderStageResult={() => null}/>)
  expect(screen.getByText('同组复测')).toBeVisible()
  fireEvent.click(screen.getByRole('button',{name:'查看上次试读'}))
  expect(open).toHaveBeenCalledWith('old')
})

it('history removes progress after completion without duplicate sibling keys', () => {
  const errors = vi.spyOn(console, 'error').mockImplementation(() => {})
  const props = {publicMode:true, simulationRuns:[run], selectedSimulationRun:run,
    simulationReviewDraft:{userNotes:'',reviewStatus:'unreviewed' as const},
    simulationReviewSaveState:{phase:'idle' as const}, reviewStatusLabel:(s:string) => s,
    onOpenSimulationRun:vi.fn(), onSimulationObserved:vi.fn(),
    onSimulationReviewDraftChange:vi.fn(), onSaveSimulationRunReview:vi.fn(),
    stageSeedFromSimulation:() => [], renderStageResult:() => null}
  const page = render(<SimulationHistoryPage {...props}/>)
  expect(screen.getByText('正在准备这次试读')).toBeVisible()
  page.rerender(<SimulationHistoryPage {...props} selectedSimulationRun={{...run,status:'completed'}}/>)
  expect(screen.queryByText('正在准备这次试读')).not.toBeInTheDocument()
  expect(errors).not.toHaveBeenCalled()
})
