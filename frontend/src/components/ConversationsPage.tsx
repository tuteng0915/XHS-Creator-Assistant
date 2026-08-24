import type {
  AgentConversation,
  AgentConversationStatus,
  AgentConversationSummary,
  AgentSummary,
  AssetProposal,
  AssetProposalPreview,
  SkillSummary,
} from '../types'
import { AgentConversationPanel } from './AgentConversationPanel'

type ConversationsPageProps = {
  conversations: AgentConversationSummary[]
  selectedConversation: AgentConversation | null
  agents: AgentSummary[]
  assetProposals: AssetProposal[]
  availableSkills: SkillSummary[]
  conversationTitleDraft: string
  conversationSaving: boolean
  conversationSaveStatus: string
  onOpenConversation: (conversationId: string) => void
  onOpenConversationAgent: (agentAssetId: string) => void
  onConversationTitleDraftChange: (value: string) => void
  onUpdateConversation: (patch: {
    title?: string
    status?: AgentConversationStatus
  }) => void
  onUpdateProposal: (
    proposal: AssetProposal,
    patch: {
      title: string
      description: string
      proposedAction: Record<string, unknown>
    },
  ) => Promise<AssetProposal>
  onPreviewProposal: (proposal: AssetProposal) => Promise<AssetProposalPreview>
  onApplyProposal: (proposal: AssetProposal) => Promise<void>
  onRejectProposal: (proposal: AssetProposal) => Promise<void>
}

export function ConversationsPage({
  conversations,
  selectedConversation,
  agents,
  assetProposals,
  availableSkills,
  conversationTitleDraft,
  conversationSaving,
  conversationSaveStatus,
  onOpenConversation,
  onOpenConversationAgent,
  onConversationTitleDraftChange,
  onUpdateConversation,
  onUpdateProposal,
  onPreviewProposal,
  onApplyProposal,
  onRejectProposal,
}: ConversationsPageProps) {
  const selectedConversationAgent = selectedConversation
    ? agents.find((agent) => agent.id === selectedConversation.agentAssetId) || null
    : null

  return (
    <div className="workspace-page">
      <section className="history-list">
        <div className="panel-title">💬 对话记录</div>
        <p className="subline">
          Agent 对话、Maker 生成建议和输入素材整理过程会自动保存；这里按内容资产方式复盘。
        </p>
        {conversations.length === 0 ? (
          <div className="empty-card compact-empty">
            暂无对话记录。可以从右侧 Agents 页面开始一次对话。
          </div>
        ) : (
          conversations.map((conversation) => {
            const agent = agents.find((item) => item.id === conversation.agentAssetId)
            return (
              <button
                key={conversation.id}
                className={`run-row ${
                  selectedConversation?.id === conversation.id ? 'active' : ''
                }`}
                onClick={() => onOpenConversation(conversation.id)}
              >
                <span>{conversation.title}</span>
                <b>{conversation.executionStatus || conversation.status}</b>
                <small>
                  {agent?.displayName || 'Unknown Agent'} ·{' '}
                  {new Date(conversation.updatedAt).toLocaleString()}
                </small>
              </button>
            )
          })
        )}
      </section>
      <section className="history-detail">
        {selectedConversation ? (
          <>
            <div className="detail-head">
              <div>
                <h2>{selectedConversation.title}</h2>
                <p>
                  {selectedConversationAgent?.displayName || 'Unknown Agent'} ·{' '}
                  {selectedConversation.executionStatus || selectedConversation.status} ·{' '}
                  {new Date(selectedConversation.updatedAt).toLocaleString()}
                </p>
              </div>
              <span>{selectedConversation.status}</span>
            </div>
            {Object.keys(selectedConversation.contextTarget || {}).length > 0 && (
              <>
                <label>Context Target</label>
                <pre className="json-preview">
                  {JSON.stringify(selectedConversation.contextTarget, null, 2)}
                </pre>
              </>
            )}
            <div className="detail-actions">
              <button
                type="button"
                disabled={!selectedConversationAgent}
                onClick={() => {
                  if (!selectedConversationAgent) return
                  onOpenConversationAgent(selectedConversationAgent.id)
                }}
              >
                打开对应 Agent
              </button>
              <button
                type="button"
                disabled={conversationSaving}
                onClick={() =>
                  onUpdateConversation({
                    status:
                      selectedConversation.status === 'archived'
                        ? 'active'
                        : 'archived',
                  })
                }
              >
                {selectedConversation.status === 'archived'
                  ? '恢复对话'
                  : '归档对话'}
              </button>
            </div>
            <div className="source-editor-card compact">
              <label htmlFor="conversation-title-editor">对话标题</label>
              <input
                id="conversation-title-editor"
                value={conversationTitleDraft}
                onChange={(event) => onConversationTitleDraftChange(event.target.value)}
              />
              <div className="save-row">
                <button
                  className="save-button"
                  disabled={
                    conversationSaving ||
                    !conversationTitleDraft.trim() ||
                    conversationTitleDraft === selectedConversation.title
                  }
                  onClick={() =>
                    onUpdateConversation({
                      title: conversationTitleDraft.trim(),
                    })
                  }
                >
                  {conversationSaving ? '保存中…' : '保存对话标题'}
                </button>
                {conversationSaveStatus && (
                  <span
                    className={
                      conversationSaveStatus.startsWith('error:')
                        ? 'inline-error'
                        : 'inline-save-state'
                    }
                  >
                    {conversationSaveStatus === 'saving'
                      ? '保存中…'
                      : conversationSaveStatus === 'saved'
                        ? '已保存'
                        : conversationSaveStatus.replace('error:', '保存失败：')}
                  </span>
                )}
              </div>
            </div>
            <div className="conversation-asset-chat">
              <AgentConversationPanel
                conversation={selectedConversation}
                agent={selectedConversationAgent}
                proposals={assetProposals}
                availableSkills={availableSkills}
                availableAgents={agents}
                showComposer={false}
                showModeSwitch={false}
                onUpdateProposal={onUpdateProposal}
                onPreviewProposal={onPreviewProposal}
                onApplyProposal={onApplyProposal}
                onRejectProposal={onRejectProposal}
              />
            </div>
          </>
        ) : (
          <div className="empty-card">
            选择一条对话记录，查看消息、引用资产、model metadata 和 proposed actions。
          </div>
        )}
      </section>
    </div>
  )
}
