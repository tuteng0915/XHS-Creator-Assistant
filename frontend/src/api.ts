import type {
  Agent,
  AgentConversation,
  AgentConversationSummary,
  AssetProposal,
  AgentStatus,
  AgentSummary,
  AnalysisRun,
  AnalysisRunSummary,
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
  WorkflowAssetStatus,
  WorkflowAssetSummary,
  WorkflowType,
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

  uploadAccountProfilesCsv: (workspaceId: string, file: File) => {
    const form = new FormData()
    form.set('file', file)
    return request<{ materials: TextInputAsset[] }>(
      `/api/workspaces/${workspaceId}/input-assets/account-profiles-csv`,
      { method: 'POST', body: form },
    )
  },

  uploadTextCsv: (
    workspaceId: string,
    type:
      | 'account_profile'
      | 'historical_posts'
      | 'comments'
      | 'video_creator_samples'
      | 'xhs_creator_profile',
    file: File,
  ) => {
    const form = new FormData()
    form.set('type', type)
    form.set('file', file)
    return request<{ materials: TextInputAsset[] }>(
      `/api/workspaces/${workspaceId}/input-assets/text-csv`,
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

  sendMessage: (
    conversationId: string,
    content: string,
    mode: 'demo' | 'live',
  ) =>
    request<AgentConversation>(
      `/api/agent-conversations/${conversationId}/messages`,
      {
        method: 'POST',
        headers: jsonHeaders,
        body: JSON.stringify({ content, mode }),
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

  createBatch: (
    workspaceId: string,
    payload: {
      workflowType: WorkflowType
      accountProfileInputAssetIds: string[]
      xhsCreatorProfileInputAssetIds?: string[]
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
    request<AnalysisRun[]>(`/api/workspaces/${workspaceId}/analysis-runs/batch`, {
      method: 'POST',
      headers: jsonHeaders,
      body: JSON.stringify(payload),
    }),

  list: (workspaceId: string) =>
    request<AnalysisRunSummary[]>(
      `/api/workspaces/${workspaceId}/analysis-runs`,
    ),

  get: (runId: string) => request<AnalysisRun>(`/api/analysis-runs/${runId}`),

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
}

export const draftApi = {
  list: (workspaceId: string) =>
    request<DraftSummary[]>(`/api/workspaces/${workspaceId}/drafts`),

  get: (draftId: string) => request<Draft>(`/api/drafts/${draftId}`),

  generateFromTopic: (topicId: string, mode: 'demo' | 'live') =>
    request<Draft>(`/api/topics/${topicId}/drafts/generate`, {
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
