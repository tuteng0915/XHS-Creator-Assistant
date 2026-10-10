import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'
import type {
  Agent,
  AgentConversation,
  AgentConversationStatus,
  AgentConversationSummary,
  AgentSummary,
  AnalysisRunSummary,
  AssetProposal,
  Draft,
  DraftSummary,
  SimulationRunSummary,
  Skill,
  SkillSummary,
  InputAsset,
  MediaAsset,
  Topic,
  WorkflowAsset,
  WorkflowAssetSummary,
  Workspace,
} from './types'

const workspaceOne: Workspace = {
  id: 'workspace-1',
  name: '留学账号',
  accountPositioning: '帮助文科生做留学决策。',
  positioningVersion: 1,
  currentTopicId: null,
  createdAt: '2026-07-11T10:00:00Z',
  updatedAt: '2026-07-11T10:00:00Z',
}

const workspaceTwo: Workspace = {
  id: 'workspace-2',
  name: '数字游民账号',
  accountPositioning: '记录真实的数字游民转型路径。',
  positioningVersion: 2,
  currentTopicId: 'topic-2',
  createdAt: '2026-07-11T11:00:00Z',
  updatedAt: '2026-07-11T11:00:00Z',
}

const materials: Record<string, InputAsset[]> = {
  'workspace-1': [
    {
      id: 'history-1',
      workspaceId: 'workspace-1',
      type: 'historical_posts',
      name: '留学帖子数据合集',
      content: '留学中介到底值不值｜赞1.1k｜爆',
      createdAt: '2026-07-11T10:00:00Z',
      updatedAt: '2026-07-11T10:00:00Z',
    },
    {
      id: 'comments-1',
      workspaceId: 'workspace-1',
      type: 'comments',
      name: '留学评论区合集',
      content: '双非背景冲英国前30有戏吗？',
      createdAt: '2026-07-11T10:00:00Z',
      updatedAt: '2026-07-11T10:00:00Z',
    },
  ],
  'workspace-2': [
    {
      id: 'history-2',
      workspaceId: 'workspace-2',
      type: 'historical_posts',
      name: '历史笔记',
      content: '普通小孩不要轻易尝试数字游民｜赞953｜爆',
      createdAt: '2026-07-11T11:00:00Z',
      updatedAt: '2026-07-11T11:00:00Z',
    },
    {
      id: 'comments-2',
      workspaceId: 'workspace-2',
      type: 'comments',
      name: '评论样本',
      content: '文科生能做数字游民吗？',
      createdAt: '2026-07-11T11:00:00Z',
      updatedAt: '2026-07-11T11:00:00Z',
    },
    {
      id: 'trend-2',
      workspaceId: 'workspace-2',
      type: 'trend_csv',
      name: '数字游民热帖',
      keyword: '数字游民',
      originalFilename: '数字游民趋势.csv',
      mediaType: 'text/csv',
      byteSize: 128,
      sha256: 'abc',
      rowCount: 1,
      preview: [{ 标题: '普通人如何开始数字游民', 点赞: '45' }],
      createdAt: '2026-07-11T11:00:00Z',
      updatedAt: '2026-07-11T11:00:00Z',
    },
    {
      id: 'video-samples-2',
      workspaceId: 'workspace-2',
      type: 'video_creator_samples',
      name: '视频创作样本',
      content: '创作者：@AI短剧研究所\n运营备注：剧情内容催更多，商单互动低。',
      createdAt: '2026-07-11T11:00:00Z',
      updatedAt: '2026-07-11T11:00:00Z',
    },
  ],
}

const qsheepXhsCreatorProfileAsset: InputAsset = {
  id: 'xhs-profile-1',
  workspaceId: 'workspace-1',
  type: 'xhs_creator_profile',
  name: 'XHS QSheep 创作者主页',
  content: JSON.stringify({
    schemaVersion: 'xhs-creator-profile/v1',
    creator: { displayName: 'QSheep' },
    notes: [
      {
        noteId: 'n1',
        type: 'video',
        title: '中传大三专业第一，我为什么放弃保研',
        desc: '申请季前梳理自己的履历发现写不下了。',
        metrics: { liked: 1454, collected: 349, comments: 66, shares: 253 },
        comments: [{ content: '太真实了' }],
        cover: { relativePath: 'images/n1/0.jpg' },
      },
      {
        noteId: 'n2',
        type: 'normal',
        title: 'lse 最后一节 gender 课',
        desc: '老师说不要停止想象。',
        metrics: { liked: 536, collected: 165, comments: 22, shares: 86 },
        comments: [],
      },
    ],
  }),
  createdAt: '2026-07-11T10:00:00Z',
  updatedAt: '2026-07-11T10:00:00Z',
}

const analysisRuns: Record<string, AnalysisRunSummary[]> = {
  'workspace-1': [
    {
      id: 'run-1',
      workspaceId: 'workspace-1',
      workflowType: 'account_diagnosis',
      status: 'completed',
      userNotes: '',
      reviewStatus: 'unreviewed',
      createdAt: '2026-07-11T12:00:00Z',
      startedAt: '2026-07-11T12:00:01Z',
      completedAt: '2026-07-11T12:00:03Z',
      updatedAt: '2026-07-11T12:00:03Z',
    },
  ],
  'workspace-2': [],
}

const mediaAssets: Record<string, MediaAsset[]> = {
  'workspace-1': [],
  'workspace-2': [
    {
      id: 'media-image-2',
      workspaceId: 'workspace-2',
      type: 'image',
      name: 'AI短剧主页截图',
      purpose: '视频质量诊断参考',
      sourceType: 'upload',
      originalFilename: 'home.png',
      mediaType: 'image/png',
      byteSize: 128,
      sha256: 'abc',
      metadata: { width: null, height: null },
      derived: {
        visualSummary: '主页强调连续 AI 短剧角色设定。',
        imageUnderstanding: {
          visualSummary: '主页强调连续 AI 短剧角色设定。',
          creatorSignals: ['系列化'],
        },
      },
      userNotes: '',
      fileUrl: '/api/media-assets/media-image-2/file',
      createdAt: '2026-07-11T11:00:00Z',
      updatedAt: '2026-07-11T11:00:00Z',
    },
  ],
}

const simulationRuns: Record<string, SimulationRunSummary[]> = {
  'workspace-1': [],
  'workspace-2': [
    {
      id: 'simulation-2',
      workspaceId: 'workspace-2',
      topicId: 'topic-2',
      draftId: 'draft-2',
      status: 'completed',
      userNotes: '',
      reviewStatus: 'unreviewed',
      createdAt: '2026-07-11T13:00:00Z',
      startedAt: '2026-07-11T13:00:01Z',
      completedAt: '2026-07-11T13:00:04Z',
      updatedAt: '2026-07-11T13:00:04Z',
    },
  ],
}

const drafts: Record<string, DraftSummary[]> = {
  'workspace-1': [],
  'workspace-2': [
    {
      id: 'draft-2',
      workspaceId: 'workspace-2',
      topicId: 'topic-2',
      kind: 'content_structure',
      sourceAnalysisRunId: null,
      sourceWorkflow: 'manual',
      status: 'completed',
      createdAt: '2026-07-11T12:30:00Z',
      completedAt: '2026-07-11T12:30:01Z',
      updatedAt: '2026-07-11T12:30:01Z',
    },
  ],
}

const topics: Record<string, Topic[]> = {
  'workspace-1': [],
  'workspace-2': [
    {
      id: 'topic-2',
      workspaceId: 'workspace-2',
      title: '文科生如何开始数字游民',
      angle: '拆成可执行的六条路径',
      associatedPainPoint: '入门技能不清晰',
      whyItFits: '符合真实记录和入门指南定位',
      generatedSnapshot: {},
      sourceAnalysisRunId: null,
      sourceWorkflow: 'manual',
      status: 'selected',
      createdAt: '2026-07-11T12:00:00Z',
      updatedAt: '2026-07-11T12:00:00Z',
    },
  ],
}

const skillSummary: SkillSummary = {
  id: 'skill-profile',
  workspaceId: 'workspace-1',
  skillId: 'analysis.profile_from_history',
  displayName: 'Analyze Account Profile',
  category: 'analysis',
  purpose: 'Infer creator profile from historical posts.',
  artifactEffect: 'AnalysisRun.stageResults.profile',
  source: 'builtin',
  status: 'enabled',
  version: 'v1',
  updatedAt: '2026-07-11T12:00:00Z',
}

const painPointSkill: SkillSummary = {
  ...skillSummary,
  id: 'skill-pain-points',
  skillId: 'analysis.pain_points_from_comments',
  displayName: 'Analyze Comment Pain Points',
}

const accountTopicSkill: SkillSummary = {
  ...skillSummary,
  id: 'skill-account-topics',
  skillId: 'topic.generate_from_account_diagnosis',
  displayName: 'Generate Account Topics',
  category: 'topic',
}

const commentsFormatterSkill: SkillSummary = {
  ...skillSummary,
  id: 'skill-format-comments',
  skillId: 'input_asset.format_comments',
  displayName: 'Format Comment Samples',
  category: 'input_asset',
  purpose: 'Format pasted comments into an editable draft.',
  artifactEffect: 'Draft InputAsset.comments',
}

const creativeBriefSkill: SkillSummary = {
  ...skillSummary,
  id: 'skill-creative-brief',
  skillId: 'topic.refine_to_brief',
  displayName: 'Generate Creative Brief',
  category: 'creative_output',
  purpose: 'Turn a selected Topic into a persistent creative brief.',
  artifactEffect: 'Draft(kind=content_brief)',
}

const topicSaveSkill: SkillSummary = {
  ...skillSummary,
  id: 'skill-topic-save',
  skillId: 'topic.save_candidate',
  displayName: 'Save Topic Candidate',
  category: 'topic',
  artifactEffect: 'Topic',
}

const draftStructureSkill: SkillSummary = {
  ...skillSummary,
  id: 'skill-draft-structure',
  skillId: 'draft.generate_structure_from_brief',
  displayName: 'Generate Content Structure from Brief',
  category: 'creative_output',
  artifactEffect: 'Draft(kind=content_structure)',
}

const draftEditSkill: SkillSummary = {
  ...skillSummary,
  id: 'skill-draft-edit',
  skillId: 'draft.edit',
  displayName: 'Edit Draft',
  category: 'creative_output',
  artifactEffect: 'Draft.editableContent',
}

const videoQualitySkill: SkillSummary = {
  ...skillSummary,
  id: 'skill-video-quality',
  skillId: 'analysis.video_quality',
  displayName: 'Analyze AIGC Video Quality',
  category: 'analysis',
  purpose: 'Score AIGC video quality with PM rubric.',
  artifactEffect: 'AnalysisRun.stageResults.video_quality',
}

const skills: Record<string, SkillSummary[]> = {
  'workspace-1': [
    skillSummary,
    painPointSkill,
    accountTopicSkill,
    videoQualitySkill,
    commentsFormatterSkill,
    creativeBriefSkill,
    topicSaveSkill,
    draftStructureSkill,
    draftEditSkill,
  ],
  'workspace-2': [
    {
      ...skillSummary,
      id: 'skill-trend',
      workspaceId: 'workspace-2',
      skillId: 'analysis.trend_patterns',
      displayName: 'Analyze Trend Patterns',
    },
  ],
}

const skillDetail: Skill = {
  ...skillSummary,
  triggerIntents: ['ACCOUNT_DIAGNOSIS'],
  requiredInputs: ['positioning_snapshot', 'historical_posts_material_id'],
  optionalInputs: [],
  contextPolicy: { allowed_fields: ['positioning', 'historicalPosts'] },
  outputSchema: { root: 'profile' },
  sideEffects: ['writes stage result'],
  failureMode: 'partial_allowed',
  composableWith: ['topic.generate_from_account_diagnosis'],
  implementationRefs: ['ModelOperation.PROFILE'],
  userNotes: '',
}

const creativeBriefSkillDetail: Skill = {
  ...skillDetail,
  ...creativeBriefSkill,
  triggerIntents: ['TOPIC_REFINEMENT'],
  requiredInputs: ['topic_id', 'positioning_snapshot'],
  optionalInputs: ['compact_analysis_context'],
  contextPolicy: { allowed_fields: ['positioning', 'topic', 'background'] },
  outputSchema: { root: 'brief' },
  sideEffects: ['creates creative brief artifact'],
  failureMode: 'atomic',
  composableWith: ['draft.generate_structure_from_brief'],
  implementationRefs: ['ModelOperation.CONTENT_BRIEF'],
}

const commentsFormatterSkillDetail: Skill = {
  ...skillDetail,
  ...commentsFormatterSkill,
  triggerIntents: ['FORMAT_INPUT_ASSET'],
  requiredInputs: ['rawText', 'targetAssetType'],
  optionalInputs: [],
  contextPolicy: { allowed_fields: ['rawText'] },
  outputSchema: { root: 'FormattedInputAssetDraft' },
  sideEffects: ['returns draft only'],
  failureMode: 'draft_only',
  composableWith: ['source.save_comments'],
  implementationRefs: ['InputAssetFormatterAgent'],
}

const videoQualitySkillDetail: Skill = {
  ...skillDetail,
  ...videoQualitySkill,
  triggerIntents: ['VIDEO_CREATOR_QUALITY'],
  requiredInputs: [
    'positioning_snapshot',
    'video_creator_evidence_pack',
    'creatorProfile',
  ],
  optionalInputs: ['media_asset_ids'],
  contextPolicy: {
    allowed_fields: ['positioning', 'videoCreatorEvidencePack', 'creatorProfile'],
    pmRubric: {
      creatorTypes: [
        {
          type: '剧本驱动型',
          fitForIncentive: '高',
          rule: '连续剧情内容，评论催更。',
        },
      ],
      qualityDimensions: [
        {
          dimension: '叙事完整度',
          high: '冲突明确，有结尾钩子。',
          medium: '有主题但结构松散。',
          low: '只有概念展示。',
          evidenceRequired: '标题、正文、评论或视频理解。',
        },
      ],
      evidenceRules: ['没有视频理解时不得声称看过镜头。'],
      incentiveRules: [
        {
          signal: '剧本驱动 + 系列化潜力高',
          interpretation: '适合连续更新激励。',
          operatorAction: '给 4 周连续更新任务。',
        },
      ],
    },
  },
  outputSchema: { root: 'videoQuality' },
  sideEffects: ['writes stage result'],
  failureMode: 'partial_allowed',
  composableWith: ['analysis.incentive_fit'],
  implementationRefs: ['ModelOperation.VIDEO_QUALITY_ANALYSIS'],
}

const skillDetails: Record<string, Skill> = {
  'skill-profile': skillDetail,
  'skill-creative-brief': creativeBriefSkillDetail,
  'skill-format-comments': commentsFormatterSkillDetail,
  'skill-video-quality': videoQualitySkillDetail,
}

const agentSummary: AgentSummary = {
  id: 'agent-account',
  workspaceId: 'workspace-1',
  agentId: 'account_diagnosis_strategist',
  displayName: 'Account Diagnosis Strategist',
  purpose: 'Diagnoses account profile and turns findings into topics.',
  skillIds: [
    'analysis.profile_from_history',
    'analysis.pain_points_from_comments',
    'topic.generate_from_account_diagnosis',
  ],
  source: 'builtin',
  status: 'enabled',
  version: 'v1',
  updatedAt: '2026-07-11T12:00:00Z',
}

const creativeOutputAgentSummary: AgentSummary = {
  ...agentSummary,
  id: 'agent-creative-output',
  agentId: 'topic_draft_editor',
  displayName: 'Topic and Creative Output Editor',
  purpose: 'Turns selected topics into creative briefs and content structures.',
  skillIds: [
    'topic.refine_to_brief',
    'draft.generate_structure_from_brief',
    'draft.edit',
  ],
}

const agents: Record<string, AgentSummary[]> = {
  'workspace-1': [agentSummary, creativeOutputAgentSummary],
  'workspace-2': [
    {
      ...agentSummary,
      id: 'agent-trend',
      workspaceId: 'workspace-2',
      agentId: 'trend_opportunity_strategist',
      displayName: 'Trend Opportunity Strategist',
      skillIds: [
        'analysis.trend_patterns',
        'analysis.pain_points_from_trend_posts',
        'topic.generate_from_trend_analysis',
      ],
    },
  ],
}

const agentConversations: Record<string, AgentConversationSummary[]> = {
  'workspace-1': [],
  'workspace-2': [],
}

const assetProposals: Record<string, AssetProposal[]> = {
  'conversation-1': [],
}

const agentDetail: Agent = {
  ...agentSummary,
  systemPrompt:
    'You are a creator account strategist. Use only selected input assets.',
  defaultContextPolicy: {
    may_read: ['positioning snapshot', 'selected historical posts'],
    must_not_read: ['full workspace'],
  },
  userNotes: '',
}

const creativeOutputAgentDetail: Agent = {
  ...agentDetail,
  ...creativeOutputAgentSummary,
  systemPrompt:
    'You are a creator content editor. Use creative briefs before structure generation.',
  defaultContextPolicy: {
    may_read: ['selected topic', 'selected creative brief'],
    must_not_read: ['raw input assets unless explicitly provided'],
  },
}

const workflowSummary: WorkflowAssetSummary = {
  id: 'workflow-account',
  workspaceId: 'workspace-1',
  workflowId: 'account_diagnosis',
  displayName: 'Account Diagnosis Workflow',
  purpose: 'Diagnose profile and generate topic candidates.',
  entryAgentIds: ['creator_material_curator', 'account_diagnosis_strategist'],
  artifactEffect: 'AnalysisRun + Topic candidates',
  source: 'builtin',
  status: 'enabled',
  version: 'v1',
  callBinding: 'account',
  updatedAt: '2026-07-11T12:00:00Z',
}

const creativeOutputWorkflowSummary: WorkflowAssetSummary = {
  ...workflowSummary,
  id: 'workflow-creative-output',
  workflowId: 'topic_to_draft',
  displayName: 'Topic to Creative Output Workflow',
  purpose: 'Generate a creative brief, then generate a content structure.',
  entryAgentIds: ['topic_draft_editor'],
  artifactEffect: 'Topic + Draft(kind=content_brief) + Draft(kind=content_structure)',
  callBinding: '',
}

const trendWorkflowSummary: WorkflowAssetSummary = {
  ...workflowSummary,
  id: 'workflow-trend',
  workflowId: 'trend_analysis',
  displayName: 'Trend Analysis Workflow',
  purpose: 'Analyze uploaded trend data.',
  entryAgentIds: ['creator_material_curator', 'trend_opportunity_strategist'],
  callBinding: 'trend',
}

const videoWorkflowSummary: WorkflowAssetSummary = {
  ...workflowSummary,
  id: 'workflow-video',
  workflowId: 'video_creator_quality',
  displayName: 'Video Creator Quality Workflow',
  purpose: 'Diagnose AIGC video creator quality.',
  entryAgentIds: ['creator_material_curator', 'video_creator_quality_analyst'],
  callBinding: 'video',
}

const workflowAssets: Record<string, WorkflowAssetSummary[]> = {
  'workspace-1': [
    workflowSummary,
    trendWorkflowSummary,
    videoWorkflowSummary,
    creativeOutputWorkflowSummary,
  ],
  'workspace-2': [
    {
      ...trendWorkflowSummary,
      workspaceId: 'workspace-2',
    },
  ],
}

const workflowDetail: WorkflowAsset = {
  ...workflowSummary,
  agentPlan: {
    tasks: [
      {
        taskId: 'diagnose_account',
        agentId: 'account_diagnosis_strategist',
        skillIds: [
          'analysis.profile_from_history',
          'analysis.pain_points_from_comments',
        ],
        parallel: true,
      },
    ],
  },
  userNotes: '',
}

const creativeOutputWorkflowDetail: WorkflowAsset = {
  ...workflowDetail,
  ...creativeOutputWorkflowSummary,
  agentPlan: {
    tasks: [
      {
        taskId: 'select_topic',
        agentId: 'topic_draft_editor',
        skillIds: ['topic.save_candidate'],
        dependsOn: [],
      },
      {
        taskId: 'generate_brief',
        agentId: 'topic_draft_editor',
        skillIds: ['topic.refine_to_brief'],
        dependsOn: ['select_topic'],
      },
      {
        taskId: 'generate_structure',
        agentId: 'topic_draft_editor',
        skillIds: ['draft.generate_structure_from_brief'],
        dependsOn: ['generate_brief'],
      },
    ],
  },
}

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
}

function installWorkspaceApiMock(defaultWorkspaceId: 'workspace-1' | 'workspace-2' = 'workspace-1') {
  return vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const url = String(input)
    const method = init?.method || 'GET'
    if (url === '/api/workspaces' && method === 'GET') {
      return jsonResponse(
        defaultWorkspaceId === 'workspace-1'
          ? [workspaceOne, workspaceTwo]
          : [workspaceTwo, workspaceOne],
      )
    }
    if (url === '/api/workspaces' && method === 'POST') {
      const body = JSON.parse(String(init?.body)) as {
        name: string
        accountPositioning: string
      }
      return jsonResponse(
        {
          id: 'workspace-default',
          name: body.name,
          accountPositioning: body.accountPositioning,
          positioningVersion: 1,
          currentTopicId: null,
          createdAt: '2026-07-11T09:00:00Z',
          updatedAt: '2026-07-11T09:00:00Z',
        },
        201,
      )
    }
    const workspaceMatch = url.match(/^\/api\/workspaces\/(workspace-[12])$/)
    if (workspaceMatch && method === 'GET') {
      return jsonResponse(
        workspaceMatch[1] === 'workspace-1' ? workspaceOne : workspaceTwo,
      )
    }
    const materialsMatch = url.match(
      /^\/api\/workspaces\/(workspace-[12])\/input-assets$/,
    )
    if (materialsMatch && method === 'GET') {
      return jsonResponse(materials[materialsMatch[1]])
    }
    const mediaAssetsMatch = url.match(
      /^\/api\/workspaces\/(workspace-[12])\/media-assets$/,
    )
    if (mediaAssetsMatch && method === 'GET') {
      return jsonResponse(mediaAssets[mediaAssetsMatch[1]])
    }
    if (materialsMatch && method === 'POST') {
      const body = JSON.parse(String(init?.body)) as {
        type: InputAsset['type']
        name: string
        content: string
      }
      return jsonResponse(
        {
          id: `new-${body.type}`,
          workspaceId: materialsMatch[1],
          type: body.type,
          name: body.name,
          content: body.content,
          createdAt: '2026-07-11T15:00:00Z',
          updatedAt: '2026-07-11T15:00:00Z',
        },
        201,
      )
    }
    const inputAssetMatch = url.match(/^\/api\/input-assets\/(.+)$/)
    if (inputAssetMatch && method === 'PATCH') {
      const body = JSON.parse(String(init?.body)) as {
        content?: string
        keyword?: string
      }
      const asset = Object.values(materials)
        .flat()
        .find((item) => item.id === inputAssetMatch[1])
      if (!asset) throw new Error(`Unknown input asset ${inputAssetMatch[1]}`)
      const updated = {
        ...asset,
        ...('content' in asset && body.content !== undefined
          ? { content: body.content }
          : {}),
        ...('keyword' in asset && body.keyword !== undefined
          ? { keyword: body.keyword }
          : {}),
        updatedAt: '2026-07-11T15:00:00Z',
      }
      return jsonResponse(updated)
    }
    const runsMatch = url.match(
      /^\/api\/workspaces\/(workspace-[12])\/analysis-runs$/,
    )
    if (runsMatch && method === 'GET') {
      return jsonResponse(analysisRuns[runsMatch[1]])
    }
    const simulationRunsMatch = url.match(
      /^\/api\/workspaces\/(workspace-[12])\/simulation-runs$/,
    )
    if (simulationRunsMatch && method === 'GET') {
      return jsonResponse(simulationRuns[simulationRunsMatch[1]])
    }
    const skillsMatch = url.match(/^\/api\/workspaces\/(workspace-[12])\/skills$/)
    if (skillsMatch && method === 'GET') {
      return jsonResponse(skills[skillsMatch[1]])
    }
    if (url === '/api/skills/skill-profile' && method === 'GET') {
      return jsonResponse(skillDetails['skill-profile'])
    }
    if (url === '/api/skills/skill-creative-brief' && method === 'GET') {
      return jsonResponse(skillDetails['skill-creative-brief'])
    }
    if (url === '/api/skills/skill-format-comments' && method === 'GET') {
      return jsonResponse(skillDetails['skill-format-comments'])
    }
    if (url === '/api/skills/skill-video-quality' && method === 'GET') {
      return jsonResponse(skillDetails['skill-video-quality'])
    }
    const skillDefinitionMatch = url.match(/^\/api\/skills\/([^/]+)\/definition$/)
    if (skillDefinitionMatch && method === 'PATCH') {
      const skillAssetId = skillDefinitionMatch[1]
      const body = JSON.parse(String(init?.body)) as {
        displayName: string
        category: string
        purpose: string
        artifactEffect: string
        failureMode: string
        version: string
        triggerIntents: string[]
        requiredInputs: string[]
        optionalInputs: string[]
        contextPolicy: Record<string, unknown>
        outputSchema: Record<string, unknown>
        sideEffects: string[]
        composableWith: string[]
        implementationRefs: string[]
        userNotes: string
        expectedUpdatedAt: string
      }
      const current = skillDetails[skillAssetId]
      if (body.expectedUpdatedAt !== current.updatedAt) {
        return jsonResponse({ detail: 'Skill changed since it was loaded' }, 409)
      }
      const updated: Skill = {
        ...current,
        displayName: body.displayName,
        category: body.category,
        purpose: body.purpose,
        artifactEffect: body.artifactEffect,
        failureMode: body.failureMode,
        version: body.version,
        triggerIntents: body.triggerIntents,
        requiredInputs: body.requiredInputs,
        optionalInputs: body.optionalInputs,
        contextPolicy: body.contextPolicy,
        outputSchema: body.outputSchema,
        sideEffects: body.sideEffects,
        composableWith: body.composableWith,
        implementationRefs: body.implementationRefs,
        userNotes: body.userNotes,
        source: 'generated',
        updatedAt: '2026-07-11T14:40:00Z',
      }
      skillDetails[skillAssetId] = updated
      skills['workspace-1'] = skills['workspace-1'].map((item) =>
        item.id === updated.id ? updated : item,
      )
      return jsonResponse(updated)
    }
    const skillDiffMatch = url.match(/^\/api\/skills\/([^/]+)\/definition-diff$/)
    if (skillDiffMatch && method === 'GET') {
      const skillAssetId = skillDiffMatch[1]
      const current = skillDetails[skillAssetId]
      const builtin = skillAssetId === 'skill-profile' ? skillDetail : current
      return jsonResponse({
        assetId: skillAssetId,
        assetType: 'skill',
        stableId: current.skillId,
        source: current.source,
        canRevert: current.source === 'generated',
        changedFields: ['displayName', 'version'].filter((field) => {
          if (field === 'displayName') return current.displayName !== builtin.displayName
          if (field === 'version') return current.version !== builtin.version
          return false
        }),
        currentDefinition: {
          displayName: current.displayName,
          purpose: current.purpose,
          version: current.version,
        },
        builtinDefinition: {
          displayName: builtin.displayName,
          purpose: builtin.purpose,
          version: builtin.version,
        },
      })
    }
    const skillRevertMatch = url.match(/^\/api\/skills\/([^/]+)\/revert-definition$/)
    if (skillRevertMatch && method === 'POST') {
      const skillAssetId = skillRevertMatch[1]
      const current = skillDetails[skillAssetId]
      const body = JSON.parse(String(init?.body)) as { expectedUpdatedAt: string }
      if (body.expectedUpdatedAt !== current.updatedAt) {
        return jsonResponse({ detail: 'Skill changed since it was loaded' }, 409)
      }
      const builtin = skillAssetId === 'skill-profile' ? skillDetail : current
      const updated: Skill = {
        ...current,
        ...builtin,
        source: 'builtin',
        userNotes: current.userNotes,
        updatedAt: '2026-07-11T14:55:00Z',
      }
      skillDetails[skillAssetId] = updated
      skills['workspace-1'] = skills['workspace-1'].map((item) =>
        item.id === updated.id ? updated : item,
      )
      return jsonResponse(updated)
    }
    if (url === '/api/skills/skill-format-comments/invoke' && method === 'POST') {
      return jsonResponse({
        skillAssetId: 'skill-format-comments',
        skillId: 'input_asset.format_comments',
        status: 'completed',
        output: {
          assetType: 'comments',
          name: '整理后的评论样本合集',
          content: '太焦虑了，不知道怎么选校\n求时间线',
          notes: '已整理为一行一条评论样本。',
        },
        modelMetadata: {
          provider: 'code',
          operation: 'skill.invoke',
        },
      })
    }
    if (url === '/api/skills/skill-profile/dry-run' && method === 'POST') {
      return jsonResponse({
        skillAssetId: 'skill-profile',
        skillId: 'analysis.profile_from_history',
        status: 'completed',
        output: {
          profile: {
            pillars: ['定位表达'],
          },
        },
        modelMetadata: {
          provider: 'deterministic',
          operation: 'skill.dry_run',
        },
      })
    }
    const agentsMatch = url.match(/^\/api\/workspaces\/(workspace-[12])\/agents$/)
    if (agentsMatch && method === 'GET') {
      return jsonResponse(agents[agentsMatch[1]])
    }
    const agentConversationsMatch = url.match(
      /^\/api\/workspaces\/(workspace-[12])\/agent-conversations$/,
    )
    if (agentConversationsMatch && method === 'GET') {
      return jsonResponse(agentConversations[agentConversationsMatch[1]])
    }
    if (agentConversationsMatch && method === 'POST') {
      const body = JSON.parse(String(init?.body)) as {
        agentAssetId: string
        title?: string
        contextTarget?: Record<string, unknown>
      }
      const conversation: AgentConversation = {
        id: 'conversation-1',
        workspaceId: agentConversationsMatch[1],
        agentAssetId: body.agentAssetId,
        title: body.title || '与 Agent 对话',
        status: 'active',
        contextTarget: body.contextTarget || {},
        createdAt: '2026-07-11T14:00:00Z',
        updatedAt: '2026-07-11T14:00:00Z',
        messages: [],
      }
      agentConversations[agentConversationsMatch[1]] = [conversation]
      return jsonResponse(conversation, 201)
    }
    if (url === '/api/agent-conversations/conversation-1' && method === 'GET') {
      const conversation = agentConversations['workspace-1'][0]
      return jsonResponse({
        ...conversation,
        messages: 'messages' in conversation ? conversation.messages : [],
      })
    }
    if (url === '/api/agent-conversations/conversation-1' && method === 'PATCH') {
      const body = JSON.parse(String(init?.body)) as {
        title?: string
        status?: AgentConversationStatus
        expectedUpdatedAt: string
      }
      const current = agentConversations['workspace-1'][0]
      if (body.expectedUpdatedAt !== current.updatedAt) {
        return jsonResponse(
          { detail: 'Agent conversation changed since it was loaded' },
          409,
        )
      }
      const updated: AgentConversation = {
        ...current,
        title: body.title || current.title,
        status: body.status || current.status,
        updatedAt: '2026-07-11T14:08:00Z',
        messages: 'messages' in current ? current.messages : [],
      } as AgentConversation
      agentConversations['workspace-1'] = [updated]
      return jsonResponse(updated)
    }
    if (
      url === '/api/agent-conversations/conversation-1/messages' &&
      method === 'POST'
    ) {
      const body = JSON.parse(String(init?.body)) as {
        content: string
        mode: 'demo' | 'live'
        clientMessageKey?: string
      }
      const conversation = agentConversations['workspace-1'][0]
      const messages: AgentConversation['messages'] = [
        {
          id: 'message-user',
          conversationId: 'conversation-1',
          clientMessageKey: body.clientMessageKey || null,
          role: 'user',
          content: body.content,
          contextPack: {},
          assetRefs: [],
          proposedActions: [],
          modelMetadata: {},
          createdAt: '2026-07-11T14:00:01Z',
        },
        {
          id: 'message-agent',
          conversationId: 'conversation-1',
          role: 'assistant',
          content:
            '我是 Account Diagnosis Strategist。我已读取当前 workspace 的 broad context pack。',
          contextPack: { mode: 'workspace_pack', scope: 'broad' },
          assetRefs: [{ assetType: 'account_profile', assetId: 'workspace-1' }],
          proposedActions: [
            {
              type: 'workspace.update_profile',
              status: 'requires_confirmation',
            },
          ],
          modelMetadata: {
            provider: body.mode === 'live' ? 'anthropic' : 'fake',
            operation: 'agent_chat',
          },
          createdAt: '2026-07-11T14:00:02Z',
        },
      ]
      const baseProposal = {
        id: 'proposal-1',
        workspaceId: 'workspace-1',
        conversationId: 'conversation-1',
        messageId: 'message-agent',
        status: 'pending' as const,
        result: {},
        error: '',
        createdAt: '2026-07-11T14:00:02Z',
        updatedAt: '2026-07-11T14:00:02Z',
        appliedAt: null,
      }
      const nextProposal: AssetProposal = body.content.includes('workflow proposal')
        ? {
            ...baseProposal,
            actionType: 'workflow.propose_definition',
            title: '新增 Workflow Proposal',
            description: '建议新增工作流。',
            proposedAction: {
              type: 'workflow.propose_definition',
              status: 'requires_confirmation',
              description: '建议新增工作流。',
              payload: {
                definition: {
                  workflowId: 'generated.creator_review_workflow',
                  displayName: 'Creator Review Workflow',
                  purpose: 'Review creator assets.',
                  entryAgentIds: ['creator_material_curator'],
                  agentPlan: {
                    tasks: [
                      {
                        taskId: 'review_creator',
                        agentId: 'creator_material_curator',
                        skillIds: ['input_asset.format_account_profile'],
                        dependsOn: [],
                        parallel: false,
                      },
                    ],
                  },
                  artifactEffect: 'AssetProposal',
                  callBinding: '',
                  version: 'v1',
                },
              },
            },
          }
        : body.content.includes('agent proposal')
          ? {
              ...baseProposal,
              actionType: 'agent.propose_definition',
              title: '新增 Agent Proposal',
              description: '建议新增 Agent。',
              proposedAction: {
                type: 'agent.propose_definition',
                status: 'requires_confirmation',
                description: '建议新增 Agent。',
                payload: {
                  definition: {
                    agentId: 'generated.creator_reviewer',
                    displayName: 'Creator Reviewer',
                    purpose: 'Review creator assets.',
                    systemPrompt: 'Review creator assets with evidence.',
                    skillIds: ['input_asset.format_account_profile'],
                    defaultContextPolicy: {},
                    version: 'v1',
                  },
                },
              },
            }
          : {
              ...baseProposal,
              actionType: 'workspace.update_profile',
              title: '更新 Account Profile',
              description: '建议更新账号定位。',
              proposedAction: {
                type: 'workspace.update_profile',
                status: 'requires_confirmation',
                description: '建议更新账号定位。',
                payload: { accountPositioning: body.content },
              },
            }
      assetProposals['conversation-1'] = [nextProposal]
      const updatedConversation: AgentConversation = {
        ...conversation,
        messages,
      }
      agentConversations['workspace-1'] = [updatedConversation]
      return jsonResponse(updatedConversation)
    }
    if (
      url === '/api/agent-conversations/conversation-1/asset-proposals' &&
      method === 'GET'
    ) {
      return jsonResponse(assetProposals['conversation-1'])
    }
    if (url === '/api/asset-proposals/proposal-1' && method === 'PATCH') {
      const body = JSON.parse(String(init?.body)) as {
        title?: string
        description?: string
        proposedAction?: Record<string, unknown>
      }
      const current = assetProposals['conversation-1'][0]
      const updated: AssetProposal = {
        ...current,
        title: body.title || current.title,
        description:
          body.description === undefined ? current.description : body.description,
        proposedAction: body.proposedAction || current.proposedAction,
        updatedAt: '2026-07-11T14:05:00Z',
      }
      assetProposals['conversation-1'] = [updated]
      return jsonResponse(updated)
    }
    if (url === '/api/asset-proposals/proposal-1/preview' && method === 'GET') {
      const current = assetProposals['conversation-1'][0]
      const payload = current.proposedAction.payload as Record<string, unknown>
      const definition = (payload.definition || payload) as Record<string, unknown>
      if (current.actionType === 'agent.propose_definition') {
        return jsonResponse({
          proposalId: 'proposal-1',
          actionType: current.actionType,
          operation: 'create',
          targetAssetType: 'agent',
          targetAssetId: null,
          targetStableId: definition.agentId,
          changedFields: [
            { field: 'displayName', current: undefined, proposed: definition.displayName },
            { field: 'skillIds', current: undefined, proposed: definition.skillIds },
          ],
          currentSnapshot: {},
          proposedSnapshot: definition,
          validationErrors: [],
        })
      }
      if (current.actionType === 'workflow.propose_definition') {
        return jsonResponse({
          proposalId: 'proposal-1',
          actionType: current.actionType,
          operation: 'create',
          targetAssetType: 'workflow',
          targetAssetId: null,
          targetStableId: definition.workflowId,
          changedFields: [
            { field: 'displayName', current: undefined, proposed: definition.displayName },
            { field: 'agentPlan', current: undefined, proposed: definition.agentPlan },
          ],
          currentSnapshot: {},
          proposedSnapshot: definition,
          validationErrors: [],
        })
      }
      return jsonResponse({
        proposalId: 'proposal-1',
        actionType: current.actionType,
        operation: 'update',
        targetAssetType: 'account_profile',
        targetAssetId: 'workspace-1',
        targetStableId: 'workspace-1',
        changedFields: [
          {
            field: 'accountPositioning',
            current: workspaceOne.accountPositioning,
            proposed: payload.accountPositioning || '',
          },
        ],
        currentSnapshot: {
          name: workspaceOne.name,
          accountPositioning: workspaceOne.accountPositioning,
        },
        proposedSnapshot: {
          name: workspaceOne.name,
          accountPositioning: payload.accountPositioning || '',
        },
        validationErrors: [],
      })
    }
    if (url === '/api/asset-proposals/proposal-1/apply' && method === 'POST') {
      const current = assetProposals['conversation-1'][0]
      const updated: AssetProposal = {
        ...current,
        status: 'applied',
        result: { assetType: 'account_profile', assetId: 'workspace-1' },
        updatedAt: '2026-07-11T14:06:00Z',
        appliedAt: '2026-07-11T14:06:00Z',
      }
      assetProposals['conversation-1'] = [updated]
      return jsonResponse(updated)
    }
    if (url === '/api/asset-proposals/proposal-1/reject' && method === 'POST') {
      const current = assetProposals['conversation-1'][0]
      const updated: AssetProposal = {
        ...current,
        status: 'rejected',
        updatedAt: '2026-07-11T14:06:00Z',
      }
      assetProposals['conversation-1'] = [updated]
      return jsonResponse(updated)
    }
    if (url === '/api/agents/agent-account' && method === 'GET') {
      return jsonResponse(agentDetail)
    }
    if (url === '/api/agents/agent-creative-output' && method === 'GET') {
      return jsonResponse(creativeOutputAgentDetail)
    }
    const agentDefinitionMatch = url.match(/^\/api\/agents\/([^/]+)\/definition$/)
    if (agentDefinitionMatch && method === 'PATCH') {
      const agentAssetId = agentDefinitionMatch[1]
      const current =
        agentAssetId === 'agent-creative-output'
          ? creativeOutputAgentDetail
          : agentDetail
      const body = JSON.parse(String(init?.body)) as {
        displayName: string
        purpose: string
        systemPrompt: string
        skillIds: string[]
        defaultContextPolicy: Record<string, unknown>
        version: string
        userNotes: string
        expectedUpdatedAt: string
      }
      if (body.expectedUpdatedAt !== current.updatedAt) {
        return jsonResponse({ detail: 'Agent changed since it was loaded' }, 409)
      }
      const updated: Agent = {
        ...current,
        displayName: body.displayName,
        purpose: body.purpose,
        systemPrompt: body.systemPrompt,
        skillIds: body.skillIds,
        defaultContextPolicy: body.defaultContextPolicy,
        version: body.version,
        userNotes: body.userNotes,
        source: 'generated',
        updatedAt: '2026-07-11T14:45:00Z',
      }
      agents['workspace-1'] = agents['workspace-1'].map((item) =>
        item.id === updated.id ? updated : item,
      )
      return jsonResponse(updated)
    }
    const workflowsMatch = url.match(
      /^\/api\/workspaces\/(workspace-[12])\/workflows$/,
    )
    if (workflowsMatch && method === 'GET') {
      return jsonResponse(workflowAssets[workflowsMatch[1]])
    }
    if (url === '/api/workflows/workflow-account' && method === 'GET') {
      return jsonResponse(workflowDetail)
    }
    if (url === '/api/workflows/workflow-creative-output' && method === 'GET') {
      const currentSummary =
        workflowAssets['workspace-1'].find((item) => item.id === 'workflow-creative-output') ||
        creativeOutputWorkflowSummary
      return jsonResponse({
        ...creativeOutputWorkflowDetail,
        ...currentSummary,
      })
    }
    const workflowDefinitionMatch = url.match(/^\/api\/workflows\/([^/]+)\/definition$/)
    if (workflowDefinitionMatch && method === 'PATCH') {
      const workflowAssetId = workflowDefinitionMatch[1]
      const current =
        workflowAssetId === 'workflow-creative-output'
          ? creativeOutputWorkflowDetail
          : workflowDetail
      const body = JSON.parse(String(init?.body)) as {
        displayName: string
        purpose: string
        entryAgentIds: string[]
        agentPlan: Record<string, unknown>
        artifactEffect: string
        callBinding: WorkflowAsset['callBinding']
        version: string
        userNotes: string
        expectedUpdatedAt: string
      }
      if (body.expectedUpdatedAt !== current.updatedAt) {
        return jsonResponse({ detail: 'Workflow changed since it was loaded' }, 409)
      }
      const updated: WorkflowAsset = {
        ...current,
        displayName: body.displayName,
        purpose: body.purpose,
        entryAgentIds: body.entryAgentIds,
        agentPlan: body.agentPlan,
        artifactEffect: body.artifactEffect,
        callBinding: body.callBinding,
        version: body.version,
        userNotes: body.userNotes,
        source: 'generated',
        updatedAt: '2026-07-11T14:50:00Z',
      }
      workflowAssets['workspace-1'] = workflowAssets['workspace-1'].map((item) =>
        item.id === updated.id ? updated : item,
      )
      return jsonResponse(updated)
    }
    if (
      url === '/api/workflows/workflow-creative-output/call-binding' &&
      method === 'PATCH'
    ) {
      const body = JSON.parse(String(init?.body)) as {
        callBinding: WorkflowAsset['callBinding']
        expectedUpdatedAt: string
      }
      const current =
        workflowAssets['workspace-1'].find((item) => item.id === 'workflow-creative-output') ||
        creativeOutputWorkflowSummary
      if (body.expectedUpdatedAt !== current.updatedAt) {
        return jsonResponse({ detail: 'Workflow changed since it was loaded' }, 409)
      }
      const updated: WorkflowAssetSummary = {
        ...current,
        callBinding: body.callBinding,
        updatedAt: '2026-07-11T14:30:00Z',
      }
      workflowAssets['workspace-1'] = workflowAssets['workspace-1'].map((item) =>
        item.id === updated.id ? updated : item,
      )
      return jsonResponse({
        ...creativeOutputWorkflowDetail,
        ...updated,
      })
    }
    const draftsMatch = url.match(/^\/api\/workspaces\/(workspace-[12])\/drafts$/)
    if (draftsMatch && method === 'GET') {
      return jsonResponse(drafts[draftsMatch[1]])
    }
    if (url === '/api/analysis-runs/run-1' && method === 'GET') {
      return jsonResponse({
        ...analysisRuns['workspace-1'][0],
        inputSnapshot: { accountPositioning: '帮助文科生做留学决策。' },
        stageResults: {
          topics: {
            topics: [
              {
                title: '中介费到底该花在哪三步',
                angle: '按环节配置预算',
                pain: 'DIY vs 中介',
                whyFit: '延续避坑拆解风格',
              },
            ],
          },
        },
        stageErrors: {},
        modelMetadata: { mode: 'demo' },
      })
    }
    if (url === '/api/analysis-runs/run-1/review' && method === 'PATCH') {
      const body = JSON.parse(String(init?.body)) as {
        userNotes: string
        reviewStatus: 'unreviewed' | 'useful' | 'rejected'
        expectedUpdatedAt: string
      }
      expect(body.expectedUpdatedAt).toBe(analysisRuns['workspace-1'][0].updatedAt)
      const updated = {
        ...analysisRuns['workspace-1'][0],
        userNotes: body.userNotes,
        reviewStatus: body.reviewStatus,
        updatedAt: '2026-07-11T12:30:00Z',
      }
      analysisRuns['workspace-1'] = [updated]
      return jsonResponse({
        ...updated,
        inputSnapshot: { accountPositioning: '帮助文科生做留学决策。' },
        stageResults: {
          topics: {
            topics: [
              {
                title: '中介费到底该花在哪三步',
                angle: '按环节配置预算',
                pain: 'DIY vs 中介',
                whyFit: '延续避坑拆解风格',
              },
            ],
          },
        },
        stageErrors: {},
        modelMetadata: { mode: 'demo' },
      })
    }
    if (url === '/api/simulation-runs/simulation-2' && method === 'GET') {
      return jsonResponse({
        ...simulationRuns['workspace-2'][0],
        inputSnapshot: {
          accountPositioning: '记录真实的数字游民转型路径。',
          topic: {
            title: '文科生如何开始数字游民',
            angle: '拆成可执行的六条路径',
          },
        },
        personaDefinitions: [
          {
            id: 'p1',
            name: '谨慎执行派',
            profile: '想开始但怕踩坑',
            coreConcern: '能不能复制',
            contentPreference: '清单和反例',
          },
        ],
        reactionResults: [
          {
            personaId: 'p1',
            stance: '喜欢',
            quote: '需要更具体的证据',
            concerns: ['能不能复制'],
            opportunities: ['清单'],
          },
        ],
        debateResults: [],
        synthesis: {
          verdict: '值得做',
          mainResistance: '担心幸存者偏差',
          strongestAngle: '真实前提 + 分阶段路径',
          contentAdjustments: ['先讲限制'],
          riskWarnings: ['不要承诺收入'],
        },
        stageErrors: {},
        modelMetadata: { mode: 'demo' },
      })
    }
    if (url === '/api/simulation-runs/simulation-2/review' && method === 'PATCH') {
      const body = JSON.parse(String(init?.body)) as {
        userNotes: string
        reviewStatus: 'unreviewed' | 'useful' | 'rejected'
        expectedUpdatedAt: string
      }
      expect(body.expectedUpdatedAt).toBe(simulationRuns['workspace-2'][0].updatedAt)
      const updated = {
        ...simulationRuns['workspace-2'][0],
        userNotes: body.userNotes,
        reviewStatus: body.reviewStatus,
        updatedAt: '2026-07-11T13:30:00Z',
      }
      simulationRuns['workspace-2'] = [updated]
      return jsonResponse({
        ...updated,
        inputSnapshot: {
          accountPositioning: '记录真实的数字游民转型路径。',
          topic: {
            title: '文科生如何开始数字游民',
            angle: '拆成可执行的六条路径',
          },
        },
        personaDefinitions: [
          {
            id: 'p1',
            name: '谨慎执行派',
            profile: '想开始但怕踩坑',
            coreConcern: '能不能复制',
            contentPreference: '清单和反例',
          },
        ],
        reactionResults: [
          {
            personaId: 'p1',
            stance: '喜欢',
            quote: '需要更具体的证据',
            concerns: ['能不能复制'],
            opportunities: ['清单'],
          },
        ],
        debateResults: [],
        synthesis: {
          verdict: '值得做',
          mainResistance: '担心幸存者偏差',
          strongestAngle: '真实前提 + 分阶段路径',
          contentAdjustments: ['先讲限制'],
          riskWarnings: ['不要承诺收入'],
        },
        stageErrors: {},
        modelMetadata: { mode: 'demo' },
      })
    }
    if (url === '/api/drafts/draft-2' && method === 'GET') {
      return jsonResponse({
        ...drafts['workspace-2'][0],
        generatedSnapshot: {
          structure: {
            topicChosen: '文科生如何开始数字游民',
            outline: [{ sec: '路径拆解', ct: '六条路径逐一说明' }],
            reuse: '问题切入 → 路径拆解 → 行动清单',
          },
        },
        editableContent: {
          structure: {
            topicChosen: '文科生如何开始数字游民',
            outline: [{ sec: '路径拆解', ct: '六条路径逐一说明' }],
            reuse: '问题切入 → 路径拆解 → 行动清单',
          },
        },
        inputSnapshot: {
          topic: {
            title: '文科生如何开始数字游民',
            angle: '拆成可执行的六条路径',
          },
        },
        stageErrors: {},
        modelMetadata: { mode: 'demo' },
      })
    }
    if (url === '/api/drafts/draft-2' && method === 'PATCH') {
      const body = JSON.parse(String(init?.body)) as {
        editableContent: Record<string, unknown>
      }
      return jsonResponse({
        ...drafts['workspace-2'][0],
        updatedAt: '2026-07-11T13:30:00Z',
        generatedSnapshot: {
          structure: {
            topicChosen: '文科生如何开始数字游民',
            outline: [{ sec: '路径拆解', ct: '六条路径逐一说明' }],
            reuse: '问题切入 → 路径拆解 → 行动清单',
          },
        },
        editableContent: body.editableContent,
        inputSnapshot: {
          topic: {
            title: '文科生如何开始数字游民',
            angle: '拆成可执行的六条路径',
          },
        },
        stageErrors: {},
        modelMetadata: { mode: 'demo' },
      })
    }
    const topicsMatch = url.match(/^\/api\/workspaces\/(workspace-[12])\/topics/)
    if (topicsMatch && method === 'GET') {
      return jsonResponse(topics[topicsMatch[1]])
    }
    if (url === '/api/topics/topic-2/briefs/generate' && method === 'POST') {
      const brief: Draft = {
        id: 'brief-2',
        workspaceId: 'workspace-2',
        topicId: 'topic-2',
        kind: 'content_brief',
        sourceAnalysisRunId: null,
        sourceWorkflow: 'manual',
        status: 'completed',
        createdAt: '2026-07-11T13:10:00Z',
        completedAt: '2026-07-11T13:10:01Z',
        updatedAt: '2026-07-11T13:10:01Z',
        generatedSnapshot: {
          brief: {
            topicTitle: '文科生如何开始数字游民',
            refinedAngle: '拆成可执行的六条路径',
            targetReader: '想转型但不知道从哪里开始的文科生',
            readerPain: '担心自己没有技术能力',
            contentPromise: '给出低门槛路径和判断标准',
            corePoint: '先选可验证路径，再谈长期迁移',
            formatRecommendation: '清单型图文',
            openingHook: '文科生不是不能做数字游民，而是起点要选对。',
            argumentPath: ['先破除误区', '再拆路径', '最后给行动清单'],
            materialNeeds: ['真实转型案例'],
            titleDirections: ['文科生做数字游民，先别学代码'],
            cta: '留言你的专业背景',
            risks: ['不要承诺收入'],
            revisionSuggestions: ['补一个失败反例'],
          },
        },
        editableContent: {
          brief: {
            topicTitle: '文科生如何开始数字游民',
            refinedAngle: '拆成可执行的六条路径',
            targetReader: '想转型但不知道从哪里开始的文科生',
            readerPain: '担心自己没有技术能力',
            contentPromise: '给出低门槛路径和判断标准',
            corePoint: '先选可验证路径，再谈长期迁移',
            formatRecommendation: '清单型图文',
            openingHook: '文科生不是不能做数字游民，而是起点要选对。',
            argumentPath: ['先破除误区', '再拆路径', '最后给行动清单'],
            materialNeeds: ['真实转型案例'],
            titleDirections: ['文科生做数字游民，先别学代码'],
            cta: '留言你的专业背景',
            risks: ['不要承诺收入'],
            revisionSuggestions: ['补一个失败反例'],
          },
        },
        inputSnapshot: {
          topic: {
            title: '文科生如何开始数字游民',
            angle: '拆成可执行的六条路径',
          },
        },
        stageErrors: {},
        modelMetadata: { mode: 'demo', kind: 'content_brief' },
      }
      drafts['workspace-2'] = [brief, ...drafts['workspace-2']]
      return jsonResponse(brief, 201)
    }
    if (url === '/api/drafts/brief-2/structure/generate' && method === 'POST') {
      const structure: Draft = {
        id: 'structure-from-brief-2',
        workspaceId: 'workspace-2',
        topicId: 'topic-2',
        kind: 'content_structure',
        sourceAnalysisRunId: null,
        sourceWorkflow: 'manual',
        status: 'completed',
        createdAt: '2026-07-11T13:20:00Z',
        completedAt: '2026-07-11T13:20:01Z',
        updatedAt: '2026-07-11T13:20:01Z',
        generatedSnapshot: {
          structure: {
            topicChosen: '文科生如何开始数字游民',
            outline: [{ sec: '从 Brief 进入结构', ct: '沿用 Brief 的核心观点展开' }],
            reuse: 'Brief 对齐 → 结构拆解 → 行动清单',
          },
        },
        editableContent: {
          structure: {
            topicChosen: '文科生如何开始数字游民',
            outline: [{ sec: '从 Brief 进入结构', ct: '沿用 Brief 的核心观点展开' }],
            reuse: 'Brief 对齐 → 结构拆解 → 行动清单',
          },
        },
        inputSnapshot: {
          topic: {
            title: '文科生如何开始数字游民',
            angle: '拆成可执行的六条路径',
          },
          sourceBrief: {
            draftId: 'brief-2',
          },
        },
        stageErrors: {},
        modelMetadata: { mode: 'demo', kind: 'content_structure' },
      }
      drafts['workspace-2'] = [structure, ...drafts['workspace-2']]
      return jsonResponse(structure, 201)
    }
    if (url === '/api/topics/topic-2' && method === 'PATCH') {
      const body = JSON.parse(String(init?.body)) as {
        title: string
        angle: string
      }
      const updated = {
        ...topics['workspace-2'][0],
        title: body.title,
        angle: body.angle,
        updatedAt: '2026-07-11T13:00:00Z',
      }
      topics['workspace-2'][0] = updated
      return jsonResponse(updated)
    }
    throw new Error(`Unexpected request: ${method} ${url}`)
  })
}

beforeEach(() => {
  window.history.pushState({}, '', '/?internal=1')
  agentConversations['workspace-1'] = []
  agentConversations['workspace-2'] = []
  assetProposals['conversation-1'] = []
  agents['workspace-1'] = [agentSummary, creativeOutputAgentSummary]
  agents['workspace-2'] = [
    {
      ...agentSummary,
      id: 'agent-trend',
      workspaceId: 'workspace-2',
      agentId: 'trend_opportunity_strategist',
      displayName: 'Trend Opportunity Strategist',
      skillIds: [
        'analysis.trend_patterns',
        'analysis.pain_points_from_trend_posts',
        'topic.generate_from_trend_analysis',
      ],
    },
  ]
  skills['workspace-1'] = [
    skillSummary,
    painPointSkill,
    accountTopicSkill,
    videoQualitySkill,
    commentsFormatterSkill,
    creativeBriefSkill,
    topicSaveSkill,
    draftStructureSkill,
    draftEditSkill,
  ]
  skills['workspace-2'] = [
    {
      ...skillSummary,
      id: 'skill-trend',
      workspaceId: 'workspace-2',
      skillId: 'analysis.trend_patterns',
      displayName: 'Analyze Trend Patterns',
    },
  ]
  skillDetails['skill-profile'] = skillDetail
  skillDetails['skill-creative-brief'] = creativeBriefSkillDetail
  skillDetails['skill-format-comments'] = commentsFormatterSkillDetail
  skillDetails['skill-video-quality'] = videoQualitySkillDetail
  workflowAssets['workspace-1'] = [
    workflowSummary,
    trendWorkflowSummary,
    videoWorkflowSummary,
    creativeOutputWorkflowSummary,
  ]
  workflowAssets['workspace-2'] = [
    {
      ...trendWorkflowSummary,
      workspaceId: 'workspace-2',
    },
  ]
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  cleanup()
})

async function openCreatorAssetTab(label: RegExp | string) {
  fireEvent.click(await screen.findByRole('button', { name: /创作者档案/ }))
  fireEvent.click((await screen.findAllByRole('button', { name: label }))[0])
}

describe('frontend health page', () => {
  it('remains available at /health', () => {
    window.history.pushState({}, '', '/health')
    render(<App />)

    expect(
      screen.getByRole('heading', { name: 'Frontend is healthy' }),
    ).toBeInTheDocument()
  })
})

describe('workspace UI', () => {
  it('auto-creates and hides the default workspace controls', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation((input, init) => {
        const url = String(input)
        const method = init?.method || 'GET'
        if (url === '/api/workspaces' && method === 'GET') {
          return jsonResponse([])
        }
        if (url === '/api/workspaces' && method === 'POST') {
          const body = JSON.parse(String(init?.body)) as {
            name: string
            accountPositioning: string
          }
          expect(body.name).toBe('默认创作者工作区')
          return jsonResponse(
            {
              id: 'workspace-default',
              name: body.name,
              accountPositioning: body.accountPositioning,
              positioningVersion: 1,
              currentTopicId: null,
              createdAt: '2026-07-11T09:00:00Z',
              updatedAt: '2026-07-11T09:00:00Z',
            },
            201,
          )
        }
        if (url === '/api/workspaces/workspace-default' && method === 'GET') {
          return jsonResponse({
            id: 'workspace-default',
            name: '默认创作者工作区',
            accountPositioning: '',
            positioningVersion: 1,
            currentTopicId: null,
            createdAt: '2026-07-11T09:00:00Z',
            updatedAt: '2026-07-11T09:00:00Z',
          })
        }
        if (url.startsWith('/api/workspaces/workspace-default/') && method === 'GET') {
          return jsonResponse([])
        }
        throw new Error(`Unexpected request: ${method} ${url}`)
      })

    render(<App />)

    expect(await screen.findByText('账号诊断待运行')).toBeInTheDocument()
    expect(screen.queryByLabelText('选择工作区')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /新建工作区/ })).not.toBeInTheDocument()
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.filter(
          ([url, init]) => String(url) === '/api/workspaces' && init?.method === 'POST',
        ),
      ).toHaveLength(1)
    })
  })

  it('loads account profile and input asset instances separately', async () => {
    installWorkspaceApiMock()
    render(<App />)

    await screen.findByText('账号诊断待运行')
    expect(screen.queryByLabelText('选择工作区')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /新建工作区/ })).not.toBeInTheDocument()
    await openCreatorAssetTab(/账号概况/)
    expect(await screen.findByText('创作者档案概览')).toBeInTheDocument()
    expect(screen.getByText(/请先从左侧选择一个实例/)).toBeInTheDocument()
    expect(screen.getByText(/请选择左侧的\s*账号概况\s*实例/)).toBeInTheDocument()
    expect(screen.queryByDisplayValue('帮助文科生做留学决策。')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /新建账号概况/ }))
    expect(await screen.findByLabelText('账号概况名称')).toHaveValue('')
    expect(screen.queryByRole('button', { name: /载入/ })).not.toBeInTheDocument()
    await openCreatorAssetTab(/历史笔记/)
    expect(screen.getByText(/请选择左侧的\s*历史笔记\s*实例/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /留学帖子数据合集/ }))
    expect(await screen.findByLabelText('历史笔记名称')).toHaveValue(
      '留学帖子数据合集',
    )
    expect(
      await screen.findByDisplayValue('留学中介到底值不值｜赞1.1k｜爆'),
    ).toBeInTheDocument()
    await openCreatorAssetTab(/评论样本/)
    fireEvent.click(screen.getByRole('button', { name: /留学评论区合集/ }))
    expect(await screen.findByLabelText('评论样本名称')).toHaveValue(
      '留学评论区合集',
    )
    expect(
      screen.getByDisplayValue('双非背景冲英国前30有戏吗？'),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /热点分析/ }))
    expect(await screen.findByLabelText('趋势数据实例')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '管理账号概况' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '管理输入资产' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /视频博主质量诊断/ }))
    await screen.findByText('视频创作者诊断待运行')
    expect(screen.getAllByText('视频创作样本').length).toBeGreaterThan(0)
  })

  it('shows XHS creator profile workflow inputs as a derived asset source', async () => {
    const originalWorkspaceOneMaterials = materials['workspace-1']
    materials['workspace-1'] = [
      qsheepXhsCreatorProfileAsset,
      ...originalWorkspaceOneMaterials,
    ]
    try {
      installWorkspaceApiMock()
      render(<App />)

      await screen.findByText('账号诊断待运行')

      expect(screen.getByLabelText('小红书创作者主页实例')).toHaveValue(
        'xhs-profile-1',
      )
      expect(screen.getByText('账号：QSheep')).toBeInTheDocument()
      expect(screen.getByText('笔记：2')).toBeInTheDocument()
      expect(screen.getByText('评论：1')).toBeInTheDocument()
      expect(screen.getByText('封面引用：1')).toBeInTheDocument()
      expect(screen.getByText('本次账号诊断会由后端派生')).toBeInTheDocument()
      expect(screen.getByText('账号概况快照')).toBeInTheDocument()
      expect(screen.getByText('历史笔记摘要')).toBeInTheDocument()
      expect(screen.getByText('评论痛点样本')).toBeInTheDocument()
      expect(
        screen.getByText('中传大三专业第一，我为什么放弃保研'),
      ).toBeInTheDocument()
      expect(screen.queryByLabelText('账号概况实例')).not.toBeInTheDocument()
    } finally {
      materials['workspace-1'] = originalWorkspaceOneMaterials
      cleanup()
    }
  })

  it('uses an XHS creator profile as the video quality input source', async () => {
    class MockEventSource {
      private listeners = new Map<string, EventListener[]>()

      constructor(readonly url: string) {
        setTimeout(() => {
          this.dispatch('run.succeeded', {
            eventId: 'event-video-xhs',
            runId: 'run-video-xhs',
            runType: 'video_creator_quality',
            stageKey: null,
            status: 'completed',
            sequence: 1,
            occurredAt: '2026-07-11T12:00:01Z',
            data: { eventType: 'run.succeeded' },
          })
        }, 0)
      }

      addEventListener(type: string, listener: EventListener) {
        this.listeners.set(type, [...(this.listeners.get(type) || []), listener])
      }

      close() {
        // Test double does not keep an open network connection.
      }

      private dispatch(type: string, payload: unknown) {
        const event = new MessageEvent(type, { data: JSON.stringify(payload) })
        ;(this.listeners.get(type) || []).forEach((listener) => listener(event))
      }
    }

    vi.stubGlobal('EventSource', MockEventSource)
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation((input, init) => {
        const url = String(input)
        const method = init?.method || 'GET'
        if (url === '/api/workspaces' && method === 'GET') {
          return jsonResponse([workspaceOne])
        }
        if (url === '/api/workspaces/workspace-1' && method === 'GET') {
          return jsonResponse(workspaceOne)
        }
        if (
          url === '/api/workspaces/workspace-1/input-assets' &&
          method === 'GET'
        ) {
          return jsonResponse([qsheepXhsCreatorProfileAsset])
        }
        if (url.startsWith('/api/workspaces/workspace-1/') && method === 'GET') {
          return jsonResponse([])
        }
        if (
          url === '/api/workspaces/workspace-1/input-assets' &&
          method === 'POST'
        ) {
          const body = JSON.parse(String(init?.body)) as {
            type: InputAsset['type']
            name: string
            content: string
          }
          expect(body.type).toBe('account_profile')
          return jsonResponse(
            {
              id: 'new-video-program-profile',
              workspaceId: 'workspace-1',
              type: body.type,
              name: body.name,
              content: body.content,
              createdAt: '2026-07-11T12:00:00Z',
              updatedAt: '2026-07-11T12:00:00Z',
            },
            201,
          )
        }
        if (
          url === '/api/workspaces/workspace-1/analysis-runs' &&
          method === 'POST'
        ) {
          const body = JSON.parse(String(init?.body)) as {
            workflowType?: string
            accountProfileInputAssetId?: string
            videoCreatorSamplesInputAssetId?: string
            xhsCreatorProfileInputAssetId?: string
          }
          expect(body.workflowType).toBe('video_creator_quality')
          expect(body.accountProfileInputAssetId).toBe('new-video-program-profile')
          expect(body.videoCreatorSamplesInputAssetId).toBeUndefined()
          expect(body.xhsCreatorProfileInputAssetId).toBe('xhs-profile-1')
          return jsonResponse(
            {
              id: 'run-video-xhs',
              workspaceId: 'workspace-1',
              workflowType: 'video_creator_quality',
              status: 'running',
              inputSnapshot: {},
              stageResults: {},
              stageErrors: {},
              modelMetadata: { mode: 'demo' },
              createdAt: '2026-07-11T12:00:00Z',
              startedAt: null,
              completedAt: null,
              updatedAt: '2026-07-11T12:00:00Z',
            },
            201,
          )
        }
        if (url === '/api/analysis-runs/run-video-xhs' && method === 'GET') {
          return jsonResponse({
            id: 'run-video-xhs',
            workspaceId: 'workspace-1',
            workflowType: 'video_creator_quality',
            status: 'completed',
            inputSnapshot: {},
            stageResults: {},
            stageErrors: {},
            modelMetadata: { mode: 'demo' },
            createdAt: '2026-07-11T12:00:00Z',
            startedAt: '2026-07-11T12:00:00Z',
            completedAt: '2026-07-11T12:00:01Z',
            updatedAt: '2026-07-11T12:00:01Z',
          })
        }
        throw new Error(`Unexpected request: ${method} ${url}`)
      })

    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /视频博主质量诊断/ }))
    expect(await screen.findByText('本次视频诊断会由后端派生')).toBeInTheDocument()
    expect(screen.getByText('视频作者证据包')).toBeInTheDocument()
    expect(screen.getByText('视频：1')).toBeInTheDocument()
    expect(screen.queryByLabelText('视频创作样本实例')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '⚡ 生成视频创作者诊断' }))

    await waitFor(() => {
      const createRunCall = fetchMock.mock.calls.find(
        ([url, init]) =>
          String(url) === '/api/workspaces/workspace-1/analysis-runs' &&
          init?.method === 'POST',
      )
      expect(createRunCall).toBeTruthy()
    })
  })

  it('prefers a workspace with input assets when the newest workspace is empty', async () => {
    const originalWorkspaceTwoMaterials = materials['workspace-2']
    materials['workspace-2'] = []
    try {
      const fetchMock = installWorkspaceApiMock('workspace-2')
      render(<App />)

      await screen.findByText('账号诊断待运行')
      await openCreatorAssetTab(/历史笔记/)
      fireEvent.click(screen.getByRole('button', { name: /留学帖子数据合集/ }))

      expect(
        await screen.findByDisplayValue('留学中介到底值不值｜赞1.1k｜爆'),
      ).toBeInTheDocument()
      await waitFor(() => {
        expect(
          fetchMock.mock.calls.some(
            ([url]) => String(url) === '/api/workspaces/workspace-2/input-assets',
          ),
        ).toBe(true)
        expect(
          fetchMock.mock.calls.some(
            ([url]) => String(url) === '/api/workspaces/workspace-1/input-assets',
          ),
        ).toBe(true)
      })
    } finally {
      materials['workspace-2'] = originalWorkspaceTwoMaterials
    }
  })

  it('uses explicit save buttons for current and new input asset instances', async () => {
    const fetchMock = installWorkspaceApiMock()
    render(<App />)

    await openCreatorAssetTab(/历史笔记/)
    fireEvent.click(screen.getByRole('button', { name: /留学帖子数据合集/ }))
    const historicalEditor = await screen.findByLabelText(
      '主页 / 历史笔记 + 数据（格式：标题 ｜ 数据 ｜ 爆/平/差）',
    )
    fireEvent.change(historicalEditor, {
      target: { value: '更新后的历史笔记｜赞2k｜爆' },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存当前历史笔记' }))

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) =>
            String(url) === '/api/input-assets/history-1' &&
            init?.method === 'PATCH',
        ),
      ).toBe(true)
    })
    await waitFor(() => {
      expect(screen.getAllByText('已保存').length).toBeGreaterThan(0)
    })

    fireEvent.change(historicalEditor, {
      target: { value: '另存的新历史笔记｜赞3k｜爆' },
    })
    fireEvent.change(screen.getByLabelText('历史笔记名称'), {
      target: { value: '另存历史笔记合集' },
    })
    fireEvent.click(screen.getByRole('button', { name: '另存为新历史笔记' }))

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) =>
            String(url) === '/api/workspaces/workspace-1/input-assets' &&
            init?.method === 'POST',
        ),
      ).toBe(true)
    })
    const createCall = fetchMock.mock.calls.find(
      ([url, init]) =>
        String(url) === '/api/workspaces/workspace-1/input-assets' &&
        init?.method === 'POST',
    )
    expect(JSON.parse(String(createCall?.[1]?.body)).name).toBe('另存历史笔记合集')
  })

  it('uses the input asset formatter agent to fill an editor without saving', async () => {
    const fetchMock = installWorkspaceApiMock()
    render(<App />)

    await openCreatorAssetTab(/评论样本/)
    fireEvent.change(
      await screen.findByPlaceholderText(/粘贴账号定位、历史帖子、评论/),
      {
        target: { value: '1. “太焦虑了，不知道怎么选校”\n2. 求时间线' },
      },
    )
    fireEvent.click(screen.getByRole('button', { name: '让 Agent 整理并填入' }))

    expect(await screen.findByLabelText('评论样本名称')).toHaveValue(
      '整理后的评论样本合集',
    )
    expect(await screen.findByLabelText('评论区原文（一行一条）')).toHaveValue(
      '太焦虑了，不知道怎么选校\n求时间线',
    )
    expect(screen.getByText(/已整理为一行一条/)).toBeInTheDocument()
    expect(
      fetchMock.mock.calls.some(
        ([url, init]) =>
          String(url) === '/api/skills/skill-format-comments/invoke' &&
          init?.method === 'POST',
      ),
    ).toBe(true)
    expect(
      fetchMock.mock.calls.filter(
        ([url, init]) =>
          init?.method === 'POST' &&
          String(url) === '/api/workspaces/workspace-1/input-assets',
      ),
    ).toHaveLength(0)
  })

  it('does not expose batch CSV import in input asset pages', async () => {
    installWorkspaceApiMock()
    render(<App />)

    await openCreatorAssetTab(/评论样本/)

    expect(screen.queryByText(/批量导入/)).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /上传并保存评论样本/ }),
    ).not.toBeInTheDocument()
  })

  it('shows workspace skills as product assets', async () => {
    installWorkspaceApiMock()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /Skills/ }))
    expect(await screen.findByText('Analyze Account Profile')).toBeInTheDocument()
    expect(screen.getByText('Generate Creative Brief')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Analyze Account Profile/ }))

    expect(await screen.findByText('analysis.profile_from_history')).toBeInTheDocument()
    expect(screen.getByText('AnalysisRun.stageResults.profile')).toBeInTheDocument()
    expect(screen.getByText('partial_allowed')).toBeInTheDocument()
    expect(screen.getByText('ModelOperation.PROFILE')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Generate Creative Brief/ }))

    expect(await screen.findByText('topic.refine_to_brief')).toBeInTheDocument()
    expect(screen.getByText('Draft(kind=content_brief)')).toBeInTheDocument()
    expect(screen.getByText('ModelOperation.CONTENT_BRIEF')).toBeInTheDocument()
  })

  it('lets PM edit and save a skill contract as a generated override', async () => {
    const fetchMock = installWorkspaceApiMock()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /Skills/ }))
    fireEvent.click(await screen.findByRole('button', { name: /Analyze Account Profile/ }))
    fireEvent.click(await screen.findByRole('button', { name: '编辑 contract' }))

    fireEvent.change(await screen.findByLabelText('用途 / 调优说明'), {
      target: { value: 'PM 调整：更重视视频质量证据限制。' },
    })
    fireEvent.change(screen.getByLabelText('Output Schema JSON'), {
      target: {
        value: JSON.stringify(
          {
            root: 'profile',
            rubricVersion: 'pm-v1',
          },
          null,
          2,
        ),
      },
    })
    fireEvent.change(screen.getByLabelText('Workspace Notes'), {
      target: { value: '施琦姗前端调优。' },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存 Skill Contract' }))

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) =>
            String(url) === '/api/skills/skill-profile/definition' &&
            init?.method === 'PATCH',
        ),
      ).toBe(true)
    })
    expect(await screen.findByText('已保存')).toBeInTheDocument()
    expect(screen.getAllByText('PM 调整：更重视视频质量证据限制。').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/generated/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/rubricVersion/).length).toBeGreaterThan(0)
  })

  it('shows skill definition diff and reverts a generated override', async () => {
    const fetchMock = installWorkspaceApiMock()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /Skills/ }))
    fireEvent.click(await screen.findByRole('button', { name: /Analyze Account Profile/ }))
    fireEvent.click(await screen.findByRole('button', { name: '编辑 contract' }))

    fireEvent.change(await screen.findByLabelText('Skill 名称'), {
      target: { value: 'PM Profile Skill' },
    })
    fireEvent.change(screen.getByLabelText('版本'), {
      target: { value: 'pm-v1' },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存 Skill Contract' }))

    expect(await screen.findByText('已保存')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '查看与内置差异' }))

    expect(await screen.findByText('displayName / version')).toBeInTheDocument()
    expect(screen.getAllByText(/PM Profile Skill/).length).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole('button', { name: '恢复内置版本' }))

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) =>
            String(url) === '/api/skills/skill-profile/revert-definition' &&
            init?.method === 'POST',
        ),
      ).toBe(true)
    })
    expect(await screen.findByText('已恢复内置版本')).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: 'Analyze Account Profile' }),
    ).toBeInTheDocument()
    expect(screen.getAllByText(/builtin/).length).toBeGreaterThan(0)
  })

  it('lets PM edit video diagnosis rubric without editing raw JSON directly', async () => {
    const fetchMock = installWorkspaceApiMock()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /Skills/ }))
    fireEvent.click(
      await screen.findByRole('button', { name: /Analyze AIGC Video Quality/ }),
    )
    fireEvent.click(await screen.findByRole('button', { name: '编辑 contract' }))

    expect(await screen.findByText('视频诊断 Rubric')).toBeInTheDocument()
    fireEvent.change(
      screen.getByLabelText('创作者类型规则：类型 | 激励适配度 | 判定规则'),
      {
        target: {
          value:
            '剧本驱动型 | 高 | 连续剧情内容，评论催更，适合连续更新激励。\n商单驱动型 | 低 | 商单占比高，非商单内容弱。',
        },
      },
    )
    fireEvent.change(screen.getByLabelText('证据限制规则（一行一个）'), {
      target: {
        value:
          '没有视频理解时不得声称看过镜头。\n证据弱时必须降低 evidenceConfidence。',
      },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存 Skill Contract' }))

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([url, init]) =>
          String(url) === '/api/skills/skill-video-quality/definition' &&
          init?.method === 'PATCH',
      )
      expect(call).toBeTruthy()
      const body = JSON.parse(String(call?.[1]?.body)) as {
        contextPolicy: { pmRubric?: { creatorTypes?: unknown[]; evidenceRules?: string[] } }
      }
      expect(body.contextPolicy.pmRubric?.creatorTypes).toEqual([
        {
          type: '剧本驱动型',
          fitForIncentive: '高',
          rule: '连续剧情内容，评论催更，适合连续更新激励。',
        },
        {
          type: '商单驱动型',
          fitForIncentive: '低',
          rule: '商单占比高，非商单内容弱。',
        },
      ])
      expect(body.contextPolicy.pmRubric?.evidenceRules).toContain(
        '证据弱时必须降低 evidenceConfidence。',
      )
    })
    expect(await screen.findByText('已保存')).toBeInTheDocument()
  })

  it('lets PM compose agent skills from a structured checklist', async () => {
    const fetchMock = installWorkspaceApiMock()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /Agents/ }))
    fireEvent.click(
      await screen.findByRole('button', { name: /Account Diagnosis Strategist/ }),
    )
    fireEvent.click(await screen.findByRole('button', { name: '编辑 Agent' }))

    expect(await screen.findByText('组合 Skills')).toBeInTheDocument()
    const creativeBriefCheckbox = screen.getByLabelText(/Generate Creative Brief/)
    fireEvent.click(creativeBriefCheckbox)
    fireEvent.click(screen.getByRole('button', { name: '保存 Agent Definition' }))

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([url, init]) =>
          String(url) === '/api/agents/agent-account/definition' &&
          init?.method === 'PATCH',
      )
      expect(call).toBeTruthy()
      const body = JSON.parse(String(call?.[1]?.body)) as { skillIds: string[] }
      expect(body.skillIds).toContain('topic.refine_to_brief')
    })
    expect(await screen.findByText('已保存')).toBeInTheDocument()
  })

  it('runs a direct skill test for supported formatter skills', async () => {
    const fetchMock = installWorkspaceApiMock()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /Skills/ }))
    fireEvent.click(await screen.findByRole('button', { name: /Format Comment Samples/ }))

    expect(await screen.findByText('Skill Test')).toBeInTheDocument()
    expect(screen.getByText('invoke-ready')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Input JSON'), {
      target: { value: JSON.stringify({ rawText: '太焦虑了\n求时间线' }, null, 2) },
    })
    fireEvent.click(screen.getByRole('button', { name: '运行 Skill Test' }))

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) =>
            String(url) === '/api/skills/skill-format-comments/invoke' &&
            init?.method === 'POST',
        ),
      ).toBe(true)
    })
    expect(await screen.findByText('测试完成')).toBeInTheDocument()
    expect(screen.getByText(/整理后的评论样本合集/)).toBeInTheDocument()
    expect(screen.getByText(/skill.invoke/)).toBeInTheDocument()
  })

  it('supports dry-run for workflow analysis skills without direct invoke', async () => {
    const fetchMock = installWorkspaceApiMock()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /Skills/ }))
    fireEvent.click(await screen.findByRole('button', { name: /Analyze Account Profile/ }))

    expect(await screen.findByText('dry-run-ready')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '运行 Skill Test' }))
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) =>
            String(url) === '/api/skills/skill-profile/dry-run' &&
            init?.method === 'POST',
        ),
      ).toBe(true)
    })
    expect(await screen.findByText('测试完成')).toBeInTheDocument()
    expect(screen.getByText(/skill.dry_run/)).toBeInTheDocument()
  })

  it('shows workspace agents as composed product roles', async () => {
    installWorkspaceApiMock()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /Agents/ }))
    expect(
      await screen.findByText('Account Diagnosis Strategist'),
    ).toBeInTheDocument()
    expect(screen.getByText('Topic and Creative Output Editor')).toBeInTheDocument()

    fireEvent.click(
      screen.getByRole('button', { name: /Account Diagnosis Strategist/ }),
    )

    expect(
      await screen.findByText(/creator account strategist/),
    ).toBeInTheDocument()
    expect(screen.getByText('analysis.profile_from_history')).toBeInTheDocument()
    expect(screen.getByText(/selected historical posts/)).toBeInTheDocument()

    fireEvent.click(
      screen.getByRole('button', { name: /Topic and Creative Output Editor/ }),
    )

    expect(await screen.findByText('topic.refine_to_brief')).toBeInTheDocument()
    expect(screen.getByText('draft.generate_structure_from_brief')).toBeInTheDocument()
    expect(screen.getByText(/selected creative brief/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /开始对话/ }))

    expect(
      await screen.findByText(/发送第一条消息/),
    ).toBeInTheDocument()
    const composer = screen.getByPlaceholderText(/直接和这个 Agent 对话/)
    await waitFor(() => expect(composer).toHaveFocus())
  })

  it('lets PM edit and save an agent definition as a generated override', async () => {
    const fetchMock = installWorkspaceApiMock()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /Agents/ }))
    fireEvent.click(
      await screen.findByRole('button', { name: /Account Diagnosis Strategist/ }),
    )
    fireEvent.click(await screen.findByRole('button', { name: '编辑 Agent' }))

    fireEvent.change(await screen.findByLabelText('Agent 名称'), {
      target: { value: 'PM Account Diagnosis Agent' },
    })
    fireEvent.change(screen.getByLabelText('System Prompt'), {
      target: {
        value:
          'You are a creator account strategist. Always explain evidence boundaries first.',
      },
    })
    fireEvent.change(screen.getByLabelText('Skill IDs（一行一个）'), {
      target: {
        value: 'analysis.profile_from_history\nanalysis.pain_points_from_comments',
      },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存 Agent Definition' }))

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) =>
            String(url) === '/api/agents/agent-account/definition' &&
            init?.method === 'PATCH',
        ),
      ).toBe(true)
    })
    expect(await screen.findByText('已保存')).toBeInTheDocument()
    expect(screen.getAllByText('PM Account Diagnosis Agent').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/generated/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/evidence boundaries first/).length).toBeGreaterThan(0)
  })

  it('validates agent definition skill references before saving', async () => {
    const fetchMock = installWorkspaceApiMock()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /Agents/ }))
    fireEvent.click(
      await screen.findByRole('button', { name: /Account Diagnosis Strategist/ }),
    )
    fireEvent.click(await screen.findByRole('button', { name: '编辑 Agent' }))

    fireEvent.change(screen.getByLabelText('Skill IDs（一行一个）'), {
      target: { value: 'missing.skill' },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存 Agent Definition' }))

    expect(await screen.findByText(/未知 Skill：missing\.skill/)).toBeInTheDocument()
    expect(
      fetchMock.mock.calls.some(
        ([url, init]) =>
          String(url) === '/api/agents/agent-account/definition' &&
          init?.method === 'PATCH',
      ),
    ).toBe(false)
  })

  it('lets users edit and apply asset proposals from agent conversations', async () => {
    const fetchMock = installWorkspaceApiMock()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /Agents/ }))
    fireEvent.click(
      await screen.findByRole('button', { name: /Account Diagnosis Strategist/ }),
    )
    fireEvent.click(await screen.findByRole('button', { name: /开始对话/ }))

    const composer = await screen.findByPlaceholderText(/直接和这个 Agent 对话/)
    fireEvent.change(composer, {
      target: { value: '把账号定位改成更关注 DIY 申请' },
    })
    fireEvent.click(screen.getByRole('button', { name: /发送给 Agent/ }))

    expect(await screen.findByText('Asset Proposals')).toBeInTheDocument()
    await waitFor(() => {
      const sendCall = fetchMock.mock.calls.find(
        ([url, init]) =>
          String(url) === '/api/agent-conversations/conversation-1/messages' &&
          init?.method === 'POST',
      )
      expect(sendCall).toBeTruthy()
      const payload = JSON.parse(String(sendCall?.[1]?.body)) as {
        clientMessageKey?: string
      }
      expect(payload.clientMessageKey).toMatch(/^agent-message-/)
    })
    expect(await screen.findByText('更新 Account Profile')).toBeInTheDocument()
    const actionEditor = screen.getByDisplayValue(
      /把账号定位改成更关注 DIY 申请/,
    )
    fireEvent.change(actionEditor, {
      target: {
        value: JSON.stringify(
          {
            type: 'workspace.update_profile',
            status: 'requires_confirmation',
            description: '建议更新账号定位。',
            payload: {
              accountPositioning: '更关注 DIY 申请和预算决策',
            },
          },
          null,
          2,
        ),
      },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存提案' }))

    await waitFor(() =>
      expect(assetProposals['conversation-1'][0].proposedAction).toMatchObject({
        payload: { accountPositioning: '更关注 DIY 申请和预算决策' },
      }),
    )
    fireEvent.click(screen.getByRole('button', { name: '应用提案' }))

    expect(await screen.findByText('accountPositioning')).toBeInTheDocument()
    expect(screen.getByText('更关注 DIY 申请和预算决策')).toBeInTheDocument()
    expect(
      await screen.findByText('已生成 apply 前 diff，请确认后再次点击“确认应用”。'),
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '确认应用' }))

    await waitFor(() =>
      expect(assetProposals['conversation-1'][0].status).toBe('applied'),
    )
    expect(await screen.findByText('applied')).toBeInTheDocument()
  })

  it('lets PM edit an agent proposal with structured fields', async () => {
    installWorkspaceApiMock()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /Agents/ }))
    fireEvent.click(
      await screen.findByRole('button', { name: /Account Diagnosis Strategist/ }),
    )
    fireEvent.click(await screen.findByRole('button', { name: /开始对话/ }))

    const composer = await screen.findByPlaceholderText(/直接和这个 Agent 对话/)
    fireEvent.change(composer, {
      target: { value: '请生成一个 agent proposal' },
    })
    fireEvent.click(screen.getByRole('button', { name: /发送给 Agent/ }))

    expect(await screen.findByText('Agent Proposal 表单')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Agent 名称'), {
      target: { value: 'PM Creator Reviewer' },
    })
    fireEvent.click(screen.getByLabelText(/Generate Creative Brief/))
    fireEvent.click(screen.getByRole('button', { name: '保存提案' }))

    await waitFor(() => {
      const payload = assetProposals['conversation-1'][0].proposedAction
        .payload as { definition: Record<string, unknown> }
      const definition = payload.definition
      expect(definition.displayName).toBe('PM Creator Reviewer')
      expect(definition.skillIds).toEqual(
        expect.arrayContaining(['topic.refine_to_brief']),
      )
    })
    expect(await screen.findByText('提案已保存，请预览 diff 后再应用。')).toBeInTheDocument()
  })

  it('lets PM edit a workflow proposal task plan before previewing diff', async () => {
    installWorkspaceApiMock()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /Agents/ }))
    fireEvent.click(
      await screen.findByRole('button', { name: /Account Diagnosis Strategist/ }),
    )
    fireEvent.click(await screen.findByRole('button', { name: /开始对话/ }))

    const composer = await screen.findByPlaceholderText(/直接和这个 Agent 对话/)
    fireEvent.change(composer, {
      target: { value: '请生成一个 workflow proposal' },
    })
    fireEvent.click(screen.getByRole('button', { name: /发送给 Agent/ }))

    expect(await screen.findByText('Workflow Proposal 表单')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Workflow 名称'), {
      target: { value: 'PM Creator Review Workflow' },
    })
    fireEvent.click(screen.getByRole('button', { name: '添加 Task' }))
    const newTaskId = document.querySelector(
      '#proposal-1-task-id-1',
    ) as HTMLInputElement | null
    if (!newTaskId) throw new Error('Missing workflow proposal task input')
    fireEvent.change(newTaskId, { target: { value: 'pm_review_assets' } })
    fireEvent.click(screen.getByRole('button', { name: '保存提案' }))

    await waitFor(() => {
      const payload = assetProposals['conversation-1'][0].proposedAction
        .payload as { definition: Record<string, unknown> }
      const definition = payload.definition
      const agentPlan = definition.agentPlan as { tasks: Array<{ taskId: string }> }
      expect(definition.displayName).toBe('PM Creator Review Workflow')
      expect(agentPlan.tasks).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ taskId: 'pm_review_assets' }),
        ]),
      )
    })

    expect(await screen.findByText('提案已保存，请预览 diff 后再应用。')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '预览 Diff' }))
    expect(await screen.findByText(/将创建\s+workflow/)).toBeInTheDocument()
    expect(screen.getByText('agentPlan')).toBeInTheDocument()
  })

  it('surfaces saved agent conversations in the content asset sidebar', async () => {
    installWorkspaceApiMock()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /Agents/ }))
    fireEvent.click(
      await screen.findByRole('button', { name: /Account Diagnosis Strategist/ }),
    )
    fireEvent.click(await screen.findByRole('button', { name: /开始对话/ }))

    const composer = await screen.findByPlaceholderText(/直接和这个 Agent 对话/)
    fireEvent.change(composer, {
      target: { value: '帮我生成一个新的选题能力提案' },
    })
    fireEvent.click(screen.getByRole('button', { name: /发送给 Agent/ }))

    expect(await screen.findByText(/broad context pack/)).toBeInTheDocument()

    const contentNav = screen.getByRole('navigation', { name: '内容资产导航' })
    fireEvent.click(within(contentNav).getByRole('button', { name: /对话记录/ }))

    expect(await screen.findByText('💬 对话记录')).toBeInTheDocument()
    expect(screen.getAllByText(/与 Account Diagnosis Strategist 对话/).length).toBeGreaterThan(0)
    expect(screen.getByText('帮我生成一个新的选题能力提案')).toBeInTheDocument()
    expect(screen.getByText(/broad context pack/)).toBeInTheDocument()
    expect(screen.getByText('Asset Proposals')).toBeInTheDocument()
    expect(screen.getByText('更新 Account Profile')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('对话标题'), {
      target: { value: '已整理的能力讨论' },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存对话标题' }))

    expect(await screen.findByText('已保存')).toBeInTheDocument()
    expect(screen.getAllByText(/已整理的能力讨论/).length).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole('button', { name: '归档对话' }))

    await waitFor(() =>
      expect(screen.getAllByText('archived').length).toBeGreaterThan(0),
    )
    expect(screen.getByRole('button', { name: '恢复对话' })).toBeInTheDocument()
  })

  it('shows workspace workflows as multi-agent task plans', async () => {
    const fetchMock = installWorkspaceApiMock()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /Workflows/ }))
    expect(await screen.findByText('Account Diagnosis Workflow')).toBeInTheDocument()
    expect(screen.getByText('Topic to Creative Output Workflow')).toBeInTheDocument()

    fireEvent.click(
      screen.getByRole('button', { name: /Account Diagnosis Workflow/ }),
    )

    expect(await screen.findByText('AnalysisRun + Topic candidates')).toBeInTheDocument()
    expect(screen.getAllByText(/diagnose_account/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/account_diagnosis_strategist/).length).toBeGreaterThan(0)

    fireEvent.click(
      screen.getByRole('button', { name: /Topic to Creative Output Workflow/ }),
    )

    expect(
      await screen.findByText(
        'Topic + Draft(kind=content_brief) + Draft(kind=content_structure)',
      ),
    ).toBeInTheDocument()
    expect(screen.getAllByText(/generate_brief/).length).toBeGreaterThan(0)
    expect(
      screen.getAllByText(/draft.generate_structure_from_brief/).length,
    ).toBeGreaterThan(0)

    fireEvent.change(screen.getByLabelText('Workflow 调用注册'), {
      target: { value: 'trend' },
    })

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) =>
            String(url) === '/api/workflows/workflow-creative-output/call-binding' &&
            init?.method === 'PATCH',
        ),
      ).toBe(true)
    })
    const capabilityNav = screen.getByRole('navigation', { name: '能力资产导航' })
    expect(
      within(capabilityNav).getByRole('button', {
        name: /Topic to Creative Output Workflow/,
      }),
    ).toBeInTheDocument()
  })

  it('lets PM edit and save a workflow definition as a generated override', async () => {
    const fetchMock = installWorkspaceApiMock()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /Workflows/ }))
    fireEvent.click(
      await screen.findByRole('button', { name: /Topic to Creative Output Workflow/ }),
    )
    fireEvent.click(await screen.findByRole('button', { name: '编辑 Workflow' }))

    fireEvent.change(await screen.findByLabelText('Workflow 名称'), {
      target: { value: 'PM Creative Output Workflow' },
    })
    expect(await screen.findByText('Workflow Tasks')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '添加 Task' }))
    fireEvent.change(screen.getByLabelText('Task ID', { selector: '#workflow-task-id-3' }), {
      target: { value: 'pm_review_brief' },
    })
    fireEvent.change(screen.getByLabelText('Agent', { selector: '#workflow-task-agent-3' }), {
      target: { value: 'topic_draft_editor' },
    })
    const secondTaskSkillBox = document.querySelector(
      '#workflow-task-skills-3',
    ) as HTMLTextAreaElement | null
    expect(secondTaskSkillBox).toBeTruthy()
    if (!secondTaskSkillBox) throw new Error('Missing second task skill textarea')
    fireEvent.change(secondTaskSkillBox, {
      target: { value: 'draft.generate_structure_from_brief' },
    })
    fireEvent.change(screen.getByLabelText('调用注册'), {
      target: { value: 'trend' },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存 Workflow Definition' }))

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) =>
            String(url) === '/api/workflows/workflow-creative-output/definition' &&
            init?.method === 'PATCH',
        ),
      ).toBe(true)
      const call = fetchMock.mock.calls.find(
        ([url, init]) =>
          String(url) === '/api/workflows/workflow-creative-output/definition' &&
          init?.method === 'PATCH',
      )
      const body = JSON.parse(String(call?.[1]?.body)) as {
        agentPlan: { tasks: Array<{ taskId: string; skillIds: string[] }> }
      }
      expect(body.agentPlan.tasks).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            taskId: 'pm_review_brief',
            skillIds: ['draft.generate_structure_from_brief'],
          }),
        ]),
      )
    })
    expect(await screen.findByText('已保存')).toBeInTheDocument()
    expect(screen.getAllByText('PM Creative Output Workflow').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/generated/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/pm_review_brief/).length).toBeGreaterThan(0)
  })

  it('validates workflow task plans before saving', async () => {
    const fetchMock = installWorkspaceApiMock()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /Workflows/ }))
    fireEvent.click(
      await screen.findByRole('button', { name: /Topic to Creative Output Workflow/ }),
    )
    fireEvent.click(await screen.findByRole('button', { name: '编辑 Workflow' }))

    fireEvent.change(
      screen.getByLabelText('Task ID', { selector: '#workflow-task-id-1' }),
      {
        target: { value: 'select_topic' },
      },
    )
    fireEvent.click(screen.getByRole('button', { name: '保存 Workflow Definition' }))

    expect(
      await screen.findByText(/Task ID 不能重复：select_topic/),
    ).toBeInTheDocument()
    expect(
      fetchMock.mock.calls.some(
        ([url, init]) =>
          String(url) === '/api/workflows/workflow-creative-output/definition' &&
          init?.method === 'PATCH',
      ),
    ).toBe(false)
  })

  it('auto-saves account inputs before creating a diagnosis run', async () => {
    class MockEventSource {
      private listeners = new Map<string, EventListener[]>()

      constructor(readonly url: string) {
        setTimeout(() => {
          this.dispatch('run.succeeded', {
            eventId: 'event-1',
            runId: 'run-auto',
            runType: 'account_diagnosis',
            stageKey: null,
            status: 'completed',
            sequence: 1,
            occurredAt: '2026-07-11T12:00:01Z',
            data: { eventType: 'run.succeeded' },
          })
        }, 0)
      }

      addEventListener(type: string, listener: EventListener) {
        this.listeners.set(type, [...(this.listeners.get(type) || []), listener])
      }

      close() {
        // Test double does not keep an open network connection.
      }

      private dispatch(type: string, payload: unknown) {
        const event = new MessageEvent(type, { data: JSON.stringify(payload) })
        ;(this.listeners.get(type) || []).forEach((listener) => listener(event))
      }
    }

    vi.stubGlobal('EventSource', MockEventSource)
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation((input, init) => {
        const url = String(input)
        const method = init?.method || 'GET'
        if (url === '/api/workspaces' && method === 'GET') {
          return jsonResponse([workspaceOne])
        }
        if (url === '/api/workspaces/workspace-1' && method === 'GET') {
          return jsonResponse(workspaceOne)
        }
        if (
          url === '/api/workspaces/workspace-1/input-assets' &&
          method === 'GET'
        ) {
          return jsonResponse([])
        }
        if (
          url === '/api/workspaces/workspace-1/media-assets' &&
          method === 'GET'
        ) {
          return jsonResponse([
            {
              ...mediaAssets['workspace-2'][0],
              id: 'media-workflow-1',
              workspaceId: 'workspace-1',
              name: 'AI短剧主页截图',
            },
          ])
        }
        if (
          url === '/api/workspaces/workspace-1/analysis-runs' &&
          method === 'GET'
        ) {
          return jsonResponse([])
        }
        if (
          url === '/api/workspaces/workspace-1/simulation-runs' &&
          method === 'GET'
        ) {
          return jsonResponse([])
        }
        if (url === '/api/workspaces/workspace-1/skills' && method === 'GET') {
          return jsonResponse([])
        }
        if (url === '/api/workspaces/workspace-1/agents' && method === 'GET') {
          return jsonResponse([])
        }
        if (
          url === '/api/workspaces/workspace-1/agent-conversations' &&
          method === 'GET'
        ) {
          return jsonResponse([])
        }
        if (url === '/api/workspaces/workspace-1/workflows' && method === 'GET') {
          return jsonResponse([])
        }
        if (url === '/api/workspaces/workspace-1/drafts' && method === 'GET') {
          return jsonResponse([])
        }
        if (url === '/api/workspaces/workspace-1/topics' && method === 'GET') {
          return jsonResponse([])
        }
        if (
          url === '/api/workspaces/workspace-1/input-assets' &&
          method === 'POST'
        ) {
          const body = JSON.parse(String(init?.body)) as {
            type: 'account_profile' | 'historical_posts' | 'comments'
            name: string
            content: string
          }
          const idByType = {
            account_profile: 'new-profile',
            comments: 'new-comments',
            historical_posts: 'new-history',
          }
          return jsonResponse(
            {
              id: idByType[body.type],
              workspaceId: 'workspace-1',
              type: body.type,
              name: body.name,
              content: body.content,
              createdAt: '2026-07-11T12:00:00Z',
              updatedAt: '2026-07-11T12:00:00Z',
            },
            201,
          )
        }
        if (
          url === '/api/workspaces/workspace-1/analysis-runs' &&
          method === 'POST'
        ) {
          const body = JSON.parse(String(init?.body)) as {
            accountProfileInputAssetId?: string
            historicalPostsInputAssetId?: string
            commentsInputAssetId?: string
          }
          expect(body.accountProfileInputAssetId).toBe('new-profile')
          expect(body.historicalPostsInputAssetId).toBe('new-history')
          expect(body.commentsInputAssetId).toBe('new-comments')
          return jsonResponse(
            {
              id: 'run-auto',
              workspaceId: 'workspace-1',
              workflowType: 'account_diagnosis',
              status: 'running',
              inputSnapshot: {},
              stageResults: {},
              stageErrors: {},
              modelMetadata: { mode: 'demo' },
              createdAt: '2026-07-11T12:00:00Z',
              startedAt: null,
              completedAt: null,
              updatedAt: '2026-07-11T12:00:00Z',
            },
            201,
          )
        }
        if (url === '/api/analysis-runs/run-auto' && method === 'GET') {
          return jsonResponse({
            id: 'run-auto',
            workspaceId: 'workspace-1',
            workflowType: 'account_diagnosis',
            status: 'completed',
            inputSnapshot: {},
            stageResults: {},
            stageErrors: {},
            modelMetadata: { mode: 'demo' },
            createdAt: '2026-07-11T12:00:00Z',
            startedAt: '2026-07-11T12:00:00Z',
            completedAt: '2026-07-11T12:00:01Z',
            updatedAt: '2026-07-11T12:00:01Z',
          })
        }
        throw new Error(`Unexpected request: ${method} ${url}`)
      })

    render(<App />)
    await openCreatorAssetTab(/历史笔记/)
    fireEvent.click(screen.getByRole('button', { name: /新建历史笔记/ }))
    const historicalEditor = await screen.findByLabelText(
      '主页 / 历史笔记 + 数据（格式：标题 ｜ 数据 ｜ 爆/平/差）',
    )
    fireEvent.change(historicalEditor, {
      target: { value: '留学中介到底值不值｜赞1.1k｜爆' },
    })
    await openCreatorAssetTab(/评论样本/)
    fireEvent.click(screen.getByRole('button', { name: /新建评论样本/ }))
    const commentsEditor = await screen.findByLabelText('评论区原文（一行一条）')
    fireEvent.change(commentsEditor, { target: { value: '这是一条新评论' } })

    expect(
      fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST'),
    ).toHaveLength(0)
    expect(
      screen.queryByRole('button', { name: '保存为评论样本' }),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /账号诊断/ }))
    expect(screen.getByLabelText(/下期选题/)).toHaveValue('')
    fireEvent.click(screen.getByRole('button', { name: '⚡ 生成账号诊断' }))

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST'),
      ).toHaveLength(4)
    })
    expect(screen.getByLabelText(/下期选题/)).toHaveValue('')
  })

  it('auto-saves video creation samples before creating a video quality run', async () => {
    class MockEventSource {
      private listeners = new Map<string, EventListener[]>()

      constructor(readonly url: string) {
        setTimeout(() => {
          this.dispatch('run.succeeded', {
            eventId: 'event-video',
            runId: 'run-video',
            runType: 'video_creator_quality',
            stageKey: null,
            status: 'completed',
            sequence: 1,
            occurredAt: '2026-07-11T12:00:01Z',
            data: { eventType: 'run.succeeded' },
          })
        }, 0)
      }

      addEventListener(type: string, listener: EventListener) {
        this.listeners.set(type, [...(this.listeners.get(type) || []), listener])
      }

      close() {
        // Test double does not keep an open network connection.
      }

      private dispatch(type: string, payload: unknown) {
        const event = new MessageEvent(type, { data: JSON.stringify(payload) })
        ;(this.listeners.get(type) || []).forEach((listener) => listener(event))
      }
    }

    vi.stubGlobal('EventSource', MockEventSource)
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation((input, init) => {
        const url = String(input)
        const method = init?.method || 'GET'
        if (url === '/api/workspaces' && method === 'GET') {
          return jsonResponse([workspaceOne])
        }
        if (url === '/api/workspaces/workspace-1' && method === 'GET') {
          return jsonResponse(workspaceOne)
        }
        if (
          url === '/api/workspaces/workspace-1/input-assets' &&
          method === 'GET'
        ) {
          return jsonResponse([])
        }
        if (
          url === '/api/workspaces/workspace-1/media-assets' &&
          method === 'GET'
        ) {
          return jsonResponse([
            {
              id: 'media-workflow-1',
              workspaceId: 'workspace-1',
              type: 'image',
              name: 'AI短剧主页截图',
              purpose: '视频质量诊断参考',
              sourceType: 'upload',
              originalFilename: 'home.png',
              mediaType: 'image/png',
              byteSize: 128,
              sha256: 'abc',
              metadata: {},
              derived: {
                visualSummary: '主页突出连续 AI 短剧角色和系列化更新。',
                imageUnderstanding: {
                  visualSummary: '主页突出连续 AI 短剧角色和系列化更新。',
                  creatorSignals: ['系列化', '剧情驱动'],
                },
              },
              userNotes: '',
              fileUrl: '/api/media-assets/media-workflow-1/file',
              createdAt: '2026-07-11T12:00:00Z',
              updatedAt: '2026-07-11T12:00:00Z',
            },
          ])
        }
        if (
          url === '/api/workspaces/workspace-1/analysis-runs' &&
          method === 'GET'
        ) {
          return jsonResponse([])
        }
        if (
          url === '/api/workspaces/workspace-1/simulation-runs' &&
          method === 'GET'
        ) {
          return jsonResponse([])
        }
        if (url === '/api/workspaces/workspace-1/skills' && method === 'GET') {
          return jsonResponse([])
        }
        if (url === '/api/workspaces/workspace-1/agents' && method === 'GET') {
          return jsonResponse([])
        }
        if (
          url === '/api/workspaces/workspace-1/agent-conversations' &&
          method === 'GET'
        ) {
          return jsonResponse([])
        }
        if (url === '/api/workspaces/workspace-1/workflows' && method === 'GET') {
          return jsonResponse([])
        }
        if (url === '/api/workspaces/workspace-1/drafts' && method === 'GET') {
          return jsonResponse([])
        }
        if (url === '/api/workspaces/workspace-1/topics' && method === 'GET') {
          return jsonResponse([])
        }
        if (
          url === '/api/workspaces/workspace-1/input-assets' &&
          method === 'POST'
        ) {
          const body = JSON.parse(String(init?.body)) as {
            type: 'account_profile' | 'video_creator_samples'
            name: string
            content: string
          }
          if (body.type === 'account_profile') {
            expect(body.name).toBe('AIGC视频创作者激励计划')
          } else {
            expect(body.content).toContain('@AI短剧研究所')
          }
          return jsonResponse(
            {
              id: body.type === 'account_profile' ? 'new-video-profile' : 'new-video-samples',
              workspaceId: 'workspace-1',
              type: body.type,
              name: body.name,
              content: body.content,
              createdAt: '2026-07-11T12:00:00Z',
              updatedAt: '2026-07-11T12:00:00Z',
            },
            201,
          )
        }
        if (
          url === '/api/workspaces/workspace-1/analysis-runs' &&
          method === 'POST'
        ) {
          const body = JSON.parse(String(init?.body)) as {
            workflowType?: string
            accountProfileInputAssetId?: string
            videoCreatorSamplesInputAssetId?: string
            mediaAssetIds?: string[]
          }
          expect(body.workflowType).toBe('video_creator_quality')
          expect(body.accountProfileInputAssetId).toBe('new-video-profile')
          expect(body.videoCreatorSamplesInputAssetId).toBe('new-video-samples')
          expect(body.mediaAssetIds).toEqual(['media-workflow-1'])
          return jsonResponse(
            {
              id: 'run-video',
              workspaceId: 'workspace-1',
              workflowType: 'video_creator_quality',
              status: 'running',
              inputSnapshot: {},
              stageResults: {},
              stageErrors: {},
              modelMetadata: { mode: 'demo' },
              createdAt: '2026-07-11T12:00:00Z',
              startedAt: null,
              completedAt: null,
              updatedAt: '2026-07-11T12:00:00Z',
            },
            201,
          )
        }
        if (url === '/api/analysis-runs/run-video' && method === 'GET') {
          return jsonResponse({
            id: 'run-video',
            workspaceId: 'workspace-1',
            workflowType: 'video_creator_quality',
            status: 'completed',
            inputSnapshot: {},
            stageResults: {},
            stageErrors: {},
            modelMetadata: { mode: 'demo' },
            createdAt: '2026-07-11T12:00:00Z',
            startedAt: '2026-07-11T12:00:00Z',
            completedAt: '2026-07-11T12:00:01Z',
            updatedAt: '2026-07-11T12:00:01Z',
          })
        }
        throw new Error(`Unexpected request: ${method} ${url}`)
      })

    render(<App />)
    await openCreatorAssetTab(/视频创作样本/)
    fireEvent.click(screen.getByRole('button', { name: /新建视频创作样本/ }))
    fireEvent.change(
      await screen.findByLabelText(
        '视频创作样本（创作者背景、视频样本、互动数据、运营备注）',
      ),
      {
        target: {
          value: '创作者：@AI短剧研究所\n运营备注：剧情内容催更多。',
        },
      },
    )

    expect(
      fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST'),
    ).toHaveLength(0)

    fireEvent.click(screen.getByRole('button', { name: /视频博主质量诊断/ }))
    fireEvent.click(await screen.findByLabelText(/AI短剧主页截图/))
    fireEvent.click(screen.getByRole('button', { name: '⚡ 生成视频创作者诊断' }))

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST'),
      ).toHaveLength(3)
    })
  })

  it('opens a saved analysis run from history', async () => {
    installWorkspaceApiMock()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /分析结果/ }))
    const historyList = await screen.findByText('◷ 分析结果')
    fireEvent.click(
      within(historyList.closest('section') as HTMLElement).getByRole('button', {
        name: /账号诊断/,
      }),
    )

    expect(await screen.findByText('原始输入快照')).toBeInTheDocument()
    expect(screen.getByText('中介费到底该花在哪三步')).toBeInTheDocument()
  })

  it.each(['success','failure'] as const)('analysis history ignores late %s after selecting another record', async late => {
    const fetchMock=installWorkspaceApiMock()
    const original=fetchMock.getMockImplementation()!
    let resolve!:(response:Response)=>void
    fetchMock.mockImplementation(async(input,init)=>{
      const url=String(input)
      if(url==='/api/analysis-runs/run-1') return new Promise<Response>(done=>{resolve=done})
      if(url==='/api/analysis-runs/run-new') {
        const body=await (await original('/api/analysis-runs/run-1',{method:'GET'})).json()
        return jsonResponse({...body,id:'run-new',userNotes:'当前选择'})
      }
      const response=await original(input,init)
      if(url==='/api/workspaces/workspace-1/analysis-runs') {
        const rows=await response.json()
        return jsonResponse([...rows,{...rows[0],id:'run-new'}])
      }
      return response
    })
    render(<App />)
    fireEvent.click(await screen.findByRole('button',{name:/分析结果/}))
    const list=(await screen.findByText('◷ 分析结果')).closest('section') as HTMLElement
    const buttons=within(list).getAllByRole('button')
    fireEvent.click(buttons[0]);fireEvent.click(buttons[1])
    expect(await screen.findByDisplayValue('当前选择')).toBeInTheDocument()
    const body=await (await original('/api/analysis-runs/run-1',{method:'GET'})).json()
    await act(async()=>resolve(await (late==='success'
      ? jsonResponse({...body,userNotes:'过期选择'}) : jsonResponse({detail:'过期读取失败'},503))))
    expect(screen.getByDisplayValue('当前选择')).toBeInTheDocument()
    expect(screen.queryByDisplayValue('过期选择')).not.toBeInTheDocument()
    expect(screen.queryByText(/过期读取失败/)).not.toBeInTheDocument()
  })

  it('analysis history reports failed reads and retries only the GET', async()=>{
    const fetchMock=installWorkspaceApiMock()
    const original=fetchMock.getMockImplementation()!
    let fail=true
    fetchMock.mockImplementation((input,init)=>String(input)==='/api/analysis-runs/run-1' && fail
      ? Promise.resolve(jsonResponse({detail:'读取暂时失败'},503)) : original(input,init))
    render(<App />)
    fireEvent.click(await screen.findByRole('button',{name:/分析结果/}))
    const list=(await screen.findByText('◷ 分析结果')).closest('section') as HTMLElement
    fireEvent.click(within(list).getByRole('button'))
    expect(await screen.findByRole('alert')).toHaveTextContent('读取暂时失败')
    fail=false
    fireEvent.click(within(list).getByRole('button'))
    expect(await screen.findByLabelText('复盘备注')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(fetchMock.mock.calls.filter(([,init])=>init?.method==='POST')).toHaveLength(0)
  })

  it.each([{workspaceId:'wrong-account'},{id:'wrong-run'}])('analysis history rejects mismatched receipt %j',async mismatch=>{
    const fetchMock=installWorkspaceApiMock()
    const original=fetchMock.getMockImplementation()!
    fetchMock.mockImplementation(async(input,init)=>{
      const response=await original(input,init)
      return String(input)==='/api/analysis-runs/run-1'
        ? jsonResponse({...await response.json(),...mismatch}) : response
    })
    render(<App />)
    fireEvent.click(await screen.findByRole('button',{name:/分析结果/}))
    const list=(await screen.findByText('◷ 分析结果')).closest('section') as HTMLElement
    fireEvent.click(within(list).getByRole('button'))
    expect(await screen.findByRole('alert')).toHaveTextContent('与当前选择不一致')
    expect(screen.queryByLabelText('复盘备注')).not.toBeInTheDocument()
  })

  it('analysis history discards an old read after an account round trip',async()=>{
    window.history.pushState({},'','/')
    const fetchMock=installWorkspaceApiMock()
    const original=fetchMock.getMockImplementation()!
    let resolve!:(response:Response)=>void
    fetchMock.mockImplementation((input,init)=>String(input)==='/api/analysis-runs/run-1'
      ? new Promise<Response>(done=>{resolve=done}) : original(input,init))
    render(<App />)
    await waitFor(()=>expect(screen.getByLabelText('当前账号档案')).toBeEnabled())
    fireEvent.click(await screen.findByRole('button',{name:/分析历史/}))
    const list=(await screen.findByText('◷ 分析结果')).closest('section') as HTMLElement
    fireEvent.click(within(list).getByRole('button'))
    await screen.findByText('正在读取分析记录…')
    fireEvent.change(screen.getByLabelText('当前账号档案'),{target:{value:'workspace-2'}})
    await waitFor(()=>expect(screen.getByLabelText('当前账号档案')).toBeEnabled())
    fireEvent.change(screen.getByLabelText('当前账号档案'),{target:{value:'workspace-1'}})
    await waitFor(()=>expect(screen.getByLabelText('当前账号档案')).toBeEnabled())
    fireEvent.click(screen.getByRole('button',{name:/分析历史/}))
    await act(async()=>resolve(await original('/api/analysis-runs/run-1',{method:'GET'})))
    expect(screen.queryByText('中介费到底该花在哪三步')).not.toBeInTheDocument()
    expect(screen.queryByText('正在读取分析记录…')).not.toBeInTheDocument()
  })

  async function delayedAnalysisReview(publicMode=false) {
    if(publicMode) window.history.pushState({},'','/')
    const fetchMock=installWorkspaceApiMock()
    const original=fetchMock.getMockImplementation()!
    const saved=await (await original('/api/analysis-runs/run-1',{method:'GET'})).json()
    const pending:Array<{body:Record<string,unknown>;resolve:(response:Response)=>void}>=[]
    fetchMock.mockImplementation((input,init)=>{
      if(String(input)==='/api/analysis-runs/run-1/review') return new Promise<Response>(resolve=>pending.push({body:JSON.parse(String(init?.body)),resolve}))
      if(String(input)==='/api/workspaces/workspace-1/analysis-runs') return jsonResponse([analysisRuns['workspace-1'][0],{...analysisRuns['workspace-1'][0],id:'other'}])
      if(String(input)==='/api/analysis-runs/other') return jsonResponse({...saved,id:'other',userNotes:'另一报告的备注'})
      return original(input,init)
    })
    render(<App/> )
    if(publicMode) await screen.findByRole('button',{name:'开始导入'})
    fireEvent.click(await screen.findByRole('button',{name:publicMode?/分析历史/:/分析结果/}))
    const list=(await screen.findByText('◷ 分析结果')).closest('section') as HTMLElement
    const open=within(list).getAllByRole('button')[0]
    fireEvent.click(open)
    await screen.findByLabelText('复盘备注')
    if(publicMode) fireEvent.click(screen.getByText('复盘备注',{selector:'summary'}))
    return {saved,pending,list,open}
  }

  it('analysis review keeps edits made during save and uses the returned version next time',async()=>{
    const {saved,pending}=await delayedAnalysisReview()
    fireEvent.change(screen.getByLabelText('复盘备注'),{target:{value:'本次提交'}})
    fireEvent.click(screen.getByRole('button',{name:'保存复盘'}))
    fireEvent.change(screen.getByLabelText('复盘备注'),{target:{value:'继续编辑'}})
    fireEvent.change(screen.getByLabelText('复盘状态'),{target:{value:'useful'}})
    await act(async()=>pending[0].resolve(await jsonResponse({...saved,userNotes:'本次提交',updatedAt:'2026-10-04T02:00:00Z'})))
    expect(screen.getByLabelText('复盘备注')).toHaveValue('继续编辑')
    expect(screen.getByLabelText('复盘状态')).toHaveValue('useful')
    expect(screen.getByText('已保存上次提交，当前修改尚未保存')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'保存复盘'}))
    expect(pending[1].body).toMatchObject({userNotes:'继续编辑',reviewStatus:'useful',expectedUpdatedAt:'2026-10-04T02:00:00Z'})
    await act(async()=>pending[1].resolve(await jsonResponse({...saved,...pending[1].body})))
  })

  it.each(['success','failure'] as const)('analysis review ignores late %s after reopening',async outcome=>{
    const {saved,pending,open}=await delayedAnalysisReview()
    fireEvent.click(screen.getByRole('button',{name:'保存复盘'}))
    fireEvent.click(open)
    await waitFor(()=>expect(screen.queryByText('正在读取分析记录…')).not.toBeInTheDocument())
    fireEvent.change(screen.getByLabelText('复盘备注'),{target:{value:'重新打开后的编辑'}})
    await act(async()=>pending[0].resolve(await (outcome==='success'
      ? jsonResponse({...saved,userNotes:'旧回执'}) : jsonResponse({detail:'旧保存错误'},409))))
    expect(screen.getByLabelText('复盘备注')).toHaveValue('重新打开后的编辑')
    expect(screen.queryByText('旧保存错误')).not.toBeInTheDocument()
  })

  it('analysis review does not replace another selected report',async()=>{
    const {saved,pending,list}=await delayedAnalysisReview()
    fireEvent.click(screen.getByRole('button',{name:'保存复盘'}))
    fireEvent.click(within(list).getAllByRole('button')[1])
    await screen.findByDisplayValue('另一报告的备注')
    await act(async()=>pending[0].resolve(await jsonResponse({...saved,userNotes:'旧报告保存成功'})))
    expect(screen.getByLabelText('复盘备注')).toHaveValue('另一报告的备注')
    expect(within(list).getAllByRole('button')[1]).toHaveClass('active')
  })

  it('analysis review ignores a save from the previous account',async()=>{
    const {saved,pending}=await delayedAnalysisReview(true)
    fireEvent.click(screen.getByRole('button',{name:'保存复盘'}))
    fireEvent.change(screen.getByLabelText('当前账号档案'),{target:{value:'workspace-2'}})
    await waitFor(()=>expect(screen.getByLabelText('当前账号档案')).toBeEnabled())
    fireEvent.click(screen.getByRole('button',{name:/分析历史/}))
    await act(async()=>pending[0].resolve(await jsonResponse({...saved,userNotes:'上个账号的备注'})))
    expect(screen.queryByLabelText('复盘备注')).not.toBeInTheDocument()
  })

  it.each([{id:'wrong'},{workspaceId:'wrong'}])('analysis review rejects a mismatched receipt %j',async mismatch=>{
    const {saved,pending}=await delayedAnalysisReview()
    fireEvent.change(screen.getByLabelText('复盘备注'),{target:{value:'保留编辑'}})
    fireEvent.click(screen.getByRole('button',{name:'保存复盘'}))
    await act(async()=>pending[0].resolve(await jsonResponse({...saved,...mismatch,userNotes:'不属于本次的内容'})))
    expect(screen.getByLabelText('复盘备注')).toHaveValue('保留编辑')
    expect(screen.getByText('保存回执与当前分析记录不一致，请重新核对。')).toBeInTheDocument()
  })

  it('analysis review prevents duplicate submits and preserves input on conflict',async()=>{
    const {saved,pending}=await delayedAnalysisReview()
    fireEvent.change(screen.getByLabelText('复盘备注'),{target:{value:'待保存备注'}})
    const button=screen.getByRole('button',{name:'保存复盘'})
    fireEvent.click(button);fireEvent.click(button)
    expect(pending).toHaveLength(1)
    await act(async()=>pending[0].resolve(await jsonResponse({detail:'版本冲突，请核对'},409)))
    expect(screen.getByLabelText('复盘备注')).toHaveValue('待保存备注')
    expect(screen.getByText('版本冲突，请核对')).toBeInTheDocument()
    fireEvent.click(button)
    expect(pending[1].body.expectedUpdatedAt).toBe(saved.updatedAt)
    await act(async()=>pending[1].resolve(await jsonResponse({...saved,userNotes:'待保存备注'})))
  })

  it('saves review metadata for a saved analysis run', async () => {
    const fetchMock = installWorkspaceApiMock()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /分析结果/ }))
    const historyList = await screen.findByText('◷ 分析结果')
    fireEvent.click(
      within(historyList.closest('section') as HTMLElement).getByRole('button', {
        name: /账号诊断/,
      }),
    )

    fireEvent.change(await screen.findByLabelText('复盘状态'), {
      target: { value: 'useful' },
    })
    fireEvent.change(screen.getByLabelText('复盘备注'), {
      target: { value: '这个诊断可以作为示例结果复用。' },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存复盘' }))

    await screen.findByDisplayValue('这个诊断可以作为示例结果复用。')
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) =>
            String(url) === '/api/analysis-runs/run-1/review' &&
            init?.method === 'PATCH',
        ),
      ).toBe(true)
    })
    expect(screen.getAllByText('已保存').length).toBeGreaterThan(0)
  })

  it('opens and edits a topic from the library', async () => {
    installWorkspaceApiMock('workspace-2')
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /选题库/ }))

    fireEvent.click(await screen.findByRole('button', { name: /数字游民/ }))
    const title = await screen.findByLabelText('标题')
    fireEvent.change(title, { target: { value: '非技术人如何开始数字游民' } })
    fireEvent.click(screen.getByRole('button', { name: '保存选题资产' }))

    await waitFor(() => {
      expect(screen.getAllByText('已保存').length).toBeGreaterThan(0)
    })
    expect(screen.getByDisplayValue('非技术人如何开始数字游民')).toBeInTheDocument()
  })

  it('generates a content brief from a selected topic', async () => {
    installWorkspaceApiMock('workspace-2')
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /选题库/ }))
    fireEvent.click(await screen.findByRole('button', { name: /数字游民/ }))
    fireEvent.click(await screen.findByRole('button', { name: /生成创作 Brief/ }))

    expect(await screen.findByText('▱ 创作输出')).toBeInTheDocument()
    expect(await screen.findByText(/创作 Brief · completed/)).toBeInTheDocument()
    expect(screen.getByText('先选可验证路径，再谈长期迁移')).toBeInTheDocument()
    expect(
      (screen.getByLabelText('Editable Content JSON') as HTMLTextAreaElement).value,
    ).toContain('"corePoint": "先选可验证路径，再谈长期迁移"')

    fireEvent.click(screen.getByRole('button', { name: /继续生成内容结构/ }))

    expect(await screen.findByText(/内容结构 · completed/)).toBeInTheDocument()
    expect(screen.getByText('从 Brief 进入结构')).toBeInTheDocument()
    expect(
      (screen.getByLabelText('Editable Content JSON') as HTMLTextAreaElement).value,
    ).toContain('"reuse": "Brief 对齐 → 结构拆解 → 行动清单"')
  })

  it('separates context assets from capability assets and hides content drafts navigation', async () => {
    installWorkspaceApiMock()
    render(<App />)

    expect(screen.queryByText('Input Assets')).not.toBeInTheDocument()
    expect(screen.queryByText('Reusable Outputs')).not.toBeInTheDocument()
    expect(screen.queryByText('Capability Assets')).not.toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /创作者档案/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /分析结果/ })).toBeInTheDocument()
    expect(screen.getAllByText('能力资产').length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: /Skills/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Agents/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Workflows/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /创作输出/ })).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /Content Drafts/ }),
    ).not.toBeInTheDocument()
    expect(screen.queryByText('Content Drafts')).not.toBeInTheDocument()
  })

  it('shows overall and page-specific help from the topbar help entry', async () => {
    installWorkspaceApiMock()
    render(<App />)

    const helpButton = await screen.findByRole('button', { name: '帮助' })
    expect(helpButton).toHaveAttribute('aria-expanded', 'false')

    fireEvent.click(helpButton)

    expect(helpButton).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('整体说明')).toBeInTheDocument()
    expect(screen.getByText('账号诊断帮助')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /热点分析/ }))

    expect(screen.getByText('热点分析帮助')).toBeInTheDocument()
    expect(screen.getByText(/热点分析会读取账号概况/)).toBeInTheDocument()
  })

  it('opens a saved audience simulation from history', async () => {
    installWorkspaceApiMock('workspace-2')
    render(<App />)

    fireEvent.click(
      await screen.findByRole('button', { name: /受众模拟/ }),
    )
    const simulationList = await screen.findByText('👥 受众模拟')
    fireEvent.click(
      within(simulationList.closest('section') as HTMLElement).getByRole('button', {
        name: /受众模拟/,
      }),
    )

    expect(await screen.findByText('模拟结果')).toBeInTheDocument()
    expect(screen.getAllByRole('heading', { name: '谨慎执行派' })).toHaveLength(2)
    expect(screen.getByText('真实前提 + 分阶段路径')).toBeInTheDocument()
  })

  it.each(['success', 'failure'] as const)('ignores a late simulation history %s after a newer selection', async (late) => {
    const fetchMock = installWorkspaceApiMock('workspace-2')
    const original = fetchMock.getMockImplementation()!
    const pending: Array<(response: Response) => void> = []
    fetchMock.mockImplementation((input, init) => String(input) === '/api/simulation-runs/simulation-2'
      ? new Promise<Response>(resolve => pending.push(resolve)) : original(input, init))
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: /受众模拟/ }))
    const list = (await screen.findByText('👥 受众模拟')).closest('section') as HTMLElement
    const open = within(list).getByRole('button', { name: /受众模拟/ })
    fireEvent.click(open)
    fireEvent.click(open)
    await waitFor(() => expect(pending).toHaveLength(2))
    const response = await original('/api/simulation-runs/simulation-2', { method: 'GET' })
    const body = await response.json()
    await act(async () => pending[1](await jsonResponse({...body,userNotes:'最新选择的备注'})))
    expect(await screen.findByDisplayValue('最新选择的备注')).toBeInTheDocument()
    await act(async () => pending[0](await (late === 'success'
      ? jsonResponse({...body,userNotes:'过时的备注'})
      : jsonResponse({detail:'过时的错误'},500))))
    expect(screen.getByDisplayValue('最新选择的备注')).toBeInTheDocument()
    expect(screen.queryByDisplayValue('过时的备注')).not.toBeInTheDocument()
    expect(screen.queryByText(/过时的错误/)).not.toBeInTheDocument()
  })

  it('shows a simulation history read failure and allows retry without a model call', async () => {
    const fetchMock = installWorkspaceApiMock('workspace-2')
    const original = fetchMock.getMockImplementation()!
    let fail = true
    fetchMock.mockImplementation((input, init) => String(input) === '/api/simulation-runs/simulation-2' && fail
      ? Promise.resolve(jsonResponse({detail:'历史读取失败'},503)) : original(input, init))
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: /受众模拟/ }))
    const list = (await screen.findByText('👥 受众模拟')).closest('section') as HTMLElement
    fireEvent.click(within(list).getByRole('button', { name: /受众模拟/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('历史读取失败')
    fail = false
    fireEvent.click(within(list).getByRole('button', { name: /受众模拟/ }))
    expect(await screen.findByText('模拟结果')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(fetchMock.mock.calls.filter(([url, init]) => String(url).includes('simulation-runs') && init?.method === 'POST')).toHaveLength(0)
  })

  it('invalidates a simulation history request across an account round trip', async () => {
    window.history.pushState({}, '', '/')
    const fetchMock = installWorkspaceApiMock('workspace-2')
    const original = fetchMock.getMockImplementation()!
    let resolve!: (response: Response) => void
    fetchMock.mockImplementation((input, init) => String(input) === '/api/simulation-runs/simulation-2'
      ? new Promise<Response>(done => { resolve = done }) : original(input, init))
    render(<App />)
    await screen.findByRole('button', { name: '开始导入' })
    fireEvent.click(within(await screen.findByRole('navigation', {name: '创作者功能导航'})).getByRole('button', {name: '受众模拟'}))
    fireEvent.click(screen.getByRole('tab', {name:/创作级/}))
    const list = (await screen.findByText('历史记录')).closest('section') as HTMLElement
    fireEvent.click(within(list).getByRole('button', { name: /受众模拟/ }))
    await screen.findByText('正在读取模拟记录…')
    fireEvent.change(screen.getByLabelText('当前账号档案'), {target:{value:'workspace-1'}})
    await waitFor(() => expect(screen.getByLabelText('当前账号档案')).toBeEnabled())
    fireEvent.change(screen.getByLabelText('当前账号档案'), {target:{value:'workspace-2'}})
    await waitFor(() => expect(screen.getByLabelText('当前账号档案')).toBeEnabled())
    fireEvent.click(within(screen.getByRole('navigation', {name: '创作者功能导航'})).getByRole('button', {name: '受众模拟'}))
    const response = await original('/api/simulation-runs/simulation-2', {method:'GET'})
    await act(async () => resolve(response))
    expect(screen.queryByText('真实前提 + 分阶段路径')).not.toBeInTheDocument()
    expect(screen.queryByText('正在读取模拟记录…')).not.toBeInTheDocument()
  })

  it.each([{workspaceId:'another-account'},{id:'another-run'}])('rejects a mismatched simulation history response %j', async mismatch => {
    const fetchMock = installWorkspaceApiMock('workspace-2')
    const original = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation(async (input, init) => {
      const response = await original(input, init)
      return String(input) === '/api/simulation-runs/simulation-2'
        ? jsonResponse({...await response.json(), ...mismatch}) : response
    })
    render(<App />)
    fireEvent.click(await screen.findByRole('button', {name:/受众模拟/}))
    const list = (await screen.findByText('👥 受众模拟')).closest('section') as HTMLElement
    fireEvent.click(within(list).getByRole('button', {name:/受众模拟/}))
    expect(await screen.findByRole('alert')).toHaveTextContent('与当前选择不一致')
    expect(screen.queryByText('真实前提 + 分阶段路径')).not.toBeInTheDocument()
  })

  async function delayedSimulationReview(publicMode = false, secondRun = false) {
    if (publicMode) window.history.pushState({}, '', '/')
    const fetchMock = installWorkspaceApiMock('workspace-2')
    const original = fetchMock.getMockImplementation()!
    const pending: Array<{body: Record<string, unknown>; resolve: (response: Response) => void}> = []
    const saved = await (await original('/api/simulation-runs/simulation-2', {method:'GET'})).json()
    fetchMock.mockImplementation((input, init) => {
      if (secondRun && String(input) === '/api/workspaces/workspace-2/simulation-runs') {
        return jsonResponse([simulationRuns['workspace-2'][0], {...simulationRuns['workspace-2'][0],id:'simulation-3'}])
      }
      if (secondRun && String(input) === '/api/simulation-runs/simulation-3') {
        return jsonResponse({...saved,id:'simulation-3',userNotes:'第二次模拟的备注'})
      }
      if (String(input).endsWith('/simulation-2/review')) {
        return new Promise<Response>(resolve => pending.push({body:JSON.parse(String(init?.body)),resolve}))
      }
      return original(input, init)
    })
    render(<App />)
    if (publicMode) await screen.findByRole('button', {name:'开始导入'})
    fireEvent.click(within(await screen.findByRole('navigation', {name: publicMode ? '创作者功能导航' : '内容资产导航'})).getByRole('button', {name:/受众模拟/}))
    if (publicMode) fireEvent.click(screen.getByRole('tab', {name:/创作级/}))
    const list = (await screen.findByText(publicMode?'历史记录':'👥 受众模拟')).closest('section') as HTMLElement
    const open = within(list).getAllByRole('button', {name:/受众模拟/})[0]
    fireEvent.click(open)
    await screen.findByLabelText('复盘备注')
    if (publicMode) fireEvent.click(screen.getByText('复盘备注', {selector:'summary'}))
    return {pending,saved,open,list}
  }

  it('simulation review preserves edits during save and advances the next save version', async () => {
    const {pending,saved} = await delayedSimulationReview()
    fireEvent.change(screen.getByLabelText('复盘备注'), {target:{value:'第一次提交'}})
    fireEvent.click(screen.getByRole('button', {name:'保存复盘'}))
    fireEvent.change(screen.getByLabelText('复盘备注'), {target:{value:'期间继续写的新备注'}})
    fireEvent.change(screen.getByLabelText('复盘状态'), {target:{value:'useful'}})
    await act(async () => pending[0].resolve(await jsonResponse({...saved,userNotes:'第一次提交',updatedAt:'2026-10-04T01:00:00Z'})))
    expect(screen.getByLabelText('复盘备注')).toHaveValue('期间继续写的新备注')
    expect(screen.getByLabelText('复盘状态')).toHaveValue('useful')
    expect(screen.getAllByText(/当前修改尚未保存/).length).toBeGreaterThan(0)
    fireEvent.click(screen.getByRole('button', {name:'保存复盘'}))
    expect(pending[1].body).toMatchObject({userNotes:'期间继续写的新备注',reviewStatus:'useful',expectedUpdatedAt:'2026-10-04T01:00:00Z'})
    await act(async () => pending[1].resolve(await jsonResponse({...saved,...pending[1].body})))
  })

  it.each(['success','failure'] as const)('simulation review ignores a late %s after reopening history', async result => {
    const {pending,saved,open} = await delayedSimulationReview()
    fireEvent.change(screen.getByLabelText('复盘备注'), {target:{value:'旧提交'}})
    fireEvent.click(screen.getByRole('button', {name:'保存复盘'}))
    fireEvent.click(open)
    await waitFor(() => expect(screen.getByLabelText('复盘备注')).toHaveValue(saved.userNotes))
    fireEvent.change(screen.getByLabelText('复盘备注'), {target:{value:'重新打开后的备注'}})
    await act(async () => pending[0].resolve(await (result==='success'
      ? jsonResponse({...saved,userNotes:'旧提交'}) : jsonResponse({detail:'迟到保存失败'},409))))
    expect(screen.getByLabelText('复盘备注')).toHaveValue('重新打开后的备注')
    expect(screen.queryByText('迟到保存失败')).not.toBeInTheDocument()
  })

  it('simulation review prevents duplicate saves and retains input after a conflict', async () => {
    const {pending,saved} = await delayedSimulationReview()
    fireEvent.change(screen.getByLabelText('复盘备注'), {target:{value:'保留我的备注'}})
    const button = screen.getByRole('button', {name:'保存复盘'})
    fireEvent.click(button)
    fireEvent.click(button)
    expect(pending).toHaveLength(1)
    await act(async () => pending[0].resolve(await jsonResponse({detail:'版本已变化，请重新核对'},409)))
    expect(screen.getByLabelText('复盘备注')).toHaveValue('保留我的备注')
    expect(screen.getAllByText('版本已变化，请重新核对').length).toBeGreaterThan(0)
    fireEvent.click(button)
    expect(pending).toHaveLength(2)
    expect(pending[1].body.expectedUpdatedAt).toBe(saved.updatedAt)
    await act(async () => pending[1].resolve(await jsonResponse({...saved,userNotes:'保留我的备注'})))
  })

  it('simulation review does not reappear after changing accounts', async () => {
    const {pending,saved} = await delayedSimulationReview(true)
    fireEvent.click(screen.getByRole('button', {name:'保存复盘'}))
    fireEvent.change(screen.getByLabelText('当前账号档案'), {target:{value:'workspace-1'}})
    await waitFor(() => expect(screen.getByLabelText('当前账号档案')).toBeEnabled())
    fireEvent.click(within(screen.getByRole('navigation', {name: '创作者功能导航'})).getByRole('button', {name: '受众模拟'}))
    await act(async () => pending[0].resolve(await jsonResponse({...saved,userNotes:'其他账号的旧提交'})))
    expect(screen.queryByDisplayValue('其他账号的旧提交')).not.toBeInTheDocument()
    expect(screen.queryByText('本次读者')).not.toBeInTheDocument()
  })

  it('simulation review never replaces a different selected run with a late save', async () => {
    const {pending,saved,list} = await delayedSimulationReview(false,true)
    fireEvent.click(screen.getByRole('button', {name:'保存复盘'}))
    fireEvent.click(within(list).getAllByRole('button', {name:/受众模拟/})[1])
    await screen.findByDisplayValue('第二次模拟的备注')
    fireEvent.change(screen.getByLabelText('复盘备注'), {target:{value:'第二次模拟的新编辑'}})
    await act(async () => pending[0].resolve(await jsonResponse({...saved,userNotes:'第一条保存回执'})))
    expect(screen.getByLabelText('复盘备注')).toHaveValue('第二次模拟的新编辑')
    expect(within(list).getAllByRole('button')[1]).toHaveClass('active')
  })

  it('simulation review rejects a receipt for another account without replacing the draft', async () => {
    const {pending,saved} = await delayedSimulationReview()
    fireEvent.change(screen.getByLabelText('复盘备注'), {target:{value:'我的备注'}})
    fireEvent.click(screen.getByRole('button', {name:'保存复盘'}))
    await act(async () => pending[0].resolve(await jsonResponse({...saved,workspaceId:'wrong',userNotes:'别人的备注'})))
    expect(screen.getByLabelText('复盘备注')).toHaveValue('我的备注')
    expect(screen.getAllByText('保存回执与当前模拟记录不一致，请重新核对。').length).toBeGreaterThan(0)
  })

  it('saves review metadata for a saved audience simulation', async () => {
    const fetchMock = installWorkspaceApiMock('workspace-2')
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /受众模拟/ }))
    const simulationList = await screen.findByText('👥 受众模拟')
    fireEvent.click(
      within(simulationList.closest('section') as HTMLElement).getByRole('button', {
        name: /受众模拟/,
      }),
    )

    fireEvent.change(await screen.findByLabelText('复盘状态'), {
      target: { value: 'rejected' },
    })
    fireEvent.change(screen.getByLabelText('复盘备注'), {
      target: { value: '角色反应不够尖锐，暂时弃用。' },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存复盘' }))

    await screen.findByDisplayValue('角色反应不够尖锐，暂时弃用。')
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) =>
            String(url) === '/api/simulation-runs/simulation-2/review' &&
            init?.method === 'PATCH',
        ),
      ).toBe(true)
    })
    expect(screen.getAllByText('已保存').length).toBeGreaterThan(0)
  })
})
