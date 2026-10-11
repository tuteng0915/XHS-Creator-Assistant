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
