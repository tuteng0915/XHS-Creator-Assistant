import {beforeEach, expect, it, vi} from 'vitest'
import {analysisRunApi, audienceAnalysisApi, inputAssetApi} from './api'
import {accountReferencePreview, audienceReferencePreview, importedReferenceNotes, loadCreatorReference, referenceDate} from './creatorReferences'
import type {AnalysisRun, AudienceAnalysis, TextInputAsset} from './types'

vi.mock('./api', () => ({analysisRunApi: {get: vi.fn()}, audienceAnalysisApi: {get: vi.fn()}, inputAssetApi: {get: vi.fn()}}))
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
function profile(notes: unknown[] = [{noteId: 'saved-1', title: '保存的完整标题', desc: '保存的完整正文\n第二段', coverMediaAssetId: 'cover-1', metrics: {liked: 3}, comments: [{content: 'PRIVATE_COMMENT'}]}], overrides: Partial<TextInputAsset> = {}): TextInputAsset {
  return {id: 'profile-1', workspaceId: 'workspace-1', type: 'xhs_creator_profile', name: '账号原文', createdAt: '', updatedAt: '',
    content: JSON.stringify({notes, creator: {biography: 'UNSELECTED_ACCOUNT_CONTEXT'}}), ...overrides}
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

it('loads the exact imported note with the full saved title and body, without comments or account context', async () => {
  const body = '完整正文，不做摘要。'.repeat(300) + '\n最后一段'
  vi.mocked(inputAssetApi.get).mockResolvedValue(profile([{noteId: 'saved-1', title: '保存的完整标题', desc: body, coverMediaAssetId: 'cover-1', comments: [{content: 'PRIVATE_COMMENT'}]}]))
  const preview = await loadCreatorReference('workspace-1', {kind: 'imported_note', id: 'profile-1', noteId: 'saved-1'})
  expect(inputAssetApi.get).toHaveBeenCalledExactlyOnceWith('profile-1')
  expect(preview.reference).toEqual({kind: 'imported_note', id: 'profile-1', noteId: 'saved-1'})
  expect(preview.label).toBe('原笔记 · 保存的完整标题')
  expect(preview.summary).toBe(body)
  expect(preview.note).toMatchObject({noteId: 'saved-1', title: '保存的完整标题', desc: body, coverMediaAssetId: 'cover-1', comments: []})
  expect(JSON.stringify(preview)).not.toContain('PRIVATE_COMMENT')
  expect(JSON.stringify(preview)).not.toContain('UNSELECTED_ACCOUNT_CONTEXT')
  expect(analysisRunApi.get).not.toHaveBeenCalled()
  expect(audienceAnalysisApi.get).not.toHaveBeenCalled()
})

it('offers only stable exact unique imported note IDs and rejects missing, positional and malformed IDs', () => {
  const notes = importedReferenceNotes(profile([
    {noteId: 'saved-1', title: '只保存标题', desc: ''}, {noteId: 'body-only', title: '', desc: '只保存正文'},
    {title: '无标识正文', desc: '不能按索引认领'}, {noteId: 123, title: '数字标识'}, {noteId: ' ', title: '空标识'},
    {noteId: 'note-0', title: '位置兜底标识'}, {noteId: 'duplicate', title: '重名一'}, {noteId: 'duplicate', title: '重名二'},
    {noteId: 'empty', title: ' ', desc: ''},
  ]))
  expect(notes.map(note => note.noteId)).toEqual(['saved-1', 'body-only'])
  expect(notes[1].title).toBe('')
  expect(importedReferenceNotes()).toEqual([])
  expect(importedReferenceNotes(profile([], {type: 'comments'}))).toEqual([])
  expect(importedReferenceNotes(profile([], {content: 'malformed json'}))).toEqual([])
})

it('rejects unavailable or ambiguous imported notes without falling back to an array position', async () => {
  const reference = {kind: 'imported_note' as const, id: 'profile-1', noteId: 'saved-1'}
  for (const value of [profile(undefined, {id: 'other'}), profile(undefined, {workspaceId: 'workspace-2'}), profile(undefined, {type: 'historical_posts'}),
    profile([{noteId: 'other', title: '别篇'}]), profile([{noteId: 'saved-1', title: '第一篇'}, {noteId: 'saved-1', title: '第二篇'}]), profile([], {content: '{'})]) {
    vi.mocked(inputAssetApi.get).mockResolvedValue(value)
    await expect(loadCreatorReference('workspace-1', reference)).rejects.toThrow('不可用')
  }
  vi.mocked(inputAssetApi.get).mockResolvedValue(profile([{title: '没有 noteId 的原文'}]))
  await expect(loadCreatorReference('workspace-1', {...reference, noteId: '0'})).rejects.toThrow('不可用')
})

it('keeps title-only notes explicit and propagates original-note transport failures', async () => {
  const reference = {kind: 'imported_note' as const, id: 'profile-1', noteId: 'saved-1'}
  vi.mocked(inputAssetApi.get).mockResolvedValue(profile([{noteId: 'saved-1', title: '只保存标题', desc: ''}]))
  expect((await loadCreatorReference('workspace-1', reference)).summary).toBe('这篇笔记只保存了标题。')
  vi.mocked(inputAssetApi.get).mockRejectedValue(new Error('读取原笔记中断'))
  await expect(loadCreatorReference('workspace-1', reference)).rejects.toThrow('读取原笔记中断')
})
