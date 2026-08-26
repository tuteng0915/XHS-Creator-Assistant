import type { ReactNode } from 'react'

import { ErrorBanner } from './CommonUi'
import type {
  Agent,
  AgentConversation,
  AgentConversationSummary,
  AgentSummary,
  SkillSummary,
} from '../types'

type AgentsPageProps = {
  agents: AgentSummary[]
  skills: SkillSummary[]
  selectedAgent: Agent | null
  conversations: AgentConversationSummary[]
  selectedConversation: AgentConversation | null
  agentConversationCreating: boolean
  runError: string
  definitionDiffPanel: ReactNode
  definitionEditor: ReactNode
  conversationPanel: ReactNode
  onOpenAgent: (agentAssetId: string) => void
  onEditAgent: (agent: Agent) => void
  onDesignAgent: () => void
  onTuneAgent: (agent: Agent) => void
  onStartConversation: (agent: Agent) => void
  onOpenConversation: (conversationId: string) => void
  onOpenSkill: (skillAssetId: string) => void
}

function capabilityStatusClass(status: 'enabled' | 'disabled'): string {
  return `capability-status ${status}`
}

export function AgentsPage({
  agents,
  skills,
  selectedAgent,
  conversations,
  selectedConversation,
  agentConversationCreating,
  runError,
  definitionDiffPanel,
  definitionEditor,
  conversationPanel,
  onOpenAgent,
  onEditAgent,
  onDesignAgent,
  onTuneAgent,
  onStartConversation,
  onOpenConversation,
  onOpenSkill,
}: AgentsPageProps) {
  const selectedAgentConversations = selectedAgent
    ? conversations.filter(
        (conversation) => conversation.agentAssetId === selectedAgent.id,
      )
    : []

  return (
    <div className="workspace-page">
      <section className="history-list">
        <div className="panel-title">◉ Agents</div>
        <p className="subline">
          Agent 是产品角色资产：system prompt + 多个 Skills +
          默认上下文边界。用户侧只读展示，不提供通用 agent builder。
        </p>
        <div className="asset-maker-call">
          <span>
            描述你需要的角色，Capability Maker 会组合 system prompt、skills 和上下文边界。
          </span>
          <button
            className="small-primary"
            disabled={agentConversationCreating}
            onClick={onDesignAgent}
          >
            让 Capability Maker 设计 Agent
          </button>
        </div>
        <ErrorBanner message={runError} />
        {agents.map((agent) => (
          <button
            key={agent.id}
            className={`run-row ${selectedAgent?.id === agent.id ? 'active' : ''}`}
            onClick={() => onOpenAgent(agent.id)}
          >
            <span>{agent.displayName}</span>
            <b className={capabilityStatusClass(agent.status)}>{agent.status}</b>
            <small>{agent.agentId}</small>
          </button>
        ))}
        {selectedAgent && (
          <>
            <div className="panel-title secondary-title">Conversations</div>
            <button
              className="small-primary"
              disabled={agentConversationCreating}
              onClick={() => onStartConversation(selectedAgent)}
            >
              {agentConversationCreating ? '创建中…' : '＋ 开始对话'}
            </button>
            {selectedAgentConversations.length === 0 ? (
              <div className="empty-card compact-empty">暂无 agent 对话。</div>
            ) : (
              selectedAgentConversations.map((conversation) => (
                <button
                  key={conversation.id}
                  className={`run-row ${
                    selectedConversation?.id === conversation.id ? 'active' : ''
                  }`}
                  onClick={() => onOpenConversation(conversation.id)}
                >
                  <span>{conversation.title}</span>
                  <b>{conversation.executionStatus || conversation.status}</b>
                  <small>{new Date(conversation.updatedAt).toLocaleString()}</small>
                </button>
              ))
            )}
          </>
        )}
      </section>
      <section className="history-detail">
        {selectedAgent ? (
          <>
            <div className="detail-head">
              <div>
                <h2>{selectedAgent.displayName}</h2>
                <p>
                  {selectedAgent.agentId} · {selectedAgent.source} ·{' '}
                  {selectedAgent.version}
                </p>
              </div>
              <span className={capabilityStatusClass(selectedAgent.status)}>
                {selectedAgent.status}
              </span>
            </div>
            <div className="detail-actions">
              <button type="button" onClick={() => onEditAgent(selectedAgent)}>
                编辑 Agent
              </button>
              <button
                type="button"
                disabled={agentConversationCreating}
                onClick={() => onTuneAgent(selectedAgent)}
              >
                让 Capability Maker 调优
              </button>
            </div>
            {definitionDiffPanel}
            {definitionEditor}
            <p>{selectedAgent.purpose}</p>
            <label>System Prompt</label>
            <div className="why">{selectedAgent.systemPrompt}</div>
            <label>Skills</label>
            <div className="capability-ref-list" aria-label="组合能力">
              {selectedAgent.skillIds.length === 0 ? (
                <div className="empty-card compact">未绑定 Skill。</div>
              ) : (
                selectedAgent.skillIds.map((skillId) => {
                  const skill = skills.find((item) => item.skillId === skillId)
                  return (
                    <button
                      key={skillId}
                      type="button"
                      className="capability-ref-chip"
                      disabled={!skill}
                      onClick={() => skill && onOpenSkill(skill.id)}
                    >
                      <b>{skill?.displayName || skillId}</b>
                      <small>{skillId}</small>
                    </button>
                  )
                })
              )}
            </div>
            <label>Default Context Policy</label>
            <pre className="json-preview">
              {JSON.stringify(selectedAgent.defaultContextPolicy, null, 2)}
            </pre>
            {selectedAgent.userNotes && (
              <>
                <label>Workspace Notes</label>
                <div className="why">{selectedAgent.userNotes}</div>
              </>
            )}
            <label>Agent Conversation</label>
            {conversationPanel}
          </>
        ) : (
          <div className="empty-card">
            选择一个 Agent 查看 system prompt、skills 和上下文边界。
          </div>
        )}
      </section>
    </div>
  )
}
