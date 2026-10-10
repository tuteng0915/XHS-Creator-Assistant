import {analysisRunApi, audienceAnalysisApi, inputAssetApi} from './api'
import type {CreatorContextReference} from './contentCollaboration'
import type {CreatorNote} from './creatorNotes'
import type {AnalysisRun, AudienceAnalysis, TextInputAsset} from './types'
import {isOracleShowcase} from './recordOrigin'

export const referenceKindNames = {account_analysis: '账号分析', audience_analysis: '受众分析', imported_note: '原笔记'}
export interface CreatorReferencePreview {
  reference: CreatorContextReference
  label: string
  scope: string
  summary: string
  lines: string[]
  isExample: boolean
  note?: CreatorNote
}
export function referenceDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '历史记录' : date.toLocaleString('zh-CN', {month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit'})
}
const object = (value: unknown): Record<string, unknown> => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
const text = (value: unknown): string => typeof value === 'string' ? value : typeof object(value).statement === 'string' ? object(value).statement as string : ''
const lines = (value: unknown): string[] => Array.isArray(value) ? value.map(text).filter(Boolean) : []

/** References need stable source IDs; the generic browser's index fallback is not safe here. */
export function importedReferenceNotes(profile?: TextInputAsset): CreatorNote[] {
  if (profile?.type !== 'xhs_creator_profile') return []
  let payload: Record<string, unknown>
  try {payload = object(JSON.parse(profile.content))} catch {return []}
  if (!Array.isArray(payload.notes)) return []
  const rawNotes = payload.notes.map(object)
  const counts = new Map<string, number>()
  for (const note of rawNotes) if (typeof note.noteId === 'string') counts.set(note.noteId, (counts.get(note.noteId) || 0) + 1)
  return rawNotes.flatMap(note => {
    if (typeof note.noteId !== 'string' || !note.noteId.trim() || /^note-\d+$/.test(note.noteId) || counts.get(note.noteId) !== 1) return []
    const title = typeof note.title === 'string' ? note.title : '', desc = typeof note.desc === 'string' ? note.desc : ''
    if (!title.trim() && !desc.trim()) return []
    const timestamp = (value: unknown) => typeof value === 'string' || typeof value === 'number' ? value : undefined
    return [{noteId: note.noteId, title, desc, metrics: object(note.metrics), comments: [],
      publishedAt: timestamp(note.publishedAt),
      ...(typeof note.coverMediaAssetId === 'string' ? {coverMediaAssetId: note.coverMediaAssetId} : {})}]
  })
}

export function importedReferencePreview(profile: TextInputAsset, note: CreatorNote): CreatorReferencePreview {
  return {
    reference: {kind: 'imported_note', id: profile.id, noteId: note.noteId},
    label: `原笔记 · ${note.title || '未命名笔记'}`,
    scope: '已保存的标题与正文', summary: note.desc || '这篇笔记只保存了标题。',
    lines: [], isExample: false, note,
  }
}

export function accountReferencePreview(run: AnalysisRun): CreatorReferencePreview {
  const profileStage = object(run.stageResults.profile)
  const profile = object(profileStage.profile)
  const portrait = object(profile.accountPortrait)
  const count = object(run.inputSnapshot.analysisRange).selectedNoteCount ?? object(run.inputSnapshot.xhsCreatorProfile).noteCount
  return {
    reference: {kind: 'account_analysis', id: run.id}, label: `账号分析 · ${referenceDate(run.createdAt)}`,
    scope: typeof count === 'number' ? `${count} 篇笔记` : '按这次分析的保存范围',
    summary: text(portrait.summary) || lines(profile.pillars).join('、') || '参考这次账号分析的已保存结果。',
    lines: [...lines(portrait.keywords).map(value => `关键词 · ${value}`), ...lines(portrait.strengths), ...lines(profile.voiceFingerprint)],
    isExample: isOracleShowcase(run),
  }
}
export function audienceReferencePreview(run: AudienceAnalysis): CreatorReferencePreview {
  return {
    reference: {kind: 'audience_analysis', id: run.id}, label: `受众分析 · ${referenceDate(run.createdAt)}`,
    scope: `${run.inputSnapshot.scope?.selectedNoteCount ?? 0} 篇笔记 · ${run.result.groups?.length ?? 0} 位候选`,
    summary: run.result.summary || '参考这次分析中的模拟读者与阅读需求。',
    lines: (run.result.groups || []).map(group => `${group.name} · ${group.coreConcern || group.profile}`),
    isExample: isOracleShowcase(run),
  }
}
export async function loadCreatorReference(workspaceId: string, reference: CreatorContextReference): Promise<CreatorReferencePreview> {
  if (reference.kind === 'imported_note') {
    const profile = await inputAssetApi.get(reference.id)
    if (profile.id !== reference.id || profile.workspaceId !== workspaceId || profile.type !== 'xhs_creator_profile') throw new Error('这篇原笔记的来源已不可用，请移除后重新选择。')
    const note = importedReferenceNotes(profile).find(item => item.noteId === reference.noteId)
    if (!note) throw new Error('这篇原笔记已不可用，请移除后重新选择。')
    return importedReferencePreview(profile, note)
  }
  if (reference.kind === 'account_analysis') {
    const run = await analysisRunApi.get(reference.id)
    if (run.id !== reference.id || run.workspaceId !== workspaceId || run.workflowType !== 'account_diagnosis' || run.status !== 'completed') throw new Error('这份账号分析已不可用，请移除后重新选择。')
    return accountReferencePreview(run)
  }
  const run = await audienceAnalysisApi.get(reference.id)
  if (run.id !== reference.id || run.workspaceId !== workspaceId || run.status !== 'completed') throw new Error('这份受众分析已不可用，请移除后重新选择。')
  return audienceReferencePreview(run)
}
