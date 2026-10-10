import {beforeEach, expect, it, vi} from 'vitest'
import {analysisRunApi, audienceAnalysisApi} from './api'
import {accountReferencePreview, audienceReferencePreview, loadCreatorReference, referenceDate} from './creatorReferences'
import type {AnalysisRun, AudienceAnalysis} from './types'

vi.mock('./api', () => ({analysisRunApi: {get: vi.fn()}, audienceAnalysisApi: {get: vi.fn()}}))
beforeEach(() => vi.resetAllMocks())

function account(overrides: Partial<AnalysisRun> = {}): AnalysisRun {
  return {id: 'account-1', workspaceId: 'workspace-1', workflowType: 'account_diagnosis', status: 'completed',
    userNotes: '', reviewStatus: 'unreviewed', createdAt: '2026-10-10T10:00:00Z', startedAt: null,
    completedAt: '2026-10-10T10:01:00Z', updatedAt: '2026-10-10T10:01:00Z',
    inputSnapshot: {analysisRange: {selectedNoteCount: 5}}, stageResults: {}, stageErrors: {}, modelMetadata: {}, ...overrides}
}
function audience(overrides: Partial<AudienceAnalysis> = {}): AudienceAnalysis {
  return {id: 'audience-1', workspaceId: 'workspace-1', sourceMaterialId: 'material-1', status: 'completed',
    inputSnapshot: {scope: {scope: 'recent_10', selectedNoteCount: 6}}, result: {}, error: '',
    createdAt: '2026-10-10T10:00:00Z', ...overrides}
}

it('previews meaningful account statements without exposing raw snapshots or JSON', () => {
  const preview = accountReferencePreview(account({stageResults: {profile: {profile: {
    accountPortrait: {summary: {statement: '用具体经历解释选择'}, keywords: [{statement: '生活观察'}], strengths: [{statement: '能讲清楚取舍'}]},
    voiceFingerprint: ['短句推进', {statement: '先给场景'}],
  }}}, inputSnapshot: {analysisRange: {selectedNoteCount: 5}, contextPack: {secret: 'UNSELECTED_CONTEXT'}}}))
  expect(preview.summary).toBe('用具体经历解释选择')
  expect(preview.scope).toBe('5 篇笔记')
  expect(preview.lines).toEqual(['关键词 · 生活观察', '能讲清楚取舍', '短句推进', '先给场景'])
  expect(JSON.stringify(preview)).not.toContain('UNSELECTED_CONTEXT')
  expect(preview.lines.join(' ')).not.toContain('[object Object]')
})

it('supports old account results and absent or malformed dates without rendering objects', () => {
  const preview = accountReferencePreview(account({createdAt: 'not-a-date', inputSnapshot: {xhsCreatorProfile: {noteCount: 3}},
    stageResults: {profile: {profile: {pillars: ['职业发展', '日常观察', {unexpected: 'RAW_OBJECT'}], voiceFingerprint: []}}}}))
  expect(preview.summary).toBe('职业发展、日常观察')
  expect(preview.scope).toBe('3 篇笔记')
  expect(preview.label).toBe('账号分析 · 历史记录')
  expect(referenceDate('invalid')).toBe('历史记录')
  expect(accountReferencePreview(account()).summary).toBe('参考这次账号分析的已保存结果。')
  expect(accountReferencePreview(account({inputSnapshot: {}})).scope).toBe('按这次分析的保存范围')
})

it('previews reader concerns and uses the profile only as a fallback', () => {
  const preview = audienceReferencePreview(audience({result: {summary: '读者在意不同决策条件', groups: [
    {id: 'one', name: '先看成本', profile: '时间有限', coreConcern: '先看投入是否值得', evidence: []},
    {id: 'two', name: '边试边学', profile: '先找到可以动手的一步', coreConcern: '', evidence: []},
  ]}}))
  expect(preview.scope).toBe('6 篇笔记 · 2 位候选')
  expect(preview.lines).toEqual(['先看成本 · 先看投入是否值得', '边试边学 · 先找到可以动手的一步'])
  expect(preview.summary).toBe('读者在意不同决策条件')
})

it('preserves example provenance in legacy and current result shapes', () => {
  expect(accountReferencePreview(account({origin: 'oracle_showcase'})).isExample).toBe(true)
  expect(accountReferencePreview(account({modelMetadata: {origin: 'oracle_showcase'}})).isExample).toBe(true)
  expect(accountReferencePreview(account({inputSnapshot: {origin: 'oracle_showcase'}})).isExample).toBe(true)
  expect(audienceReferencePreview(audience({result: {origin: 'oracle_showcase'}})).isExample).toBe(true)
  expect(audienceReferencePreview({...audience(), origin: 'oracle_showcase'} as AudienceAnalysis).isExample).toBe(true)
  expect(accountReferencePreview(account()).isExample).toBe(false)
})

it('loads only the exact chosen record and verifies its workspace ownership', async () => {
  vi.mocked(analysisRunApi.get).mockResolvedValue(account())
  expect((await loadCreatorReference('workspace-1', {kind: 'account_analysis', id: 'account-1'})).reference.id).toBe('account-1')
  expect(analysisRunApi.get).toHaveBeenCalledWith('account-1')
  expect(audienceAnalysisApi.get).not.toHaveBeenCalled()
  await expect(loadCreatorReference('another-workspace', {kind: 'account_analysis', id: 'account-1'})).rejects.toThrow('不可用')
  vi.mocked(audienceAnalysisApi.get).mockResolvedValue(audience())
  await expect(loadCreatorReference('another-workspace', {kind: 'audience_analysis', id: 'audience-1'})).rejects.toThrow('不可用')
})

it('rejects changed identities, wrong workflow and unfinished results before returning a preview', async () => {
  for (const value of [account({id: 'other'}), account({workflowType: 'trend_analysis'}), account({status: 'running'})]) {
    vi.mocked(analysisRunApi.get).mockResolvedValue(value)
    await expect(loadCreatorReference('workspace-1', {kind: 'account_analysis', id: 'account-1'})).rejects.toThrow('不可用')
  }
  for (const value of [audience({id: 'other'}), audience({status: 'failed'})]) {
    vi.mocked(audienceAnalysisApi.get).mockResolvedValue(value)
    await expect(loadCreatorReference('workspace-1', {kind: 'audience_analysis', id: 'audience-1'})).rejects.toThrow('不可用')
  }
})

it('propagates missing-source errors without inventing or loading a replacement', async () => {
  vi.mocked(analysisRunApi.get).mockRejectedValue(new Error('这份记录已删除'))
  await expect(loadCreatorReference('workspace-1', {kind: 'account_analysis', id: 'deleted'})).rejects.toThrow('已删除')
  expect(analysisRunApi.get).toHaveBeenCalledTimes(1)
})
