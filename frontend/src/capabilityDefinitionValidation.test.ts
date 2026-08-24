import { describe, expect, it } from 'vitest'

import {
  agentPlanJsonWithTasks,
  validateAgentDefinitionDraft,
  validateWorkflowDefinitionDraft,
  workflowTasksFromPlanJson,
  type AgentDefinitionDraft,
  type WorkflowDefinitionDraft,
  type WorkflowTaskDraft,
} from './capabilityDefinitionValidation'
import type { AgentSummary, SkillSummary } from './types'

const skills: SkillSummary[] = [
  {
    id: 'skill-profile',
    workspaceId: 'workspace-1',
    skillId: 'analysis.profile_from_history',
    displayName: 'Analyze Account Profile',
    category: 'analysis',
    purpose: '',
    artifactEffect: '',
    source: 'builtin',
    status: 'enabled',
    version: 'v1',
    updatedAt: '2026-07-11T12:00:00Z',
  },
  {
    id: 'skill-topic',
    workspaceId: 'workspace-1',
    skillId: 'topic.refine_to_brief',
    displayName: 'Generate Brief',
    category: 'creative_output',
    purpose: '',
    artifactEffect: '',
    source: 'builtin',
    status: 'enabled',
    version: 'v1',
    updatedAt: '2026-07-11T12:00:00Z',
  },
]

const agents: AgentSummary[] = [
  {
    id: 'agent-strategist',
    workspaceId: 'workspace-1',
    agentId: 'account_diagnosis_strategist',
    displayName: 'Account Diagnosis Strategist',
    purpose: '',
    skillIds: ['analysis.profile_from_history'],
    source: 'builtin',
    status: 'enabled',
    version: 'v1',
    updatedAt: '2026-07-11T12:00:00Z',
  },
]

function agentDraft(patch: Partial<AgentDefinitionDraft> = {}): AgentDefinitionDraft {
  return {
    displayName: 'Agent',
    purpose: '',
    systemPrompt: '',
    skillIds: 'analysis.profile_from_history',
    defaultContextPolicyJson: '{}',
    version: 'v1',
    userNotes: '',
    ...patch,
  }
}

function workflowDraft(
  patch: Partial<WorkflowDefinitionDraft> = {},
): WorkflowDefinitionDraft {
  return {
    displayName: 'Workflow',
    purpose: '',
    entryAgentIds: 'account_diagnosis_strategist',
    agentPlanJson: JSON.stringify(
      {
        tasks: [
          {
            taskId: 'analyze',
            agentId: 'account_diagnosis_strategist',
            skillIds: ['analysis.profile_from_history'],
            dependsOn: [],
          },
        ],
      },
      null,
      2,
    ),
    artifactEffect: 'AnalysisRun',
    callBinding: '',
    version: 'v1',
    userNotes: '',
    ...patch,
  }
}

describe('capability definition validation', () => {
  it('validates agent skills and context policy JSON', () => {
    const result = validateAgentDefinitionDraft(
      agentDraft({
        skillIds: 'analysis.profile_from_history\nmissing.skill\nmissing.skill',
        defaultContextPolicyJson: '[]',
      }),
      skills,
    )

    expect(result.ok).toBe(false)
    expect(result.errors).toEqual(
      expect.arrayContaining([
        'Skill IDs 不能重复：missing.skill。',
        '未知 Skill：missing.skill, missing.skill。',
        'Default Context Policy 必须是 JSON object。',
      ]),
    )
  })

  it('accepts a valid workflow task plan', () => {
    const result = validateWorkflowDefinitionDraft(workflowDraft(), agents, skills)

    expect(result.ok).toBe(true)
    expect(result.errors).toEqual([])
    if (result.ok) {
      expect(result.value.tasks).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ taskId: 'analyze' }),
        ]),
      )
    }
  })

  it('reports workflow reference and dependency errors', () => {
    const result = validateWorkflowDefinitionDraft(
      workflowDraft({
        entryAgentIds: 'missing_agent',
        agentPlanJson: JSON.stringify({
          tasks: [
            {
              taskId: 'a',
              agentId: 'missing_agent',
              skillIds: ['missing.skill'],
              dependsOn: ['missing_task'],
            },
            {
              taskId: 'a',
              agentId: 'account_diagnosis_strategist',
              skillIds: [],
              dependsOn: ['a'],
            },
          ],
        }),
      }),
      agents,
      skills,
    )

    expect(result.errors).toEqual(
      expect.arrayContaining([
        '未知 Entry Agent：missing_agent。',
        'Task ID 不能重复：a。',
        'a 引用了未知 Agent：missing_agent。',
        'a 引用了未知 Skill：missing.skill。',
        'a 依赖了不存在的 Task：missing_task。',
        'a 至少需要一个 Skill。',
        'a 不能依赖自己。',
      ]),
    )
  })

  it('detects workflow dependency cycles', () => {
    const result = validateWorkflowDefinitionDraft(
      workflowDraft({
        agentPlanJson: JSON.stringify({
          tasks: [
            {
              taskId: 'a',
              agentId: 'account_diagnosis_strategist',
              skillIds: ['analysis.profile_from_history'],
              dependsOn: ['b'],
            },
            {
              taskId: 'b',
              agentId: 'account_diagnosis_strategist',
              skillIds: ['topic.refine_to_brief'],
              dependsOn: ['a'],
            },
          ],
        }),
      }),
      agents,
      skills,
    )

    expect(result.errors.some((error) => error.includes('依赖存在循环'))).toBe(true)
  })

  it('round-trips workflow task drafts back to agent plan JSON', () => {
    const tasks: WorkflowTaskDraft[] = [
      {
        taskId: ' draft ',
        agentId: ' account_diagnosis_strategist ',
        skillIds: 'analysis.profile_from_history\ntopic.refine_to_brief',
        dependsOn: 'analyze',
        parallel: true,
      },
    ]

    const json = agentPlanJsonWithTasks('{"note":"keep"}', tasks)
    const parsed = JSON.parse(json) as {
      note: string
      tasks: Array<{
        taskId: string
        agentId: string
        skillIds: string[]
        dependsOn: string[]
        parallel: boolean
      }>
    }

    expect(parsed.note).toBe('keep')
    expect(parsed.tasks[0]).toEqual({
      taskId: 'draft',
      agentId: 'account_diagnosis_strategist',
      skillIds: ['analysis.profile_from_history', 'topic.refine_to_brief'],
      dependsOn: ['analyze'],
      parallel: true,
    })
    expect(workflowTasksFromPlanJson(json)?.[0].skillIds).toBe(
      'analysis.profile_from_history\ntopic.refine_to_brief',
    )
  })
})
