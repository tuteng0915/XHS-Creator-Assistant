export type SourceMaterialType =
  | 'historical_posts'
  | 'comments'
  | 'trend_csv'

export interface Workspace {
  id: string
  name: string
  accountPositioning: string
  positioningVersion: number
  currentTopicId: string | null
  createdAt: string
  updatedAt: string
}

interface SourceMaterialBase {
  id: string
  workspaceId: string
  name: string
  createdAt: string
  updatedAt: string
}

export interface TextSourceMaterial extends SourceMaterialBase {
  type: 'historical_posts' | 'comments'
  content: string
}

export interface TrendCsvSourceMaterial extends SourceMaterialBase {
  type: 'trend_csv'
  keyword: string
  originalFilename: string
  mediaType: string
  byteSize: number
  sha256: string
  rowCount: number
  preview: Array<Record<string, string>>
}

export type SourceMaterial = TextSourceMaterial | TrendCsvSourceMaterial
export type SavePhase = 'idle' | 'saving' | 'saved' | 'error'

export type SkillStatus = 'enabled' | 'disabled'
export type SkillSource = 'builtin'

export interface SkillSummary {
  id: string
  workspaceId: string
  skillId: string
  displayName: string
  category: string
  purpose: string
  artifactEffect: string
  source: SkillSource
  status: SkillStatus
  version: string
  updatedAt: string
}

export interface Skill extends SkillSummary {
  triggerIntents: string[]
  requiredInputs: string[]
  optionalInputs: string[]
  contextPolicy: Record<string, unknown>
  outputSchema: Record<string, unknown>
  sideEffects: string[]
  failureMode: string
  composableWith: string[]
  implementationRefs: string[]
  userNotes: string
}

export type AgentStatus = 'enabled' | 'disabled'
export type AgentSource = 'builtin'

export interface AgentSummary {
  id: string
  workspaceId: string
  agentId: string
  displayName: string
  purpose: string
  skillIds: string[]
  source: AgentSource
  status: AgentStatus
  version: string
  updatedAt: string
}

export interface Agent extends AgentSummary {
  systemPrompt: string
  defaultContextPolicy: Record<string, unknown>
  userNotes: string
}

export type WorkflowAssetStatus = 'enabled' | 'disabled'
export type WorkflowAssetSource = 'builtin'

export interface WorkflowAssetSummary {
  id: string
  workspaceId: string
  workflowId: string
  displayName: string
  purpose: string
  entryAgentIds: string[]
  artifactEffect: string
  source: WorkflowAssetSource
  status: WorkflowAssetStatus
  version: string
  updatedAt: string
}

export interface WorkflowAsset extends WorkflowAssetSummary {
  agentPlan: Record<string, unknown>
  userNotes: string
}

export type WorkflowType = 'account_diagnosis' | 'trend_analysis'
export type ActivityRunType = WorkflowType | 'audience_simulation'
export type RunStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'partially_completed'
  | 'failed'

export interface AnalysisRunSummary {
  id: string
  workspaceId: string
  workflowType: WorkflowType
  status: RunStatus
  createdAt: string
  startedAt: string | null
  completedAt: string | null
  updatedAt: string
}

export interface AnalysisRun extends AnalysisRunSummary {
  inputSnapshot: Record<string, unknown>
  stageResults: Record<string, unknown>
  stageErrors: Record<string, string>
  modelMetadata: Record<string, unknown>
}

export interface SimulationRunSummary {
  id: string
  workspaceId: string
  topicId: string | null
  draftId: string | null
  status: RunStatus
  createdAt: string
  startedAt: string | null
  completedAt: string | null
  updatedAt: string
}

export interface SimulationRun extends SimulationRunSummary {
  inputSnapshot: Record<string, unknown>
  personaDefinitions: Array<Record<string, unknown>>
  reactionResults: Array<Record<string, unknown>>
  debateResults: Array<Record<string, unknown>>
  synthesis: Record<string, unknown>
  stageErrors: Record<string, string>
  modelMetadata: Record<string, unknown>
}

export type DraftStatus = 'pending' | 'running' | 'completed' | 'failed'

export interface DraftSummary {
  id: string
  workspaceId: string
  topicId: string
  sourceAnalysisRunId: string | null
  sourceWorkflow: TopicSourceWorkflow
  status: DraftStatus
  createdAt: string
  completedAt: string | null
  updatedAt: string
}

export interface Draft extends DraftSummary {
  generatedSnapshot: Record<string, unknown>
  editableContent: Record<string, unknown>
  inputSnapshot: Record<string, unknown>
  stageErrors: Record<string, string>
  modelMetadata: Record<string, unknown>
}

export type TopicStatus = 'candidate' | 'selected' | 'archived'
export type TopicSourceWorkflow = WorkflowType | 'manual'

export interface Topic {
  id: string
  workspaceId: string
  title: string
  angle: string
  associatedPainPoint: string
  whyItFits: string
  generatedSnapshot: Record<string, unknown>
  sourceAnalysisRunId: string | null
  sourceWorkflow: TopicSourceWorkflow
  status: TopicStatus
  createdAt: string
  updatedAt: string
}

export type ModelOperation =
  | 'profile'
  | 'pain_points'
  | 'topics'
  | 'structure'
  | 'trend_analysis'
  | 'trend_topics'
  | 'simulation_personas'
  | 'simulation_reaction'
  | 'simulation_debate'
  | 'simulation_synthesis'

export interface ModelCallResponse {
  output: Record<string, unknown>
  modelMetadata: Record<string, unknown>
}

export interface ActivityEvent {
  eventId: string
  runId: string
  runType: ActivityRunType
  stageKey: string | null
  status: string
  sequence: number
  occurredAt: string
  data: Record<string, unknown> & { eventType?: string }
}
