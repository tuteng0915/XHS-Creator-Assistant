import {cleanup, fireEvent, render, screen} from '@testing-library/react'
import {afterEach, expect, it, vi} from 'vitest'
import type {ActivityEvent, SimulationRun} from '../types'
import {applySimulationStageEvent, simulationStageSeed, stageSeedFromSimulation} from '../workflowStageViews'
import {withSimulationPersonaLabels} from '../simulationPersonaLabels'
import {stageDisplayStatus} from '../simulationStageStatus'
import {SimulationStageNotice} from './SimulationStageNotice'
import {WorkflowOutputPanel, type StageView} from './WorkflowOutputPanel'
import {StageResultRenderer} from './ArtifactRenderers'
import {SimulationHistoryPage} from './SimulationHistoryPage'

afterEach(cleanup)
const personas = [{id:'a',name:'行动派'},{id:'b',name:'安静派'},{id:'c',name:'核对派'}]
const reactions = [{personaId:'a',quote:'我先试试',action:'comment'},{personaId:'b',quote:'',action:'no_comment'}]
const run = {id:'r',status:'partially_completed',createdAt:'2026-10-03T00:00:00Z',inputSnapshot:{simulationMethod:'audience_methods_v2'},personaDefinitions:personas,reactionResults:reactions,debateResults:[{personaId:'b',response:''}],synthesis:{verdict:'先补步骤'},stageErrors:{'initial_reactions.c':'连接失败'}} as unknown as SimulationRun
const renderer = (stage:StageView) => <StageResultRenderer stage={stage} currentRun={null} onSaveGeneratedTopic={vi.fn()} onSelectTopic={vi.fn()} onGenerateBrief={vi.fn()} onGenerateDraft={vi.fn()} onFillSimulationTopic={vi.fn()}/>
const panel = (views:StageView[]) => <WorkflowOutputPanel targetTab="account" views={views} outputKind="simulation" runError="" renderStageResult={renderer}/>
function event(key:string,kind:string,data:Record<string,unknown>={}):ActivityEvent {
  return {stageKey:key,data:{eventType:kind,...data}} as ActivityEvent
}

it('preserves comments and silence while naming a failed role in reopened results', () => {
  render(panel(stageSeedFromSimulation(run)))
  expect(screen.getByText('部分完成')).toBeInTheDocument()
  expect(screen.getByText('已返回 2 位 · 1 位评论 · 1 位不评论')).toBeInTheDocument()
  expect(screen.getByText(/模拟评论：我先试试/)).toBeInTheDocument()
  expect(screen.getByText(/读完，不评论/)).toBeInTheDocument()
  fireEvent.click(screen.getByText('部分角色未完成，已保留成功结果'))
  expect(screen.getByText('核对派：连接失败')).toBeVisible()
  expect(screen.getByText('已返回 1 位 · 0 位回应 · 1 位不追加回应')).toBeInTheDocument()
})

it('uses the same partial status and role errors in the actual history page', () => {
  render(<SimulationHistoryPage publicMode simulationRuns={[]} selectedSimulationRun={run}
    simulationReviewDraft={{reviewStatus:'unreviewed',userNotes:''}} simulationReviewSaveState={{phase:'idle'}} reviewStatusLabel={s=>s}
    onOpenSimulationRun={vi.fn()} onSimulationReviewDraftChange={vi.fn()} onSaveSimulationRunReview={vi.fn()}
    stageSeedFromSimulation={stageSeedFromSimulation} renderStageResult={renderer}/>)
  expect(screen.getByText(/已有部分结果/)).toBeInTheDocument()
  expect(screen.getByText('我先试试')).toBeInTheDocument()
  fireEvent.click(screen.getByText('部分环节未完成，已保留现有发言'))
  expect(screen.getByText('核对派：连接失败')).toBeVisible()
})

it('retains successes for either SSE ordering and agrees with persisted history', () => {
  for (const failuresFirst of [true,false]) {
    let views=applySimulationStageEvent(simulationStageSeed(),event('personas','stage.succeeded',{personas}))
    const success=event('initial_reactions','stage.succeeded',{reactions})
    const failure=event('initial_reactions','stage.failed',{error:'连接失败',stageErrors:run.stageErrors})
    for (const activity of failuresFirst?[failure,success]:[success,failure]) views=applySimulationStageEvent(views,activity)
    const stage=withSimulationPersonaLabels(views)[1]
    expect(stageDisplayStatus(stage).label).toBe('部分完成')
    expect(stage.result).toEqual({reactions})
    expect(stage.executionErrors).toEqual(run.stageErrors)
    expect(stage.executionErrors).toEqual(stageSeedFromSimulation(run)[1].executionErrors)
  }
})

it('supports nested legacy failures and does not carry them into the next run', () => {
  const views=applySimulationStageEvent(simulationStageSeed(),event('initial_reactions.c','stage.failed',{error:'失败'}))
  expect(views[1].executionErrors).toEqual({'initial_reactions.c':'失败'})
  expect(views[2].executionErrors).toBeUndefined()
  expect(simulationStageSeed()[1].executionErrors).toBeUndefined()
})

it('does not call all-silent reactions failures or require every persona to debate', () => {
  const views=stageSeedFromSimulation({...run,status:'completed',stageErrors:{},reactionResults:personas.map(p=>({personaId:p.id,action:'skip',quote:''})),debateResults:[]})
  expect(stageDisplayStatus(views[1]).label).toBe('已完成')
  expect(stageDisplayStatus(views[2]).label).toBe('已完成')
  render(panel(views))
  expect(screen.getByText('已返回 3 位 · 0 位评论 · 3 位不评论')).toBeInTheDocument()
  expect(screen.queryByText('查看未完成原因')).not.toBeInTheDocument()
})

it('distinguishes missing records from known errors and pending work', () => {
  const completed=stageSeedFromSimulation({...run,stageErrors:{}})[1]
  expect(stageDisplayStatus(completed).label).toBe('部分完成')
  const {rerender}=render(<SimulationStageNotice stage={completed}/>)
  expect(screen.getByText(/未记录反应：核对派/)).toBeInTheDocument()
  rerender(<SimulationStageNotice stage={{...completed,status:'running',executionEnded:false}}/>)
  expect(screen.queryByText(/未记录反应/)).not.toBeInTheDocument()
  expect(stageDisplayStatus({...completed,status:'waiting',result:undefined}).label).toBe('未完成')
})

it('preserves legacy aggregate errors and does not invent names or behavior', () => {
  const stage:StageView={key:'initial_reactions',n:'2',title:'反应',status:'failed',error:'服务暂不可用',result:{reactions:[{personaId:'old'}]}}
  render(<SimulationStageNotice stage={stage}/>)
  expect(screen.getByText('服务暂不可用')).toBeInTheDocument()
  expect(screen.getByText(/1 位未注明行为/)).toBeInTheDocument()
  expect(screen.queryByText(/未记录反应/)).not.toBeInTheDocument()
})

it('shows total failure and never hides a saved debate error behind a skip', () => {
  const views=stageSeedFromSimulation({...run,reactionResults:[],debateResults:[],stageErrors:{'initial_reactions.a':'失败','debate_responses.b':'中断'}})
  expect(stageDisplayStatus(views[1]).label).toBe('失败')
  expect(stageDisplayStatus(views[2]).label).toBe('失败')
  expect(views[2].result).toBeUndefined()
  const silentWithError=stageSeedFromSimulation({...run,reactionResults:[{personaId:'b',action:'no_comment',quote:''}],debateResults:[],stageErrors:{'debate_responses.b':'中断'}})
  expect(stageDisplayStatus(silentWithError[2]).label).toBe('失败')
  expect(silentWithError[2].result).toBeUndefined()
})
