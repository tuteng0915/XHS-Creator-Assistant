import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { SimulationRun } from '../types'
import { stageSeedFromSimulation } from '../workflowStageViews'
import { ReactionListView, SynthesisView } from './StageResultViews'
import { withSimulationPersonaLabels } from '../simulationPersonaLabels'
import { StageResultRenderer } from './ArtifactRenderers'
import { WorkflowOutputPanel, type StageView } from './WorkflowOutputPanel'

afterEach(cleanup)

const renderStage = (stage:StageView) => <StageResultRenderer stage={stage} currentRun={null}
  onSaveGeneratedTopic={vi.fn()} onSelectTopic={vi.fn()} onGenerateBrief={vi.fn()}
  onGenerateDraft={vi.fn()} onFillSimulationTopic={vi.fn()} />

it('shows saved actor and recipient names through the production renderer', () => {
  const stages = withSimulationPersonaLabels([
    {key:'personas',n:'1',title:'角色',status:'completed',result:{personas:[{id:'a',name:'行动派'},{id:'b',name:'核对派'}]}},
    {key:'debate_responses',n:'3',title:'交流',status:'completed',result:{debateResponses:[{personaId:'b',replyToId:'initial:a',targetedAt:'wrong-id',response:'先核对日期'}]}},
  ])
  render(renderStage(stages[1]))
  expect(screen.getByRole('heading',{name:'核对派'})).toBeInTheDocument()
  expect(screen.getByText('回应：行动派')).toBeInTheDocument()
  expect(screen.queryByText(/wrong-id|Persona|initial:/)).not.toBeInTheDocument()
})

it('updates progressive names from the same stage set and clears them when runs change', () => {
  const reaction:StageView = {key:'initial_reactions',n:'2',title:'独立反应',status:'completed',result:{reactions:[{personaId:'a',quote:'我先试试'}]}}
  const persona:StageView = {key:'personas',n:'1',title:'角色',status:'completed',result:{personas:[{id:'a',name:'行动派'}]}}
  const panel = (views:StageView[]) => <WorkflowOutputPanel targetTab="account" views={views} outputKind="simulation" runError="" renderStageResult={renderStage} />
  const {rerender} = render(panel([reaction]))
  expect(screen.getByRole('heading',{name:'受众 1'})).toBeInTheDocument()
  rerender(panel([persona,reaction]))
  expect(screen.getAllByRole('heading',{name:'行动派'})).toHaveLength(2)
  rerender(panel([{...persona,result:{personas:[{id:'a',name:'另一运行的角色'}]}},reaction]))
  expect(screen.queryByRole('heading',{name:'行动派'})).not.toBeInTheDocument()
  expect(screen.getAllByRole('heading',{name:'另一运行的角色'})).toHaveLength(2)
  rerender(panel([reaction]))
  expect(screen.getByRole('heading',{name:'受众 1'})).toBeInTheDocument()
})

it('keeps legacy recipient-only replies readable even without stance or message IDs', () => {
  render(<ReactionListView type="debate" items={[{personaId:'a',targetedAt:'b',response:'收到'}]}
    personaLabels={new Map([['a','提问者'],['b','分享者']])} />)
  expect(screen.getByText('回应：分享者')).toBeInTheDocument()
  expect(screen.getByRole('heading',{name:'提问者'})).toBeInTheDocument()
})

it('distinguishes silence from a public simulated comment', () => {
  render(<ReactionListView type="reaction" items={[{personaId:'p',stance:'无感',action:'no_comment',quote:'不能展示的旧文本',understanding:'标题还不清楚'}]} />)
  expect(screen.getByText(/读完，不评论/)).toBeInTheDocument()
  expect(screen.queryByText(/不能展示的旧文本/)).not.toBeInTheDocument()
  expect(screen.getByText(/标题还不清楚/)).toBeInTheDocument()
})

it('labels synthesis as preview and displays limitations', () => {
  render(<SynthesisView data={{verdict:'补充费用',limitations:'没有正文'}} />)
  expect(screen.getByText(/模拟反应不是实际评论/)).toBeInTheDocument()
  expect(screen.getByText('没有正文')).toBeInTheDocument()
})

it.each(['completed', 'partially_completed'])('reopens a skipped discussion when run is %s', status => {
  const run = {status,personaDefinitions:[{id:'p'}],reactionResults:[{personaId:'p',action:'skip',quote:''}],debateResults:[],synthesis:{},stageErrors:{synthesis:'失败'}} as unknown as SimulationRun
  const stage = stageSeedFromSimulation(run).find(s => s.key === 'debate_responses')
  expect(stage?.status).toBe('completed')
  expect(stage?.result).toMatchObject({skippedReason:expect.stringContaining('无需交叉回应')})
})

it('does not label a one-comment stateful discussion as skipped', () => {
  const run = {status:'partially_completed',inputSnapshot:{simulationMethod:'audience_methods_v2'},personaDefinitions:[],reactionResults:[{personaId:'a',quote:'费用？'},{personaId:'b',action:'no_comment'}],debateResults:[],synthesis:{},stageErrors:{'debate_responses.b':'失败'}} as unknown as SimulationRun
  const stage = stageSeedFromSimulation(run).find(s => s.key === 'debate_responses')
  expect(stage?.result).toBeUndefined()
  expect(stage?.status).toBe('failed')
  expect(stage?.error).toBe('失败')
})

it('restores stateful discussion skip when there is nobody else to reply', () => {
  const run = {status:'completed',inputSnapshot:{simulationMethod:'audience_methods_v2'},personaDefinitions:[],reactionResults:[{personaId:'a',quote:'费用？'}],debateResults:[],synthesis:{},stageErrors:{}} as unknown as SimulationRun
  const stage = stageSeedFromSimulation(run).find(s => s.key === 'debate_responses')
  expect(stage?.result).toMatchObject({skippedReason:expect.stringContaining('跳过交流')})
})

it('shows reply target and a concrete opinion change without requiring a stance', () => {
  render(<ReactionListView type="debate" items={[{personaId:'b',response:'明白了',replyToId:'initial:a',targetedAt:'a',changedMind:true,changeReason:'补充了费用包含范围'}]} />)
  expect(screen.getByText('回应：受众 2')).toBeInTheDocument()
  expect(screen.getByText(/补充了费用包含范围/)).toBeInTheDocument()
})
