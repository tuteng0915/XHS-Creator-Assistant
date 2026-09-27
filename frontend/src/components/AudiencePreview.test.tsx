import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import type { SimulationRun } from '../types'
import { stageSeedFromSimulation } from '../workflowStageViews'
import { ReactionListView, SynthesisView } from './StageResultViews'

afterEach(cleanup)

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
  expect(screen.getByText('回应：a')).toBeInTheDocument()
  expect(screen.getByText(/补充了费用包含范围/)).toBeInTheDocument()
})
