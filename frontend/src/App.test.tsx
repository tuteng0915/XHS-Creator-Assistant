import {
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
  AgentConversationSummary,
  AgentSummary,
  AnalysisRunSummary,
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
      name: '视频创作者样本',
      content: '创作者：@AI短剧研究所\n运营备注：剧情内容催更多，商单互动低。',
      createdAt: '2026-07-11T11:00:00Z',
      updatedAt: '2026-07-11T11:00:00Z',
    },
  ],
}

const analysisRuns: Record<string, AnalysisRunSummary[]> = {
  'workspace-1': [
    {
      id: 'run-1',
      workspaceId: 'workspace-1',
      workflowType: 'account_diagnosis',
      status: 'completed',
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

const commentsFormatterSkill: SkillSummary = {
  ...skillSummary,
  id: 'skill-format-comments',
  skillId: 'input_asset.format_comments',
  displayName: 'Format Comment Samples',
  category: 'input_asset',
  purpose: 'Format pasted comments into an editable draft.',
  artifactEffect: 'Draft InputAsset.comments',
}

const skills: Record<string, SkillSummary[]> = {
  'workspace-1': [skillSummary, commentsFormatterSkill],
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

const agents: Record<string, AgentSummary[]> = {
  'workspace-1': [agentSummary],
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
  updatedAt: '2026-07-11T12:00:00Z',
}

const workflowAssets: Record<string, WorkflowAssetSummary[]> = {
  'workspace-1': [workflowSummary],
  'workspace-2': [
    {
      ...workflowSummary,
      id: 'workflow-trend',
      workspaceId: 'workspace-2',
      workflowId: 'trend_analysis',
      displayName: 'Trend Analysis Workflow',
      entryAgentIds: ['creator_material_curator', 'trend_opportunity_strategist'],
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
    const textCsvImportMatch = url.match(
      /^\/api\/workspaces\/(workspace-[12])\/input-assets\/text-csv$/,
    )
    if (textCsvImportMatch && method === 'POST') {
      const form = init?.body as FormData
      const type = form.get('type') as InputAsset['type']
      return jsonResponse(
        {
          materials: [
            {
              id: `imported-${type}`,
              workspaceId: textCsvImportMatch[1],
              type,
              name: '批量导入资产',
              content: '批量导入内容',
              createdAt: '2026-07-11T15:00:00Z',
              updatedAt: '2026-07-11T15:00:00Z',
            },
          ],
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
      return jsonResponse(skillDetail)
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
      return jsonResponse({ ...conversation, messages: [] })
    }
    if (
      url === '/api/agent-conversations/conversation-1/messages' &&
      method === 'POST'
    ) {
      const body = JSON.parse(String(init?.body)) as {
        content: string
        mode: 'demo' | 'live'
      }
      const conversation = agentConversations['workspace-1'][0]
      return jsonResponse({
        ...conversation,
        messages: [
          {
            id: 'message-user',
            conversationId: 'conversation-1',
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
        ],
      })
    }
    if (url === '/api/agents/agent-account' && method === 'GET') {
      return jsonResponse(agentDetail)
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
  window.history.pushState({}, '', '/')
  agentConversations['workspace-1'] = []
  agentConversations['workspace-2'] = []
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  cleanup()
})

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
    fireEvent.click((await screen.findAllByRole('button', { name: /账号概况/ }))[0])
    expect(
      await screen.findByDisplayValue('帮助文科生做留学决策。'),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /载入/ })).not.toBeInTheDocument()
    fireEvent.click(screen.getAllByRole('button', { name: /历史笔记/ })[0])
    expect(await screen.findByLabelText('历史笔记名称')).toHaveValue(
      '留学帖子数据合集',
    )
    expect(
      await screen.findByDisplayValue('留学中介到底值不值｜赞1.1k｜爆'),
    ).toBeInTheDocument()
    fireEvent.click(screen.getAllByRole('button', { name: /评论样本/ })[0])
    expect(await screen.findByLabelText('评论样本名称')).toHaveValue(
      '留学评论区合集',
    )
    expect(
      screen.getByDisplayValue('双非背景冲英国前30有戏吗？'),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /热点分析/ }))
    expect(await screen.findByText('趋势 CSV')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '管理账号概况' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '管理输入资产' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /视频博主质量诊断/ }))
    await screen.findByText('视频创作者诊断待运行')
    expect(screen.getAllByText('视频创作者样本').length).toBeGreaterThan(0)
  })

  it('prefers a workspace with input assets when the newest workspace is empty', async () => {
    const originalWorkspaceTwoMaterials = materials['workspace-2']
    materials['workspace-2'] = []
    try {
      const fetchMock = installWorkspaceApiMock('workspace-2')
      render(<App />)

      await screen.findByText('账号诊断待运行')
      fireEvent.click((await screen.findAllByRole('button', { name: /历史笔记/ }))[0])

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

    fireEvent.click((await screen.findAllByRole('button', { name: /历史笔记/ }))[0])
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

    fireEvent.click(await screen.findByRole('button', { name: /评论样本/ }))
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

  it('supports batch CSV import for non-profile text input assets', async () => {
    const fetchMock = installWorkspaceApiMock()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /评论样本/ }))
    const file = new File(['name,content\n评论合集,我很焦虑\n'], 'comments.csv', {
      type: 'text/csv',
    })
    fireEvent.change(await screen.findByLabelText('评论样本批量导入（CSV / TSV）'), {
      target: { files: [file] },
    })
    fireEvent.click(screen.getByRole('button', { name: '上传并保存评论样本' }))

    await waitFor(() => {
      const importCall = fetchMock.mock.calls.find(
        ([url, init]) =>
          String(url) === '/api/workspaces/workspace-1/input-assets/text-csv' &&
          init?.method === 'POST',
      )
      expect(importCall).toBeTruthy()
      const body = importCall?.[1]?.body as FormData
      expect(body.get('type')).toBe('comments')
    })
    await waitFor(() => {
      expect(screen.getAllByText('已保存').length).toBeGreaterThan(0)
    })
    expect(screen.getByDisplayValue('批量导入内容')).toBeInTheDocument()
  })

  it('shows workspace skills as product assets', async () => {
    installWorkspaceApiMock()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /Skills/ }))
    expect(await screen.findByText('Analyze Account Profile')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Analyze Account Profile/ }))

    expect(await screen.findByText('analysis.profile_from_history')).toBeInTheDocument()
    expect(screen.getByText('AnalysisRun.stageResults.profile')).toBeInTheDocument()
    expect(screen.getByText('partial_allowed')).toBeInTheDocument()
    expect(screen.getByText('ModelOperation.PROFILE')).toBeInTheDocument()
  })

  it('shows workspace agents as composed product roles', async () => {
    installWorkspaceApiMock()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /Agents/ }))
    expect(
      await screen.findByText('Account Diagnosis Strategist'),
    ).toBeInTheDocument()

    fireEvent.click(
      screen.getByRole('button', { name: /Account Diagnosis Strategist/ }),
    )

    expect(
      await screen.findByText(/creator account strategist/),
    ).toBeInTheDocument()
    expect(screen.getByText('analysis.profile_from_history')).toBeInTheDocument()
    expect(screen.getByText(/selected historical posts/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /开始对话/ }))

    expect(
      await screen.findByText(/发送第一条消息/),
    ).toBeInTheDocument()
    const composer = screen.getByPlaceholderText(/直接和这个 Agent 对话/)
    await waitFor(() => expect(composer).toHaveFocus())
  })

  it('shows workspace workflows as multi-agent task plans', async () => {
    installWorkspaceApiMock()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /Workflows/ }))
    expect(await screen.findByText('Account Diagnosis Workflow')).toBeInTheDocument()

    fireEvent.click(
      screen.getByRole('button', { name: /Account Diagnosis Workflow/ }),
    )

    expect(await screen.findByText('AnalysisRun + Topic candidates')).toBeInTheDocument()
    expect(screen.getByText(/diagnose_account/)).toBeInTheDocument()
    expect(screen.getAllByText(/account_diagnosis_strategist/).length).toBeGreaterThan(0)
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
    fireEvent.click((await screen.findAllByRole('button', { name: /历史笔记/ }))[0])
    const historicalEditor = await screen.findByLabelText(
      '主页 / 历史笔记 + 数据（格式：标题 ｜ 数据 ｜ 爆/平/差）',
    )
    fireEvent.change(historicalEditor, {
      target: { value: '留学中介到底值不值｜赞1.1k｜爆' },
    })
    fireEvent.click(screen.getAllByRole('button', { name: /评论样本/ })[0])
    const commentsEditor = await screen.findByLabelText('评论区原文（一行一条）')
    fireEvent.change(commentsEditor, { target: { value: '这是一条新评论' } })

    expect(
      fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST'),
    ).toHaveLength(0)
    expect(
      screen.queryByRole('button', { name: '保存为评论样本' }),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /账号诊断/ }))
    fireEvent.click(screen.getByRole('button', { name: '⚡ 生成账号诊断' }))

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST'),
      ).toHaveLength(4)
    })
  })

  it('auto-saves video creator samples before creating a video quality run', async () => {
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
    fireEvent.click(await screen.findByRole('button', { name: /视频创作者样本/ }))
    fireEvent.change(
      await screen.findByLabelText(
        '视频创作者样本（创作者背景、视频样本、互动数据、运营备注）',
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

  it('opens and edits a topic from the library', async () => {
    installWorkspaceApiMock('workspace-2')
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /选题库/ }))

    fireEvent.click(await screen.findByRole('button', { name: /文科生如何开始数字游民/ }))
    const title = await screen.findByLabelText('标题')
    fireEvent.change(title, { target: { value: '非技术人如何开始数字游民' } })
    fireEvent.click(screen.getByRole('button', { name: '保存选题编辑' }))

    await waitFor(() => {
      expect(screen.getAllByText('已保存').length).toBeGreaterThan(0)
    })
    expect(screen.getByDisplayValue('非技术人如何开始数字游民')).toBeInTheDocument()
  })

  it('separates context assets from capability assets and hides content drafts navigation', async () => {
    installWorkspaceApiMock()
    render(<App />)

    expect(screen.queryByText('Input Assets')).not.toBeInTheDocument()
    expect(screen.queryByText('Reusable Outputs')).not.toBeInTheDocument()
    expect(screen.queryByText('Capability Assets')).not.toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /账号概况/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /分析结果/ })).toBeInTheDocument()
    expect(screen.getAllByText('能力资产').length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: /Skills/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Agents/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Workflows/ })).toBeInTheDocument()
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
    expect(screen.getByText('谨慎执行派')).toBeInTheDocument()
    expect(screen.getByText('真实前提 + 分阶段路径')).toBeInTheDocument()
  })
})
