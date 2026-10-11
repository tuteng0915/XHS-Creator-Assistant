import { describe, expect, it } from 'vitest'
import type { ActivityEvent, AnalysisRun } from './types'
import { applyAnalysisStageEvent, stageSeed, stageSeedFromRun } from './workflowStageViews'
import { parseWorkflowProgress, workflowProgressLabel } from './workflowProgress'

const progress = {phase: 'reading', status: 'running', completed: 1, total: 2,
  preview: '《真实标题》：先准备，再逐项核对。'} as const
const event = (kind: string, data: Record<string, unknown> = {}, runId = 'run'): ActivityEvent => ({
  eventId: 'event', runId, runType: 'account_diagnosis', stageKey: 'profile',
  status: 'running', sequence: 1, occurredAt: 'now', data: {eventType: kind, ...data},
})
const run = (overrides: Partial<AnalysisRun> = {}): AnalysisRun => ({
  id: 'run', workspaceId: 'workspace', workflowType: 'account_diagnosis', status: 'running',
  inputSnapshot: {}, stageResults: {}, stageErrors: {}, modelMetadata: {profile: {progress}},
  userNotes: '', reviewStatus: 'unreviewed', createdAt: '', startedAt: null,
  completedAt: null, updatedAt: '', ...overrides,
})

describe('account report segmented progress', () => {
  it('keeps phase previews separate from final reports and ignores duplicate updates', () => {
    const states = applyAnalysisStageEvent(stageSeed('account'), event('stage.progress', progress), 'run')
    expect(states[0]).toMatchObject({status: 'running', progress})
    expect(states[0].result).toBeUndefined()
    expect(workflowProgressLabel(progress)).toBe('逐篇细读 · 1/2')
    const repeated = applyAnalysisStageEvent(states, event('stage.progress', progress), 'run')
    expect(repeated[0]).toBe(states[0])
  })

  it.each(['stage.succeeded', 'stage.failed'])('clears terminal previews for %s and ignores late progress', kind => {
    const states = applyAnalysisStageEvent(stageSeed('account'), event('stage.progress', progress), 'run')
    const finished = applyAnalysisStageEvent(states, event(kind, {profile: {pillars: ['完成']}}), 'run')
    expect(finished[0].progress).toBeUndefined()
    const late = applyAnalysisStageEvent(finished, event('stage.progress', progress), 'run')
    expect(late[0]).toBe(finished[0])
  })

  it('ignores stale-run and malformed progress', () => {
    const states = stageSeed('account')
    expect(applyAnalysisStageEvent(states, event('stage.progress', progress, 'other-run'), 'run')).toBe(states)
    expect(applyAnalysisStageEvent(states, event('stage.progress', {phase: 'reading'}), 'run')[0]).toBe(states[0])
    expect(parseWorkflowProgress({...progress, completed: 5})).toBeUndefined()
    expect(parseWorkflowProgress({...progress, total: -1})).toBeUndefined()
  })

  it('restores persisted progress for polling fallback without treating it as a completed report', () => {
    expect(stageSeedFromRun(run())[0]).toMatchObject({status: 'running', progress})
    expect(stageSeedFromRun(run())[0].result).toBeUndefined()
    expect(stageSeedFromRun(run({stageResults: {profile: {profile: {pillars: ['完成']}}}}))[0].progress).toBeUndefined()
    expect(stageSeedFromRun(run({stageErrors: {profile: '失败'}}))[0].progress).toBeUndefined()
    expect(stageSeedFromRun(run({status: 'failed'}))[0].progress).toBeUndefined()
    expect(stageSeedFromRun(run({modelMetadata: {}}))[0].progress).toBeUndefined()
  })
})

describe('reader feedback two-stage progress', () => {
  const retrieval = {phase: 'feedback_retrieval', status: 'running', completed: 0, total: 2} as const
  const ranking = {phase: 'feedback_ranking', status: 'running', completed: 1, total: 2,
    preview: '候选：想了解 DIY 的具体步骤。'} as const
  const feedbackEvent = (kind: string, data: Record<string, unknown>) => ({
    ...event(kind, data), stageKey: 'pain_points',
  })

  it('recognizes both phases and keeps retrieved candidates out of final results', () => {
    expect(parseWorkflowProgress(retrieval)).toEqual(retrieval)
    expect(parseWorkflowProgress(ranking)).toEqual(ranking)
    expect(workflowProgressLabel(retrieval)).toBe('提取评论反馈 · 0/2')
    expect(workflowProgressLabel(ranking)).toBe('筛选重要反馈 · 1/2')
    const first = applyAnalysisStageEvent(stageSeed('account'), feedbackEvent('stage.progress', retrieval), 'run')
    const states = applyAnalysisStageEvent(first, feedbackEvent('stage.progress', ranking), 'run')
    expect(states.find(stage => stage.key === 'pain_points')).toMatchObject({status: 'running', progress: ranking})
    expect(states.find(stage => stage.key === 'pain_points')?.result).toBeUndefined()
    expect(states.find(stage => stage.key === 'profile')?.progress).toBeUndefined()
  })

  it('restores candidates from persisted progress but never from completed empty feedback', () => {
    const running = run({modelMetadata: {pain_points: {progress: ranking}}})
    expect(stageSeedFromRun(running).find(stage => stage.key === 'pain_points')).toMatchObject({
      status: 'running', progress: ranking,
    })
    const finished = {...running, stageResults: {pain_points: {painPoints: []}}}
    expect(stageSeedFromRun(finished).find(stage => stage.key === 'pain_points')).toMatchObject({
      status: 'completed', result: {painPoints: []}, progress: undefined,
    })
  })

  it.each(['stage.succeeded', 'stage.failed'])('clears feedback candidates on %s and ignores late ranking updates', kind => {
    const running = applyAnalysisStageEvent(stageSeed('account'), feedbackEvent('stage.progress', ranking), 'run')
    const finished = applyAnalysisStageEvent(running, feedbackEvent(kind, {painPoints: []}), 'run')
    const stage = finished.find(item => item.key === 'pain_points')
    expect(stage?.progress).toBeUndefined()
    expect(applyAnalysisStageEvent(finished, feedbackEvent('stage.progress', ranking), 'run')
      .find(item => item.key === 'pain_points')).toBe(stage)
  })
})
