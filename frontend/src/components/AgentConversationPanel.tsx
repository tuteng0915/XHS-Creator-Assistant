import type { FormEvent, RefObject } from 'react'

import type {
  AgentConversation,
  AgentSummary,
  AssetProposal,
  AssetProposalPreview,
  SkillSummary,
} from '../types'
import type { GenerationMode } from '../workflows'
import { AssetProposalsPanel } from './AssetProposalsPanel'

type AgentConversationPanelProps = {
  conversation: AgentConversation | null
  agent: AgentSummary | null
  proposals: AssetProposal[]
  availableSkills: SkillSummary[]
  availableAgents: AgentSummary[]
  mode?: GenerationMode
  draft?: string
  sending?: boolean
  showComposer?: boolean
  showModeSwitch?: boolean
  composerRef?: RefObject<HTMLTextAreaElement | null>
  emptyText?: string
  onModeChange?: (mode: GenerationMode) => void
  onDraftChange?: (value: string) => void
  onSend?: (event: FormEvent) => void
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

export function AgentConversationPanel({
  conversation,
  agent,
  proposals,
  availableSkills,
  availableAgents,
  mode = 'demo',
  draft = '',
  sending = false,
  showComposer = true,
  showModeSwitch = true,
  composerRef,
  emptyText = '点击“开始对话”，直接调用这个 Agent。第一版只读 workspace context，并把潜在修改保存为 proposed actions。',
  onModeChange,
  onDraftChange,
  onSend,
  onUpdateProposal,
  onPreviewProposal,
  onApplyProposal,
  onRejectProposal,
}: AgentConversationPanelProps) {
  if (!conversation) {
    return <div className="empty-card">{emptyText}</div>
  }

  const agentName = agent?.displayName || 'Assistant'

  return (
    <>
      <div className="agent-chat">
        {showModeSwitch && (
          <>
            <p className="microcopy">
              当前对话模式：{mode === 'demo' ? '演示模式' : '实时生成'}
            </p>
            <div className="mode-switch">
              <button
                type="button"
                className={mode === 'demo' ? 'active' : ''}
                onClick={() => onModeChange?.('demo')}
              >
                演示模式
              </button>
              <button
                type="button"
                className={mode === 'live' ? 'active' : ''}
                onClick={() => onModeChange?.('live')}
              >
                实时生成
              </button>
            </div>
          </>
        )}
        {conversation.messages.length === 0 ? (
          <div className="empty-card compact-empty">
            发送第一条消息，Agent 会读取当前 workspace broad context。
          </div>
        ) : (
          conversation.messages.map((message) => (
            <div className={`chat-message ${message.role}`} key={message.id}>
              <b>{message.role === 'user' ? '你' : agentName}</b>
              <p>{message.content}</p>
              {message.role === 'assistant' && (
                <details>
                  <summary>
                    引用资产 {message.assetRefs.length} · Proposed Actions{' '}
                    {message.proposedActions.length}
                  </summary>
                  <pre className="json-preview">
                    {JSON.stringify(
                      {
                        assetRefs: message.assetRefs,
                        proposedActions: message.proposedActions,
                        modelMetadata: message.modelMetadata,
                      },
                      null,
                      2,
                    )}
                  </pre>
                </details>
              )}
            </div>
          ))
        )}
      </div>
      <AssetProposalsPanel
        proposals={proposals}
        availableSkills={availableSkills}
        availableAgents={availableAgents}
        onUpdate={onUpdateProposal}
        onPreview={onPreviewProposal}
        onApply={onApplyProposal}
        onReject={onRejectProposal}
      />
      {showComposer && (
        <form className="agent-chat-form" onSubmit={onSend}>
          <textarea
            ref={composerRef}
            rows={3}
            value={draft}
            onChange={(event) => onDraftChange?.(event.target.value)}
            placeholder="直接和这个 Agent 对话。第一版会引用 workspace 资产并提出建议，不会自动修改资产。"
          />
          <button className="primary" disabled={sending || !draft.trim()}>
            {sending ? '发送中…' : '发送给 Agent'}
          </button>
        </form>
      )}
    </>
  )
}
