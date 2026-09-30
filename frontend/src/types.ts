export type InputAssetType =
  | 'account_profile'
  | 'historical_posts'
  | 'comments'
  | 'trend_csv'
  | 'video_creator_samples'
  | 'xhs_creator_profile'

export type SourceMaterialType = InputAssetType

export interface Workspace {
  id: string
  name: string
  accountPositioning: string
  positioningVersion: number
  currentTopicId: string | null
  createdAt: string
  updatedAt: string
}

interface InputAssetBase {
  id: string
  workspaceId: string
  name: string
  createdAt: string
  updatedAt: string
}

export interface TextInputAsset extends InputAssetBase {
  type:
    | 'account_profile'
    | 'historical_posts'
    | 'comments'
    | 'video_creator_samples'
    | 'xhs_creator_profile'
  content: string
}

export interface TrendCsvInputAsset extends InputAssetBase {
  type: 'trend_csv'
  keyword: string
  originalFilename: string
  mediaType: string
  byteSize: number
  sha256: string
  rowCount: number
  preview: Array<Record<string, string>>
}

export type InputAsset = TextInputAsset | TrendCsvInputAsset
export type SourceMaterial = InputAsset
export type TextSourceMaterial = TextInputAsset
export type TrendCsvSourceMaterial = TrendCsvInputAsset
export type SavePhase = 'idle' | 'saving' | 'saved' | 'error'

export interface XhsOfflineImportResponse {
  inputAsset: TextInputAsset
  parsedNoteCount: number
  sourceUrl: string
  warnings: string[]
}

export interface XhsOfflineImportPackageResponse extends XhsOfflineImportResponse {
  mediaAssets: MediaAsset[]
}

export type XhsCaptureJobStatus =
  | 'pending'
  | 'waiting_for_login'
  | 'running'
  | 'processing'
  | 'completed'
  | 'failed'

export interface XhsCaptureJob {
  id: string
  workspaceId: string
  profileUrl: string
  resolvedUrl: string
  status: XhsCaptureJobStatus
  noteLimit: number
  includeComments: boolean
  statusMessage: string
  error: string
  resultInputAssetId: string | null
  createdAt: string
  startedAt: string | null
  completedAt: string | null
  updatedAt: string
}

export type MediaAssetType = 'image' | 'video'
export type MediaAssetSourceType = 'upload' | 'url' | 'generated' | 'extracted_frame'

export interface MediaAsset {
  id: string
  workspaceId: string
  type: MediaAssetType
  name: string
  purpose: string
  sourceType: MediaAssetSourceType
  originalFilename: string
  mediaType: string
  byteSize: number
  sha256: string
  metadata: Record<string, unknown>
  derived: Record<string, unknown>
  userNotes: string
  fileUrl: string
  externalUrl?: string
  createdAt: string
  updatedAt: string
}

export interface VideoPreviewDeriveResponse {
  videoAsset: MediaAsset
  frames: MediaAsset[]
}

export type SkillStatus = 'enabled' | 'disabled'
export type SkillSource = 'builtin' | 'generated'

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

export interface SkillDefinitionUpdate {
  displayName: string
  category: string
  purpose: string
  triggerIntents: string[]
  requiredInputs: string[]
  optionalInputs: string[]
  contextPolicy: Record<string, unknown>
  outputSchema: Record<string, unknown>
  artifactEffect: string
  sideEffects: string[]
  failureMode: string
  composableWith: string[]
  implementationRefs: string[]
  version: string
  userNotes: string
  expectedUpdatedAt: string
}

export interface CapabilityDefinitionDiff {
  assetId: string
  assetType: 'skill' | 'agent' | 'workflow'
  stableId: string
  source: 'builtin' | 'generated'
  canRevert: boolean
  changedFields: string[]
  currentDefinition: Record<string, unknown>
  builtinDefinition: Record<string, unknown> | null
}

export interface SkillInvokeResponse {
  skillAssetId: string
  skillId: string
  status: 'completed'
  output: Record<string, unknown>
  modelMetadata: Record<string, unknown>
}

export type SkillDryRunResponse = SkillInvokeResponse

export type AgentStatus = 'enabled' | 'disabled'
export type AgentSource = 'builtin' | 'generated'

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

export interface AgentDefinitionUpdate {
  displayName: string
  purpose: string
  systemPrompt: string
  skillIds: string[]
  defaultContextPolicy: Record<string, unknown>
  version: string
  userNotes: string
  expectedUpdatedAt: string
}

export type AgentConversationStatus = 'active' | 'archived'

export interface AgentConversationUpdate {
  title?: string
  status?: AgentConversationStatus
  expectedUpdatedAt: string
}

export interface AgentConversationSummary {
  id: string
  workspaceId: string
  agentAssetId: string
  title: string
  status: AgentConversationStatus
  executionStatus?: 'idle' | 'running' | 'failed' | 'completed'
  contextTarget: Record<string, unknown>
  createdAt: string
  updatedAt: string
}

export interface AgentMessage {
  id: string
  conversationId: string
  clientMessageKey?: string | null
  role: 'user' | 'assistant'
  content: string
  contextPack: Record<string, unknown>
  assetRefs: Array<Record<string, unknown>>
  proposedActions: Array<Record<string, unknown>>
  modelMetadata: Record<string, unknown>
  createdAt: string
}

export interface AgentConversation extends AgentConversationSummary {
  messages: AgentMessage[]
}

export type AssetProposalStatus = 'pending' | 'applied' | 'rejected' | 'failed'

export interface AssetProposal {
  id: string
  workspaceId: string
  conversationId: string
  messageId: string
  actionType: string
  title: string
  description: string
  status: AssetProposalStatus
  proposedAction: Record<string, unknown>
  result: Record<string, unknown>
  error: string
  createdAt: string
  updatedAt: string
  appliedAt: string | null
}

export interface AssetProposalDiffField {
  field: string
  current: unknown
  proposed: unknown
}

export interface AssetProposalPreview {
  proposalId: string
  actionType: string
  operation: 'create' | 'update' | 'unknown'
  targetAssetType: string
  targetAssetId: string | null
  targetStableId: string | null
  changedFields: AssetProposalDiffField[]
  currentSnapshot: Record<string, unknown>
  proposedSnapshot: Record<string, unknown>
  validationErrors: string[]
}

export type WorkflowAssetStatus = 'enabled' | 'disabled'
export type WorkflowAssetSource = 'builtin' | 'generated'

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
  callBinding: '' | 'account' | 'trend' | 'video'
  updatedAt: string
}

export interface WorkflowAsset extends WorkflowAssetSummary {
  agentPlan: Record<string, unknown>
  userNotes: string
}

export interface WorkflowAssetDefinitionUpdate {
  displayName: string
  purpose: string
  entryAgentIds: string[]
  agentPlan: Record<string, unknown>
  artifactEffect: string
  callBinding: '' | 'account' | 'trend' | 'video'
  version: string
  userNotes: string
  expectedUpdatedAt: string
}

export type WorkflowType =
  | 'account_diagnosis'
  | 'trend_analysis'
  | 'video_creator_quality'
export type ActivityRunType = WorkflowType | 'audience_simulation'
export type RunStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'partially_completed'
  | 'failed'
export type ReviewStatus = 'unreviewed' | 'useful' | 'rejected'

export interface AnalysisRunSummary {
  id: string
  workspaceId: string
  workflowType: WorkflowType
  status: RunStatus
  userNotes: string
  reviewStatus: ReviewStatus
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
  userNotes: string
  reviewStatus: ReviewStatus
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

export interface FanDefinition {
  name: string
  profile: string
  coreConcern: string
  contentPreference: string
  expressionStyle: string
}

export interface SimulatedFan {
  id: string
  workspaceId: string
  sourceAnalysisId: string
  sourceGroupId: string
  original: Record<string, unknown>
  editable: FanDefinition
  status: 'active' | 'archived'
  createdAt: string
  updatedAt: string
}

export type DraftStatus = 'pending' | 'running' | 'completed' | 'failed'
export type DraftKind = 'content_brief' | 'content_structure'

export interface DraftSummary {
  id: string
  workspaceId: string
  topicId: string
  kind: DraftKind
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
export type TopicSourceWorkflow = 'account_diagnosis' | 'trend_analysis' | 'manual'

export interface Topic {
  id: string
  workspaceId: string
  title: string
  angle: string
  body?: string
  pinned?: boolean
  associatedPainPoint: string
  whyItFits: string
  generatedSnapshot: Record<string, unknown>
  sourceAnalysisRunId: string | null
  sourceWorkflow: TopicSourceWorkflow
  status: TopicStatus
  createdAt: string
  updatedAt: string
}

export interface AudienceAnalysis {
  id: string
  workspaceId: string
  sourceMaterialId: string
  status: string
  diagnostics?: {
    acceptedGroups?: number;
    rejectedGroups?: Array<{groupIndex: number; groupId?: string; groupName?: string;
      issues: Array<{code: string; message: string; referenceIndex?: number}>}>;
  }
  inputSnapshot: { scope: { scope: string; selectedNoteCount: number } }
  result: {
    method?: string; origin?: string; summary?: string; limitations?: string;
    sampling?: { sentNotes: number; sentComments: number; availableComments: number };
    groups?: Array<{
      id: string; name: string; profile: string; coreConcern: string;
      estimatedPercent?: number | null; evidence: string[];
      evidenceRefs?: Array<{noteId: string; commentId?: string | null; sourceType: 'note' | 'comment'; quote: string}>;
    }>;
  }
  error: string
  createdAt: string
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
