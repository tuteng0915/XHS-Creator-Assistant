import {
  agentPlanJsonWithTasks,
  listFromText,
  textFromList,
  workflowTasksFromPlanJson,
  type WorkflowDefinitionDraft,
  type WorkflowTaskDraft,
} from '../capabilityDefinitionValidation'
import type { AgentSummary, SkillSummary, WorkflowAsset } from '../types'

type Props = {
  draft: WorkflowDefinitionDraft | null
  saving: boolean
  status: string
  agents: AgentSummary[]
  skills: SkillSummary[]
  onDraftChange: (draft: WorkflowDefinitionDraft | null) => void
  onStatusChange: (status: string) => void
  onSave: () => void
}

export function WorkflowDefinitionEditor({
  draft,
  saving,
  status,
  agents,
  skills,
  onDraftChange,
  onStatusChange,
  onSave,
}: Props) {
  if (!draft) return null

  const updateDraft = (patch: Partial<WorkflowDefinitionDraft>) => {
    onDraftChange({ ...draft, ...patch })
  }
  const workflowTaskDrafts = workflowTasksFromPlanJson(draft.agentPlanJson)
  const updateTaskDrafts = (tasks: WorkflowTaskDraft[]) => {
    updateDraft({
      agentPlanJson: agentPlanJsonWithTasks(draft.agentPlanJson, tasks),
    })
  }
  const statusText =
    status === 'saving'
      ? '保存中…'
      : status === 'saved'
        ? '已保存'
        : status.startsWith('error:')
          ? status.replace('error:', '保存失败：')
          : ''

  return (
    <div className="source-editor-card capability-editor-card">
      <p className="subline">
        PM 调优模式：保存后会把当前 workflow 变成 workspace-level generated override。
        这里编辑的是产品 task plan，不是任意图执行器。
      </p>
      <div className="compact-grid two-col">
        <div>
          <label htmlFor="workflow-display-name">Workflow 名称</label>
          <input
            id="workflow-display-name"
            value={draft.displayName}
            onChange={(event) => updateDraft({ displayName: event.target.value })}
          />
        </div>
        <div>
          <label htmlFor="workflow-version">版本</label>
          <input
            id="workflow-version"
            value={draft.version}
            onChange={(event) => updateDraft({ version: event.target.value })}
          />
        </div>
      </div>
      <label htmlFor="workflow-purpose">用途 / 调优说明</label>
      <textarea
        id="workflow-purpose"
        rows={3}
        value={draft.purpose}
        onChange={(event) => updateDraft({ purpose: event.target.value })}
      />
      <label htmlFor="workflow-entry-agent-ids">Entry Agent IDs（一行一个）</label>
      <textarea
        id="workflow-entry-agent-ids"
        rows={4}
        value={draft.entryAgentIds}
        onChange={(event) => updateDraft({ entryAgentIds: event.target.value })}
      />
      <div className="structured-editor-card">
        <div className="asset-section-head">
          <h3>Workflow Tasks</h3>
          <span>structured</span>
        </div>
        <p className="subline">
          表格会同步写入 agentPlan.tasks。复杂字段仍可在下方 JSON 里手动编辑。
        </p>
        {workflowTaskDrafts === null ? (
          <div className="err">Agent Task Plan JSON 当前无法解析，先修复 JSON。</div>
        ) : (
          <>
            <div className="workflow-task-editor">
              {workflowTaskDrafts.map((task, index) => (
                <div className="workflow-task-card" key={`${task.taskId}-${index}`}>
                  <div className="asset-section-head">
                    <h3>Task {index + 1}</h3>
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() =>
                        updateTaskDrafts(
                          workflowTaskDrafts.filter((_, itemIndex) => itemIndex !== index),
                        )
                      }
                    >
                      删除
                    </button>
                  </div>
                  <div className="compact-grid two-col">
                    <div>
                      <label htmlFor={`workflow-task-id-${index}`}>Task ID</label>
                      <input
                        id={`workflow-task-id-${index}`}
                        value={task.taskId}
                        onChange={(event) => {
                          const next = [...workflowTaskDrafts]
                          next[index] = { ...task, taskId: event.target.value }
                          updateTaskDrafts(next)
                        }}
                      />
                    </div>
                    <div>
                      <label htmlFor={`workflow-task-agent-${index}`}>Agent</label>
                      <select
                        id={`workflow-task-agent-${index}`}
                        value={task.agentId}
                        onChange={(event) => {
                          const next = [...workflowTaskDrafts]
                          next[index] = { ...task, agentId: event.target.value }
                          updateTaskDrafts(next)
                        }}
                      >
                        <option value="">未选择</option>
                        {agents.map((agent) => (
                          <option key={agent.id} value={agent.agentId}>
                            {agent.displayName} · {agent.agentId}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                  <label htmlFor={`workflow-task-skills-${index}`}>
                    Skill IDs（一行一个）
                  </label>
                  <textarea
                    id={`workflow-task-skills-${index}`}
                    rows={3}
                    value={task.skillIds}
                    onChange={(event) => {
                      const next = [...workflowTaskDrafts]
                      next[index] = { ...task, skillIds: event.target.value }
                      updateTaskDrafts(next)
                    }}
                  />
                  <div className="capability-checkbox-list compact">
                    {skills.map((skill) => {
                      const selected = listFromText(task.skillIds).includes(skill.skillId)
                      return (
                        <label key={skill.id}>
                          <input
                            type="checkbox"
                            checked={selected}
                            onChange={(event) => {
                              const nextSkills = new Set(listFromText(task.skillIds))
                              if (event.target.checked) nextSkills.add(skill.skillId)
                              else nextSkills.delete(skill.skillId)
                              const next = [...workflowTaskDrafts]
                              next[index] = {
                                ...task,
                                skillIds: textFromList([...nextSkills]),
                              }
                              updateTaskDrafts(next)
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
                  <div className="compact-grid two-col">
                    <div>
                      <label htmlFor={`workflow-task-depends-${index}`}>
                        Depends On（一行一个 taskId）
                      </label>
                      <textarea
                        id={`workflow-task-depends-${index}`}
                        rows={3}
                        value={task.dependsOn}
                        onChange={(event) => {
                          const next = [...workflowTaskDrafts]
                          next[index] = { ...task, dependsOn: event.target.value }
                          updateTaskDrafts(next)
                        }}
                      />
                    </div>
                    <label className="checkbox-line">
                      <input
                        type="checkbox"
                        checked={task.parallel}
                        onChange={(event) => {
                          const next = [...workflowTaskDrafts]
                          next[index] = { ...task, parallel: event.target.checked }
                          updateTaskDrafts(next)
                        }}
                      />
                      可并行执行
                    </label>
                  </div>
                </div>
              ))}
            </div>
            <button
              type="button"
              className="secondary-button"
              onClick={() =>
                updateTaskDrafts([
                  ...workflowTaskDrafts,
                  {
                    taskId: `task_${workflowTaskDrafts.length + 1}`,
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
      </div>
      <label htmlFor="workflow-agent-plan-json">Agent Task Plan JSON</label>
      <textarea
        id="workflow-agent-plan-json"
        rows={12}
        value={draft.agentPlanJson}
        onChange={(event) => updateDraft({ agentPlanJson: event.target.value })}
      />
      <div className="compact-grid two-col">
        <div>
          <label htmlFor="workflow-artifact-effect">Artifact Effect</label>
          <input
            id="workflow-artifact-effect"
            value={draft.artifactEffect}
            onChange={(event) => updateDraft({ artifactEffect: event.target.value })}
          />
        </div>
        <div>
          <label htmlFor="workflow-call-binding-edit">调用注册</label>
          <select
            id="workflow-call-binding-edit"
            value={draft.callBinding}
            onChange={(event) =>
              updateDraft({
                callBinding: event.target.value as WorkflowAsset['callBinding'],
              })
            }
          >
            <option value="">不注册为调用入口</option>
            <option value="account">账号诊断执行入口</option>
            <option value="trend">热点分析执行入口</option>
            <option value="video">视频博主质量诊断执行入口</option>
          </select>
        </div>
      </div>
      <label htmlFor="workflow-user-notes">Workspace Notes</label>
      <textarea
        id="workflow-user-notes"
        rows={3}
        value={draft.userNotes}
        onChange={(event) => updateDraft({ userNotes: event.target.value })}
      />
      <div className="save-row">
        <button className="save-button" disabled={saving} onClick={onSave}>
          {saving ? '保存中…' : '保存 Workflow Definition'}
        </button>
        <button
          type="button"
          className="secondary-button"
          disabled={saving}
          onClick={() => {
            onDraftChange(null)
            onStatusChange('')
          }}
        >
          取消编辑
        </button>
        {statusText && (
          <span
            className={
              status.startsWith('error:') ? 'inline-error' : 'inline-save-state'
            }
          >
            {statusText}
          </span>
        )}
      </div>
    </div>
  )
}
