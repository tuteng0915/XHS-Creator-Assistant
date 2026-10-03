import type { StageView } from './components/WorkflowOutputPanel'

export function simulationStageItems(stage: StageView): Record<string, unknown>[] {
  const result = stage.result as Record<string, unknown> | undefined
  const value = stage.key === 'initial_reactions' ? result?.reactions
    : stage.key === 'debate_responses' ? result?.debateResponses : undefined
  return Array.isArray(value) ? value.filter(item => item && typeof item === 'object') : []
}

export function missingReactionPeople(stage: StageView): string[] {
  if (stage.key !== 'initial_reactions' || (!stage.executionEnded && !['completed', 'failed'].includes(stage.status))) return []
  const returned = new Set(simulationStageItems(stage).map(item => String(item.personaId)))
  return (stage.personaIds || []).filter(id => !returned.has(id))
}

export function stageDisplayStatus(stage: StageView): { label: string; className: string } {
  const hasErrors = Boolean(stage.error || Object.keys(stage.executionErrors || {}).length)
  const missing = missingReactionPeople(stage).length > 0
  if (simulationStageItems(stage).length && (hasErrors || missing)) return {label:'部分完成',className:'partial'}
  if (stage.status === 'failed' || hasErrors) return {label:'失败',className:'failed'}
  if (stage.executionEnded && stage.status === 'waiting') return {label:'未完成',className:'waiting'}
  return {label: {waiting:'等待中',running:'分析中…',completed:'已完成',failed:'失败'}[stage.status],className:stage.status}
}
