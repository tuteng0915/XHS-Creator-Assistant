import type { ReactNode } from 'react'

import type {
  AgentSummary,
  SkillSummary,
  WorkflowAsset,
  WorkflowAssetSummary,
} from '../types'

type WorkflowsPageProps = {
  workflowAssets: WorkflowAssetSummary[]
  agents: AgentSummary[]
  skills: SkillSummary[]
  selectedWorkflowAsset: WorkflowAsset | null
  agentConversationCreating: boolean
  definitionDiffPanel: ReactNode
  definitionEditor: ReactNode
  onOpenWorkflow: (workflowAssetId: string) => void
  onEditWorkflow: (workflowAsset: WorkflowAsset) => void
  onDesignWorkflow: () => void
  onTuneWorkflow: (workflowAsset: WorkflowAsset) => void
  onUpdateCallBinding: (
    workflowAsset: WorkflowAsset,
    callBinding: WorkflowAsset['callBinding'],
  ) => void
  onOpenAgent: (agentAssetId: string) => void
  onOpenSkill: (skillAssetId: string) => void
}

function capabilityStatusClass(status: 'enabled' | 'disabled'): string {
  return `capability-status ${status}`
}

export function WorkflowsPage({
  workflowAssets,
  agents,
  skills,
  selectedWorkflowAsset,
  agentConversationCreating,
  definitionDiffPanel,
  definitionEditor,
  onOpenWorkflow,
  onEditWorkflow,
  onDesignWorkflow,
  onTuneWorkflow,
  onUpdateCallBinding,
  onOpenAgent,
  onOpenSkill,
}: WorkflowsPageProps) {
  const tasks = Array.isArray(selectedWorkflowAsset?.agentPlan.tasks)
    ? selectedWorkflowAsset.agentPlan.tasks
    : []

  return (
    <div className="workspace-page">
      <section className="history-list">
        <div className="panel-title">⌘ Workflows</div>
        <p className="subline">
          Workflow 是多 agent、多级 task 的产品工作流资产；用户侧只读展示计划结构，
          不提供通用流程编辑器。
        </p>
        <div className="asset-maker-call">
          <span>描述你想新增的创作者链路，Capability Maker 会生成多 Agent task plan 提案。</span>
          <button
            className="small-primary"
            disabled={agentConversationCreating}
            onClick={onDesignWorkflow}
          >
            让 Capability Maker 设计 Workflow
          </button>
        </div>
        {workflowAssets.map((workflowAsset) => (
          <button
            key={workflowAsset.id}
            className={`run-row ${
              selectedWorkflowAsset?.id === workflowAsset.id ? 'active' : ''
            }`}
            onClick={() => onOpenWorkflow(workflowAsset.id)}
          >
            <span>{workflowAsset.displayName}</span>
            <b className={capabilityStatusClass(workflowAsset.status)}>
              {workflowAsset.status}
            </b>
            <small>
              {workflowAsset.workflowId}
              {workflowAsset.callBinding ? ` · 调用:${workflowAsset.callBinding}` : ''}
            </small>
          </button>
        ))}
      </section>
      <section className="history-detail">
        {selectedWorkflowAsset ? (
          <>
            <div className="detail-head">
              <div>
                <h2>{selectedWorkflowAsset.displayName}</h2>
                <p>
                  {selectedWorkflowAsset.workflowId} · {selectedWorkflowAsset.source} ·{' '}
                  {selectedWorkflowAsset.version}
                </p>
              </div>
              <span className={capabilityStatusClass(selectedWorkflowAsset.status)}>
                {selectedWorkflowAsset.status}
              </span>
            </div>
            <div className="detail-actions">
              <button type="button" onClick={() => onEditWorkflow(selectedWorkflowAsset)}>
                编辑 Workflow
              </button>
              <button
                type="button"
                disabled={agentConversationCreating}
                onClick={() => onTuneWorkflow(selectedWorkflowAsset)}
              >
                让 Capability Maker 调优
              </button>
            </div>
            {definitionDiffPanel}
            {definitionEditor}
            <p>{selectedWorkflowAsset.purpose}</p>
            <label>Workflow 调用注册</label>
            <div className="source-editor-card compact">
              <p className="subline">
                注册后会出现在右侧 workflow 调用区。这里绑定的是已有产品执行入口，
                不会把 workflow asset 当成任意图执行器。
              </p>
              <select
                aria-label="Workflow 调用注册"
                value={selectedWorkflowAsset.callBinding}
                onChange={(event) =>
                  onUpdateCallBinding(
                    selectedWorkflowAsset,
                    event.target.value as WorkflowAsset['callBinding'],
                  )
                }
              >
                <option value="">不注册为调用入口</option>
                <option value="account">账号诊断执行入口</option>
                <option value="trend">热点分析执行入口</option>
                <option value="video">视频博主质量诊断执行入口</option>
              </select>
            </div>
            <label>Artifact Effect</label>
            <div className="why">{selectedWorkflowAsset.artifactEffect}</div>
            <label>Entry Agents</label>
            <div className="capability-ref-list" aria-label="入口角色">
              {selectedWorkflowAsset.entryAgentIds.length === 0 ? (
                <div className="empty-card compact">未配置入口 Agent。</div>
              ) : (
                selectedWorkflowAsset.entryAgentIds.map((agentId) => {
                  const agent = agents.find((item) => item.agentId === agentId)
                  return (
                    <button
                      key={agentId}
                      type="button"
                      className="capability-ref-chip"
                      disabled={!agent}
                      onClick={() => agent && onOpenAgent(agent.id)}
                    >
                      <b>{agent?.displayName || agentId}</b>
                      <small>{agentId}</small>
                    </button>
                  )
                })
              )}
            </div>
            {tasks.length > 0 && (
              <>
                <label>Task 组装关系</label>
                <div className="workflow-task-summary-list">
                  {tasks.map((task, index) => {
                    const taskRecord =
                      task && typeof task === 'object'
                        ? (task as Record<string, unknown>)
                        : {}
                    const taskId = String(taskRecord.taskId || taskRecord.id || index + 1)
                    const agentId = String(taskRecord.agentId || '')
                    const taskSkillIds = Array.isArray(taskRecord.skillIds)
                      ? taskRecord.skillIds.filter(
                          (item): item is string => typeof item === 'string',
                        )
                      : []
                    const description =
                      typeof taskRecord.description === 'string'
                        ? taskRecord.description
                        : ''
                    const agent = agents.find((item) => item.agentId === agentId)
                    return (
                      <div className="workflow-task-summary-card" key={`${taskId}-${index}`}>
                        <div>
                          <b>{String(taskRecord.label || taskRecord.name || taskId)}</b>
                          {description && <p>{description}</p>}
                        </div>
                        {agentId && (
                          <button
                            type="button"
                            className="capability-ref-chip compact"
                            disabled={!agent}
                            onClick={() => agent && onOpenAgent(agent.id)}
                          >
                            <b>{agent?.displayName || agentId}</b>
                            <small>{agentId}</small>
                          </button>
                        )}
                        {taskSkillIds.length > 0 && (
                          <div className="capability-ref-list inline">
                            {taskSkillIds.map((skillId) => {
                              const skill = skills.find((item) => item.skillId === skillId)
                              return (
                                <button
                                  key={skillId}
                                  type="button"
                                  className="capability-ref-chip compact"
                                  disabled={!skill}
                                  onClick={() => skill && onOpenSkill(skill.id)}
                                >
                                  <b>{skill?.displayName || skillId}</b>
                                  <small>{skillId}</small>
                                </button>
                              )
                            })}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </>
            )}
            <label>Agent Task Plan</label>
            <pre className="json-preview">
              {JSON.stringify(selectedWorkflowAsset.agentPlan, null, 2)}
            </pre>
            {selectedWorkflowAsset.userNotes && (
              <>
                <label>Workspace Notes</label>
                <div className="why">{selectedWorkflowAsset.userNotes}</div>
              </>
            )}
          </>
        ) : (
          <div className="empty-card">
            选择一个 Workflow 查看 entry agents、task 层级和产物影响。
          </div>
        )}
      </section>
    </div>
  )
}
