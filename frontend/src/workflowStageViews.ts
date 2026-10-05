import type { ActivePage } from './components/WorkspaceShell'
import type {
  StageView,
  WorkflowOutputKind,
} from './components/WorkflowOutputPanel'
import type { ActivityEvent, AnalysisRun, SimulationRun } from './types'
import { withSimulationPersonaLabels } from './simulationPersonaLabels'
import {
  ACCOUNT_STAGES,
  TREND_STAGES,
  VIDEO_CREATOR_STAGES,
  type WorkflowTab,
} from './workflows'

export type WorkflowStageViews = Record<WorkflowTab, StageView[]>
export type WorkflowOutputKinds = Record<WorkflowTab, WorkflowOutputKind>

const SIMULATION_STAGES = [
  { key: 'personas', n: '01', title: '受众角色推导' },
  { key: 'initial_reactions', n: '02', title: '第一轮独立反应' },
  { key: 'debate_responses', n: '03', title: '看到评论后的情境回应' },
  { key: 'synthesis', n: '04', title: '策略合成' },
]

export const emptyWorkflowStageViews = (): WorkflowStageViews => ({
  account: [],
  trend: [],
  video: [],
})

export const defaultWorkflowOutputKinds = (): WorkflowOutputKinds => ({
  account: 'analysis',
  trend: 'analysis',
  video: 'analysis',
})

export function activePageForWorkflowTab(tab: WorkflowTab): ActivePage {
  if (tab === 'account') return 'account-diagnosis'
  if (tab === 'video') return 'video-quality'
  return 'trend-analysis'
}

export function stageSeed(tab: WorkflowTab): StageView[] {
  const stages =
    tab === 'account'
      ? ACCOUNT_STAGES
      : tab === 'video'
        ? VIDEO_CREATOR_STAGES
        : TREND_STAGES
  return stages.map((stage) => ({ ...stage, status: 'waiting' }))
}

export function simulationStageSeed(): StageView[] {
  return SIMULATION_STAGES.map((stage) => ({ ...stage, status: 'waiting' }))
}

// Observation only: preserve successful results when a parallel role fails.
export function applySimulationStageEvent(stages: StageView[], activity: ActivityEvent): StageView[] {
  const frozen = stages.find(s=>s.key==='synthesis')?.feedbackRun
  if (frozen && activity.runId !== frozen.id) return stages
  const key = activity.stageKey
  const kind = activity.data.eventType
  if (!key || !['stage.started', 'stage.succeeded', 'stage.failed'].includes(String(kind))) return stages
  const next:StageView[] = stages.map(stage => {
    if (stage.key !== key && !key.startsWith(`${stage.key}.`)) return stage
    if (kind === 'stage.started') return {...stage, status:'running'}
    if (kind === 'stage.succeeded') {
      const result = {...activity.data}
      delete result.eventType
      return {...stage, status:'completed', result}
    }
    const error = String(activity.data.error || '阶段执行失败')
    const raw = activity.data.stageErrors
    const structured = raw && typeof raw === 'object' && !Array.isArray(raw)
      ? Object.fromEntries(Object.entries(raw).filter(([k,v]) => (k === stage.key || k.startsWith(`${stage.key}.`)) && typeof v === 'string')) as Record<string,string>
      : {[key]:error}
    return {...stage, status:'failed', error, executionErrors:{...stage.executionErrors,...structured}}
  })
  if (frozen) {
    const result = (key:string) => (next.find(s=>s.key===key)?.result || {}) as Record<string,unknown>
    const records = (value:unknown, fallback:Record<string,unknown>[]) => Array.isArray(value) ? value : fallback
    return next.map(s=>s.key==='synthesis' ? {...s, feedbackRun:{...frozen,
      personaDefinitions:records(result('personas').personas,frozen.personaDefinitions),
      reactionResults:records(result('initial_reactions').reactions,frozen.reactionResults),
      debateResults:records(result('debate_responses').debateResponses,frozen.debateResults),
    }} : s)
  }
  return next
}

export function stageSeedFromRun(run: AnalysisRun): StageView[] {
  const tab =
    run.workflowType === 'account_diagnosis'
      ? 'account'
      : run.workflowType === 'video_creator_quality'
        ? 'video'
        : 'trend'
  return stageSeed(tab).map((stage) => ({
    ...stage,
    status: run.stageErrors[stage.key]
      ? 'failed'
      : run.stageResults[stage.key]
        ? 'completed'
        : run.status === 'running'
          ? 'running'
          : 'waiting',
    result: run.stageResults[stage.key],
    error: run.stageErrors[stage.key],
  }))
}

export function stageSeedFromSimulation(run: SimulationRun): StageView[] {
  const hasSynthesis = Object.keys(run.synthesis || {}).length > 0
  const statefulDiscussion = run.inputSnapshot?.simulationMethod === 'audience_methods_v2'
  const task = run.inputSnapshot?.panelTask as Record<string, unknown> | undefined
  const discussionDisabled = task?.protocolVersion === 'panel/v1' && task?.discussionEnabled === false
  const publicComments = run.reactionResults.filter(r => (!r.action || r.action === 'comment') && String(r.quote || r.text || '').trim())
  const noRecipient = statefulDiscussion
    ? !run.reactionResults.some(r => publicComments.some(p => p.personaId !== r.personaId))
    : publicComments.length < 2
  const debateFailed = Object.keys(run.stageErrors).some(key => key === 'debate_responses' || key.startsWith('debate_responses.'))
  const discussionSkipped = !debateFailed && !run.debateResults.length && (hasSynthesis || ['completed', 'partially_completed', 'failed'].includes(run.status)) && run.reactionResults.length > 0 && (discussionDisabled || noRecipient)
  const resultByStage: Record<string, unknown> = {
    personas: run.personaDefinitions.length
      ? { personas: run.personaDefinitions }
      : undefined,
    initial_reactions: run.reactionResults.length
      ? { reactions: run.reactionResults }
      : undefined,
    debate_responses: run.debateResults.length
      ? { debateResponses: run.debateResults }
      : discussionSkipped ? { debateResponses: [], skippedReason: discussionDisabled
        ? '本次只做独立试读，未开启互相回应。' : statefulDiscussion
        ? '没有可供其他读者回应的公开评论，跳过交流。'
        : '不足两条模拟公开评论，无需交叉回应。' } : undefined,
    synthesis: hasSynthesis ? { synthesis: run.synthesis } : undefined,
  }
  return withSimulationPersonaLabels(SIMULATION_STAGES.map((stage) => {
    const error = Object.entries(run.stageErrors)
      .filter(([key]) => key === stage.key || key.startsWith(`${stage.key}.`))
      .map(([, message]) => message).join('; ')
    return {
      ...stage,
      status: error
        ? 'failed'
        : resultByStage[stage.key]
          ? 'completed'
          : run.status === 'running'
            ? 'running'
            : 'waiting',
      result: resultByStage[stage.key],
      ...(stage.key === 'synthesis' ? {feedbackRun:{id:run.id,inputSnapshot:run.inputSnapshot,
        personaDefinitions:run.personaDefinitions,reactionResults:run.reactionResults,debateResults:run.debateResults}} : {}),
      error: error || undefined,
      executionErrors: Object.fromEntries(Object.entries(run.stageErrors).filter(([key]) => key === stage.key || key.startsWith(`${stage.key}.`))),
      executionEnded: ['completed', 'partially_completed', 'failed'].includes(run.status),
    }
  }))
}
