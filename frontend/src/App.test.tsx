import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'
import type {
  Agent,
  AgentSummary,
  AnalysisRunSummary,
  DraftSummary,
  SimulationRunSummary,
  Skill,
  SkillSummary,
  SourceMaterial,
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

const materials: Record<string, SourceMaterial[]> = {
  'workspace-1': [
    {
      id: 'history-1',
      workspaceId: 'workspace-1',
      type: 'historical_posts',
      name: '历史笔记',
      content: '留学中介到底值不值｜赞1.1k｜爆',
      createdAt: '2026-07-11T10:00:00Z',
      updatedAt: '2026-07-11T10:00:00Z',
    },
    {
      id: 'comments-1',
      workspaceId: 'workspace-1',
      type: 'comments',
      name: '评论样本',
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

const skills: Record<string, SkillSummary[]> = {
  'workspace-1': [skillSummary],
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

const agentDetail: Agent = {
  ...agentSummary,
  systemPrompt:
    'You are a creator account strategist. Use only selected source materials.',
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

function installWorkspaceApiMock() {
  return vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const url = String(input)
    const method = init?.method || 'GET'
    if (url === '/api/workspaces' && method === 'GET') {
      return jsonResponse([workspaceOne, workspaceTwo])
    }
    const workspaceMatch = url.match(/^\/api\/workspaces\/(workspace-[12])$/)
    if (workspaceMatch && method === 'GET') {
      return jsonResponse(
        workspaceMatch[1] === 'workspace-1' ? workspaceOne : workspaceTwo,
      )
    }
    const materialsMatch = url.match(
      /^\/api\/workspaces\/(workspace-[12])\/source-materials$/,
    )
    if (materialsMatch && method === 'GET') {
      return jsonResponse(materials[materialsMatch[1]])
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
    const agentsMatch = url.match(/^\/api\/workspaces\/(workspace-[12])\/agents$/)
    if (agentsMatch && method === 'GET') {
      return jsonResponse(agents[agentsMatch[1]])
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
  it('loads account profile and source material assets separately', async () => {
    installWorkspaceApiMock()
    render(<App />)

    fireEvent.click((await screen.findAllByRole('button', { name: /Account Profile/ }))[0])
    expect(
      await screen.findByDisplayValue('帮助文科生做留学决策。'),
    ).toBeInTheDocument()
    fireEvent.click(screen.getAllByRole('button', { name: /Source Materials/ })[0])
    expect(
      await screen.findByDisplayValue('留学中介到底值不值｜赞1.1k｜爆'),
    ).toBeInTheDocument()
    expect(
      screen.getByDisplayValue('双非背景冲英国前30有戏吗？'),
    ).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('选择工作区'), {
      target: { value: 'workspace-2' },
    })

    fireEvent.click((await screen.findAllByRole('button', { name: /Account Profile/ }))[0])
    expect(
      await screen.findByDisplayValue('记录真实的数字游民转型路径。'),
    ).toBeInTheDocument()
    fireEvent.click(screen.getAllByRole('button', { name: /Source Materials/ })[0])
    expect(
      await screen.findByDisplayValue('普通小孩不要轻易尝试数字游民｜赞953｜爆'),
    ).toBeInTheDocument()
    expect(
      screen.getByDisplayValue('文科生能做数字游民吗？'),
    ).toBeInTheDocument()

    expect(screen.getByDisplayValue('数字游民')).toBeInTheDocument()
    expect(screen.getAllByText('数字游民趋势.csv').length).toBeGreaterThan(0)
    expect(screen.getByText('普通人如何开始数字游民')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Trend Analysis/ }))
    expect(await screen.findByText('Trend CSV')).toBeInTheDocument()
    expect(screen.getByText(/数字游民趋势.csv/)).toBeInTheDocument()
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
          url === '/api/workspaces/workspace-1/source-materials' &&
          method === 'GET'
        ) {
          return jsonResponse([])
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
          url === '/api/workspaces/workspace-1/source-materials' &&
          method === 'POST'
        ) {
          const body = JSON.parse(String(init?.body)) as {
            type: 'historical_posts' | 'comments'
            name: string
            content: string
          }
          return jsonResponse(
            {
              id: body.type === 'comments' ? 'new-comments' : 'new-history',
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
            historicalPostsMaterialId?: string
            commentsMaterialId?: string
          }
          expect(body.historicalPostsMaterialId).toBe('new-history')
          expect(body.commentsMaterialId).toBe('new-comments')
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
    fireEvent.click((await screen.findAllByRole('button', { name: /Source Materials/ }))[0])
    const historicalEditor = await screen.findByLabelText(
      '主页 / 历史笔记 + 数据（格式：标题 ｜ 数据 ｜ 爆/平/差）',
    )
    const commentsEditor = await screen.findByLabelText('评论区原文（一行一条）')
    fireEvent.change(historicalEditor, {
      target: { value: '留学中介到底值不值｜赞1.1k｜爆' },
    })
    fireEvent.change(commentsEditor, { target: { value: '这是一条新评论' } })

    expect(
      fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST'),
    ).toHaveLength(0)
    expect(screen.queryByRole('button', { name: '保存评论' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Account Diagnosis/ }))
    fireEvent.click(screen.getByRole('button', { name: '⚡ 生成账号诊断' }))

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST'),
      ).toHaveLength(3)
    })
  })

  it('opens a saved analysis run from history', async () => {
    installWorkspaceApiMock()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /Analysis History/ }))
    fireEvent.click(await screen.findByRole('button', { name: /账号诊断/ }))

    expect(await screen.findByText('原始输入快照')).toBeInTheDocument()
    expect(screen.getByText('中介费到底该花在哪三步')).toBeInTheDocument()
  })

  it('opens and edits a topic from the library', async () => {
    installWorkspaceApiMock()
    render(<App />)

    fireEvent.change(await screen.findByLabelText('选择工作区'), {
      target: { value: 'workspace-2' },
    })
    fireEvent.click(await screen.findByRole('button', { name: /Topic Library/ }))

    fireEvent.click(await screen.findByRole('button', { name: /文科生如何开始数字游民/ }))
    const title = await screen.findByLabelText('标题')
    fireEvent.change(title, { target: { value: '非技术人如何开始数字游民' } })
    fireEvent.click(screen.getByRole('button', { name: '保存选题编辑' }))

    expect(await screen.findByText('已保存')).toBeInTheDocument()
    expect(screen.getByDisplayValue('非技术人如何开始数字游民')).toBeInTheDocument()
  })

  it('separates context assets from capability assets and hides content drafts navigation', async () => {
    installWorkspaceApiMock()
    render(<App />)

    expect(await screen.findByText('Context Assets')).toBeInTheDocument()
    expect(screen.getByText('Capability Assets')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Account Profile/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Analysis History/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Skills/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Agents/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Workflows/ })).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /Content Drafts/ }),
    ).not.toBeInTheDocument()
  })

  it('opens a saved audience simulation from history', async () => {
    installWorkspaceApiMock()
    render(<App />)

    fireEvent.change(await screen.findByLabelText('选择工作区'), {
      target: { value: 'workspace-2' },
    })
    fireEvent.click(
      await screen.findByRole('button', { name: /Audience Simulations/ }),
    )
    fireEvent.click(await screen.findByRole('button', { name: /受众模拟/ }))

    expect(await screen.findByText('模拟结果')).toBeInTheDocument()
    expect(screen.getByText('谨慎执行派')).toBeInTheDocument()
    expect(screen.getByText('真实前提 + 分阶段路径')).toBeInTheDocument()
  })
})
