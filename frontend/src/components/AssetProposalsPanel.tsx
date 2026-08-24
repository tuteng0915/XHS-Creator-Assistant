import { useEffect, useState } from 'react'

import type {
  AgentSummary,
  AssetProposal,
  AssetProposalPreview,
  SkillSummary,
} from '../types'

type AssetProposalDraft = {
  title: string
  description: string
  proposedActionText: string
  error: string
  dirty: boolean
  saving: boolean
}

type AssetProposalsPanelProps = {
  proposals: AssetProposal[]
  availableSkills?: SkillSummary[]
  availableAgents?: AgentSummary[]
  onUpdate: (
    proposal: AssetProposal,
    patch: {
      title: string
      description: string
      proposedAction: Record<string, unknown>
    },
  ) => Promise<AssetProposal>
  onPreview: (proposal: AssetProposal) => Promise<AssetProposalPreview>
  onApply: (proposal: AssetProposal) => Promise<void>
  onReject: (proposal: AssetProposal) => Promise<void>
}

type ProposalPreviewState = {
  loading: boolean
  error: string
  confirmationMessage: string
  proposalUpdatedAt: string
  data: AssetProposalPreview | null
}

type WorkflowTaskDraft = {
  taskId: string
  agentId: string
  skillIds: string
  dependsOn: string
  parallel: boolean
}

function draftFromProposal(proposal: AssetProposal): AssetProposalDraft {
  return {
    title: proposal.title,
    description: proposal.description,
    proposedActionText: JSON.stringify(proposal.proposedAction, null, 2),
    error: '',
    dirty: false,
    saving: false,
  }
}

function objectValue(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function capabilitySummary(proposal: AssetProposal) {
  const payload = objectValue(proposal.proposedAction.payload)
  const definition = objectValue(payload?.definition) || payload
  if (!definition) return null
  const stableId =
    definition.skillId || definition.agentId || definition.workflowId || payload?.targetAssetId
  const displayName = definition.displayName
  const artifactEffect = definition.artifactEffect
  if (!stableId && !displayName && !artifactEffect) return null
  return {
    stableId: typeof stableId === 'string' ? stableId : '',
    displayName: typeof displayName === 'string' ? displayName : '',
    artifactEffect: typeof artifactEffect === 'string' ? artifactEffect : '',
  }
}

function jsonText(value: unknown): string {
  if (value === undefined) return '未设置'
  if (typeof value === 'string') return value || '空字符串'
  return JSON.stringify(value, null, 2)
}

function textFromList(items: string[]): string {
  return items.join('\n')
}

function listFromText(value: string): string[] {
  return value
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)
}

function parsedAction(text: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(text) as unknown
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null
  } catch {
    return null
  }
}

function definitionFromAction(
  action: Record<string, unknown> | null,
): Record<string, unknown> | null {
  const payload = objectValue(action?.payload)
  if (!payload) return null
  return objectValue(payload.definition) || payload
}

function updateActionDefinitionText(
  actionText: string,
  patch: Record<string, unknown>,
): string | null {
  const action = parsedAction(actionText)
  if (!action) return null
  const payload = objectValue(action.payload)
  if (!payload) return null
  const definition = objectValue(payload.definition)
  const nextPayload = definition
    ? { ...payload, definition: { ...definition, ...patch } }
    : { ...payload, ...patch }
  return JSON.stringify({ ...action, payload: nextPayload }, null, 2)
}

function workflowTasksFromDefinition(
  definition: Record<string, unknown> | null,
): WorkflowTaskDraft[] | null {
  const agentPlan = objectValue(definition?.agentPlan)
  if (!agentPlan) return []
  const tasks = agentPlan.tasks
  if (tasks === undefined) return []
  if (!Array.isArray(tasks)) return null
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
}

export function AssetProposalsPanel({
  proposals,
  availableSkills = [],
  availableAgents = [],
  onUpdate,
  onPreview,
  onApply,
  onReject,
}: AssetProposalsPanelProps) {
  const [drafts, setDrafts] = useState<Record<string, AssetProposalDraft>>({})
  const [previews, setPreviews] = useState<Record<string, ProposalPreviewState>>({})

  useEffect(() => {
    setDrafts((current) => {
      const next: Record<string, AssetProposalDraft> = {}
      for (const proposal of proposals) {
        const existing = current[proposal.id]
        next[proposal.id] =
          existing && existing.dirty ? existing : draftFromProposal(proposal)
      }
      return next
    })
  }, [proposals])

  if (proposals.length === 0) return null

  function updateDraft(
    proposalId: string,
    patch: Partial<AssetProposalDraft>,
  ) {
    setDrafts((current) => ({
      ...current,
      [proposalId]: {
        ...current[proposalId],
        ...patch,
        dirty: patch.dirty ?? true,
      },
    }))
    if (patch.proposedActionText !== undefined) {
      setPreviews((current) => ({
        ...current,
        [proposalId]: {
          loading: false,
          error: '',
          confirmationMessage: '提案内容已修改，请重新预览 diff。',
          proposalUpdatedAt: '',
          data: null,
        },
      }))
    }
  }

  function parseProposalDraft(proposal: AssetProposal) {
    const draft = drafts[proposal.id]
    if (!draft) return null
    let proposedAction: Record<string, unknown>
    try {
      const parsed = JSON.parse(draft.proposedActionText) as unknown
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error('Proposed action 必须是 JSON object。')
      }
      proposedAction = parsed as Record<string, unknown>
    } catch (error) {
      updateDraft(proposal.id, {
        error: error instanceof Error ? error.message : 'JSON 解析失败。',
        dirty: true,
      })
      return null
    }
    return { draft, proposedAction }
  }

  function updateProposalDefinition(
    proposalId: string,
    currentActionText: string,
    patch: Record<string, unknown>,
  ) {
    const nextText = updateActionDefinitionText(currentActionText, patch)
    if (!nextText) {
      updateDraft(proposalId, {
        error: '当前 Proposed Action JSON 无法结构化编辑。请先修复 JSON。',
      })
      return
    }
    updateDraft(proposalId, { proposedActionText: nextText, error: '' })
  }

  function updateWorkflowTasks(
    proposalId: string,
    currentActionText: string,
    definition: Record<string, unknown>,
    tasks: WorkflowTaskDraft[],
  ) {
    const currentPlan = objectValue(definition.agentPlan) || {}
    updateProposalDefinition(proposalId, currentActionText, {
      agentPlan: {
        ...currentPlan,
        tasks: tasks
          .filter((task) => task.taskId.trim())
          .map((task) => ({
            taskId: task.taskId.trim(),
            agentId: task.agentId.trim(),
            skillIds: listFromText(task.skillIds),
            dependsOn: listFromText(task.dependsOn),
            parallel: task.parallel,
          })),
      },
    })
  }

  async function saveProposal(proposal: AssetProposal) {
    const parsed = parseProposalDraft(proposal)
    if (!parsed) return null
    const { draft, proposedAction } = parsed
    updateDraft(proposal.id, { saving: true, error: '', dirty: draft.dirty })
    try {
      const updated = await onUpdate(proposal, {
        title: draft.title,
        description: draft.description,
        proposedAction,
      })
      setPreviews((current) => ({
        ...current,
        [proposal.id]: {
          loading: false,
          error: '',
          confirmationMessage: '提案已保存，请预览 diff 后再应用。',
          proposalUpdatedAt: '',
          data: null,
        },
      }))
      setDrafts((current) => ({
        ...current,
        [proposal.id]: {
          ...current[proposal.id],
          saving: false,
          dirty: false,
          error: '',
        },
      }))
      return updated
    } catch (error) {
      updateDraft(proposal.id, {
        saving: false,
        error: error instanceof Error ? error.message : '保存 proposal 失败。',
        dirty: true,
      })
      return null
    }
  }

  async function previewProposal(proposal: AssetProposal) {
    setPreviews((current) => ({
      ...current,
      [proposal.id]: {
        ...(current[proposal.id] || {
          data: null,
          proposalUpdatedAt: '',
          confirmationMessage: '',
        }),
        loading: true,
        error: '',
      },
    }))
    try {
      const preview = await onPreview(proposal)
      setPreviews((current) => ({
        ...current,
        [proposal.id]: {
          loading: false,
          error: '',
          confirmationMessage: '',
          proposalUpdatedAt: proposal.updatedAt,
          data: preview,
        },
      }))
      return preview
    } catch (error) {
      setPreviews((current) => ({
        ...current,
        [proposal.id]: {
          loading: false,
          error: error instanceof Error ? error.message : '加载 diff 失败。',
          confirmationMessage: '',
          proposalUpdatedAt: proposal.updatedAt,
          data: null,
        },
      }))
      return null
    }
  }

  async function applyProposal(proposal: AssetProposal) {
    const draft = drafts[proposal.id]
    let proposalToApply = proposal
    if (draft?.dirty) {
      const saved = await saveProposal(proposal)
      if (!saved) return
      proposalToApply = saved
    }
    const preview = previews[proposalToApply.id]
    if (!preview?.data || preview.proposalUpdatedAt !== proposalToApply.updatedAt) {
      await previewProposal(proposalToApply)
      setPreviews((current) => ({
        ...current,
        [proposalToApply.id]: {
          ...(current[proposalToApply.id] || {
            loading: false,
            error: '',
            proposalUpdatedAt: proposalToApply.updatedAt,
            data: null,
          }),
          confirmationMessage: '已生成 apply 前 diff，请确认后再次点击“确认应用”。',
        },
      }))
      return
    }
    if (preview.data.validationErrors.length > 0) return
    await onApply(proposalToApply)
  }

  function renderStructuredDefinitionEditor(
    proposal: AssetProposal,
    draft: AssetProposalDraft,
    isPending: boolean,
  ) {
    const action = parsedAction(draft.proposedActionText)
    const definition = definitionFromAction(action)
    if (!definition) return null

    if (proposal.actionType === 'agent.propose_definition') {
      const skillIds = Array.isArray(definition.skillIds)
        ? definition.skillIds.filter((value): value is string => typeof value === 'string')
        : []
      return (
        <div className="structured-editor-card">
          <div className="asset-section-head">
            <h3>Agent Proposal 表单</h3>
            <span>structured</span>
          </div>
          <label htmlFor={`${proposal.id}-agent-name`}>Agent 名称</label>
          <input
            id={`${proposal.id}-agent-name`}
            disabled={!isPending}
            value={typeof definition.displayName === 'string' ? definition.displayName : ''}
            onChange={(event) =>
              updateProposalDefinition(proposal.id, draft.proposedActionText, {
                displayName: event.target.value,
              })
            }
          />
          <label htmlFor={`${proposal.id}-agent-purpose`}>用途 / 调优说明</label>
          <textarea
            id={`${proposal.id}-agent-purpose`}
            disabled={!isPending}
            rows={3}
            value={typeof definition.purpose === 'string' ? definition.purpose : ''}
            onChange={(event) =>
              updateProposalDefinition(proposal.id, draft.proposedActionText, {
                purpose: event.target.value,
              })
            }
          />
          <label htmlFor={`${proposal.id}-agent-system-prompt`}>System Prompt</label>
          <textarea
            id={`${proposal.id}-agent-system-prompt`}
            disabled={!isPending}
            rows={5}
            value={
              typeof definition.systemPrompt === 'string'
                ? definition.systemPrompt
                : ''
            }
            onChange={(event) =>
              updateProposalDefinition(proposal.id, draft.proposedActionText, {
                systemPrompt: event.target.value,
              })
            }
          />
          <label htmlFor={`${proposal.id}-agent-skills`}>Skill IDs（一行一个）</label>
          <textarea
            id={`${proposal.id}-agent-skills`}
            disabled={!isPending}
            rows={4}
            value={textFromList(skillIds)}
            onChange={(event) =>
              updateProposalDefinition(proposal.id, draft.proposedActionText, {
                skillIds: listFromText(event.target.value),
              })
            }
          />
          {availableSkills.length > 0 && (
            <div className="capability-checkbox-list compact">
              {availableSkills.map((skill) => {
                const selected = skillIds.includes(skill.skillId)
                return (
                  <label key={skill.id}>
                    <input
                      type="checkbox"
                      disabled={!isPending}
                      checked={selected}
                      onChange={(event) => {
                        const next = new Set(skillIds)
                        if (event.target.checked) next.add(skill.skillId)
                        else next.delete(skill.skillId)
                        updateProposalDefinition(proposal.id, draft.proposedActionText, {
                          skillIds: [...next],
                        })
                      }}
                    />
                    <span>
                      <b>{skill.displayName}</b>
                      <small>{skill.skillId}</small>
                    </span>
                  </label>
                )
              })}
            </div>
          )}
          <label htmlFor={`${proposal.id}-agent-version`}>版本</label>
          <input
            id={`${proposal.id}-agent-version`}
            disabled={!isPending}
            value={typeof definition.version === 'string' ? definition.version : ''}
            onChange={(event) =>
              updateProposalDefinition(proposal.id, draft.proposedActionText, {
                version: event.target.value,
              })
            }
          />
        </div>
      )
    }

    if (proposal.actionType === 'workflow.propose_definition') {
      const entryAgentIds = Array.isArray(definition.entryAgentIds)
        ? definition.entryAgentIds.filter(
            (value): value is string => typeof value === 'string',
          )
        : []
      const taskDrafts = workflowTasksFromDefinition(definition)
      return (
        <div className="structured-editor-card">
          <div className="asset-section-head">
            <h3>Workflow Proposal 表单</h3>
            <span>structured</span>
          </div>
          <label htmlFor={`${proposal.id}-workflow-name`}>Workflow 名称</label>
          <input
            id={`${proposal.id}-workflow-name`}
            disabled={!isPending}
            value={typeof definition.displayName === 'string' ? definition.displayName : ''}
            onChange={(event) =>
              updateProposalDefinition(proposal.id, draft.proposedActionText, {
                displayName: event.target.value,
              })
            }
          />
          <label htmlFor={`${proposal.id}-workflow-purpose`}>用途 / 调优说明</label>
          <textarea
            id={`${proposal.id}-workflow-purpose`}
            disabled={!isPending}
            rows={3}
            value={typeof definition.purpose === 'string' ? definition.purpose : ''}
            onChange={(event) =>
              updateProposalDefinition(proposal.id, draft.proposedActionText, {
                purpose: event.target.value,
              })
            }
          />
          <label htmlFor={`${proposal.id}-workflow-entry-agents`}>
            Entry Agent IDs（一行一个）
          </label>
          <textarea
            id={`${proposal.id}-workflow-entry-agents`}
            disabled={!isPending}
            rows={3}
            value={textFromList(entryAgentIds)}
            onChange={(event) =>
              updateProposalDefinition(proposal.id, draft.proposedActionText, {
                entryAgentIds: listFromText(event.target.value),
              })
            }
          />
          <label htmlFor={`${proposal.id}-workflow-artifact-effect`}>
            Artifact Effect
          </label>
          <input
            id={`${proposal.id}-workflow-artifact-effect`}
            disabled={!isPending}
            value={
              typeof definition.artifactEffect === 'string'
                ? definition.artifactEffect
                : ''
            }
            onChange={(event) =>
              updateProposalDefinition(proposal.id, draft.proposedActionText, {
                artifactEffect: event.target.value,
              })
            }
          />
          <label htmlFor={`${proposal.id}-workflow-call-binding`}>调用注册</label>
          <select
            id={`${proposal.id}-workflow-call-binding`}
            disabled={!isPending}
            value={typeof definition.callBinding === 'string' ? definition.callBinding : ''}
            onChange={(event) =>
              updateProposalDefinition(proposal.id, draft.proposedActionText, {
                callBinding: event.target.value,
              })
            }
          >
            <option value="">不注册为调用入口</option>
            <option value="account">账号诊断执行入口</option>
            <option value="trend">热点分析执行入口</option>
            <option value="video">视频博主质量诊断执行入口</option>
          </select>
          <label>Workflow Tasks</label>
          {taskDrafts === null ? (
            <div className="err">agentPlan.tasks 当前不是数组，无法表格化编辑。</div>
          ) : (
            <>
              <div className="workflow-task-editor">
                {taskDrafts.map((task, index) => (
                  <div className="workflow-task-card" key={`${task.taskId}-${index}`}>
                    <div className="asset-section-head">
                      <h3>Task {index + 1}</h3>
                      <button
                        type="button"
                        className="secondary-button"
                        disabled={!isPending}
                        onClick={() =>
                          updateWorkflowTasks(
                            proposal.id,
                            draft.proposedActionText,
                            definition,
                            taskDrafts.filter((_, itemIndex) => itemIndex !== index),
                          )
                        }
                      >
                        删除
                      </button>
                    </div>
                    <div className="compact-grid two-col">
                      <div>
                        <label htmlFor={`${proposal.id}-task-id-${index}`}>Task ID</label>
                        <input
                          id={`${proposal.id}-task-id-${index}`}
                          disabled={!isPending}
                          value={task.taskId}
                          onChange={(event) => {
                            const next = [...taskDrafts]
                            next[index] = { ...task, taskId: event.target.value }
                            updateWorkflowTasks(
                              proposal.id,
                              draft.proposedActionText,
                              definition,
                              next,
                            )
                          }}
                        />
                      </div>
                      <div>
                        <label htmlFor={`${proposal.id}-task-agent-${index}`}>Agent</label>
                        <select
                          id={`${proposal.id}-task-agent-${index}`}
                          disabled={!isPending}
                          value={task.agentId}
                          onChange={(event) => {
                            const next = [...taskDrafts]
                            next[index] = { ...task, agentId: event.target.value }
                            updateWorkflowTasks(
                              proposal.id,
                              draft.proposedActionText,
                              definition,
                              next,
                            )
                          }}
                        >
                          <option value="">未选择</option>
                          {availableAgents.map((agent) => (
                            <option key={agent.id} value={agent.agentId}>
                              {agent.displayName} · {agent.agentId}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                    <label htmlFor={`${proposal.id}-task-skills-${index}`}>
                      Skill IDs（一行一个）
                    </label>
                    <textarea
                      id={`${proposal.id}-task-skills-${index}`}
                      disabled={!isPending}
                      rows={3}
                      value={task.skillIds}
                      onChange={(event) => {
                        const next = [...taskDrafts]
                        next[index] = { ...task, skillIds: event.target.value }
                        updateWorkflowTasks(
                          proposal.id,
                          draft.proposedActionText,
                          definition,
                          next,
                        )
                      }}
                    />
                    <label htmlFor={`${proposal.id}-task-depends-${index}`}>
                      Depends On（一行一个 taskId）
                    </label>
                    <textarea
                      id={`${proposal.id}-task-depends-${index}`}
                      disabled={!isPending}
                      rows={2}
                      value={task.dependsOn}
                      onChange={(event) => {
                        const next = [...taskDrafts]
                        next[index] = { ...task, dependsOn: event.target.value }
                        updateWorkflowTasks(
                          proposal.id,
                          draft.proposedActionText,
                          definition,
                          next,
                        )
                      }}
                    />
                    <label className="checkbox-line">
                      <input
                        type="checkbox"
                        disabled={!isPending}
                        checked={task.parallel}
                        onChange={(event) => {
                          const next = [...taskDrafts]
                          next[index] = { ...task, parallel: event.target.checked }
                          updateWorkflowTasks(
                            proposal.id,
                            draft.proposedActionText,
                            definition,
                            next,
                          )
                        }}
                      />
                      可并行执行
                    </label>
                  </div>
                ))}
              </div>
              <button
                type="button"
                className="secondary-button"
                disabled={!isPending}
                onClick={() =>
                  updateWorkflowTasks(proposal.id, draft.proposedActionText, definition, [
                    ...taskDrafts,
                    {
                      taskId: `task_${taskDrafts.length + 1}`,
                      agentId: '',
                      skillIds: '',
                      dependsOn: '',
                      parallel: false,
                    },
                  ])
                }
              >
                添加 Task
              </button>
            </>
          )}
          <label htmlFor={`${proposal.id}-workflow-version`}>版本</label>
          <input
            id={`${proposal.id}-workflow-version`}
            disabled={!isPending}
            value={typeof definition.version === 'string' ? definition.version : ''}
            onChange={(event) =>
              updateProposalDefinition(proposal.id, draft.proposedActionText, {
                version: event.target.value,
              })
            }
          />
        </div>
      )
    }

    return null
  }

  return (
    <div className="source-editor-card">
      <label>Asset Proposals</label>
      {proposals.map((proposal) => {
        const draft = drafts[proposal.id] || draftFromProposal(proposal)
        const isPending = proposal.status === 'pending'
        const summary = capabilitySummary(proposal)
        const preview = previews[proposal.id]
        return (
          <details className="asset-requirement" key={proposal.id} open>
            <summary>
              <div>
                <b>{proposal.title}</b>
                <span>
                  {proposal.actionType} · {proposal.description}
                </span>
                {proposal.error && <span>错误：{proposal.error}</span>}
              </div>
              <em className={proposal.status}>{proposal.status}</em>
            </summary>
            <div className="proposal-editor">
              {summary && (
                <div className="why">
                  {summary.displayName && <div>名称：{summary.displayName}</div>}
                  {summary.stableId && <div>ID：{summary.stableId}</div>}
                  {summary.artifactEffect && (
                    <div>生成/影响：{summary.artifactEffect}</div>
                  )}
                </div>
              )}
              <label>标题</label>
              <input
                disabled={!isPending}
                value={draft.title}
                onChange={(event) =>
                  updateDraft(proposal.id, { title: event.target.value })
                }
              />
              <label>说明</label>
              <textarea
                disabled={!isPending}
                rows={2}
                value={draft.description}
                onChange={(event) =>
                  updateDraft(proposal.id, { description: event.target.value })
                }
              />
              {renderStructuredDefinitionEditor(proposal, draft, isPending)}
              <label>Proposed Action JSON</label>
              <textarea
                disabled={!isPending}
                rows={10}
                value={draft.proposedActionText}
                onChange={(event) =>
                  updateDraft(proposal.id, {
                    proposedActionText: event.target.value,
                  })
                }
              />
              {proposal.result && Object.keys(proposal.result).length > 0 && (
                <>
                  <label>Apply Result</label>
                  <pre className="json-preview">
                    {JSON.stringify(proposal.result, null, 2)}
                  </pre>
                </>
              )}
              <label>Apply 前 Diff</label>
              <div className="proposal-diff-preview">
                {preview?.loading && <div className="why">正在生成 diff…</div>}
                {preview?.error && <div className="err">{preview.error}</div>}
                {preview?.confirmationMessage && (
                  <div className="why">{preview.confirmationMessage}</div>
                )}
                {preview?.data ? (
                  <>
                    <div className="why">
                      {preview.data.operation === 'create' ? '将创建' : '将更新'}{' '}
                      {preview.data.targetAssetType}
                      {preview.data.targetStableId
                        ? ` · ${preview.data.targetStableId}`
                        : ''}
                    </div>
                    {preview.data.validationErrors.length > 0 ? (
                      <div className="err">
                        {preview.data.validationErrors.join('\n')}
                      </div>
                    ) : preview.data.changedFields.length === 0 ? (
                      <div className="empty-card compact">没有字段变化。</div>
                    ) : (
                      <div className="proposal-diff-list">
                        {preview.data.changedFields.map((field) => (
                          <div className="proposal-diff-row" key={field.field}>
                            <b>{field.field}</b>
                            <div>
                              <span>当前</span>
                              <pre>{jsonText(field.current)}</pre>
                            </div>
                            <div>
                              <span>提案</span>
                              <pre>{jsonText(field.proposed)}</pre>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                ) : (
                  <div className="empty-card compact">
                    应用前先生成 diff，确认将创建或更新哪些资产字段。
                  </div>
                )}
              </div>
              {draft.error && <div className="err">{draft.error}</div>}
              <div className="detail-actions">
                {isPending && (
                  <>
                    <button
                      type="button"
                      disabled={!draft.dirty || draft.saving}
                      onClick={() => saveProposal(proposal)}
                    >
                      {draft.saving ? '保存中…' : '保存提案'}
                    </button>
                    <button
                      type="button"
                      disabled={draft.dirty || preview?.loading}
                      onClick={() => previewProposal(proposal)}
                    >
                      {preview?.loading ? '预览中…' : '预览 Diff'}
                    </button>
                    <button type="button" onClick={() => applyProposal(proposal)}>
                      {preview?.data &&
                      preview.proposalUpdatedAt === proposal.updatedAt
                        ? '确认应用'
                        : '应用提案'}
                    </button>
                    <button type="button" onClick={() => onReject(proposal)}>
                      拒绝
                    </button>
                  </>
                )}
              </div>
            </div>
          </details>
        )
      })}
    </div>
  )
}
