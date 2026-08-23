import type { ActivePage } from './components/WorkspaceShell'
import type {
  StageView,
  WorkflowOutputKind,
} from './components/WorkflowOutputPanel'
import type { AnalysisRun, SimulationRun } from './types'
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
  { key: 'debate_responses', n: '03', title: '第二轮交叉回应' },
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
  const resultByStage: Record<string, unknown> = {
    personas: run.personaDefinitions.length
      ? { personas: run.personaDefinitions }
      : undefined,
    initial_reactions: run.reactionResults.length
      ? { reactions: run.reactionResults }
      : undefined,
    debate_responses: run.debateResults.length
      ? { debateResponses: run.debateResults }
      : undefined,
    synthesis: hasSynthesis ? { synthesis: run.synthesis } : undefined,
  }
  return SIMULATION_STAGES.map((stage) => ({
    ...stage,
    status: run.stageErrors[stage.key]
      ? 'failed'
      : resultByStage[stage.key]
        ? 'completed'
        : run.status === 'running'
          ? 'running'
          : 'waiting',
    result: resultByStage[stage.key],
    error: run.stageErrors[stage.key],
  }))
}
