import {analysisRunApi, audienceAnalysisApi} from './api'
import type {CreatorContextReference} from './contentCollaboration'
import type {AnalysisRun, AudienceAnalysis} from './types'
import {isOracleShowcase} from './recordOrigin'

export const referenceKindNames = {account_analysis: '账号分析', audience_analysis: '受众分析'}
export interface CreatorReferencePreview {
  reference: CreatorContextReference
  label: string
  scope: string
  summary: string
  lines: string[]
  isExample: boolean
}
export function referenceDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '历史记录' : date.toLocaleString('zh-CN', {month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit'})
}
const object = (value: unknown): Record<string, unknown> => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
const text = (value: unknown): string => typeof value === 'string' ? value : typeof object(value).statement === 'string' ? object(value).statement as string : ''
const lines = (value: unknown): string[] => Array.isArray(value) ? value.map(text).filter(Boolean) : []

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
  if (reference.kind === 'account_analysis') {
    const run = await analysisRunApi.get(reference.id)
    if (run.id !== reference.id || run.workspaceId !== workspaceId || run.workflowType !== 'account_diagnosis' || run.status !== 'completed') throw new Error('这份账号分析已不可用，请移除后重新选择。')
    return accountReferencePreview(run)
  }
  const run = await audienceAnalysisApi.get(reference.id)
  if (run.id !== reference.id || run.workspaceId !== workspaceId || run.status !== 'completed') throw new Error('这份受众分析已不可用，请移除后重新选择。')
  return audienceReferencePreview(run)
}
