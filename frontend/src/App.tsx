import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from 'react'

import {
  agentApi,
  agentConversationApi,
  analysisRunApi,
  assetProposalApi,
  draftApi,
  mediaAssetApi,
  simulationRunApi,
  skillApi,
  inputAssetApi,
  topicApi,
  workspaceApi,
  workflowAssetApi,
  xhsCaptureApi,
} from './api'
import { HealthPage } from './HealthPage'
import { AccountProfilePage } from './components/AccountProfilePage'
import { AgentDefinitionEditor } from './components/AgentDefinitionEditor'
import { AgentConversationPanel } from './components/AgentConversationPanel'
import { AgentsPage } from './components/AgentsPage'
import { AnalysisHistoryPage } from './components/AnalysisHistoryPage'
import {
  DraftStructureRenderer,
  StageResultRenderer,
} from './components/ArtifactRenderers'
import { CapabilityDefinitionDiffPanel } from './components/CapabilityDefinitionDiffPanel'
import { ConversationsPage } from './components/ConversationsPage'
import { CreatorStartPage } from './components/CreatorStartPage'
import { DraftsPage } from './components/DraftsPage'
import { InputAssetsPage } from './components/InputAssetsPage'
import { MediaAssetsPage } from './components/MediaAssetsPage'
import { SimulationHistoryPage } from './components/SimulationHistoryPage'
import { SkillDefinitionEditor } from './components/SkillDefinitionEditor'
import { SkillsPage } from './components/SkillsPage'
import { SkillTestPanel } from './components/SkillTestPanel'
import {
  listFromText,
  validateAgentDefinitionDraft,
  validateWorkflowDefinitionDraft,
  type AgentDefinitionDraft,
  type SkillDefinitionDraft,
  type WorkflowDefinitionDraft,
} from './capabilityDefinitionValidation'
import {
  DEFAULT_WORKSPACE_NAME,
  EMPTY_INPUT_ASSET_NAMES,
  FORMATTER_SKILL_ID_BY_PANEL,
  MAKER_AGENT_IDS,
  NEW_INPUT_ASSET_ID,
  SAMPLE_ASSET_NAMES,
  SAVE_KEY_BY_XHS_IMPORT_PANEL,
  XHS_IMPORT_TYPE_BY_PANEL,
  agentToDefinitionDraft,
  chooseDefaultWorkspaceId,
  defaultSkillTestInput,
  draftDisplayTitle,
  draftKindLabel,
  emptyXhsImportFiles,
  errorMessage,
  fileRelativePath,
  idleState,
  isDirectlyInvokableSkill,
  latestTextMaterial,
  latestTrendMaterial,
  newClientRequestKey,
  reviewStatusLabel,
  skillToDefinitionDraft,
  workflowFromTab,
  workflowTabFromSimulation,
  workflowTabFromSource,
  workflowToDefinitionDraft,
  type CapabilityAssetType,
  type ConversationContextTarget,
  type DefinitionDiffStatus,
  type SaveKey,
  type XhsImportPanel,
} from './appUtils'
import { type SaveState } from './components/StageResultViews'
import { TopicLibraryPage } from './components/TopicLibraryPage'
import { WorkspaceShell, type ActivePage } from './components/WorkspaceShell'
import { WorkflowDefinitionEditor } from './components/WorkflowDefinitionEditor'
import { WorkflowsPage } from './components/WorkflowsPage'
import { WorkflowRunPage } from './components/WorkflowRunPage'
import { CreatorMaterialsPage } from './components/CreatorMaterialsPage'
import { CreatorDiagnosisPage } from './components/CreatorDiagnosisPage'
import { CreatorOverviewPage } from './components/CreatorOverviewPage'
import { AudienceAnalysisPage } from './components/AudienceAnalysisPage'
import { CreatorCanvasPage } from './components/CreatorCanvasPage'
import { useAudienceAnalyses } from './hooks/useAudienceAnalyses'
import type { AnalysisScope } from './creatorNotes'
import {
  WorkflowOutputPanel,
  type StageView,
  type WorkflowOutputKind,
} from './components/WorkflowOutputPanel'
import {
  INPUT_ASSET_DEFINITION_BY_PANEL,
  type InputAssetPanel,
} from './inputAssets'
import { getWorkspaceHelpContent } from './helpContent'
import { useAgentConversationAutoFocus } from './hooks/useAgentConversationAutoFocus'
import { usePendingAgentConversationPolling } from './hooks/usePendingAgentConversationPolling'
import { useSaveStates } from './hooks/useSaveStates'
import { useWorkspaceAssetSelections } from './hooks/useWorkspaceAssetSelections'
import type {
  Agent,
  AgentConversation,
  AgentConversationSummary,
  AgentConversationStatus,
  AgentDefinitionUpdate,
  AgentSummary,
  AnalysisRun,
  AnalysisRunSummary,
  ActivityEvent,
  AssetProposal,
  CapabilityDefinitionDiff,
  Draft,
  DraftSummary,
  SimulationRun,
  SimulationRunSummary,
  Skill,
  SkillDefinitionUpdate,
  SkillInvokeResponse,
  SkillSummary,
  InputAsset,
  MediaAsset,
  ReviewStatus,
  TextInputAsset,
  Topic,
  TopicSourceWorkflow,
  TrendCsvInputAsset,
  Workspace,
  WorkflowAsset,
  WorkflowAssetDefinitionUpdate,
  WorkflowAssetSummary,
  XhsCaptureJob,
} from './types'
import {
  type GenerationMode,
  type TopicCandidate,
  type WorkflowTab,
} from './workflows'
import {
  activePageForWorkflowTab,
  defaultWorkflowOutputKinds,
  emptyWorkflowStageViews,
  simulationStageSeed,
  stageSeed,
  stageSeedFromRun,
  stageSeedFromSimulation,
  type WorkflowOutputKinds,
  type WorkflowStageViews,
} from './workflowStageViews'
import {
  previewXhsImportPackage,
  xhsPackageRelativePaths,
  type XhsImportPackagePreview,
} from './xhsCreatorProfile'
import {
  SAMPLE_ACCOUNT_INPUT,
  SAMPLE_TREND_CSV,
  SAMPLE_TREND_INPUT,
  SAMPLE_VIDEO_INPUT,
} from './sampleInputs'

type SkillTestStatus = 'idle' | 'running' | 'completed' | 'error'

function WorkspaceApp() {
  const internalMode = new URLSearchParams(window.location.search).get('internal') === '1'
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState('')
  const selectedWorkspaceRef = useRef(selectedWorkspaceId)
  useEffect(() => { selectedWorkspaceRef.current = selectedWorkspaceId }, [selectedWorkspaceId])
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [workspace, setWorkspace] = useState<Workspace | null>(null)
  const [materials, setMaterials] = useState<InputAsset[]>([])
  const [mediaAssets, setMediaAssets] = useState<MediaAsset[]>([])
  const [analysisRuns, setAnalysisRuns] = useState<AnalysisRunSummary[]>([])
  const [selectedRun, setSelectedRun] = useState<AnalysisRun | null>(null)
  const [simulationRuns, setSimulationRuns] = useState<SimulationRunSummary[]>([])
  const [selectedSimulationRun, setSelectedSimulationRun] =
    useState<SimulationRun | null>(null)
  const [skills, setSkills] = useState<SkillSummary[]>([])
  const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null)
  const [skillDefinitionDraft, setSkillDefinitionDraft] =
    useState<SkillDefinitionDraft | null>(null)
  const [skillDefinitionSaving, setSkillDefinitionSaving] = useState(false)
  const [skillDefinitionStatus, setSkillDefinitionStatus] = useState('')
  const [skillTestInput, setSkillTestInput] = useState('')
  const [skillTestMode, setSkillTestMode] = useState<GenerationMode>('demo')
  const [skillTestStatus, setSkillTestStatus] = useState<SkillTestStatus>('idle')
  const [skillTestResult, setSkillTestResult] = useState<SkillInvokeResponse | null>(
    null,
  )
  const [skillTestError, setSkillTestError] = useState('')
  const [agents, setAgents] = useState<AgentSummary[]>([])
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null)
  const [agentDefinitionDraft, setAgentDefinitionDraft] =
    useState<AgentDefinitionDraft | null>(null)
  const [agentDefinitionSaving, setAgentDefinitionSaving] = useState(false)
  const [agentDefinitionStatus, setAgentDefinitionStatus] = useState('')
  const [agentConversations, setAgentConversations] = useState<
    AgentConversationSummary[]
  >([])
  const [selectedAgentConversation, setSelectedAgentConversation] =
    useState<AgentConversation | null>(null)
  const [assetProposals, setAssetProposals] = useState<AssetProposal[]>([])
  const [conversationTitleDraft, setConversationTitleDraft] = useState('')
  const [agentMessageDraft, setAgentMessageDraft] = useState('')
  const [agentMessageClientKey, setAgentMessageClientKey] = useState(() =>
    newClientRequestKey('agent-message'),
  )
  const [agentSending, setAgentSending] = useState(false)
  const [conversationSaving, setConversationSaving] = useState(false)
  const [conversationSaveStatus, setConversationSaveStatus] = useState('')
  const [agentConversationCreating, setAgentConversationCreating] = useState(false)
  const [workflowAssets, setWorkflowAssets] = useState<WorkflowAssetSummary[]>([])
  const [selectedWorkflowAsset, setSelectedWorkflowAsset] =
    useState<WorkflowAsset | null>(null)
  const [workflowDefinitionDraft, setWorkflowDefinitionDraft] =
    useState<WorkflowDefinitionDraft | null>(null)
  const [workflowDefinitionSaving, setWorkflowDefinitionSaving] = useState(false)
  const [workflowDefinitionStatus, setWorkflowDefinitionStatus] = useState('')
  const [definitionDiff, setDefinitionDiff] =
    useState<CapabilityDefinitionDiff | null>(null)
  const [definitionDiffStatus, setDefinitionDiffStatus] =
    useState<DefinitionDiffStatus>('idle')
  const [definitionDiffError, setDefinitionDiffError] = useState('')
  const [drafts, setDrafts] = useState<DraftSummary[]>([])
  const [selectedDraft, setSelectedDraft] = useState<Draft | null>(null)
  const [draftEditor, setDraftEditor] = useState('')
  const [topics, setTopics] = useState<Topic[]>([])
  const [selectedTopic, setSelectedTopic] = useState<Topic | null>(null)
  const [topicFilter, setTopicFilter] = useState<TopicSourceWorkflow | 'all'>('all')
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [showHelp, setShowHelp] = useState(false)
  const [activePage, setActivePage] = useState<ActivePage>(internalMode ? 'account-diagnosis' : 'creator-overview')
  const [workflowTab, setWorkflowTab] = useState<WorkflowTab>('account')
  const [mode, setMode] = useState<GenerationMode>(internalMode ? 'demo' : 'live')
  const [workspaceName, setWorkspaceName] = useState('')
  const [positioning, setPositioning] = useState('')
  const [accountProfileDraftName, setAccountProfileDraftName] = useState<string>(
    SAMPLE_ASSET_NAMES.qsheepProfile,
  )
  const [historicalPostsDraftName, setHistoricalPostsDraftName] = useState<string>(
    SAMPLE_ASSET_NAMES.historicalPosts,
  )
  const [commentsDraftName, setCommentsDraftName] = useState<string>(
    SAMPLE_ASSET_NAMES.comments,
  )
  const [trendCsvDraftName, setTrendCsvDraftName] = useState<string>(
    SAMPLE_ASSET_NAMES.trendCsv,
  )
  const [videoCreatorSamplesDraftName, setVideoCreatorSamplesDraftName] =
    useState<string>(SAMPLE_ASSET_NAMES.videoCreatorSamples)
  const [xhsCreatorProfileDraftName, setXhsCreatorProfileDraftName] =
    useState<string>(SAMPLE_ASSET_NAMES.xhsCreatorProfile)
  const [selectedProfileInputAssetId, setSelectedProfileInputAssetId] = useState('')
  const [xhsImportFiles, setXhsImportFiles] =
    useState<Record<XhsImportPanel, File | null>>(emptyXhsImportFiles)
  const [xhsPackageFiles, setXhsPackageFiles] = useState<File[]>([])
  const [xhsPackagePreview, setXhsPackagePreview] =
    useState<XhsImportPackagePreview | null>(null)
  const [xhsPackagePreviewError, setXhsPackagePreviewError] = useState('')
  const [xhsImportWarnings, setXhsImportWarnings] = useState<string[]>([])
  const [inputAssetPanel, setInputAssetPanel] =
    useState<InputAssetPanel>('historical_posts')
  const [inputAssetDetailOpen, setInputAssetDetailOpen] = useState(false)
  const [selectedHistoricalInputAssetId, setSelectedHistoricalInputAssetId] =
    useState('')
  const [selectedCommentsInputAssetId, setSelectedCommentsInputAssetId] = useState('')
  const [selectedTrendInputAssetId, setSelectedTrendInputAssetId] = useState('')
  const [selectedVideoInputAssetId, setSelectedVideoInputAssetId] = useState('')
  const [selectedXhsCreatorProfileInputAssetId, setSelectedXhsCreatorProfileInputAssetId] =
    useState('')
  const [selectedVideoWorkflowMediaAssetIds, setSelectedVideoWorkflowMediaAssetIds] =
    useState<string[]>([])
  const [historicalPosts, setHistoricalPosts] = useState('')
  const [comments, setComments] = useState('')
  const [trendKeyword, setTrendKeyword] = useState('')
  const [trendFile, setTrendFile] = useState<File | null>(null)
  const [videoCreatorSamples, setVideoCreatorSamples] = useState('')
  const [xhsCreatorProfileContent, setXhsCreatorProfileContent] = useState('')
  const [xhsProfileUrl, setXhsProfileUrl] = useState('')
  const [captureNoteLimit, setCaptureNoteLimit] = useState(10)
  const [addingCreator, setAddingCreator] = useState(false)
  const captureFormEpoch = useRef(0)
  const [analysisScope, setAnalysisScope] = useState<AnalysisScope>('recent_10')
  const [xhsCaptureJob, setXhsCaptureJob] = useState<XhsCaptureJob | null>(null)
  const [xhsCaptureSubmitting, setXhsCaptureSubmitting] = useState(false)
  const [xhsCaptureError, setXhsCaptureError] = useState('')
  const [inputAssetFormatterDraft, setInputAssetFormatterDraft] = useState('')
  const [inputAssetFormatterStatus, setInputAssetFormatterStatus] = useState('')
  const [simulationTopic, setSimulationTopic] = useState('')
  const [analysisStageViewsByWorkflow, setAnalysisStageViewsByWorkflow] =
    useState<WorkflowStageViews>(emptyWorkflowStageViews)
  const [simulationStageViews, setSimulationStageViews] = useState<StageView[]>([])
  const [workflowOutputKindByWorkflow, setWorkflowOutputKindByWorkflow] =
    useState<WorkflowOutputKinds>(defaultWorkflowOutputKinds)
  const [currentRun, setCurrentRun] = useState<AnalysisRun | null>(null)
  const [running, setRunning] = useState(false)
  const [runError, setRunError] = useState('')
  const [manualTopicTitle, setManualTopicTitle] = useState('')
  const [manualTopicAngle, setManualTopicAngle] = useState('')
  const [topicDraft, setTopicDraft] = useState<{title:string; angle:string; body?:string}>({ title: '', angle: '', body: '' })
  const audience = useAudienceAnalyses(selectedWorkspaceId)
  const { saveStates, setSaveState, resetSaveStates, setSaveStates } =
    useSaveStates()
  const [analysisReviewDraft, setAnalysisReviewDraft] = useState<{
    userNotes: string
    reviewStatus: ReviewStatus
  }>({ userNotes: '', reviewStatus: 'unreviewed' })
  const [simulationReviewDraft, setSimulationReviewDraft] = useState<{
    userNotes: string
    reviewStatus: ReviewStatus
  }>({ userNotes: '', reviewStatus: 'unreviewed' })

  const {
    accountProfileMaterials,
    selectedProfileMaterial,
    historicalMaterials,
    commentsMaterials,
    trendMaterials,
    videoCreatorSamplesMaterials,
    xhsCreatorProfileMaterials,
    historicalMaterial,
    commentsMaterial,
    videoCreatorSamplesMaterial,
    xhsCreatorProfileMaterial,
    matchingXhsPackageMaterial,
    trendMaterial,
    videoWorkflowMediaAssets,
  } = useWorkspaceAssetSelections({
    materials,
    mediaAssets,
    selectedProfileInputAssetId,
    selectedHistoricalInputAssetId,
    selectedCommentsInputAssetId,
    selectedTrendInputAssetId,
    selectedVideoInputAssetId,
    selectedXhsCreatorProfileInputAssetId,
    selectedVideoWorkflowMediaAssetIds,
    xhsPackagePreview,
  })
  const agentChatComposerRef = useRef<HTMLTextAreaElement | null>(null)
  const selectedAgentConversationId = selectedAgentConversation?.id

  useAgentConversationAutoFocus({
    activePage,
    selectedAgentConversationId,
    composerRef: agentChatComposerRef,
  })

  function updateAgentMessageDraft(value: string) {
    setAgentMessageDraft(value)
    setAgentMessageClientKey(newClientRequestKey('agent-message'))
  }

  usePendingAgentConversationPolling({
    selectedAgentConversation,
    selectedAgentConversationId,
    setSelectedAgentConversation,
    setAgentConversations,
    setAssetProposals,
  })

  const resetWorkspaceState = useCallback(() => {
    setWorkspace(null)
    setMaterials([])
    setMediaAssets([])
    setAnalysisRuns([])
    setSimulationRuns([])
    setSkills([])
    setAgents([])
    setWorkflowAssets([])
    setDrafts([])
    setTopics([])
    setSelectedTopic(null)
    setWorkspaceName('')
    setPositioning('')
    setAccountProfileDraftName(SAMPLE_ASSET_NAMES.qsheepProfile)
    setHistoricalPostsDraftName(SAMPLE_ASSET_NAMES.historicalPosts)
    setCommentsDraftName(SAMPLE_ASSET_NAMES.comments)
    setTrendCsvDraftName(SAMPLE_ASSET_NAMES.trendCsv)
    setVideoCreatorSamplesDraftName(SAMPLE_ASSET_NAMES.videoCreatorSamples)
    setXhsCreatorProfileDraftName(SAMPLE_ASSET_NAMES.xhsCreatorProfile)
    setSelectedProfileInputAssetId('')
    setXhsImportFiles(emptyXhsImportFiles())
    setXhsPackageFiles([])
    setXhsPackagePreview(null)
    setXhsPackagePreviewError('')
    setXhsImportWarnings([])
    setInputAssetPanel('historical_posts')
    setSelectedHistoricalInputAssetId('')
    setSelectedCommentsInputAssetId('')
    setSelectedTrendInputAssetId('')
    setSelectedVideoInputAssetId('')
    setSelectedXhsCreatorProfileInputAssetId('')
    setSelectedVideoWorkflowMediaAssetIds([])
    setHistoricalPosts('')
    setComments('')
    setVideoCreatorSamples('')
    setXhsCreatorProfileContent('')
    setXhsCaptureJob(null)
    setXhsCaptureError('')
    setTrendKeyword('')
    setCurrentRun(null)
    setSelectedSimulationRun(null)
    setSelectedSkill(null)
    setSelectedAgent(null)
    setAgentConversations([])
    setSelectedAgentConversation(null)
    setAssetProposals([])
    setAgentMessageDraft('')
    setAgentMessageClientKey(newClientRequestKey('agent-message'))
    setAgentConversationCreating(false)
    setSelectedWorkflowAsset(null)
    setSelectedDraft(null)
    setDraftEditor('')
    setAnalysisStageViewsByWorkflow(emptyWorkflowStageViews())
    setSimulationStageViews([])
    setWorkflowOutputKindByWorkflow(defaultWorkflowOutputKinds())
    resetSaveStates()
  }, [resetSaveStates])

  useEffect(() => {
    let active = true
    async function loadDefaultWorkspace() {
      try {
        const items = await workspaceApi.list()
        if (!active) return
        if (items.length > 0) {
          setWorkspaces(items)
          const rememberedWorkspaceId =
            typeof window.localStorage?.getItem === 'function'
              ? window.localStorage.getItem('creator-focused-workspace-id')
              : null
          const workspaceId = items.some(
            (item) => item.id === rememberedWorkspaceId,
          )
            ? rememberedWorkspaceId || items[0].id
            : await chooseDefaultWorkspaceId(items)
          if (!active) return
          setSelectedWorkspaceId((current) => current || workspaceId)
          return
        }
        if (!internalMode) {
          setAddingCreator(true)
          setActivePage('creator-start')
          setLoading(false)
          return
        }
        const created = await workspaceApi.create(DEFAULT_WORKSPACE_NAME, '')
        if (!active) return
        setWorkspaces([created])
        setSelectedWorkspaceId(created.id)
      } catch (error: unknown) {
        if (!active) return
        setLoadError(errorMessage(error))
        setLoading(false)
      }
    }
    void loadDefaultWorkspace()
    return () => {
      active = false
    }
  }, [internalMode])

  useEffect(() => {
    if (
      selectedWorkspaceId &&
      typeof window.localStorage?.setItem === 'function'
    ) {
      window.localStorage.setItem(
        'creator-focused-workspace-id',
        selectedWorkspaceId,
      )
    }
  }, [selectedWorkspaceId])

  useEffect(() => {
    if (!selectedWorkspaceId) {
      resetWorkspaceState()
      return
    }
    let active = true
    setLoading(true)
    setLoadError('')
    Promise.all([
      workspaceApi.get(selectedWorkspaceId),
      inputAssetApi.list(selectedWorkspaceId),
      mediaAssetApi.list(selectedWorkspaceId),
      analysisRunApi.list(selectedWorkspaceId),
      simulationRunApi.list(selectedWorkspaceId),
      skillApi.list(selectedWorkspaceId),
      agentApi.list(selectedWorkspaceId),
      agentConversationApi.list(selectedWorkspaceId),
      workflowAssetApi.list(selectedWorkspaceId),
      draftApi.list(selectedWorkspaceId),
      topicApi.list(selectedWorkspaceId),
    ])
      .then(
        ([
          loadedWorkspace,
          loadedMaterials,
          loadedMediaAssets,
          loadedRuns,
          loadedSimulationRuns,
          loadedSkills,
          loadedAgents,
          loadedAgentConversations,
          loadedWorkflowAssets,
          loadedDrafts,
          loadedTopics,
        ]) => {
        if (!active) return
        setWorkspace(loadedWorkspace)
        setWorkspaces((current) =>
          current.some((item) => item.id === loadedWorkspace.id)
            ? current.map((item) =>
                item.id === loadedWorkspace.id ? loadedWorkspace : item,
              )
            : [...current, loadedWorkspace],
        )
        setMaterials(loadedMaterials)
        setMediaAssets(loadedMediaAssets)
        setAnalysisRuns(loadedRuns)
        setSimulationRuns(loadedSimulationRuns)
        setSkills(loadedSkills)
        setAgents(loadedAgents)
        setAgentConversations(loadedAgentConversations)
        setWorkflowAssets(loadedWorkflowAssets)
        setDrafts(loadedDrafts)
        setTopics(loadedTopics)
        setSelectedTopic(
          loadedTopics.find((topic) => topic.id === loadedWorkspace.currentTopicId) ||
            loadedTopics[0] ||
            null,
        )
        setWorkspaceName(loadedWorkspace.name)
        setPositioning(loadedWorkspace.accountPositioning)
        setSelectedProfileInputAssetId(
          latestTextMaterial(loadedMaterials, 'account_profile')?.id || '',
        )
        setAccountProfileDraftName(
          latestTextMaterial(loadedMaterials, 'account_profile')?.name ||
            SAMPLE_ASSET_NAMES.qsheepProfile,
        )
        setSelectedHistoricalInputAssetId(
          latestTextMaterial(loadedMaterials, 'historical_posts')?.id || '',
        )
        setHistoricalPostsDraftName(
          latestTextMaterial(loadedMaterials, 'historical_posts')?.name ||
            SAMPLE_ASSET_NAMES.historicalPosts,
        )
        setSelectedCommentsInputAssetId(
          latestTextMaterial(loadedMaterials, 'comments')?.id || '',
        )
        setCommentsDraftName(
          latestTextMaterial(loadedMaterials, 'comments')?.name ||
            SAMPLE_ASSET_NAMES.comments,
        )
        setSelectedTrendInputAssetId(latestTrendMaterial(loadedMaterials)?.id || '')
        setTrendCsvDraftName(
          latestTrendMaterial(loadedMaterials)?.name || SAMPLE_ASSET_NAMES.trendCsv,
        )
        setSelectedVideoInputAssetId(
          latestTextMaterial(loadedMaterials, 'video_creator_samples')?.id || '',
        )
        setSelectedVideoWorkflowMediaAssetIds([])
        setVideoCreatorSamplesDraftName(
          latestTextMaterial(loadedMaterials, 'video_creator_samples')?.name ||
            SAMPLE_ASSET_NAMES.videoCreatorSamples,
        )
        setSelectedXhsCreatorProfileInputAssetId(
          latestTextMaterial(loadedMaterials, 'xhs_creator_profile')?.id || '',
        )
        setXhsCreatorProfileDraftName(
          latestTextMaterial(loadedMaterials, 'xhs_creator_profile')?.name ||
            SAMPLE_ASSET_NAMES.xhsCreatorProfile,
        )
        setHistoricalPosts(
          latestTextMaterial(loadedMaterials, 'historical_posts')?.content || '',
        )
        setComments(latestTextMaterial(loadedMaterials, 'comments')?.content || '')
        setVideoCreatorSamples(
          latestTextMaterial(loadedMaterials, 'video_creator_samples')?.content || '',
        )
        setXhsCreatorProfileContent(
          latestTextMaterial(loadedMaterials, 'xhs_creator_profile')?.content || '',
        )
        if (
          !internalMode &&
          !latestTextMaterial(loadedMaterials, 'xhs_creator_profile')
        ) {
          setActivePage('creator-start')
        }
        setTrendKeyword(latestTrendMaterial(loadedMaterials)?.keyword || '')
        setSimulationTopic('')
        setCurrentRun(null)
        setSelectedRun(null)
        setSelectedSimulationRun(null)
        setSelectedSkill(null)
        setSelectedAgent(null)
        setSelectedAgentConversation(null)
        setAssetProposals([])
        setAgentMessageDraft('')
        setAgentMessageClientKey(newClientRequestKey('agent-message'))
        setSelectedWorkflowAsset(null)
        setSelectedDraft(null)
        setDraftEditor('')
        setAnalysisStageViewsByWorkflow(emptyWorkflowStageViews())
        setSimulationStageViews([])
        setWorkflowOutputKindByWorkflow(defaultWorkflowOutputKinds())
        resetSaveStates()
        setLoading(false)
      },
      )
      .catch((error: unknown) => {
        if (!active) return
        setLoadError(errorMessage(error))
        setLoading(false)
      })
    return () => {
      active = false
    }
  }, [internalMode, resetWorkspaceState, resetSaveStates, selectedWorkspaceId])

  useEffect(() => {
    if (!selectedWorkspaceId) return
    let active = true
    xhsCaptureApi
      .list(selectedWorkspaceId)
      .then((jobs) => {
        if (active) {
          setXhsCaptureJob(jobs[0] || null)
          setXhsProfileUrl(jobs[0]?.profileUrl || '')
        }
      })
      .catch(() => {
        if (active) setXhsCaptureJob(null)
      })
    return () => {
      active = false
    }
  }, [selectedWorkspaceId])

  useEffect(() => {
    if (
      !xhsCaptureJob ||
      !['pending', 'waiting_for_login', 'running', 'processing'].includes(
        xhsCaptureJob.status,
      )
    ) {
      return
    }
    let active = true
    const timer = window.setInterval(() => {
      void xhsCaptureApi
        .get(xhsCaptureJob.id)
        .then(async (job) => {
          if (!active) return
          setXhsCaptureJob(job)
          if (job.status === 'completed') {
            await refreshImportedCreatorAccount(job.workspaceId)
          }
        })
        .catch((error: unknown) => {
          if (active) setXhsCaptureError(errorMessage(error))
        })
    }, 1_500)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [xhsCaptureJob])

  async function refreshImportedCreatorAccount(workspaceId: string) {
    const [loadedWorkspace, loadedMaterials, loadedMediaAssets] = await Promise.all([
      workspaceApi.get(workspaceId),
      inputAssetApi.list(workspaceId),
      mediaAssetApi.list(workspaceId),
    ])
    if (selectedWorkspaceRef.current !== workspaceId) return
    setWorkspace(loadedWorkspace)
    setWorkspaces((current) =>
      current.map((item) => (item.id === loadedWorkspace.id ? loadedWorkspace : item)),
    )
    setMaterials(loadedMaterials)
    setMediaAssets(loadedMediaAssets)
    const importedProfile = latestTextMaterial(
      loadedMaterials,
      'xhs_creator_profile',
    )
    setSelectedXhsCreatorProfileInputAssetId(importedProfile?.id || '')
    setXhsCreatorProfileDraftName(
      importedProfile?.name || SAMPLE_ASSET_NAMES.xhsCreatorProfile,
    )
    setXhsCreatorProfileContent(importedProfile?.content || '')
  }

  function createCreatorProfile() {
    captureFormEpoch.current += 1
    setAddingCreator(true)
    setXhsProfileUrl('')
    setXhsCaptureJob(null)
    setXhsCaptureError('')
    setActivePage('creator-start')
  }

  function openExistingCreatorImport() {
    const epoch = ++captureFormEpoch.current
    setAddingCreator(false)
    setXhsCaptureError('')
    setActivePage('creator-start')
    let profileUrl = ''
    let count = 0
    try {
      const parsed = JSON.parse(xhsCreatorProfileMaterial?.content || '{}')
      profileUrl = String(parsed.source?.profileUrl || '')
      count = Array.isArray(parsed.notes) ? parsed.notes.length : 0
    } catch { /* Legacy content may not contain a structured profile URL. */ }
    setCaptureNoteLimit(count ? [20,50,100].find(limit => limit > count) || 0 : 10)
    setXhsProfileUrl(profileUrl)
    if (workspace) {
      const workspaceId = workspace.id
      void xhsCaptureApi.list(workspaceId).then(jobs => {
        if (selectedWorkspaceRef.current !== workspaceId || captureFormEpoch.current !== epoch) return
        setXhsCaptureJob(jobs[0] || null)
        if (jobs[0]?.profileUrl) setXhsProfileUrl(jobs[0].profileUrl)
      }).catch(error => {if(captureFormEpoch.current === epoch) setXhsCaptureError(errorMessage(error))})
    }
  }

  async function startXhsCapture(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!workspace && !addingCreator) return
    setXhsCaptureSubmitting(true)
    setXhsCaptureError('')
    try {
      const payload = {
        profileUrl: xhsProfileUrl,
        noteLimit: captureNoteLimit,
        includeComments: true,
      }
      const job = addingCreator
        ? await xhsCaptureApi.createAccount(payload)
        : await xhsCaptureApi.create(workspace!.id, payload)
      if (addingCreator) {
        const loaded = await workspaceApi.list()
        setWorkspaces(loaded)
        selectedWorkspaceRef.current = job.workspaceId
        setSelectedWorkspaceId(job.workspaceId)
        setAddingCreator(false)
      }
      setXhsCaptureJob(job)
    } catch (error: unknown) {
      setXhsCaptureError(errorMessage(error))
    } finally {
      setXhsCaptureSubmitting(false)
    }
  }

  function clearXhsImportTransientState() {
    setXhsPackageFiles([])
    setXhsPackagePreview(null)
    setXhsPackagePreviewError('')
    setXhsImportWarnings([])
  }

  function openInputAsset(panel: InputAssetPanel) {
    setInputAssetPanel(panel)
    setInputAssetDetailOpen(false)
    setInputAssetFormatterDraft('')
    setInputAssetFormatterStatus('')
    setActivePage('source-materials')
  }

  function chooseTextMaterialFromInputAssetPage(material: TextInputAsset) {
    setInputAssetDetailOpen(true)
    chooseTextMaterial(material)
  }

  function chooseTrendMaterialFromInputAssetPage(material: TrendCsvInputAsset) {
    setInputAssetDetailOpen(true)
    chooseTrendMaterial(material)
  }

  function chooseTextMaterial(material: TextInputAsset) {
    if (material.type === 'account_profile') {
      setSelectedProfileInputAssetId(material.id)
      setPositioning(material.content)
      setAccountProfileDraftName(material.name)
      setSaveState('workspace', idleState)
      setSaveState('accountProfiles', idleState)
      return
    }
    if (material.type === 'historical_posts') {
      setSelectedHistoricalInputAssetId(material.id)
      setHistoricalPostsDraftName(material.name)
      setHistoricalPosts(material.content)
      setSaveState('historical', idleState)
      return
    }
    if (material.type === 'comments') {
      setSelectedCommentsInputAssetId(material.id)
      setCommentsDraftName(material.name)
      setComments(material.content)
      setSaveState('comments', idleState)
      return
    }
    if (material.type === 'video_creator_samples') {
      setSelectedVideoInputAssetId(material.id)
      setVideoCreatorSamplesDraftName(material.name)
      setVideoCreatorSamples(material.content)
      setSaveState('video', idleState)
      return
    }
    if (material.type === 'xhs_creator_profile') {
      setSelectedXhsCreatorProfileInputAssetId(material.id)
      setXhsCreatorProfileDraftName(material.name)
      setXhsCreatorProfileContent(material.content)
      clearXhsImportTransientState()
      setSaveState('xhs', idleState)
    }
  }

  function chooseTrendMaterial(material: TrendCsvInputAsset) {
    setSelectedTrendInputAssetId(material.id)
    setTrendCsvDraftName(material.name)
    setTrendKeyword(material.keyword)
    setTrendFile(null)
    setSaveState('trend', idleState)
  }

  function startNewInputAsset(panel: InputAssetPanel) {
    setInputAssetDetailOpen(true)
    if (panel === 'account_profiles') {
      setSelectedProfileInputAssetId(NEW_INPUT_ASSET_ID)
      setPositioning('')
      setAccountProfileDraftName(EMPTY_INPUT_ASSET_NAMES.account_profile)
      setSaveState('workspace', idleState)
      setSaveState('accountProfiles', idleState)
      return
    }
    if (panel === 'historical_posts') {
      setSelectedHistoricalInputAssetId(NEW_INPUT_ASSET_ID)
      setHistoricalPostsDraftName(EMPTY_INPUT_ASSET_NAMES.historical_posts)
      setHistoricalPosts('')
      setSaveState('historical', idleState)
      return
    }
    if (panel === 'comments') {
      setSelectedCommentsInputAssetId(NEW_INPUT_ASSET_ID)
      setCommentsDraftName(EMPTY_INPUT_ASSET_NAMES.comments)
      setComments('')
      setSaveState('comments', idleState)
      return
    }
    if (panel === 'trend_csv') {
      setSelectedTrendInputAssetId(NEW_INPUT_ASSET_ID)
      setTrendCsvDraftName(EMPTY_INPUT_ASSET_NAMES.trend_csv)
      setTrendKeyword('')
      setTrendFile(null)
      setSaveState('trend', idleState)
      return
    }
    if (panel === 'xhs_creator_profiles') {
      setSelectedXhsCreatorProfileInputAssetId(NEW_INPUT_ASSET_ID)
      setXhsCreatorProfileDraftName(EMPTY_INPUT_ASSET_NAMES.xhs_creator_profile)
      setXhsCreatorProfileContent('')
      clearXhsImportTransientState()
      setSaveState('xhs', idleState)
      return
    }
    setSelectedVideoInputAssetId(NEW_INPUT_ASSET_ID)
    setVideoCreatorSamplesDraftName(EMPTY_INPUT_ASSET_NAMES.video_creator_samples)
    setVideoCreatorSamples('')
    setSaveState('video', idleState)
  }

  async function applyInputAssetFormatter() {
    const raw = inputAssetFormatterDraft.trim()
    if (!raw) {
      setInputAssetFormatterStatus('请先粘贴需要整理的信息。')
      return
    }
    const skillId = FORMATTER_SKILL_ID_BY_PANEL[inputAssetPanel]
    const formatterSkill = skills.find((skill) => skill.skillId === skillId)
    if (!formatterSkill) {
      setInputAssetFormatterStatus('当前 workspace 还没有同步输入素材整理 skill，请刷新后重试。')
      return
    }
    setInputAssetFormatterStatus('整理中…')
    try {
      const result = await skillApi.invoke(formatterSkill.id, {
        input: {
          rawText: raw,
          targetAssetType: INPUT_ASSET_DEFINITION_BY_PANEL[inputAssetPanel].type,
        },
        mode,
      })
      const output = result.output
      const name = typeof output.name === 'string' ? output.name : ''
      const content = typeof output.content === 'string' ? output.content : ''
      const keyword = typeof output.keyword === 'string' ? output.keyword : ''
      const notes = typeof output.notes === 'string' ? output.notes : '已整理为草稿，请确认后保存。'
      setInputAssetDetailOpen(true)
      if (inputAssetPanel === 'account_profiles') {
        setSelectedProfileInputAssetId(NEW_INPUT_ASSET_ID)
        setAccountProfileDraftName(name || '整理后的账号概况')
        setPositioning(content)
        setSaveState('workspace', idleState)
        setSaveState('accountProfiles', idleState)
        setInputAssetFormatterStatus(notes)
        return
      }
      if (inputAssetPanel === 'historical_posts') {
        setSelectedHistoricalInputAssetId(NEW_INPUT_ASSET_ID)
        setHistoricalPostsDraftName(name || '整理后的历史笔记合集')
        setHistoricalPosts(content)
        setSaveState('historical', idleState)
        setInputAssetFormatterStatus(notes)
        return
      }
      if (inputAssetPanel === 'comments') {
        setSelectedCommentsInputAssetId(NEW_INPUT_ASSET_ID)
        setCommentsDraftName(name || '整理后的评论样本合集')
        setComments(content)
        setSaveState('comments', idleState)
        setInputAssetFormatterStatus(notes)
        return
      }
      if (inputAssetPanel === 'trend_csv') {
        setSelectedTrendInputAssetId(NEW_INPUT_ASSET_ID)
        setTrendCsvDraftName(name || '整理后的趋势数据')
        setTrendKeyword(keyword)
        setSaveState('trend', idleState)
        setInputAssetFormatterStatus(notes)
        return
      }
      if (inputAssetPanel === 'xhs_creator_profiles') {
        setSelectedXhsCreatorProfileInputAssetId(NEW_INPUT_ASSET_ID)
        setXhsCreatorProfileDraftName(name || '整理后的小红书创作者主页')
        setXhsCreatorProfileContent(content)
        setSaveState('xhs', idleState)
        setInputAssetFormatterStatus(notes)
        return
      }
      setSelectedVideoInputAssetId(NEW_INPUT_ASSET_ID)
      setVideoCreatorSamplesDraftName(name || '整理后的视频创作样本')
      setVideoCreatorSamples(content)
      setSaveState('video', idleState)
      setInputAssetFormatterStatus(notes)
    } catch (error) {
      setInputAssetFormatterStatus(`整理失败：${errorMessage(error)}`)
    }
  }

  async function refreshWorkspaceSummary() {
    if (!workspace) return
    const [
      loadedWorkspace,
      loadedRuns,
      loadedSimulationRuns,
      loadedSkills,
      loadedAgents,
      loadedAgentConversations,
      loadedWorkflowAssets,
      loadedDrafts,
      loadedTopics,
    ] =
      await Promise.all([
      workspaceApi.get(workspace.id),
      analysisRunApi.list(workspace.id),
      simulationRunApi.list(workspace.id),
      skillApi.list(workspace.id),
      agentApi.list(workspace.id),
      agentConversationApi.list(workspace.id),
      workflowAssetApi.list(workspace.id),
      draftApi.list(workspace.id),
      topicApi.list(workspace.id),
    ])
    setWorkspace(loadedWorkspace)
    setAnalysisRuns(loadedRuns)
    setSimulationRuns(loadedSimulationRuns)
    setSkills(loadedSkills)
    setAgents(loadedAgents)
    setAgentConversations(loadedAgentConversations)
    setWorkflowAssets(loadedWorkflowAssets)
    setDrafts(loadedDrafts)
    setTopics(loadedTopics)
    setSelectedTopic(
      loadedTopics.find((topic) => topic.id === loadedWorkspace.currentTopicId) ||
        loadedTopics[0] ||
        null,
    )
  }

  function applyDemoSample(force = false, targetTab: WorkflowTab = workflowTab) {
    if (targetTab === 'account') {
      if (force || !positioning.trim()) {
        setSelectedProfileInputAssetId(NEW_INPUT_ASSET_ID)
        setAccountProfileDraftName(SAMPLE_ASSET_NAMES.qsheepProfile)
        setPositioning(SAMPLE_ACCOUNT_INPUT.positioning)
      }
      if (force || !historicalPosts.trim()) {
        setSelectedHistoricalInputAssetId(NEW_INPUT_ASSET_ID)
        setHistoricalPostsDraftName(SAMPLE_ASSET_NAMES.historicalPosts)
        setHistoricalPosts(SAMPLE_ACCOUNT_INPUT.historicalPosts)
      }
      if (force || !comments.trim()) {
        setSelectedCommentsInputAssetId(NEW_INPUT_ASSET_ID)
        setCommentsDraftName(SAMPLE_ASSET_NAMES.comments)
        setComments(SAMPLE_ACCOUNT_INPUT.comments)
      }
      if (force || !simulationTopic.trim()) {
        setSimulationTopic(SAMPLE_ACCOUNT_INPUT.simulationTopic)
      }
      return
    }
    if (targetTab === 'video') {
      if (force || !positioning.trim()) {
        setSelectedProfileInputAssetId(NEW_INPUT_ASSET_ID)
        setAccountProfileDraftName(SAMPLE_ASSET_NAMES.videoProgramProfile)
        setPositioning(SAMPLE_VIDEO_INPUT.positioning)
      }
      if (force || !videoCreatorSamples.trim()) {
        setSelectedVideoInputAssetId(NEW_INPUT_ASSET_ID)
        setVideoCreatorSamplesDraftName(SAMPLE_ASSET_NAMES.videoCreatorSamples)
        setVideoCreatorSamples(SAMPLE_VIDEO_INPUT.videoCreatorSamples)
      }
      if (force || !simulationTopic.trim()) {
        setSimulationTopic(SAMPLE_VIDEO_INPUT.simulationTopic)
      }
      return
    }
    if (force || !positioning.trim()) {
      setSelectedProfileInputAssetId(NEW_INPUT_ASSET_ID)
      setAccountProfileDraftName(SAMPLE_ASSET_NAMES.nomadProfile)
      setPositioning(SAMPLE_TREND_INPUT.positioning)
    }
    if (force || !trendKeyword.trim()) {
      setSelectedTrendInputAssetId(NEW_INPUT_ASSET_ID)
      setTrendCsvDraftName(SAMPLE_ASSET_NAMES.trendCsv)
      setTrendKeyword(SAMPLE_TREND_INPUT.keyword)
    }
    if (force || !simulationTopic.trim()) {
      setSimulationTopic(SAMPLE_TREND_INPUT.simulationTopic)
    }
  }

  async function persistWorkspace(
    nextName = workspaceName,
    nextPositioning = positioning,
  ): Promise<Workspace> {
    if (!workspace) throw new Error('No workspace selected')
    if (
      nextName === workspace.name &&
      nextPositioning === workspace.accountPositioning
    ) {
      return workspace
    }
    const updated = await workspaceApi.update(workspace.id, {
      name: nextName,
      accountPositioning: nextPositioning,
      expectedUpdatedAt: workspace.updatedAt,
    })
    setWorkspace(updated)
    return updated
  }

  async function persistTextMaterial(
    type:
      | 'account_profile'
      | 'historical_posts'
      | 'comments'
      | 'video_creator_samples'
      | 'xhs_creator_profile',
    content: string,
    existing?: TextInputAsset,
    nameOverride?: string,
  ): Promise<TextInputAsset> {
    if (!workspace) throw new Error('No workspace selected')
    const fallbackName =
      type === 'historical_posts'
        ? SAMPLE_ASSET_NAMES.historicalPosts
        : type === 'comments'
          ? SAMPLE_ASSET_NAMES.comments
          : type === 'account_profile'
            ? SAMPLE_ASSET_NAMES.qsheepProfile
            : type === 'video_creator_samples'
              ? SAMPLE_ASSET_NAMES.videoCreatorSamples
              : SAMPLE_ASSET_NAMES.xhsCreatorProfile
    const nextName = (nameOverride || existing?.name || fallbackName).trim()
    if (!nextName) throw new Error('请填写输入资产名称。')
    if (existing && existing.content === content && existing.name === nextName) {
      return existing
    }
    const saved = existing
      ? await inputAssetApi.update(existing.id, {
          name: nextName,
          content,
          expectedUpdatedAt: existing.updatedAt,
        })
      : await inputAssetApi.createText(
          workspace.id,
          type,
          nextName,
          content,
        )
    if (saved.type !== type) {
      throw new Error('Saved input asset type did not match request')
    }
    setMaterials((current) => [
      saved,
      ...current.filter((item) => item.id !== saved.id),
    ])
    if (type === 'account_profile') {
      setSelectedProfileInputAssetId(saved.id)
      setAccountProfileDraftName(saved.name)
    }
    if (type === 'historical_posts') {
      setSelectedHistoricalInputAssetId(saved.id)
      setHistoricalPostsDraftName(saved.name)
    }
    if (type === 'comments') {
      setSelectedCommentsInputAssetId(saved.id)
      setCommentsDraftName(saved.name)
    }
    if (type === 'video_creator_samples') {
      setSelectedVideoInputAssetId(saved.id)
      setVideoCreatorSamplesDraftName(saved.name)
    }
    if (type === 'xhs_creator_profile') {
      setSelectedXhsCreatorProfileInputAssetId(saved.id)
      setXhsCreatorProfileDraftName(saved.name)
      setXhsCreatorProfileContent(saved.content)
    }
    return saved
  }

  async function persistTrendCsv(
    file: File,
    keyword: string,
    name = trendCsvDraftName,
  ): Promise<TrendCsvInputAsset> {
    if (!workspace) throw new Error('No workspace selected')
    const cleanName = name.trim()
    if (!cleanName) throw new Error('请填写趋势数据名称。')
    const uploaded = await inputAssetApi.uploadTrendCsv(
      workspace.id,
      cleanName,
      keyword,
      file,
    )
    setMaterials((current) => [uploaded, ...current])
    setSelectedTrendInputAssetId(uploaded.id)
    setTrendCsvDraftName(uploaded.name)
    setTrendKeyword(uploaded.keyword)
    setTrendFile(null)
    return uploaded
  }

  async function uploadTrendCsv() {
    if (!workspace || !trendFile) {
      setSaveState('trend', { phase: 'error', message: '请选择 CSV 文件。' })
      return
    }
    setSaveState('trend', { phase: 'saving' })
    try {
      await persistTrendCsv(trendFile, trendKeyword, trendCsvDraftName)
      setSaveState('trend', { phase: 'saved' })
    } catch (error) {
      setSaveState('trend', { phase: 'error', message: errorMessage(error) })
    }
  }

  function setXhsImportFile(panel: XhsImportPanel, file: File | null) {
    setXhsImportFiles((current) => ({ ...current, [panel]: file }))
    setXhsImportWarnings([])
    setSaveState(SAVE_KEY_BY_XHS_IMPORT_PANEL[panel], idleState)
  }

  async function uploadXhsImport(panel: XhsImportPanel) {
    const file = xhsImportFiles[panel]
    const saveKey = SAVE_KEY_BY_XHS_IMPORT_PANEL[panel]
    if (!workspace || !file) {
      setSaveState(saveKey, {
        phase: 'error',
        message: '请选择 XHS 导出 JSON / Markdown 文件。',
      })
      return
    }
    setSaveState(saveKey, { phase: 'saving' })
    try {
      const imported = await inputAssetApi.uploadXhsImport(
        workspace.id,
        XHS_IMPORT_TYPE_BY_PANEL[panel],
        file,
      )
      setMaterials((current) => [
        imported.inputAsset,
        ...current.filter((item) => item.id !== imported.inputAsset.id),
      ])
      chooseTextMaterial(imported.inputAsset)
      setXhsImportFiles((current) => ({ ...current, [panel]: null }))
      setXhsImportWarnings(imported.warnings)
      const warningSuffix =
        imported.warnings.length > 0 ? `；${imported.warnings.length} 条提示` : ''
      setSaveState(saveKey, {
        phase: 'saved',
        message: `已导入 ${imported.parsedNoteCount} 条笔记${warningSuffix}`,
      })
    } catch (error) {
      setSaveState(saveKey, {
        phase: 'error',
        message: errorMessage(error),
      })
    }
  }

  async function setXhsImportPackageFiles(files: File[]) {
    setXhsPackageFiles(files)
    setXhsImportWarnings([])
    setXhsPackagePreview(null)
    setXhsPackagePreviewError('')
    setSaveState('xhs', idleState)
    if (files.length === 0) return
    try {
      const preview = await previewXhsImportPackage(files)
      if (!preview) {
        setXhsPackagePreviewError(
          '没有找到可预览的 xhs_creator_profile.json / profile.json。',
        )
        return
      }
      setXhsPackagePreview(preview)
    } catch (error) {
      setXhsPackagePreviewError(errorMessage(error))
    }
  }

  async function uploadXhsImportPackage(saveAsNew = false) {
    if (!workspace) {
      setSaveState('xhs', {
        phase: 'error',
        message: '工作区尚未加载。',
      })
      return
    }
    if (xhsPackageFiles.length === 0) {
      setSaveState('xhs', {
        phase: 'error',
        message: '请选择包含 profile JSON 和 images 目录的文件夹。',
      })
      return
    }

    const profileFile =
      xhsPackageFiles.find((file) =>
        /(^|\/)(xhs_creator_profile|profile)\.json$/i.test(fileRelativePath(file)),
      ) ||
      xhsPackageFiles.find((file) =>
        fileRelativePath(file).toLowerCase().endsWith('.json'),
      )
    if (!profileFile) {
      setSaveState('xhs', {
        phase: 'error',
        message: '文件夹中没有找到 xhs_creator_profile.json 或 profile.json。',
      })
      return
    }

    const packageRelativePaths = xhsPackageRelativePaths(xhsPackageFiles)
    const mediaFiles = xhsPackageFiles.filter((file) => file !== profileFile)
    const relativePaths = mediaFiles.map(
      (file) => packageRelativePaths[xhsPackageFiles.indexOf(file)] || file.name,
    )
    setSaveState('xhs', { phase: 'saving' })
    try {
      const imported = await inputAssetApi.uploadXhsImportPackage(
        workspace.id,
        profileFile,
        mediaFiles,
        relativePaths,
        '',
        saveAsNew,
      )
      setMaterials((current) => [
        imported.inputAsset,
        ...current.filter((item) => item.id !== imported.inputAsset.id),
      ])
      setMediaAssets((current) => [
        ...imported.mediaAssets,
        ...current.filter(
          (item) => !imported.mediaAssets.some((asset) => asset.id === item.id),
        ),
      ])
      chooseTextMaterial(imported.inputAsset)
      setXhsPackageFiles([])
      setXhsPackagePreview(null)
      setXhsPackagePreviewError('')
      setXhsImportWarnings(imported.warnings)
      const warningSuffix =
        imported.warnings.length > 0 ? `；${imported.warnings.length} 条提示` : ''
      setSaveState('xhs', {
        phase: 'saved',
        message: `已导入 ${imported.parsedNoteCount} 条笔记和 ${imported.mediaAssets.length} 张封面${warningSuffix}`,
      })
    } catch (error) {
      setSaveState('xhs', {
        phase: 'error',
        message: errorMessage(error),
      })
    }
  }

  async function ensureInputsSavedForRun(
    targetTab: WorkflowTab = workflowTab,
    includeProfile = true,
    includeSimulationTopic = false,
  ): Promise<{
    accountProfileInputAssetId?: string
    manualAccountProfile?: string
    historical?: TextInputAsset
    comments?: TextInputAsset
    trend?: TrendCsvInputAsset
    video?: TextInputAsset
    xhsCreatorProfile?: TextInputAsset
    simulationTopic: string
  }> {
    if (!workspace) throw new Error('No workspace selected')
    const sample =
      targetTab === 'account'
        ? SAMPLE_ACCOUNT_INPUT
        : targetTab === 'video'
          ? SAMPLE_VIDEO_INPUT
          : SAMPLE_TREND_INPUT
    const nextSimulationTopic =
      includeSimulationTopic && mode === 'demo' && !simulationTopic.trim()
        ? sample.simulationTopic
        : simulationTopic
    if (nextSimulationTopic !== simulationTopic) {
      setSimulationTopic(nextSimulationTopic)
    }

    const profileInput: {
      accountProfileInputAssetId?: string
      manualAccountProfile?: string
    } = {}
    const accountUsesXhsCreatorProfile =
      targetTab === 'account' && Boolean(xhsCreatorProfileMaterial)
    if (!includeProfile || accountUsesXhsCreatorProfile) {
      // XHS creator profile runs derive a compact profile snapshot in the backend.
    } else {
      let material = selectedProfileMaterial
      if (!material && mode === 'demo') {
        setSaveState('accountProfiles', { phase: 'saving' })
        const sampleName =
          targetTab === 'trend'
            ? SAMPLE_ASSET_NAMES.nomadProfile
            : targetTab === 'video'
              ? SAMPLE_ASSET_NAMES.videoProgramProfile
            : SAMPLE_ASSET_NAMES.qsheepProfile
        material = await persistTextMaterial(
          'account_profile',
          sample.positioning,
          undefined,
          sampleName,
        )
        setPositioning(sample.positioning)
        setSaveState('accountProfiles', { phase: 'saved' })
      }
      if (!material) throw new Error('请先在账号概况中选择或保存一个账号概况。')
      profileInput.accountProfileInputAssetId = material.id
    }

    if (targetTab === 'account') {
      if (xhsCreatorProfileMaterial) {
        return {
          ...profileInput,
          xhsCreatorProfile: xhsCreatorProfileMaterial,
          simulationTopic: nextSimulationTopic,
        }
      }
      const nextHistoricalPosts =
        mode === 'demo' && !historicalPosts.trim()
          ? SAMPLE_ACCOUNT_INPUT.historicalPosts
          : historicalPosts
      const nextComments =
        mode === 'demo' && !comments.trim() ? SAMPLE_ACCOUNT_INPUT.comments : comments
      if (nextHistoricalPosts !== historicalPosts) setHistoricalPosts(nextHistoricalPosts)
      if (nextComments !== comments) setComments(nextComments)
      if (!nextHistoricalPosts.trim() || !nextComments.trim()) {
        throw new Error('请填写历史笔记和评论样本。')
      }

      setSaveState('historical', { phase: 'saving' })
      const savedHistorical = await persistTextMaterial(
        'historical_posts',
        nextHistoricalPosts,
        historicalMaterial,
        historicalPostsDraftName || SAMPLE_ASSET_NAMES.historicalPosts,
      )
      setSaveState('historical', { phase: 'saved' })

      setSaveState('comments', { phase: 'saving' })
      const savedComments = await persistTextMaterial(
        'comments',
        nextComments,
        commentsMaterial,
        commentsDraftName || SAMPLE_ASSET_NAMES.comments,
      )
      setSaveState('comments', { phase: 'saved' })
      return {
        ...profileInput,
        historical: savedHistorical,
        comments: savedComments,
        simulationTopic: nextSimulationTopic,
      }
    }

    if (targetTab === 'video') {
      if (xhsCreatorProfileMaterial) {
        return {
          ...profileInput,
          xhsCreatorProfile: xhsCreatorProfileMaterial,
          simulationTopic: nextSimulationTopic,
        }
      }
      const nextVideoCreatorSamples =
        mode === 'demo' && !videoCreatorSamples.trim()
          ? SAMPLE_VIDEO_INPUT.videoCreatorSamples
          : videoCreatorSamples
      if (nextVideoCreatorSamples !== videoCreatorSamples) {
        setVideoCreatorSamples(nextVideoCreatorSamples)
      }
      if (!nextVideoCreatorSamples.trim()) {
        throw new Error('请填写视频创作样本。')
      }

      setSaveState('video', { phase: 'saving' })
      const savedVideo = await persistTextMaterial(
        'video_creator_samples',
        nextVideoCreatorSamples,
        videoCreatorSamplesMaterial,
        videoCreatorSamplesDraftName || SAMPLE_ASSET_NAMES.videoCreatorSamples,
      )
      setSaveState('video', { phase: 'saved' })
      return {
        ...profileInput,
        video: savedVideo,
        simulationTopic: nextSimulationTopic,
      }
    }

    let savedTrend = trendMaterial
    if (trendFile) {
      setSaveState('trend', { phase: 'saving' })
      savedTrend = await persistTrendCsv(trendFile, trendKeyword, trendCsvDraftName)
      setSaveState('trend', { phase: 'saved' })
    } else if (mode === 'demo' && !savedTrend) {
      setSaveState('trend', { phase: 'saving' })
      const sampleFile = new File([SAMPLE_TREND_CSV], SAMPLE_ASSET_NAMES.trendCsv, {
        type: 'text/csv',
      })
      savedTrend = await persistTrendCsv(
        sampleFile,
        trendKeyword || SAMPLE_TREND_INPUT.keyword,
        trendCsvDraftName || SAMPLE_ASSET_NAMES.trendCsv,
      )
      setSaveState('trend', { phase: 'saved' })
    }
    if (!savedTrend) throw new Error('请上传热点 CSV。')
    const nextTrendName = (trendCsvDraftName || savedTrend.name).trim()
    if (
      (trendKeyword.trim() && trendKeyword !== savedTrend.keyword) ||
      nextTrendName !== savedTrend.name
    ) {
      setSaveState('trend', { phase: 'saving' })
      const updated = await inputAssetApi.update(savedTrend.id, {
        name: nextTrendName,
        keyword: trendKeyword || savedTrend.keyword,
        expectedUpdatedAt: savedTrend.updatedAt,
      })
      if (updated.type !== 'trend_csv') {
        throw new Error('Updated input asset type did not match request')
      }
      savedTrend = updated
      setTrendCsvDraftName(updated.name)
      setMaterials((current) => [
        updated,
        ...current.filter((item) => item.id !== updated.id),
      ])
      setSaveState('trend', { phase: 'saved' })
    }
    return { ...profileInput, trend: savedTrend, simulationTopic: nextSimulationTopic }
  }

  function setAnalysisStageViews(
    targetTab: WorkflowTab,
    next: StageView[] | ((current: StageView[]) => StageView[]),
  ) {
    setAnalysisStageViewsByWorkflow((current) => ({
      ...current,
      [targetTab]: typeof next === 'function' ? next(current[targetTab]) : next,
    }))
  }

  function setAnalysisStageStatus(
    targetTab: WorkflowTab,
    key: string,
    patch: Partial<StageView>,
  ) {
    setAnalysisStageViews(targetTab, (current) =>
      current.map((stage) => (stage.key === key ? { ...stage, ...patch } : stage)),
    )
  }

  function setSimulationStageStatus(key: string, patch: Partial<StageView>) {
    setSimulationStageViews((current) =>
      current.map((stage) => (stage.key === key ? { ...stage, ...patch } : stage)),
    )
  }

  function setWorkflowOutputKind(targetTab: WorkflowTab, kind: WorkflowOutputKind) {
    setWorkflowOutputKindByWorkflow((current) => ({
      ...current,
      [targetTab]: kind,
    }))
  }

  async function runDiagnosis(targetTab: WorkflowTab = workflowTab) {
    if (!workspace) return
    setWorkflowTab(targetTab)
    setRunError('')
    setRunning(true)
    setWorkflowOutputKind(targetTab, 'analysis')
    setAnalysisStageViews(targetTab, stageSeed(targetTab))
    try {
      const savedInputs = await ensureInputsSavedForRun(targetTab)
      const created = await analysisRunApi.create(workspace.id, {
        workflowType: workflowFromTab(targetTab),
        idempotencyKey: newClientRequestKey(`analysis-${targetTab}`),
        accountProfileInputAssetId: savedInputs.accountProfileInputAssetId,
        manualAccountProfile: savedInputs.manualAccountProfile,
        historicalPostsInputAssetId: savedInputs.historical?.id,
        commentsInputAssetId: savedInputs.comments?.id,
        trendCsvInputAssetId: savedInputs.trend?.id,
        videoCreatorSamplesInputAssetId: savedInputs.video?.id,
        xhsCreatorProfileInputAssetId: savedInputs.xhsCreatorProfile?.id,
        analysisScope: !internalMode && targetTab === 'account' ? analysisScope : undefined,
        mediaAssetIds:
          targetTab === 'video' ? selectedVideoWorkflowMediaAssetIds : undefined,
        mode,
      })
      setCurrentRun(created)
      await runAnalysisGraphWorkflow(created, targetTab)
      await refreshWorkspaceSummary()
    } catch (error) {
      const message = errorMessage(error)
      setRunError(message)
      setSaveStates((current) =>
        Object.fromEntries(
          Object.entries(current).map(([key, state]) => [
            key,
            state.phase === 'saving' ? { phase: 'error', message } : state,
          ]),
        ) as Record<SaveKey, SaveState>,
      )
    } finally {
      setRunning(false)
    }
  }

  function downloadAnalysisRunsCsv(targetTab?: WorkflowTab) {
    if (!workspace) return
    const url = analysisRunApi.exportCsvUrl(
      workspace.id,
      targetTab ? workflowFromTab(targetTab) : undefined,
    )
    const link = document.createElement('a')
    link.href = url
    link.download = `${targetTab ? workflowFromTab(targetTab) : 'analysis-runs'}.csv`
    document.body.appendChild(link)
    link.click()
    link.remove()
  }

  async function runAnalysisGraphWorkflow(run: AnalysisRun, targetTab: WorkflowTab) {
    await new Promise<void>((resolve, reject) => {
      const source = new EventSource(`/api/analysis-runs/${run.id}/events`)
      const finish = async () => {
        source.close()
        const completed = await analysisRunApi.get(run.id)
        setCurrentRun(completed)
        setAnalysisStageViews(targetTab, stageSeedFromRun(completed))
        resolve()
      }
      const pollFallback = async () => {
        source.close()
        for (let attempt = 0; attempt < 40; attempt += 1) {
          const latest = await analysisRunApi.get(run.id)
          setCurrentRun(latest)
          setAnalysisStageViews(targetTab, stageSeedFromRun(latest))
          if (
            latest.status === 'completed' ||
            latest.status === 'partially_completed' ||
            latest.status === 'failed'
          ) {
            resolve()
            return
          }
          await new Promise((pollResolve) => window.setTimeout(pollResolve, 500))
        }
        throw new Error('事件流已断开，轮询运行状态超时。')
      }
      const fail = (error: unknown) => {
        source.close()
        reject(error)
      }
      const handleMessage = (message: MessageEvent<string>) => {
        const activity = JSON.parse(message.data) as ActivityEvent
        const eventType = activity.data.eventType
        if (eventType === 'stage.started' && activity.stageKey) {
          setAnalysisStageStatus(targetTab, activity.stageKey, { status: 'running' })
          return
        }
        if (eventType === 'stage.succeeded' && activity.stageKey) {
          const result = { ...activity.data }
          delete result.eventType
          setAnalysisStageStatus(targetTab, activity.stageKey, {
            status: 'completed',
            result,
            error: undefined,
          })
          return
        }
        if (eventType === 'stage.failed' && activity.stageKey) {
          setAnalysisStageStatus(targetTab, activity.stageKey, {
            status: 'failed',
            error: String(activity.data.error || '阶段执行失败'),
          })
          return
        }
        if (
          eventType === 'run.succeeded' ||
          eventType === 'run.partial' ||
          eventType === 'run.failed'
        ) {
          void finish().catch(fail)
        }
      }
      const eventTypes = [
        'run.created',
        'run.started',
        'stage.started',
        'stage.succeeded',
        'stage.failed',
        'run.partial',
        'run.succeeded',
        'run.failed',
      ]
      eventTypes.forEach((eventType) => {
        source.addEventListener(eventType, handleMessage as EventListener)
      })
      source.onerror = () => {
        void pollFallback().catch(fail)
      }
    })
  }

  async function runAudienceSimulation(draft?: Draft, targetTab: WorkflowTab = workflowTab, topic?: Topic) {
    if (!workspace) return
    if (!internalMode && audience.selected?.status !== 'completed') { setActivePage('audience-analysis'); return }
    setWorkflowTab(targetTab)
    setRunError('')
    setRunning(true)
    setCurrentRun(null)
    setWorkflowOutputKind(targetTab, 'simulation')
    setSimulationStageViews(simulationStageSeed())
    if (!internalMode) setActivePage('simulations')
    try {
      const savedInputs = draft || topic
        ? { simulationTopic }
        : await ensureInputsSavedForRun(targetTab, true, true)
      if (draft) {
        setSaveState('workspace', { phase: 'saving' })
        await persistWorkspace()
        setSaveState('workspace', { phase: 'saved' })
      }
      const topicForSimulation = savedInputs.simulationTopic.trim()
      if (!draft && !topic && !topicForSimulation) throw new Error('请填写受众模拟选题。')
      const useSavedTopic =
        !draft && selectedTopic && topicForSimulation.includes(selectedTopic.title)
      const created = await simulationRunApi.create(workspace.id, {
        audienceAnalysisId: internalMode ? undefined : audience.selected?.id,
        draftId: draft?.id,
        topicId: topic?.id || (useSavedTopic ? selectedTopic.id : null),
        manualTopic: draft || topic || useSavedTopic ? undefined : topicForSimulation,
        mode,
      })
      await runSimulationGraphWorkflow(created, targetTab)
      await refreshWorkspaceSummary()
    } catch (error) {
      const message = errorMessage(error)
      setRunError(message)
      setSaveStates((current) =>
        Object.fromEntries(
          Object.entries(current).map(([key, state]) => [
            key,
            state.phase === 'saving' ? { phase: 'error', message } : state,
          ]),
        ) as Record<SaveKey, SaveState>,
      )
    } finally {
      setRunning(false)
    }
  }

  async function runSimulationGraphWorkflow(run: SimulationRun, targetTab: WorkflowTab) {
    await new Promise<void>((resolve, reject) => {
      const source = new EventSource(`/api/simulation-runs/${run.id}/events`)
      const finish = async () => {
        source.close()
        const completed = await simulationRunApi.get(run.id)
        setSelectedSimulationRun(completed)
        setWorkflowOutputKind(targetTab, 'simulation')
        setSimulationStageViews(stageSeedFromSimulation(completed))
        resolve()
      }
      const pollFallback = async () => {
        source.close()
        for (let attempt = 0; attempt < 40; attempt += 1) {
          const latest = await simulationRunApi.get(run.id)
          setSelectedSimulationRun(latest)
          setWorkflowOutputKind(targetTab, 'simulation')
          setSimulationStageViews(stageSeedFromSimulation(latest))
          if (
            latest.status === 'completed' ||
            latest.status === 'partially_completed' ||
            latest.status === 'failed'
          ) {
            resolve()
            return
          }
          await new Promise((pollResolve) => window.setTimeout(pollResolve, 500))
        }
        throw new Error('受众模拟事件流已断开，轮询运行状态超时。')
      }
      const fail = (error: unknown) => {
        source.close()
        reject(error)
      }
      const handleMessage = (message: MessageEvent<string>) => {
        const activity = JSON.parse(message.data) as ActivityEvent
        const eventType = activity.data.eventType
        if (eventType === 'stage.started' && activity.stageKey) {
          setSimulationStageStatus(activity.stageKey, { status: 'running' })
          return
        }
        if (eventType === 'stage.succeeded' && activity.stageKey) {
          const result = { ...activity.data }
          delete result.eventType
          setSimulationStageStatus(activity.stageKey, {
            status: 'completed',
            result,
            error: undefined,
          })
          return
        }
        if (eventType === 'stage.failed' && activity.stageKey) {
          setSimulationStageStatus(activity.stageKey, {
            status: 'failed',
            error: String(activity.data.error || '阶段执行失败'),
          })
          return
        }
        if (
          eventType === 'run.succeeded' ||
          eventType === 'run.partial' ||
          eventType === 'run.failed'
        ) {
          void finish().catch(fail)
        }
      }
      const eventTypes = [
        'run.created',
        'run.started',
        'stage.started',
        'stage.succeeded',
        'stage.failed',
        'run.partial',
        'run.succeeded',
        'run.failed',
      ]
      eventTypes.forEach((eventType) => {
        source.addEventListener(eventType, handleMessage as EventListener)
      })
      source.onerror = () => {
        void pollFallback().catch(fail)
      }
    })
  }

  async function saveGeneratedTopic(candidate: TopicCandidate, run: AnalysisRun | null) {
    if (!workspace) throw new Error('No workspace selected')
    const created = await topicApi.create(workspace.id, {
      title: candidate.title,
      angle: candidate.angle,
      associatedPainPoint: candidate.pain || '',
      whyItFits: [candidate.whyFit, candidate.whyTrending].filter(Boolean).join('\n'),
      sourceAnalysisRunId: run?.id || null,
      sourceWorkflow: run ? undefined : 'manual',
    })
    await refreshWorkspaceSummary()
    return created
  }

  async function saveManualTopic(event: FormEvent) {
    event.preventDefault()
    if (!workspace || !manualTopicTitle.trim()) return false
    setSaveState('manualTopic', { phase: 'saving' })
    try {
      const created = await topicApi.create(workspace.id, {
        title: manualTopicTitle.trim(),
        angle: manualTopicAngle,
        sourceWorkflow: 'manual',
      })
      setManualTopicTitle('')
      setManualTopicAngle('')
      setSelectedTopic(created)
      await refreshWorkspaceSummary()
      setSaveState('manualTopic', { phase: 'saved' })
      return true
    } catch (error) {
      setSaveState('manualTopic', { phase: 'error', message: errorMessage(error) })
      return false
    }
  }

  async function selectTopic(topic: Topic) {
    const selected = await topicApi.select(topic.id)
    setSelectedTopic(selected)
    setSimulationTopic(`${selected.title}\n切入角度：${selected.angle}`)
    await refreshWorkspaceSummary()
    return selected
  }

  async function archiveTopic(topic: Topic) {
    const archived = await topicApi.archive(topic.id)
    setTopics((current) =>
      current.map((item) => (item.id === archived.id ? archived : item)),
    )
    if (selectedTopic?.id === topic.id) setSelectedTopic(archived)
    await refreshWorkspaceSummary()
  }

  async function updateSelectedTopic() {
    if (!selectedTopic) return
    setSaveState('topic', { phase: 'saving' })
    try {
      const updated = await topicApi.update(selectedTopic.id, {
        title: topicDraft.title,
        angle: topicDraft.angle,
        body: topicDraft.body,
        expectedUpdatedAt: selectedTopic.updatedAt,
      })
      setSelectedTopic(updated)
      await refreshWorkspaceSummary()
      setSaveState('topic', { phase: 'saved' })
    } catch (error) {
      setSaveState('topic', { phase: 'error', message: errorMessage(error) })
    }
  }

  async function generateDraftForTopic(topic: Topic) {
    setRunError('')
    setSaveState('draft', { phase: 'saving' })
    if (!internalMode) { setSelectedDraft(null); setActivePage('drafts') }
    try {
      const draft = await draftApi.generateFromTopic(topic.id, mode)
      setSelectedDraft(draft)
      setDraftEditor(JSON.stringify(draft.editableContent, null, 2))
      await refreshWorkspaceSummary()
      setActivePage('drafts')
      setSaveState('draft', { phase: 'saved' })
      return draft
    } catch (error) {
      const message = errorMessage(error)
      setRunError(message)
      setSaveState('draft', { phase: 'error', message })
      throw error
    }
  }

  async function generateBriefForTopic(topic: Topic) {
    setRunError('')
    setSaveState('draft', { phase: 'saving' })
    if (!internalMode) { setSelectedDraft(null); setActivePage('drafts') }
    try {
      const draft = await draftApi.generateBriefFromTopic(topic.id, mode)
      setSelectedDraft(draft)
      setDraftEditor(JSON.stringify(draft.editableContent, null, 2))
      await refreshWorkspaceSummary()
      setActivePage('drafts')
      setSaveState('draft', { phase: 'saved' })
      return draft
    } catch (error) {
      const message = errorMessage(error)
      setRunError(message)
      setSaveState('draft', { phase: 'error', message })
      throw error
    }
  }

  async function generateStructureFromBrief(draft: Draft) {
    setRunError('')
    setSaveState('draft', { phase: 'saving' })
    try {
      const structureDraft = await draftApi.generateStructureFromBrief(draft.id, mode)
      setSelectedDraft(structureDraft)
      setDraftEditor(JSON.stringify(structureDraft.editableContent, null, 2))
      await refreshWorkspaceSummary()
      setActivePage('drafts')
      setSaveState('draft', { phase: 'saved' })
      return structureDraft
    } catch (error) {
      const message = errorMessage(error)
      setRunError(message)
      setSaveState('draft', { phase: 'error', message })
      throw error
    }
  }

  async function openDraft(draftId: string) {
    const draft = await draftApi.get(draftId)
    setSelectedDraft(draft)
    setDraftEditor(JSON.stringify(draft.editableContent, null, 2))
    setSaveState('draft', idleState)
  }

  async function saveDraftEdits() {
    if (!selectedDraft) return
    setSaveState('draft', { phase: 'saving' })
    try {
      const editableContent = JSON.parse(draftEditor) as Record<string, unknown>
      const updated = await draftApi.update(selectedDraft.id, {
        editableContent,
        expectedUpdatedAt: selectedDraft.updatedAt,
      })
      setSelectedDraft(updated)
      setDraftEditor(JSON.stringify(updated.editableContent, null, 2))
      await refreshWorkspaceSummary()
      setSaveState('draft', { phase: 'saved' })
    } catch (error) {
      setSaveState('draft', { phase: 'error', message: errorMessage(error) })
    }
  }

  async function openRun(runId: string, inOutput = false) {
    const run = await analysisRunApi.get(runId)
    setSelectedRun(run)
    setAnalysisReviewDraft({
      userNotes: run.userNotes,
      reviewStatus: run.reviewStatus,
    })
    setSaveState('analysisReview', idleState)
    if (inOutput) {
      const targetTab = workflowTabFromSource(run.workflowType)
      setCurrentRun(run)
      setAnalysisStageViews(targetTab, stageSeedFromRun(run))
      setWorkflowOutputKind(targetTab, 'analysis')
      setWorkflowTab(targetTab)
      setActivePage(activePageForWorkflowTab(targetTab))
    }
  }

  async function openSimulationRun(simulationId: string, inOutput = false) {
    const run = await simulationRunApi.get(simulationId)
    setSelectedSimulationRun(run)
    setSimulationRuns((current) => current.map((item) => item.id === run.id ? run : item))
    setSimulationReviewDraft({
      userNotes: run.userNotes,
      reviewStatus: run.reviewStatus,
    })
    setSaveState('simulationReview', idleState)
    if (inOutput) {
      const targetTab = workflowTabFromSimulation(run)
      setCurrentRun(null)
      setSimulationStageViews(stageSeedFromSimulation(run))
      setWorkflowOutputKind(targetTab, 'simulation')
      setWorkflowTab(targetTab)
      const topic = run.inputSnapshot.topic as { title?: string; angle?: string }
      setSimulationTopic(
        [topic?.title || '', topic?.angle ? `切入角度：${topic.angle}` : '']
          .filter(Boolean)
          .join('\n'),
      )
      setActivePage(activePageForWorkflowTab(targetTab))
    }
  }

  async function saveAnalysisRunReview() {
    if (!selectedRun) return
    setSaveState('analysisReview', { phase: 'saving' })
    try {
      const updated = await analysisRunApi.updateReview(selectedRun.id, {
        userNotes: analysisReviewDraft.userNotes,
        reviewStatus: analysisReviewDraft.reviewStatus,
        expectedUpdatedAt: selectedRun.updatedAt,
      })
      setSelectedRun(updated)
      setAnalysisReviewDraft({
        userNotes: updated.userNotes,
        reviewStatus: updated.reviewStatus,
      })
      setAnalysisRuns((current) =>
        current.map((run) => (run.id === updated.id ? updated : run)),
      )
      if (currentRun?.id === updated.id) setCurrentRun(updated)
      setSaveState('analysisReview', { phase: 'saved' })
    } catch (error) {
      setSaveState('analysisReview', {
        phase: 'error',
        message: errorMessage(error),
      })
    }
  }

  async function saveSimulationRunReview() {
    if (!selectedSimulationRun) return
    setSaveState('simulationReview', { phase: 'saving' })
    try {
      const updated = await simulationRunApi.updateReview(selectedSimulationRun.id, {
        userNotes: simulationReviewDraft.userNotes,
        reviewStatus: simulationReviewDraft.reviewStatus,
        expectedUpdatedAt: selectedSimulationRun.updatedAt,
      })
      setSelectedSimulationRun(updated)
      setSimulationReviewDraft({
        userNotes: updated.userNotes,
        reviewStatus: updated.reviewStatus,
      })
      setSimulationRuns((current) =>
        current.map((run) => (run.id === updated.id ? updated : run)),
      )
      setSaveState('simulationReview', { phase: 'saved' })
    } catch (error) {
      setSaveState('simulationReview', {
        phase: 'error',
        message: errorMessage(error),
      })
    }
  }

  async function openSkill(skillAssetId: string) {
    const skill = await skillApi.get(skillAssetId)
    setSelectedSkill(skill)
    setSkillDefinitionDraft(null)
    setSkillDefinitionStatus('')
    resetDefinitionDiff()
    setSkillTestInput(defaultSkillTestInput(skill))
    setSkillTestStatus('idle')
    setSkillTestResult(null)
    setSkillTestError('')
  }

  function startSkillDefinitionEdit(skill: Skill) {
    setSkillDefinitionDraft(skillToDefinitionDraft(skill))
    setSkillDefinitionStatus('')
  }

  async function saveSkillDefinition() {
    if (!selectedSkill || !skillDefinitionDraft) return
    setSkillDefinitionSaving(true)
    setSkillDefinitionStatus('saving')
    try {
      const contextPolicy = JSON.parse(skillDefinitionDraft.contextPolicyJson) as Record<
        string,
        unknown
      >
      const outputSchema = JSON.parse(skillDefinitionDraft.outputSchemaJson) as Record<
        string,
        unknown
      >
      const payload: SkillDefinitionUpdate = {
        displayName: skillDefinitionDraft.displayName,
        category: skillDefinitionDraft.category,
        purpose: skillDefinitionDraft.purpose,
        artifactEffect: skillDefinitionDraft.artifactEffect,
        failureMode: skillDefinitionDraft.failureMode,
        version: skillDefinitionDraft.version,
        userNotes: skillDefinitionDraft.userNotes,
        triggerIntents: listFromText(skillDefinitionDraft.triggerIntents),
        requiredInputs: listFromText(skillDefinitionDraft.requiredInputs),
        optionalInputs: listFromText(skillDefinitionDraft.optionalInputs),
        sideEffects: listFromText(skillDefinitionDraft.sideEffects),
        composableWith: listFromText(skillDefinitionDraft.composableWith),
        implementationRefs: listFromText(skillDefinitionDraft.implementationRefs),
        contextPolicy,
        outputSchema,
        expectedUpdatedAt: selectedSkill.updatedAt,
      }
      const updated = await skillApi.updateDefinition(selectedSkill.id, payload)
      setSelectedSkill(updated)
      setSkills((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      )
      setSkillDefinitionDraft(skillToDefinitionDraft(updated))
      setSkillDefinitionStatus('saved')
      resetDefinitionDiff()
      await refreshWorkspaceSummary()
    } catch (error) {
      setSkillDefinitionStatus(`error:${errorMessage(error)}`)
    } finally {
      setSkillDefinitionSaving(false)
    }
  }

  async function runSkillTest() {
    if (!selectedSkill) return
    setSkillTestStatus('running')
    setSkillTestError('')
    setSkillTestResult(null)
    try {
      const input = JSON.parse(skillTestInput) as Record<string, unknown>
      const runner = isDirectlyInvokableSkill(selectedSkill.skillId)
        ? skillApi.invoke
        : skillApi.dryRun
      const result = await runner(selectedSkill.id, {
        input,
        mode: skillTestMode,
      })
      setSkillTestResult(result)
      setSkillTestStatus('completed')
    } catch (error) {
      setSkillTestError(errorMessage(error))
      setSkillTestStatus('error')
    }
  }

  async function openAgent(agentAssetId: string) {
    const agent = await agentApi.get(agentAssetId)
    setSelectedAgent(agent)
    setAgentDefinitionDraft(null)
    setAgentDefinitionStatus('')
    resetDefinitionDiff()
    setSelectedAgentConversation((current) =>
      current?.agentAssetId === agent.id ? current : null,
    )
    setAgentMessageDraft('')
    setAgentMessageClientKey(newClientRequestKey('agent-message'))
  }

  function startAgentDefinitionEdit(agent: Agent) {
    setAgentDefinitionDraft(agentToDefinitionDraft(agent))
    setAgentDefinitionStatus('')
  }

  async function saveAgentDefinition() {
    if (!selectedAgent || !agentDefinitionDraft) return
    setAgentDefinitionSaving(true)
    setAgentDefinitionStatus('saving')
    try {
      const validation = validateAgentDefinitionDraft(agentDefinitionDraft, skills)
      if (validation.errors.length > 0 || !validation.ok) {
        throw new Error(validation.errors.join('\n'))
      }
      const payload: AgentDefinitionUpdate = {
        displayName: agentDefinitionDraft.displayName,
        purpose: agentDefinitionDraft.purpose,
        systemPrompt: agentDefinitionDraft.systemPrompt,
        skillIds: listFromText(agentDefinitionDraft.skillIds),
        defaultContextPolicy: validation.value,
        version: agentDefinitionDraft.version,
        userNotes: agentDefinitionDraft.userNotes,
        expectedUpdatedAt: selectedAgent.updatedAt,
      }
      const updated = await agentApi.updateDefinition(selectedAgent.id, payload)
      setSelectedAgent(updated)
      setAgents((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      )
      setAgentDefinitionDraft(agentToDefinitionDraft(updated))
      setAgentDefinitionStatus('saved')
      resetDefinitionDiff()
      await refreshWorkspaceSummary()
    } catch (error) {
      setAgentDefinitionStatus(`error:${errorMessage(error)}`)
    } finally {
      setAgentDefinitionSaving(false)
    }
  }

  async function startAgentConversation(
    agent: Agent,
    title = `与 ${agent.displayName} 对话`,
    initialDraft = '',
    contextTarget?: ConversationContextTarget,
  ) {
    if (!workspace) return
    setRunError('')
    setActivePage('agents')
    setAgentConversationCreating(true)
    try {
      const conversation = await agentConversationApi.create(
        workspace.id,
        agent.id,
        title,
        contextTarget,
      )
      setAgentConversations((current) => [
        conversation,
        ...current.filter((item) => item.id !== conversation.id),
      ])
      setSelectedAgentConversation(conversation)
      setAssetProposals([])
      setConversationTitleDraft(conversation.title)
      setConversationSaveStatus('')
      setAgentMessageDraft(initialDraft)
      setAgentMessageClientKey(newClientRequestKey('agent-message'))
      await refreshWorkspaceSummary()
    } catch (error) {
      setRunError(errorMessage(error))
    } finally {
      setAgentConversationCreating(false)
    }
  }

  async function startMakerConversation(
    agentId: string,
    initialDraft: string,
    contextTarget?: ConversationContextTarget,
  ) {
    setRunError('')
    setActivePage('agents')
    const summary = agents.find((agent) => agent.agentId === agentId)
    if (!summary) {
      setRunError('这个 workspace 还没有同步对应的 maker agent，请刷新后重试。')
      return
    }
    try {
      const agent =
        selectedAgent?.id === summary.id ? selectedAgent : await agentApi.get(summary.id)
      setSelectedAgent(agent)
      await startAgentConversation(
        agent,
        `与 ${agent.displayName} 对话`,
        initialDraft,
        contextTarget,
      )
    } catch (error) {
      setRunError(errorMessage(error))
    }
  }

  async function openAgentConversation(conversationId: string) {
    setRunError('')
    const [conversation, proposals] = await Promise.all([
      agentConversationApi.get(conversationId),
      assetProposalApi.listForConversation(conversationId),
    ])
    setSelectedAgentConversation(conversation)
    setAssetProposals(proposals)
    setConversationTitleDraft(conversation.title)
    setConversationSaveStatus('')
    setAgentMessageDraft('')
    setAgentMessageClientKey(newClientRequestKey('agent-message'))
    const agent = agents.find((item) => item.id === conversation.agentAssetId)
    if (agent) {
      await openAgent(agent.id)
    }
  }

  async function sendAgentMessage(event: FormEvent) {
    event.preventDefault()
    if (!selectedAgentConversation || !agentMessageDraft.trim()) return
    setAgentSending(true)
    setRunError('')
    try {
      const conversation = await agentConversationApi.sendMessage(
        selectedAgentConversation.id,
        agentMessageDraft.trim(),
        mode,
        agentMessageClientKey,
      )
      setSelectedAgentConversation(conversation)
      setConversationTitleDraft(conversation.title)
      setAssetProposals(
        await assetProposalApi.listForConversation(selectedAgentConversation.id),
      )
      setAgentMessageDraft('')
      setAgentMessageClientKey(newClientRequestKey('agent-message'))
      await refreshWorkspaceSummary()
    } catch (error) {
      setRunError(errorMessage(error))
    } finally {
      setAgentSending(false)
    }
  }

  async function updateAgentConversationAsset(
    patch: { title?: string; status?: AgentConversationStatus },
  ) {
    if (!selectedAgentConversation) return
    setConversationSaving(true)
    setConversationSaveStatus('saving')
    setRunError('')
    try {
      const updated = await agentConversationApi.update(selectedAgentConversation.id, {
        ...patch,
        expectedUpdatedAt: selectedAgentConversation.updatedAt,
      })
      setSelectedAgentConversation(updated)
      setConversationTitleDraft(updated.title)
      setAgentConversations((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      )
      setConversationSaveStatus('saved')
      await refreshWorkspaceSummary()
    } catch (error) {
      const message = errorMessage(error)
      setConversationSaveStatus(`error:${message}`)
      setRunError(message)
    } finally {
      setConversationSaving(false)
    }
  }

  async function openWorkflowAsset(workflowAssetId: string) {
    const workflowAsset = await workflowAssetApi.get(workflowAssetId)
    setSelectedWorkflowAsset(workflowAsset)
    setWorkflowDefinitionDraft(null)
    setWorkflowDefinitionStatus('')
    resetDefinitionDiff()
  }

  function startWorkflowDefinitionEdit(workflowAsset: WorkflowAsset) {
    setWorkflowDefinitionDraft(workflowToDefinitionDraft(workflowAsset))
    setWorkflowDefinitionStatus('')
  }

  async function saveWorkflowDefinition() {
    if (!selectedWorkflowAsset || !workflowDefinitionDraft) return
    setWorkflowDefinitionSaving(true)
    setWorkflowDefinitionStatus('saving')
    try {
      const validation = validateWorkflowDefinitionDraft(
        workflowDefinitionDraft,
        agents,
        skills,
      )
      if (validation.errors.length > 0 || !validation.ok) {
        throw new Error(validation.errors.join('\n'))
      }
      const payload: WorkflowAssetDefinitionUpdate = {
        displayName: workflowDefinitionDraft.displayName,
        purpose: workflowDefinitionDraft.purpose,
        entryAgentIds: listFromText(workflowDefinitionDraft.entryAgentIds),
        agentPlan: validation.value,
        artifactEffect: workflowDefinitionDraft.artifactEffect,
        callBinding: workflowDefinitionDraft.callBinding,
        version: workflowDefinitionDraft.version,
        userNotes: workflowDefinitionDraft.userNotes,
        expectedUpdatedAt: selectedWorkflowAsset.updatedAt,
      }
      const updated = await workflowAssetApi.updateDefinition(
        selectedWorkflowAsset.id,
        payload,
      )
      setSelectedWorkflowAsset(updated)
      setWorkflowAssets((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      )
      setWorkflowDefinitionDraft(workflowToDefinitionDraft(updated))
      setWorkflowDefinitionStatus('saved')
      resetDefinitionDiff()
      await refreshWorkspaceSummary()
    } catch (error) {
      setWorkflowDefinitionStatus(`error:${errorMessage(error)}`)
    } finally {
      setWorkflowDefinitionSaving(false)
    }
  }

  function resetDefinitionDiff() {
    setDefinitionDiff(null)
    setDefinitionDiffStatus('idle')
    setDefinitionDiffError('')
  }

  async function loadCapabilityDefinitionDiff(assetType: CapabilityAssetType) {
    setDefinitionDiffStatus('loading')
    setDefinitionDiffError('')
    try {
      const diff =
        assetType === 'skill' && selectedSkill
          ? await skillApi.definitionDiff(selectedSkill.id)
          : assetType === 'agent' && selectedAgent
            ? await agentApi.definitionDiff(selectedAgent.id)
            : assetType === 'workflow' && selectedWorkflowAsset
              ? await workflowAssetApi.definitionDiff(selectedWorkflowAsset.id)
              : null
      if (!diff) return
      setDefinitionDiff(diff)
      setDefinitionDiffStatus('loaded')
    } catch (error) {
      setDefinitionDiffError(errorMessage(error))
      setDefinitionDiffStatus('error')
    }
  }

  async function revertCapabilityDefinition(assetType: CapabilityAssetType) {
    setDefinitionDiffStatus('reverting')
    setDefinitionDiffError('')
    try {
      if (assetType === 'skill' && selectedSkill) {
        const updated = await skillApi.revertDefinition(
          selectedSkill.id,
          selectedSkill.updatedAt,
        )
        setSelectedSkill(updated)
        setSkills((current) =>
          current.map((item) => (item.id === updated.id ? updated : item)),
        )
        setSkillDefinitionDraft((current) =>
          current ? skillToDefinitionDraft(updated) : current,
        )
      } else if (assetType === 'agent' && selectedAgent) {
        const updated = await agentApi.revertDefinition(
          selectedAgent.id,
          selectedAgent.updatedAt,
        )
        setSelectedAgent(updated)
        setAgents((current) =>
          current.map((item) => (item.id === updated.id ? updated : item)),
        )
        setAgentDefinitionDraft((current) =>
          current ? agentToDefinitionDraft(updated) : current,
        )
      } else if (assetType === 'workflow' && selectedWorkflowAsset) {
        const updated = await workflowAssetApi.revertDefinition(
          selectedWorkflowAsset.id,
          selectedWorkflowAsset.updatedAt,
        )
        setSelectedWorkflowAsset(updated)
        setWorkflowAssets((current) =>
          current.map((item) => (item.id === updated.id ? updated : item)),
        )
        setWorkflowDefinitionDraft((current) =>
          current ? workflowToDefinitionDraft(updated) : current,
        )
      }
      setDefinitionDiffStatus('reverted')
      setDefinitionDiff(null)
      await refreshWorkspaceSummary()
    } catch (error) {
      setDefinitionDiffError(errorMessage(error))
      setDefinitionDiffStatus('error')
    }
  }

  async function updateWorkflowCallBinding(
    workflowAsset: WorkflowAsset,
    callBinding: WorkflowAsset['callBinding'],
  ) {
    setRunError('')
    try {
      const updated = await workflowAssetApi.updateCallBinding(workflowAsset.id, {
        callBinding,
        expectedUpdatedAt: workflowAsset.updatedAt,
      })
      setSelectedWorkflowAsset(updated)
      setWorkflowAssets((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      )
      await refreshWorkspaceSummary()
    } catch (error) {
      setRunError(errorMessage(error))
    }
  }

  async function applyAssetProposal(proposal: AssetProposal) {
    setRunError('')
    try {
      const updated = await assetProposalApi.apply(proposal.id)
      setAssetProposals((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      )
      await refreshWorkspaceSummary()
    } catch (error) {
      setRunError(errorMessage(error))
    }
  }

  async function previewAssetProposal(proposal: AssetProposal) {
    return assetProposalApi.preview(proposal.id)
  }

  async function updateAssetProposal(
    proposal: AssetProposal,
    patch: {
      title: string
      description: string
      proposedAction: Record<string, unknown>
    },
  ) {
    setRunError('')
    const updated = await assetProposalApi.update(proposal.id, {
      ...patch,
      expectedUpdatedAt: proposal.updatedAt,
    })
    setAssetProposals((current) =>
      current.map((item) => (item.id === updated.id ? updated : item)),
    )
    return updated
  }

  async function rejectAssetProposal(proposal: AssetProposal) {
    setRunError('')
    try {
      const updated = await assetProposalApi.reject(proposal.id)
      setAssetProposals((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      )
    } catch (error) {
      setRunError(errorMessage(error))
    }
  }

  function renderStageResult(stage: StageView, sourceRun: AnalysisRun | null = currentRun): ReactNode {
    return (
      <StageResultRenderer
        publicMode={!internalMode}
        onSimulateSavedTopic={(topic) => void runAudienceSimulation(undefined, 'account', topic)}
        stage={stage}
        currentRun={sourceRun}
        onSaveGeneratedTopic={saveGeneratedTopic}
        onSelectTopic={async (topic) => {
          const selected = await selectTopic(topic)
          if (!internalMode) setActivePage('topics')
          return selected
        }}
        onGenerateBrief={internalMode ? generateBriefForTopic : async topic => {setSelectedTopic(topic); setActivePage('drafts'); return null}}
        onGenerateDraft={generateDraftForTopic}
        onFillSimulationTopic={setSimulationTopic}
      />
    )
  }

  function renderDraftStructure(value: Record<string, unknown>): ReactNode {
    return <DraftStructureRenderer value={value} />
  }

  useEffect(() => {
    if (selectedTopic) {
      setTopicDraft({ title: selectedTopic.title, angle: selectedTopic.angle, body: selectedTopic.body || '' })
    } else {
      setTopicDraft({ title: '', angle: '', body: '' })
    }
  }, [selectedTopic])

  const visibleTopics = topics.filter((topic) =>
    (internalMode || topic.sourceWorkflow !== 'trend_analysis') &&
    (topicFilter === 'all' ? true : topic.sourceWorkflow === topicFilter),
  )
  const helpContent = getWorkspaceHelpContent({
    activePage,
    inputAssetPanel,
    workflowTab,
    publicMode: !internalMode,
  })
  const mainContent = (
    <>
      {loadError && <div className="error-banner">⚠ {loadError}</div>}
      {loading && <div className="loading-card">正在加载账号档案…</div>}

      {!loading && !workspace && !addingCreator && (
        <div className="empty-workspace">
          <h2>账号档案暂不可用</h2>
          <p>请刷新页面，或新建一个账号档案后再开始导入。</p>
        </div>
      )}

      {!loading && (workspace || addingCreator) && activePage === 'creator-start' && (
        <CreatorStartPage
          workspace={workspace}
          xhsCreatorProfile={addingCreator ? null : xhsCreatorProfileMaterial || null}
          profileUrl={xhsProfileUrl}
          captureJob={xhsCaptureJob}
          submitting={xhsCaptureSubmitting}
          error={xhsCaptureError}
          noteLimit={captureNoteLimit}
          onNoteLimitChange={setCaptureNoteLimit}
          onProfileUrlChange={setXhsProfileUrl}
          onSubmit={startXhsCapture}
          onOpenMaterials={() => openInputAsset('xhs_creator_profiles')}
          onOpenDiagnosis={() => {
            setWorkflowTab('account')
            setActivePage('account-diagnosis')
          }}
        />
      )}
      {!loading && workspace && activePage === 'creator-overview' && <CreatorOverviewPage
        workspace={workspace}
        profile={xhsCreatorProfileMaterial}
        onNotes={() => openInputAsset('xhs_creator_profiles')}
        onAnalyze={() => { setWorkflowTab('account'); setActivePage('account-diagnosis') }}
        onImport={openExistingCreatorImport}
      />}

      {!loading &&
        workspace &&
        activePage === 'account-profile' &&
        renderAccountProfilePage()}
      {!loading &&
        workspace &&
        activePage === 'source-materials' &&
        (internalMode ? renderInputAssetsPage() : <CreatorMaterialsPage
          key={workspace.id}
          profile={xhsCreatorProfileMaterial}
          mediaAssets={mediaAssets}
          onImport={openExistingCreatorImport}
          onAnalyze={() => { setWorkflowTab('account'); setActivePage('account-diagnosis') }}
        />)}
      {!loading && workspace && activePage === 'image-assets' && (
        <MediaAssetsPage
          workspaceId={workspace.id}
          mediaType="image"
          assets={mediaAssets}
          skills={skills}
          mode={mode}
          onModeChange={setMode}
          onAssetsChange={setMediaAssets}
        />
      )}
      {!loading && workspace && activePage === 'video-assets' && (
        <MediaAssetsPage
          workspaceId={workspace.id}
          mediaType="video"
          assets={mediaAssets}
          skills={skills}
          mode={mode}
          onModeChange={setMode}
          onAssetsChange={setMediaAssets}
        />
      )}
      {!loading &&
        workspace &&
        activePage === 'account-diagnosis' &&
        (internalMode ? renderWorkflowRunPage('account') : <CreatorDiagnosisPage
          profile={xhsCreatorProfileMaterial}
          scope={analysisScope}
          onScopeChange={setAnalysisScope}
          running={running}
          onRun={() => void runDiagnosis('account')}
          onImport={openExistingCreatorImport}
        >
          {(analysisStageViewsByWorkflow.account.length > 0 || runError) && <WorkflowOutputPanel
            targetTab="account"
            views={analysisStageViewsByWorkflow.account}
            outputKind="analysis"
            runError={runError}
            renderStageResult={renderStageResult}
          />}
        </CreatorDiagnosisPage>)}
      {!loading &&
        workspace &&
        activePage === 'trend-analysis' &&
        renderWorkflowRunPage('trend')}
      {!loading &&
        workspace &&
        activePage === 'video-quality' &&
        renderWorkflowRunPage('video')}

      {!loading && workspace && activePage === 'history' && (
        <AnalysisHistoryPage
          publicMode={!internalMode}
          analysisRuns={analysisRuns.filter(
            (run) => internalMode || run.workflowType === 'account_diagnosis',
          )}
          selectedRun={selectedRun}
          analysisReviewDraft={analysisReviewDraft}
          analysisReviewSaveState={saveStates.analysisReview}
          renderStageResult={renderStageResult}
          onOpenRun={openRun}
          onAnalysisReviewDraftChange={setAnalysisReviewDraft}
          onSaveAnalysisRunReview={saveAnalysisRunReview}
        />
      )}
      {!loading && workspace && activePage === 'topics' && (
        <TopicLibraryPage
          onOpenCanvas={(topic) => {setSelectedTopic(topic); setActivePage('drafts')}}
          onTogglePinned={async (topic) => {
            try {const updated = await topicApi.update(topic.id, {pinned: !topic.pinned, expectedUpdatedAt:topic.updatedAt}); setSelectedTopic(updated); await refreshWorkspaceSummary()}
            catch (error) {setSaveState('topic', {phase:'error',message:errorMessage(error)})}
          }}
          publicMode={!internalMode}
          busy={running || saveStates.draft.phase === 'saving'}
          onSimulateTopic={(topic) => void runAudienceSimulation(undefined, 'account', topic)}
          visibleTopics={visibleTopics}
          selectedTopic={selectedTopic}
          topicFilter={topicFilter}
          manualTopicTitle={manualTopicTitle}
          manualTopicAngle={manualTopicAngle}
          topicDraft={topicDraft}
          manualTopicSaveState={saveStates.manualTopic}
          topicSaveState={saveStates.topic}
          onManualTopicTitleChange={setManualTopicTitle}
          onManualTopicAngleChange={setManualTopicAngle}
          onSaveManualTopic={saveManualTopic}
          onTopicFilterChange={setTopicFilter}
          onSelectTopicRow={setSelectedTopic}
          onSelectCurrentTopic={selectTopic}
          onGenerateBrief={(topic) => void generateBriefForTopic(topic).catch(() => undefined)}
          onGenerateDraft={(topic) => void generateDraftForTopic(topic).catch(() => undefined)}
          onArchiveTopic={archiveTopic}
          onTopicDraftChange={setTopicDraft}
          onSaveTopicEdits={updateSelectedTopic}
        />
      )}
      {!loading && workspace && activePage === 'drafts' && !internalMode && <CreatorCanvasPage
        key={workspace.id} workspaceId={workspace.id} topic={selectedTopic} topics={topics.filter(t => t.sourceWorkflow !== 'trend_analysis')}
        agentId={agents.find(a => a.agentId === 'topic_draft_editor')?.id}
        onSelect={setSelectedTopic} onUpdated={topic => {if(selectedWorkspaceRef.current !== topic.workspaceId) return; setSelectedTopic(topic); setTopics(current => current.map(t => t.id === topic.id ? topic : t))}}
      />}
      {!loading && workspace && activePage === 'drafts' && internalMode && (
        <DraftsPage
          publicMode={!internalMode}
          drafts={drafts.filter((draft) => internalMode || draft.sourceWorkflow !== 'trend_analysis')}
          selectedDraft={selectedDraft}
          draftEditor={draftEditor}
          draftSaveState={saveStates.draft}
          onOpenDraft={openDraft}
          onDraftEditorChange={(value) => {
            setDraftEditor(value)
            setSaveState('draft', idleState)
          }}
          onSaveDraftEdits={saveDraftEdits}
          onGenerateStructureFromBrief={(draft) => void generateStructureFromBrief(draft).catch(() => undefined)}
          onRunAudienceSimulation={runAudienceSimulation}
          renderDraftStructure={renderDraftStructure}
          draftDisplayTitle={draftDisplayTitle}
          draftKindLabel={draftKindLabel}
        />
      )}
      {!loading && workspace && activePage === 'simulations' && (
        <>
        {!internalMode && <div className="creator-diagnosis-controls">
          {audience.error && <p role="alert">{audience.error}</p>}
          <select aria-label="模拟使用的受众分析" value={audience.selected?.id || ''} onChange={e => audience.setSelectedId(e.target.value)}><option value="">先完成受众分析</option>{audience.rows.filter(r => r.status === 'completed').map(r => <option key={r.id} value={r.id}>{new Date(r.createdAt).toLocaleString()} · {r.inputSnapshot.scope.selectedNoteCount} 条笔记</option>)}</select>
          <select aria-label="模拟选题" value={selectedTopic?.id || ''} onChange={e => setSelectedTopic(topics.find(t => t.id === e.target.value) || null)}><option value="">选择选题</option>{topics.filter(t => t.status !== 'archived').map(t => <option key={t.id} value={t.id}>{t.title}</option>)}</select>
          <button className="primary" disabled={running || audience.selected?.status !== 'completed' || !selectedTopic} onClick={() => void runAudienceSimulation(undefined,'account',selectedTopic || undefined)}>开始模拟</button>
          {!audience.rows.some(r => r.status === 'completed') && <button onClick={() => setActivePage('audience-analysis')}>先分析受众</button>}
        </div>}
        {!internalMode && running && <WorkflowOutputPanel targetTab="account" views={simulationStageViews} outputKind="simulation" runError={runError} renderStageResult={renderStageResult} />}
        {!internalMode && !running && runError && <p role="alert">{runError}</p>}
        <SimulationHistoryPage
          publicMode={!internalMode}
          simulationRuns={simulationRuns}
          selectedSimulationRun={selectedSimulationRun}
          simulationReviewDraft={simulationReviewDraft}
          simulationReviewSaveState={saveStates.simulationReview}
          reviewStatusLabel={reviewStatusLabel}
          onOpenSimulationRun={openSimulationRun}
          onSimulationReviewDraftChange={setSimulationReviewDraft}
          onSaveSimulationRunReview={saveSimulationRunReview}
          stageSeedFromSimulation={stageSeedFromSimulation}
          renderStageResult={renderStageResult}
        />
        </>
      )}
      {!loading &&
        workspace &&
        activePage === 'conversations' &&
        renderConversationsPage()}
      {!loading && workspace && activePage === 'audience-analysis' && <AudienceAnalysisPage
        key={workspace.id} workspaceId={workspace.id} profile={xhsCreatorProfileMaterial}
        analyses={audience.rows} selectedId={audience.selectedId} onSelect={audience.setSelectedId}
        onRefresh={audience.refresh} onSimulate={() => setActivePage('simulations')}
      />}
      {!loading && workspace && activePage === 'skills' && (
        <SkillsPage
          skills={skills}
          selectedSkill={selectedSkill}
          agentConversationCreating={agentConversationCreating}
          definitionDiffPanel={renderCapabilityDefinitionDiffPanel('skill')}
          definitionEditor={
            <SkillDefinitionEditor
              selectedSkill={selectedSkill}
              draft={skillDefinitionDraft}
              saving={skillDefinitionSaving}
              status={skillDefinitionStatus}
              onDraftChange={setSkillDefinitionDraft}
              onStatusChange={setSkillDefinitionStatus}
              onSave={saveSkillDefinition}
            />
          }
          skillTestPanel={
            selectedSkill ? (
              <SkillTestPanel
                skill={selectedSkill}
                skillTestMode={skillTestMode}
                skillTestInput={skillTestInput}
                skillTestStatus={skillTestStatus}
                skillTestError={skillTestError}
                skillTestResult={skillTestResult}
                onSkillTestModeChange={setSkillTestMode}
                onSkillTestInputChange={(value) => {
                  setSkillTestInput(value)
                  setSkillTestStatus('idle')
                  setSkillTestResult(null)
                  setSkillTestError('')
                }}
                onRunSkillTest={runSkillTest}
              />
            ) : null
          }
          onOpenSkill={openSkill}
          onEditSkill={startSkillDefinitionEdit}
          onDesignSkill={(contextTarget) =>
            startMakerConversation(
              MAKER_AGENT_IDS.skill,
              '我想设计一个新的 Skill，用来：\n\n它应该读取哪些 workspace 资产：\n\n它应该输出什么结构：',
              contextTarget,
            )
          }
          onTuneSkill={(skill) =>
            startMakerConversation(
              MAKER_AGENT_IDS.skill,
              `我想调优这个 Skill：${skill.displayName}\n\n需要修改的 rubric / prompt / 输出结构：`,
              { assetType: 'skill', assetId: skill.id },
            )
          }
        />
      )}
      {!loading && workspace && activePage === 'agents' && renderAgentsPage()}
      {!loading &&
        workspace &&
        activePage === 'workflows' &&
        renderWorkflowAssetsPage()}
    </>
  )

  return (
    <WorkspaceShell
      workspace={workspace}
      workspaces={workspaces}
      selectedWorkspaceId={selectedWorkspaceId}
      activePage={activePage}
      inputAssetPanel={inputAssetPanel}
      showHelp={showHelp}
      helpContent={helpContent}
      internalMode={internalMode}
      workflowAssets={workflowAssets}
      onOpenInputAsset={openInputAsset}
      onSetActivePage={(page) => {setAddingCreator(false); setActivePage(page)}}
      onSelectWorkspace={(id) => {
        setAddingCreator(false)
        if (!internalMode) setActivePage('creator-overview')
        selectedWorkspaceRef.current = id
        setSelectedWorkspaceId(id)
        setXhsCaptureJob(null)
        setXhsCaptureError('')
        setXhsProfileUrl('')
        setAnalysisScope('recent_10')
        setCaptureNoteLimit(10)
      }}
      busy={running || xhsCaptureSubmitting || saveStates.draft.phase === 'saving' || Boolean(xhsCaptureJob && ['pending', 'waiting_for_login', 'running', 'processing'].includes(xhsCaptureJob.status))}
      onCreateCreatorProfile={() => void createCreatorProfile()}
      onSetWorkflowTab={setWorkflowTab}
      onToggleHelp={() => setShowHelp((value) => !value)}
    >
      {mainContent}
    </WorkspaceShell>
  )

  async function saveAccountProfile() {
    setSaveState('workspace', { phase: 'saving' })
    setSaveState('accountProfiles', { phase: 'saving' })
    try {
      await persistWorkspace(workspaceName, positioning)
      const savedProfile = await persistTextMaterial(
        'account_profile',
        positioning,
        selectedProfileMaterial || undefined,
        accountProfileDraftName,
      )
      setSelectedProfileInputAssetId(savedProfile.id)
      setSaveState('workspace', { phase: 'saved' })
      setSaveState('accountProfiles', { phase: 'saved' })
    } catch (error) {
      setSaveState('workspace', { phase: 'error', message: errorMessage(error) })
      setSaveState('accountProfiles', {
        phase: 'error',
        message: errorMessage(error),
      })
    }
  }

  async function saveAccountProfileAsNew() {
    setSaveState('workspace', { phase: 'saving' })
    setSaveState('accountProfiles', { phase: 'saving' })
    try {
      await persistWorkspace(workspaceName, positioning)
      const savedProfile = await persistTextMaterial(
        'account_profile',
        positioning,
        undefined,
        accountProfileDraftName,
      )
      setSelectedProfileInputAssetId(savedProfile.id)
      setSaveState('workspace', { phase: 'saved' })
      setSaveState('accountProfiles', { phase: 'saved' })
    } catch (error) {
      setSaveState('workspace', { phase: 'error', message: errorMessage(error) })
      setSaveState('accountProfiles', {
        phase: 'error',
        message: errorMessage(error),
      })
    }
  }

  async function saveHistoricalPosts() {
    setSaveState('historical', { phase: 'saving' })
    try {
      await persistTextMaterial(
        'historical_posts',
        historicalPosts,
        historicalMaterial,
        historicalPostsDraftName,
      )
      setSaveState('historical', { phase: 'saved' })
    } catch (error) {
      setSaveState('historical', { phase: 'error', message: errorMessage(error) })
    }
  }

  async function saveHistoricalPostsAsNew() {
    setSaveState('historical', { phase: 'saving' })
    try {
      await persistTextMaterial(
        'historical_posts',
        historicalPosts,
        undefined,
        historicalPostsDraftName,
      )
      setSaveState('historical', { phase: 'saved' })
    } catch (error) {
      setSaveState('historical', { phase: 'error', message: errorMessage(error) })
    }
  }

  async function saveComments() {
    setSaveState('comments', { phase: 'saving' })
    try {
      await persistTextMaterial('comments', comments, commentsMaterial, commentsDraftName)
      setSaveState('comments', { phase: 'saved' })
    } catch (error) {
      setSaveState('comments', { phase: 'error', message: errorMessage(error) })
    }
  }

  async function saveCommentsAsNew() {
    setSaveState('comments', { phase: 'saving' })
    try {
      await persistTextMaterial('comments', comments, undefined, commentsDraftName)
      setSaveState('comments', { phase: 'saved' })
    } catch (error) {
      setSaveState('comments', { phase: 'error', message: errorMessage(error) })
    }
  }

  async function saveVideoCreatorSamples() {
    setSaveState('video', { phase: 'saving' })
    try {
      await persistTextMaterial(
        'video_creator_samples',
        videoCreatorSamples,
        videoCreatorSamplesMaterial,
        videoCreatorSamplesDraftName,
      )
      setSaveState('video', { phase: 'saved' })
    } catch (error) {
      setSaveState('video', { phase: 'error', message: errorMessage(error) })
    }
  }

  async function saveVideoCreatorSamplesAsNew() {
    setSaveState('video', { phase: 'saving' })
    try {
      await persistTextMaterial(
        'video_creator_samples',
        videoCreatorSamples,
        undefined,
        videoCreatorSamplesDraftName,
      )
      setSaveState('video', { phase: 'saved' })
    } catch (error) {
      setSaveState('video', { phase: 'error', message: errorMessage(error) })
    }
  }

  async function saveXhsCreatorProfile() {
    setSaveState('xhs', { phase: 'saving' })
    try {
      await persistTextMaterial(
        'xhs_creator_profile',
        xhsCreatorProfileContent,
        xhsCreatorProfileMaterial,
        xhsCreatorProfileDraftName,
      )
      setSaveState('xhs', { phase: 'saved' })
    } catch (error) {
      setSaveState('xhs', { phase: 'error', message: errorMessage(error) })
    }
  }

  async function saveXhsCreatorProfileAsNew() {
    setSaveState('xhs', { phase: 'saving' })
    try {
      await persistTextMaterial(
        'xhs_creator_profile',
        xhsCreatorProfileContent,
        undefined,
        xhsCreatorProfileDraftName,
      )
      setSaveState('xhs', { phase: 'saved' })
    } catch (error) {
      setSaveState('xhs', { phase: 'error', message: errorMessage(error) })
    }
  }

  function renderAccountProfilePage() {
    return (
      <AccountProfilePage
        workspaceName={workspaceName}
        positioning={positioning}
        positioningVersion={workspace?.positioningVersion ?? 0}
        workspaceSaveState={saveStates.workspace}
        accountProfilesSaveState={saveStates.accountProfiles}
        onWorkspaceNameChange={(value) => {
          setWorkspaceName(value)
          setSaveState('workspace', idleState)
        }}
        onPositioningChange={(value) => {
          setPositioning(value)
          setSaveState('workspace', idleState)
        }}
        onSave={saveAccountProfile}
      />
    )
  }

  function renderInputAssetsPage() {
    return (
      <InputAssetsPage
        inputAssetPanel={inputAssetPanel}
        inputAssetDetailOpen={inputAssetDetailOpen}
        accountProfileMaterials={accountProfileMaterials}
        historicalMaterials={historicalMaterials}
        commentsMaterials={commentsMaterials}
        trendMaterials={trendMaterials}
        videoCreatorSamplesMaterials={videoCreatorSamplesMaterials}
        xhsCreatorProfileMaterials={xhsCreatorProfileMaterials}
        selectedProfileMaterial={selectedProfileMaterial}
        historicalMaterial={historicalMaterial}
        commentsMaterial={commentsMaterial}
        trendMaterial={trendMaterial}
        videoCreatorSamplesMaterial={videoCreatorSamplesMaterial}
        xhsCreatorProfileMaterial={xhsCreatorProfileMaterial}
        workspaceName={workspaceName}
        positioning={positioning}
        accountProfileDraftName={accountProfileDraftName}
        historicalPostsDraftName={historicalPostsDraftName}
        commentsDraftName={commentsDraftName}
        trendCsvDraftName={trendCsvDraftName}
        videoCreatorSamplesDraftName={videoCreatorSamplesDraftName}
        xhsCreatorProfileDraftName={xhsCreatorProfileDraftName}
        historicalPosts={historicalPosts}
        comments={comments}
        trendKeyword={trendKeyword}
        videoCreatorSamples={videoCreatorSamples}
        xhsCreatorProfileContent={xhsCreatorProfileContent}
        inputAssetFormatterDraft={inputAssetFormatterDraft}
        inputAssetFormatterStatus={inputAssetFormatterStatus}
        workspaceSaveState={saveStates.workspace}
        accountProfilesSaveState={saveStates.accountProfiles}
        historicalSaveState={saveStates.historical}
        commentsSaveState={saveStates.comments}
        trendSaveState={saveStates.trend}
        videoSaveState={saveStates.video}
        xhsSaveState={saveStates.xhs}
        onStartNewInputAsset={startNewInputAsset}
        onOpenInputAsset={openInputAsset}
        onChooseTextMaterial={chooseTextMaterialFromInputAssetPage}
        onChooseTrendMaterial={chooseTrendMaterialFromInputAssetPage}
        onFormatterDraftChange={(value) => {
          setInputAssetFormatterDraft(value)
          setInputAssetFormatterStatus('')
        }}
        onApplyInputAssetFormatter={applyInputAssetFormatter}
        onAccountProfileDraftNameChange={setAccountProfileDraftName}
        onWorkspaceNameChange={(value) => {
          setWorkspaceName(value)
          setSaveState('workspace', idleState)
        }}
        onPositioningChange={(value) => {
          setPositioning(value)
          setSaveState('workspace', idleState)
        }}
        onSaveAccountProfile={saveAccountProfile}
        onSaveAccountProfileAsNew={saveAccountProfileAsNew}
        onHistoricalPostsDraftNameChange={(value) => {
          setHistoricalPostsDraftName(value)
          setSaveState('historical', idleState)
        }}
        onHistoricalPostsChange={(value) => {
          setHistoricalPosts(value)
          setSaveState('historical', idleState)
        }}
        onSaveHistoricalPosts={saveHistoricalPosts}
        onSaveHistoricalPostsAsNew={saveHistoricalPostsAsNew}
        onCommentsDraftNameChange={(value) => {
          setCommentsDraftName(value)
          setSaveState('comments', idleState)
        }}
        onCommentsChange={(value) => {
          setComments(value)
          setSaveState('comments', idleState)
        }}
        onSaveComments={saveComments}
        onSaveCommentsAsNew={saveCommentsAsNew}
        onTrendCsvDraftNameChange={(value) => {
          setTrendCsvDraftName(value)
          setSaveState('trend', idleState)
        }}
        onTrendKeywordChange={(value) => {
          setTrendKeyword(value)
          setSaveState('trend', idleState)
        }}
        onTrendFileChange={(file) => {
          setTrendFile(file)
          setSaveState('trend', idleState)
        }}
        onUploadTrendCsv={uploadTrendCsv}
        onVideoCreatorSamplesDraftNameChange={(value) => {
          setVideoCreatorSamplesDraftName(value)
          setSaveState('video', idleState)
        }}
        onVideoCreatorSamplesChange={(value) => {
          setVideoCreatorSamples(value)
          setSaveState('video', idleState)
        }}
        onSaveVideoCreatorSamples={saveVideoCreatorSamples}
        onSaveVideoCreatorSamplesAsNew={saveVideoCreatorSamplesAsNew}
        onXhsCreatorProfileDraftNameChange={(value) => {
          setXhsCreatorProfileDraftName(value)
          setSaveState('xhs', idleState)
        }}
        onXhsCreatorProfileContentChange={(value) => {
          setXhsCreatorProfileContent(value)
          setSaveState('xhs', idleState)
        }}
        onSaveXhsCreatorProfile={saveXhsCreatorProfile}
        onSaveXhsCreatorProfileAsNew={saveXhsCreatorProfileAsNew}
        xhsImportFiles={xhsImportFiles}
        onSetXhsImportFile={setXhsImportFile}
        onUploadXhsImport={uploadXhsImport}
        xhsPackageFiles={xhsPackageFiles}
        xhsPackagePreview={xhsPackagePreview}
        xhsPackagePreviewError={xhsPackagePreviewError}
        xhsImportWarnings={xhsImportWarnings}
        matchingXhsPackageMaterial={matchingXhsPackageMaterial}
        onSetXhsPackageFiles={setXhsImportPackageFiles}
        onUploadXhsImportPackage={uploadXhsImportPackage}
      />
    )
  }

  function renderWorkflowRunPage(targetTab: WorkflowTab) {
    const outputKind = workflowOutputKindByWorkflow[targetTab]
    return (
      <WorkflowRunPage
        targetTab={targetTab}
        mode={mode}
        running={running}
        simulationTopic={simulationTopic}
        selectedXhsCreatorProfileInputAssetId={
          selectedXhsCreatorProfileInputAssetId
        }
        xhsCreatorProfileMaterial={xhsCreatorProfileMaterial}
        xhsCreatorProfileMaterials={xhsCreatorProfileMaterials}
        selectedProfileMaterial={selectedProfileMaterial}
        accountProfileMaterials={accountProfileMaterials}
        historicalMaterial={historicalMaterial}
        historicalMaterials={historicalMaterials}
        commentsMaterial={commentsMaterial}
        commentsMaterials={commentsMaterials}
        trendMaterial={trendMaterial}
        trendMaterials={trendMaterials}
        videoCreatorSamplesMaterial={videoCreatorSamplesMaterial}
        videoCreatorSamplesMaterials={videoCreatorSamplesMaterials}
        mediaAssets={mediaAssets}
        selectedVideoWorkflowMediaAssetIds={selectedVideoWorkflowMediaAssetIds}
        videoWorkflowMediaAssets={videoWorkflowMediaAssets}
        onSelectXhsCreatorProfileInputAssetId={
          setSelectedXhsCreatorProfileInputAssetId
        }
        onSelectProfileInputAssetId={setSelectedProfileInputAssetId}
        onChooseTextMaterial={chooseTextMaterial}
        onChooseTrendMaterial={chooseTrendMaterial}
        onSetSelectedVideoWorkflowMediaAssetIds={
          setSelectedVideoWorkflowMediaAssetIds
        }
        onSimulationTopicChange={setSimulationTopic}
        onSetMode={setMode}
        onApplyDemoSample={applyDemoSample}
        onRunDiagnosis={runDiagnosis}
        onRunAudienceSimulation={runAudienceSimulation}
        onDownloadAnalysisRunsCsv={downloadAnalysisRunsCsv}
        views={
          outputKind === 'simulation'
            ? simulationStageViews
            : analysisStageViewsByWorkflow[targetTab]
        }
        outputKind={outputKind}
        runError={runError}
        renderStageResult={renderStageResult}
      />
    )
  }

  function renderCapabilityDefinitionDiffPanel(assetType: CapabilityAssetType) {
    return (
      <CapabilityDefinitionDiffPanel
        assetType={assetType}
        definitionDiff={definitionDiff}
        definitionDiffStatus={definitionDiffStatus}
        definitionDiffError={definitionDiffError}
        onLoadDiff={loadCapabilityDefinitionDiff}
        onRevertDefinition={revertCapabilityDefinition}
      />
    )
  }

  function renderConversationsPage() {
    return (
      <ConversationsPage
        conversations={agentConversations}
        selectedConversation={selectedAgentConversation}
        agents={agents}
        assetProposals={assetProposals}
        availableSkills={skills}
        conversationTitleDraft={conversationTitleDraft}
        conversationSaving={conversationSaving}
        conversationSaveStatus={conversationSaveStatus}
        onOpenConversation={openAgentConversation}
        onOpenConversationAgent={(agentAssetId) => {
          setActivePage('agents')
          openAgent(agentAssetId)
        }}
        onConversationTitleDraftChange={(value) => {
          setConversationTitleDraft(value)
          setConversationSaveStatus('')
        }}
        onUpdateConversation={updateAgentConversationAsset}
        onUpdateProposal={updateAssetProposal}
        onPreviewProposal={previewAssetProposal}
        onApplyProposal={applyAssetProposal}
        onRejectProposal={rejectAssetProposal}
      />
    )
  }

  function renderAgentsPage() {
    return (
      <AgentsPage
        agents={agents}
        skills={skills}
        selectedAgent={selectedAgent}
        conversations={agentConversations}
        selectedConversation={selectedAgentConversation}
        agentConversationCreating={agentConversationCreating}
        runError={runError}
        definitionDiffPanel={renderCapabilityDefinitionDiffPanel('agent')}
        definitionEditor={
          <AgentDefinitionEditor
            draft={agentDefinitionDraft}
            saving={agentDefinitionSaving}
            status={agentDefinitionStatus}
            skills={skills}
            onDraftChange={setAgentDefinitionDraft}
            onStatusChange={setAgentDefinitionStatus}
            onSave={saveAgentDefinition}
          />
        }
        conversationPanel={
          <AgentConversationPanel
            conversation={selectedAgentConversation}
            agent={selectedAgent}
            proposals={assetProposals}
            availableSkills={skills}
            availableAgents={agents}
            mode={mode}
            draft={agentMessageDraft}
            sending={agentSending}
            composerRef={agentChatComposerRef}
            onModeChange={setMode}
            onDraftChange={updateAgentMessageDraft}
            onSend={sendAgentMessage}
            onUpdateProposal={updateAssetProposal}
            onPreviewProposal={previewAssetProposal}
            onApplyProposal={applyAssetProposal}
            onRejectProposal={rejectAssetProposal}
          />
        }
        onOpenAgent={openAgent}
        onEditAgent={startAgentDefinitionEdit}
        onDesignAgent={() =>
          startMakerConversation(
            MAKER_AGENT_IDS.agent,
            '我想设计一个新的 Agent，用来：\n\n它应该具备哪些能力 / skills：\n\n它应该读取哪些资产，不应该读取哪些资产：',
            selectedAgent && selectedAgent.agentId !== MAKER_AGENT_IDS.agent
              ? { assetType: 'agent', assetId: selectedAgent.id }
              : undefined,
          )
        }
        onTuneAgent={(agent) =>
          startMakerConversation(
            MAKER_AGENT_IDS.agent,
            `我想调优这个 Agent：${agent.displayName}\n\n需要修改的 system prompt / skills / context policy：`,
            { assetType: 'agent', assetId: agent.id },
          )
        }
        onStartConversation={startAgentConversation}
        onOpenConversation={openAgentConversation}
        onOpenSkill={(skillAssetId) => {
          setActivePage('skills')
          openSkill(skillAssetId)
        }}
      />
    )
  }

  function renderWorkflowAssetsPage() {
    return (
      <WorkflowsPage
        workflowAssets={workflowAssets}
        agents={agents}
        skills={skills}
        selectedWorkflowAsset={selectedWorkflowAsset}
        agentConversationCreating={agentConversationCreating}
        definitionDiffPanel={renderCapabilityDefinitionDiffPanel('workflow')}
        definitionEditor={
          <WorkflowDefinitionEditor
            draft={workflowDefinitionDraft}
            saving={workflowDefinitionSaving}
            status={workflowDefinitionStatus}
            agents={agents}
            skills={skills}
            onDraftChange={setWorkflowDefinitionDraft}
            onStatusChange={setWorkflowDefinitionStatus}
            onSave={saveWorkflowDefinition}
          />
        }
        onOpenWorkflow={openWorkflowAsset}
        onEditWorkflow={startWorkflowDefinitionEdit}
        onDesignWorkflow={() =>
          startMakerConversation(
            MAKER_AGENT_IDS.workflow,
            '我想设计一个新的 Workflow，用来：\n\n输入资产包括：\n\n输出资产应该是：\n\n需要哪些 agent / skill 协作：',
            selectedWorkflowAsset
              ? { assetType: 'workflow', assetId: selectedWorkflowAsset.id }
              : undefined,
          )
        }
        onTuneWorkflow={(workflowAsset) =>
          startMakerConversation(
            MAKER_AGENT_IDS.workflow,
            `我想调优这个 Workflow：${workflowAsset.displayName}\n\n需要修改的 task plan / agent / skill / 调用注册：`,
            { assetType: 'workflow', assetId: workflowAsset.id },
          )
        }
        onUpdateCallBinding={updateWorkflowCallBinding}
        onOpenAgent={(agentAssetId) => {
          setActivePage('agents')
          openAgent(agentAssetId)
        }}
        onOpenSkill={(skillAssetId) => {
          setActivePage('skills')
          openSkill(skillAssetId)
        }}
      />
    )
  }

}

function App() {
  if (window.location.pathname === '/health') return <HealthPage />
  return <WorkspaceApp />
}

export default App
