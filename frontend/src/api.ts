import type {
  Agent,
  AgentConversation,
  AgentConversationSummary,
  AgentConversationUpdate,
  AgentDefinitionUpdate,
  AssetProposal,
  AssetProposalPreview,
  AgentStatus,
  AgentSummary,
  AnalysisRun,
  AnalysisRunSummary,
  CapabilityDefinitionDiff,
  Draft,
  DraftSummary,
  InputAsset,
  InputAssetType,
  MediaAsset,
  MediaAssetType,
  VideoPreviewDeriveResponse,
  SimulationRun,
  SimulationRunSummary,
  Skill,
  SkillDefinitionUpdate,
  SkillDryRunResponse,
  SkillInvokeResponse,
  SkillSummary,
  SkillStatus,
  TextInputAsset,
  Topic,
  TopicSourceWorkflow,
  TopicStatus,
  TrendCsvInputAsset,
  Workspace,
  WorkflowAsset,
  WorkflowAssetDefinitionUpdate,
  WorkflowAssetStatus,
  WorkflowAssetSummary,
  WorkflowType,
  XhsOfflineImportPackageResponse,
  XhsOfflineImportResponse,
} from './types'

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init)
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try {
      const body = (await response.json()) as { detail?: string }
      if (body.detail) message = body.detail
    } catch {
      // Keep the stable fallback message when an error is not JSON.
    }
    throw new ApiError(message, response.status)
  }
  return (await response.json()) as T
}

const jsonHeaders = { 'Content-Type': 'application/json' }

export const workspaceApi = {
  list: () => request<Workspace[]>('/api/workspaces'),

  get: (workspaceId: string) =>
    request<Workspace>(`/api/workspaces/${workspaceId}`),

  create: (name: string, accountPositioning: string) =>
    request<Workspace>('/api/workspaces', {
      method: 'POST',
      headers: jsonHeaders,
      body: JSON.stringify({ name, accountPositioning }),
    }),

  update: (
    workspaceId: string,
    payload: {
      name?: string
      accountPositioning?: string
      expectedUpdatedAt: string
    },
  ) =>
    request<Workspace>(`/api/workspaces/${workspaceId}`, {
      method: 'PATCH',
      headers: jsonHeaders,
      body: JSON.stringify(payload),
    }),
}

export const inputAssetApi = {
  list: (workspaceId: string, type?: InputAssetType) => {
    const query = type ? `?type=${type}` : ''
    return request<InputAsset[]>(
      `/api/workspaces/${workspaceId}/input-assets${query}`,
    )
  },

  get: (assetId: string) => request<InputAsset>(`/api/input-assets/${assetId}`),

  createText: (
    workspaceId: string,
    type:
      | 'account_profile'
      | 'historical_posts'
      | 'comments'
      | 'video_creator_samples'
      | 'xhs_creator_profile',
    name: string,
    content: string,
  ) =>
    request<TextInputAsset>(
      `/api/workspaces/${workspaceId}/input-assets`,
      {
        method: 'POST',
        headers: jsonHeaders,
        body: JSON.stringify({ type, name, content }),
      },
  ),

  update: (
    assetId: string,
    payload: {
      name?: string
      content?: string
      keyword?: string
      expectedUpdatedAt: string
    },
  ) =>
    request<InputAsset>(`/api/input-assets/${assetId}`, {
      method: 'PATCH',
      headers: jsonHeaders,
      body: JSON.stringify(payload),
    }),

  uploadTrendCsv: (
    workspaceId: string,
    name: string,
    keyword: string,
    file: File,
  ) => {
    const form = new FormData()
    form.set('name', name)
    form.set('keyword', keyword)
    form.set('file', file)
    return request<TrendCsvInputAsset>(
      `/api/workspaces/${workspaceId}/input-assets/trend-csv`,
      { method: 'POST', body: form },
    )
  },

  uploadXhsImport: (
    workspaceId: string,
    type: 'historical_posts' | 'video_creator_samples' | 'xhs_creator_profile',
    file: File,
    name = '',
  ) => {
    const form = new FormData()
    form.set('type', type)
    form.set('name', name)
    form.set('file', file)
    return request<XhsOfflineImportResponse>(
      `/api/workspaces/${workspaceId}/input-assets/xhs-import`,
      { method: 'POST', body: form },
    )
  },

  uploadXhsImportPackage: (
    workspaceId: string,
    profile: File,
    files: File[],
    relativePaths: string[],
    name = '',
    saveAsNew = false,
  ) => {
    const form = new FormData()
    form.set('name', name)
    form.set('saveAsNew', String(saveAsNew))
    form.set('profile', profile, profile.name)
    files.forEach((file, index) => {
      const relativePath = relativePaths[index] || file.name
      form.append('files', file, relativePath)
      form.append('relativePaths', relativePath)
    })
    return request<XhsOfflineImportPackageResponse>(
      `/api/workspaces/${workspaceId}/input-assets/xhs-import-package`,
      { method: 'POST', body: form },
    )
  },
}

export const sourceMaterialApi = inputAssetApi

export const mediaAssetApi = {
  list: (workspaceId: string, type?: MediaAssetType) => {
    const query = type ? `?type=${type}` : ''
    return request<MediaAsset[]>(
      `/api/workspaces/${workspaceId}/media-assets${query}`,
    )
  },

  get: (assetId: string) =>
    request<MediaAsset>(`/api/media-assets/${assetId}`),

  upload: (
    workspaceId: string,
    type: MediaAssetType,
    name: string,
    purpose: string,
    file: File,
  ) => {
    const form = new FormData()
    form.set('type', type)
    form.set('name', name)
    form.set('purpose', purpose)
    form.set('file', file)
    return request<MediaAsset>(
      `/api/workspaces/${workspaceId}/media-assets/upload`,
      { method: 'POST', body: form },
    )
  },

  update: (
    assetId: string,
    payload: {
      name?: string
      purpose?: string
      metadata?: Record<string, unknown>
      derived?: Record<string, unknown>
      userNotes?: string
      expectedUpdatedAt: string
    },
  ) =>
    request<MediaAsset>(`/api/media-assets/${assetId}`, {
      method: 'PATCH',
      headers: jsonHeaders,
      body: JSON.stringify(payload),
    }),

  deriveVideoPreview: (
    assetId: string,
    payload: { frameCount?: number; force?: boolean } = {},
  ) =>
    request<VideoPreviewDeriveResponse>(
      `/api/media-assets/${assetId}/derive-video-preview`,
      {
        method: 'POST',
        headers: jsonHeaders,
        body: JSON.stringify(payload),
      },
    ),
}

export const skillApi = {
  list: (workspaceId: string) =>
    request<SkillSummary[]>(`/api/workspaces/${workspaceId}/skills`),

  get: (skillAssetId: string) => request<Skill>(`/api/skills/${skillAssetId}`),

  update: (
    skillAssetId: string,
    payload: {
      status?: SkillStatus
      userNotes?: string
      expectedUpdatedAt: string
    },
  ) =>
    request<Skill>(`/api/skills/${skillAssetId}`, {
      method: 'PATCH',
      headers: jsonHeaders,
      body: JSON.stringify(payload),
    }),

  updateDefinition: (skillAssetId: string, payload: SkillDefinitionUpdate) =>
    request<Skill>(`/api/skills/${skillAssetId}/definition`, {
      method: 'PATCH',
      headers: jsonHeaders,
      body: JSON.stringify(payload),
    }),

  definitionDiff: (skillAssetId: string) =>
    request<CapabilityDefinitionDiff>(
      `/api/skills/${skillAssetId}/definition-diff`,
    ),

  revertDefinition: (skillAssetId: string, expectedUpdatedAt: string) =>
    request<Skill>(`/api/skills/${skillAssetId}/revert-definition`, {
      method: 'POST',
      headers: jsonHeaders,
      body: JSON.stringify({ expectedUpdatedAt }),
    }),

  invoke: (
    skillAssetId: string,
    payload: {
      input: Record<string, unknown>
      mode: 'demo' | 'live'
    },
  ) =>
    request<SkillInvokeResponse>(`/api/skills/${skillAssetId}/invoke`, {
      method: 'POST',
      headers: jsonHeaders,
      body: JSON.stringify(payload),
    }),

  dryRun: (
    skillAssetId: string,
    payload: {
      input: Record<string, unknown>
      mode: 'demo' | 'live'
    },
  ) =>
    request<SkillDryRunResponse>(`/api/skills/${skillAssetId}/dry-run`, {
      method: 'POST',
      headers: jsonHeaders,
      body: JSON.stringify(payload),
    }),
}

export const agentApi = {
  list: (workspaceId: string) =>
    request<AgentSummary[]>(`/api/workspaces/${workspaceId}/agents`),

  get: (agentAssetId: string) => request<Agent>(`/api/agents/${agentAssetId}`),

  update: (
    agentAssetId: string,
    payload: {
      status?: AgentStatus
      userNotes?: string
      expectedUpdatedAt: string
    },
  ) =>
    request<Agent>(`/api/agents/${agentAssetId}`, {
      method: 'PATCH',
      headers: jsonHeaders,
      body: JSON.stringify(payload),
    }),

  updateDefinition: (agentAssetId: string, payload: AgentDefinitionUpdate) =>
    request<Agent>(`/api/agents/${agentAssetId}/definition`, {
      method: 'PATCH',
      headers: jsonHeaders,
      body: JSON.stringify(payload),
    }),

  definitionDiff: (agentAssetId: string) =>
    request<CapabilityDefinitionDiff>(
      `/api/agents/${agentAssetId}/definition-diff`,
    ),

  revertDefinition: (agentAssetId: string, expectedUpdatedAt: string) =>
    request<Agent>(`/api/agents/${agentAssetId}/revert-definition`, {
      method: 'POST',
      headers: jsonHeaders,
      body: JSON.stringify({ expectedUpdatedAt }),
    }),
}

export const agentConversationApi = {
  list: (workspaceId: string) =>
    request<AgentConversationSummary[]>(
      `/api/workspaces/${workspaceId}/agent-conversations`,
    ),

  create: (
    workspaceId: string,
    agentAssetId: string,
    title?: string,
    contextTarget?: { assetType: 'skill' | 'agent' | 'workflow'; assetId: string },
  ) =>
    request<AgentConversation>(
      `/api/workspaces/${workspaceId}/agent-conversations`,
      {
        method: 'POST',
        headers: jsonHeaders,
        body: JSON.stringify({ agentAssetId, title, contextTarget }),
      },
    ),

  get: (conversationId: string) =>
    request<AgentConversation>(`/api/agent-conversations/${conversationId}`),

  update: (conversationId: string, payload: AgentConversationUpdate) =>
    request<AgentConversation>(`/api/agent-conversations/${conversationId}`, {
      method: 'PATCH',
      headers: jsonHeaders,
      body: JSON.stringify(payload),
    }),

  sendMessage: (
    conversationId: string,
    content: string,
    mode: 'demo' | 'live',
    clientMessageKey: string,
  ) =>
    request<AgentConversation>(
      `/api/agent-conversations/${conversationId}/messages`,
      {
        method: 'POST',
        headers: jsonHeaders,
        body: JSON.stringify({ content, mode, clientMessageKey }),
      },
    ),
}

export const assetProposalApi = {
  listForConversation: (conversationId: string) =>
    request<AssetProposal[]>(
      `/api/agent-conversations/${conversationId}/asset-proposals`,
    ),

  apply: (proposalId: string) =>
    request<AssetProposal>(`/api/asset-proposals/${proposalId}/apply`, {
      method: 'POST',
    }),

  preview: (proposalId: string) =>
    request<AssetProposalPreview>(`/api/asset-proposals/${proposalId}/preview`),

  update: (
    proposalId: string,
    payload: {
      title?: string
      description?: string
      proposedAction?: Record<string, unknown>
      expectedUpdatedAt: string
    },
  ) =>
    request<AssetProposal>(`/api/asset-proposals/${proposalId}`, {
      method: 'PATCH',
      headers: jsonHeaders,
      body: JSON.stringify(payload),
    }),

  reject: (proposalId: string) =>
    request<AssetProposal>(`/api/asset-proposals/${proposalId}/reject`, {
      method: 'POST',
    }),
}

export const workflowAssetApi = {
  list: (workspaceId: string) =>
    request<WorkflowAssetSummary[]>(`/api/workspaces/${workspaceId}/workflows`),

  get: (workflowAssetId: string) =>
    request<WorkflowAsset>(`/api/workflows/${workflowAssetId}`),

  update: (
    workflowAssetId: string,
    payload: {
      status?: WorkflowAssetStatus
      userNotes?: string
      expectedUpdatedAt: string
    },
  ) =>
    request<WorkflowAsset>(`/api/workflows/${workflowAssetId}`, {
      method: 'PATCH',
      headers: jsonHeaders,
      body: JSON.stringify(payload),
    }),

  updateCallBinding: (
    workflowAssetId: string,
    payload: {
      callBinding: '' | 'account' | 'trend' | 'video'
      expectedUpdatedAt: string
    },
  ) =>
    request<WorkflowAsset>(`/api/workflows/${workflowAssetId}/call-binding`, {
      method: 'PATCH',
      headers: jsonHeaders,
      body: JSON.stringify(payload),
    }),

  updateDefinition: (
    workflowAssetId: string,
    payload: WorkflowAssetDefinitionUpdate,
  ) =>
    request<WorkflowAsset>(`/api/workflows/${workflowAssetId}/definition`, {
      method: 'PATCH',
      headers: jsonHeaders,
      body: JSON.stringify(payload),
    }),

  definitionDiff: (workflowAssetId: string) =>
    request<CapabilityDefinitionDiff>(
      `/api/workflows/${workflowAssetId}/definition-diff`,
    ),

  revertDefinition: (workflowAssetId: string, expectedUpdatedAt: string) =>
    request<WorkflowAsset>(`/api/workflows/${workflowAssetId}/revert-definition`, {
      method: 'POST',
      headers: jsonHeaders,
      body: JSON.stringify({ expectedUpdatedAt }),
    }),
}

export const analysisRunApi = {
  create: (
    workspaceId: string,
    payload: {
      workflowType: WorkflowType
      accountProfileInputAssetId?: string
      manualAccountProfile?: string
      historicalPostsInputAssetId?: string
      commentsInputAssetId?: string
      trendCsvInputAssetId?: string
      videoCreatorSamplesInputAssetId?: string
      xhsCreatorProfileInputAssetId?: string
      mediaAssetIds?: string[]
      mode: 'demo' | 'live'
      idempotencyKey?: string
    },
  ) =>
    request<AnalysisRun>(`/api/workspaces/${workspaceId}/analysis-runs`, {
      method: 'POST',
      headers: jsonHeaders,
      body: JSON.stringify(payload),
    }),

  list: (workspaceId: string) =>
    request<AnalysisRunSummary[]>(
      `/api/workspaces/${workspaceId}/analysis-runs`,
    ),

  get: (runId: string) => request<AnalysisRun>(`/api/analysis-runs/${runId}`),

  updateReview: (
    runId: string,
    payload: {
      userNotes?: string
      reviewStatus?: 'unreviewed' | 'useful' | 'rejected'
      expectedUpdatedAt: string
    },
  ) =>
    request<AnalysisRun>(`/api/analysis-runs/${runId}/review`, {
      method: 'PATCH',
      headers: jsonHeaders,
      body: JSON.stringify(payload),
    }),

  exportCsvUrl: (workspaceId: string, workflowType?: WorkflowType) => {
    const query = workflowType ? `?workflowType=${workflowType}` : ''
    return `/api/workspaces/${workspaceId}/analysis-runs/export.csv${query}`
  },
}

export const simulationRunApi = {
  create: (
    workspaceId: string,
    payload: {
      topicId?: string | null
      draftId?: string | null
      manualTopic?: string
      mode: 'demo' | 'live'
    },
  ) =>
    request<SimulationRun>(`/api/workspaces/${workspaceId}/simulation-runs`, {
      method: 'POST',
      headers: jsonHeaders,
      body: JSON.stringify(payload),
    }),

  list: (workspaceId: string) =>
    request<SimulationRunSummary[]>(
      `/api/workspaces/${workspaceId}/simulation-runs`,
    ),

  get: (simulationId: string) =>
    request<SimulationRun>(`/api/simulation-runs/${simulationId}`),

  updateReview: (
    simulationId: string,
    payload: {
      userNotes?: string
      reviewStatus?: 'unreviewed' | 'useful' | 'rejected'
      expectedUpdatedAt: string
    },
  ) =>
    request<SimulationRun>(`/api/simulation-runs/${simulationId}/review`, {
      method: 'PATCH',
      headers: jsonHeaders,
      body: JSON.stringify(payload),
    }),
}

export const draftApi = {
  list: (workspaceId: string) =>
    request<DraftSummary[]>(`/api/workspaces/${workspaceId}/drafts`),

  get: (draftId: string) => request<Draft>(`/api/drafts/${draftId}`),

  generateBriefFromTopic: (topicId: string, mode: 'demo' | 'live') =>
    request<Draft>(`/api/topics/${topicId}/briefs/generate`, {
      method: 'POST',
      headers: jsonHeaders,
      body: JSON.stringify({ mode }),
    }),

  generateFromTopic: (topicId: string, mode: 'demo' | 'live') =>
    request<Draft>(`/api/topics/${topicId}/drafts/generate`, {
      method: 'POST',
      headers: jsonHeaders,
      body: JSON.stringify({ mode }),
    }),

  generateStructureFromBrief: (draftId: string, mode: 'demo' | 'live') =>
    request<Draft>(`/api/drafts/${draftId}/structure/generate`, {
      method: 'POST',
      headers: jsonHeaders,
      body: JSON.stringify({ mode }),
    }),

  update: (
    draftId: string,
    payload: {
      editableContent: Record<string, unknown>
      expectedUpdatedAt: string
    },
  ) =>
    request<Draft>(`/api/drafts/${draftId}`, {
      method: 'PATCH',
      headers: jsonHeaders,
      body: JSON.stringify(payload),
    }),
}

export const topicApi = {
  list: (
    workspaceId: string,
    filters?: {
      sourceWorkflow?: TopicSourceWorkflow
      status?: TopicStatus
    },
  ) => {
    const query = new URLSearchParams()
    if (filters?.sourceWorkflow) query.set('sourceWorkflow', filters.sourceWorkflow)
    if (filters?.status) query.set('status', filters.status)
    const suffix = query.size ? `?${query.toString()}` : ''
    return request<Topic[]>(`/api/workspaces/${workspaceId}/topics${suffix}`)
  },

  create: (
    workspaceId: string,
    payload: {
      title: string
      angle?: string
      associatedPainPoint?: string
      whyItFits?: string
      sourceAnalysisRunId?: string | null
      sourceWorkflow?: TopicSourceWorkflow
    },
  ) =>
    request<Topic>(`/api/workspaces/${workspaceId}/topics`, {
      method: 'POST',
      headers: jsonHeaders,
      body: JSON.stringify(payload),
    }),

  update: (
    topicId: string,
    payload: {
      title?: string
      angle?: string
      expectedUpdatedAt: string
    },
  ) =>
    request<Topic>(`/api/topics/${topicId}`, {
      method: 'PATCH',
      headers: jsonHeaders,
      body: JSON.stringify(payload),
    }),

  select: (topicId: string) =>
    request<Topic>(`/api/topics/${topicId}/select`, { method: 'POST' }),

  archive: (topicId: string) =>
    request<Topic>(`/api/topics/${topicId}/archive`, { method: 'POST' }),
}
