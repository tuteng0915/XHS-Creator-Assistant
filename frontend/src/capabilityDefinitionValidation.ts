import type { AgentSummary, SkillSummary, WorkflowAsset } from './types'

export type SkillDefinitionDraft = {
  displayName: string
  category: string
  purpose: string
  artifactEffect: string
  failureMode: string
  version: string
  userNotes: string
  triggerIntents: string
  requiredInputs: string
  optionalInputs: string
  sideEffects: string
  composableWith: string
  implementationRefs: string
  contextPolicyJson: string
  outputSchemaJson: string
}

export type AgentDefinitionDraft = {
  displayName: string
  purpose: string
  systemPrompt: string
  skillIds: string
  defaultContextPolicyJson: string
  version: string
  userNotes: string
}

export type WorkflowDefinitionDraft = {
  displayName: string
  purpose: string
  entryAgentIds: string
  agentPlanJson: string
  artifactEffect: string
  callBinding: WorkflowAsset['callBinding']
  version: string
  userNotes: string
}

export type WorkflowTaskDraft = {
  taskId: string
  agentId: string
  skillIds: string
  dependsOn: string
  parallel: boolean
}

type JsonObjectParseResult =
  | { ok: true; value: Record<string, unknown> }
  | { ok: false; error: string }

export type AgentDefinitionValidationResult = JsonObjectParseResult & {
  errors: string[]
}

export type WorkflowDefinitionValidationResult = JsonObjectParseResult & {
  errors: string[]
}

function jsonErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

export function textFromList(items: string[]): string {
  return items.join('\n')
}

export function listFromText(value: string): string[] {
  return value
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)
}

function parseJsonObject(value: string, label: string): JsonObjectParseResult {
  try {
    const parsed = JSON.parse(value) as unknown
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return { ok: false, error: `${label} 必须是 JSON object。` }
    }
    return { ok: true, value: parsed as Record<string, unknown> }
  } catch (error) {
    return {
      ok: false,
      error: `${label} JSON 无法解析：${jsonErrorMessage(error)}`,
    }
  }
}

function duplicateItems(values: string[]): string[] {
  const seen = new Set<string>()
  const duplicates = new Set<string>()
  values.forEach((value) => {
    if (seen.has(value)) duplicates.add(value)
    seen.add(value)
  })
  return [...duplicates].sort()
}

export function workflowTasksFromPlanJson(
  agentPlanJson: string,
): WorkflowTaskDraft[] | null {
  try {
    const parsed = JSON.parse(agentPlanJson) as unknown
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null
    const tasks = (parsed as { tasks?: unknown }).tasks
    if (!Array.isArray(tasks)) return []
    return tasks.map((task, index) => {
      const item =
        task && typeof task === 'object' && !Array.isArray(task)
          ? (task as Record<string, unknown>)
          : {}
      return {
        taskId:
          typeof item.taskId === 'string' && item.taskId
            ? item.taskId
            : `task_${index + 1}`,
        agentId: typeof item.agentId === 'string' ? item.agentId : '',
        skillIds: Array.isArray(item.skillIds)
          ? textFromList(
              item.skillIds.filter((value): value is string => typeof value === 'string'),
            )
          : '',
        dependsOn: Array.isArray(item.dependsOn)
          ? textFromList(
              item.dependsOn.filter((value): value is string => typeof value === 'string'),
            )
          : '',
        parallel: item.parallel === true,
      }
    })
  } catch {
    return null
  }
}

export function agentPlanJsonWithTasks(
  agentPlanJson: string,
  taskDrafts: WorkflowTaskDraft[],
): string {
  let base: Record<string, unknown> = {}
  try {
    const parsed = JSON.parse(agentPlanJson) as unknown
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      base = parsed as Record<string, unknown>
    }
  } catch {
    base = {}
  }
  return JSON.stringify(
    {
      ...base,
      tasks: taskDrafts
        .filter((task) => task.taskId.trim())
        .map((task) => ({
          taskId: task.taskId.trim(),
          agentId: task.agentId.trim(),
          skillIds: listFromText(task.skillIds),
          dependsOn: listFromText(task.dependsOn),
          parallel: task.parallel,
        })),
    },
    null,
    2,
  )
}

export function validateAgentDefinitionDraft(
  draft: AgentDefinitionDraft,
  availableSkills: SkillSummary[],
): AgentDefinitionValidationResult {
  const errors: string[] = []
  if (!draft.displayName.trim()) errors.push('Agent 名称不能为空。')
  if (!draft.version.trim()) errors.push('Agent 版本不能为空。')
  const skillIds = listFromText(draft.skillIds)
  if (skillIds.length === 0) errors.push('Agent 至少需要选择一个 Skill。')
  const duplicatedSkillIds = duplicateItems(skillIds)
  if (duplicatedSkillIds.length > 0) {
    errors.push(`Skill IDs 不能重复：${duplicatedSkillIds.join(', ')}。`)
  }
  const knownSkillIds = new Set(availableSkills.map((skill) => skill.skillId))
  const unknownSkillIds = skillIds.filter((skillId) => !knownSkillIds.has(skillId))
  if (unknownSkillIds.length > 0) {
    errors.push(`未知 Skill：${unknownSkillIds.join(', ')}。`)
  }
  const contextPolicy = parseJsonObject(
    draft.defaultContextPolicyJson,
    'Default Context Policy',
  )
  if (!contextPolicy.ok) {
    return { ...contextPolicy, errors: [...errors, contextPolicy.error] }
  }
  return { ...contextPolicy, errors }
}

function detectWorkflowDependencyCycle(tasks: WorkflowTaskDraft[]): string | null {
  const taskIds = new Set(tasks.map((task) => task.taskId.trim()).filter(Boolean))
  const dependencies = new Map(
    tasks
      .map((task) => [
        task.taskId.trim(),
        listFromText(task.dependsOn).filter((dependency) => taskIds.has(dependency)),
      ] as const)
      .filter(([taskId]) => taskId),
  )
  const visiting = new Set<string>()
  const visited = new Set<string>()

  function visit(taskId: string): string | null {
    if (visiting.has(taskId)) return taskId
    if (visited.has(taskId)) return null
    visiting.add(taskId)
    for (const dependency of dependencies.get(taskId) || []) {
      const cycle = visit(dependency)
      if (cycle) return cycle
    }
    visiting.delete(taskId)
    visited.add(taskId)
    return null
  }

  for (const taskId of dependencies.keys()) {
    const cycle = visit(taskId)
    if (cycle) return cycle
  }
  return null
}

export function validateWorkflowDefinitionDraft(
  draft: WorkflowDefinitionDraft,
  availableAgents: AgentSummary[],
  availableSkills: SkillSummary[],
): WorkflowDefinitionValidationResult {
  const errors: string[] = []
  if (!draft.displayName.trim()) errors.push('Workflow 名称不能为空。')
  if (!draft.version.trim()) errors.push('Workflow 版本不能为空。')
  if (!draft.artifactEffect.trim()) errors.push('Artifact Effect 不能为空。')

  const knownAgentIds = new Set(availableAgents.map((agent) => agent.agentId))
  const knownSkillIds = new Set(availableSkills.map((skill) => skill.skillId))
  const entryAgentIds = listFromText(draft.entryAgentIds)
  if (entryAgentIds.length === 0) errors.push('Workflow 至少需要一个 Entry Agent。')
  const duplicatedEntryAgentIds = duplicateItems(entryAgentIds)
  if (duplicatedEntryAgentIds.length > 0) {
    errors.push(`Entry Agent IDs 不能重复：${duplicatedEntryAgentIds.join(', ')}。`)
  }
  const unknownEntryAgentIds = entryAgentIds.filter(
    (agentId) => !knownAgentIds.has(agentId),
  )
  if (unknownEntryAgentIds.length > 0) {
    errors.push(`未知 Entry Agent：${unknownEntryAgentIds.join(', ')}。`)
  }

  const agentPlan = parseJsonObject(draft.agentPlanJson, 'Agent Task Plan')
  if (!agentPlan.ok) return { ...agentPlan, errors: [...errors, agentPlan.error] }
  const tasks = workflowTasksFromPlanJson(draft.agentPlanJson)
  if (tasks === null) {
    return {
      ok: false,
      error: 'Agent Task Plan JSON 无法解析。',
      errors: [...errors, 'Agent Task Plan JSON 无法解析。'],
    }
  }
  if (tasks.length === 0) errors.push('Workflow 至少需要一个 Task。')

  const taskIds = tasks.map((task) => task.taskId.trim()).filter(Boolean)
  const taskIdSet = new Set(taskIds)
  const duplicatedTaskIds = duplicateItems(taskIds)
  if (duplicatedTaskIds.length > 0) {
    errors.push(`Task ID 不能重复：${duplicatedTaskIds.join(', ')}。`)
  }

  tasks.forEach((task, index) => {
    const label = task.taskId.trim() || `第 ${index + 1} 个 Task`
    if (!task.taskId.trim()) errors.push(`${label} 缺少 taskId。`)
    if (!task.agentId.trim()) {
      errors.push(`${label} 缺少 agentId。`)
    } else if (!knownAgentIds.has(task.agentId.trim())) {
      errors.push(`${label} 引用了未知 Agent：${task.agentId.trim()}。`)
    }
    const skillIds = listFromText(task.skillIds)
    if (skillIds.length === 0) errors.push(`${label} 至少需要一个 Skill。`)
    const duplicatedSkillIds = duplicateItems(skillIds)
    if (duplicatedSkillIds.length > 0) {
      errors.push(`${label} 的 Skill IDs 不能重复：${duplicatedSkillIds.join(', ')}。`)
    }
    const unknownSkillIds = skillIds.filter((skillId) => !knownSkillIds.has(skillId))
    if (unknownSkillIds.length > 0) {
      errors.push(`${label} 引用了未知 Skill：${unknownSkillIds.join(', ')}。`)
    }
    listFromText(task.dependsOn).forEach((dependency) => {
      if (dependency === task.taskId.trim()) {
        errors.push(`${label} 不能依赖自己。`)
      } else if (!taskIdSet.has(dependency)) {
        errors.push(`${label} 依赖了不存在的 Task：${dependency}。`)
      }
    })
  })

  const cycle = detectWorkflowDependencyCycle(tasks)
  if (cycle) errors.push(`Workflow task 依赖存在循环：${cycle}。`)

  return { ...agentPlan, errors }
}
