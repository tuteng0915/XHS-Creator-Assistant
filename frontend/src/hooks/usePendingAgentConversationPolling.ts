import { useEffect, type Dispatch, type SetStateAction } from 'react'

import { agentConversationApi, assetProposalApi } from '../api'
import type {
  AgentConversation,
  AgentConversationSummary,
  AssetProposal,
} from '../types'

export function conversationHasPendingAssistant(
  conversation: AgentConversation | null,
): boolean {
  return Boolean(
    conversation?.messages.some(
      (message) =>
        message.role === 'assistant' &&
        ['queued', 'running'].includes(String(message.modelMetadata.status || '')),
    ),
  )
}

type UsePendingAgentConversationPollingArgs = {
  selectedAgentConversation: AgentConversation | null
  selectedAgentConversationId?: string
  setSelectedAgentConversation: Dispatch<
    SetStateAction<AgentConversation | null>
  >
  setAgentConversations: Dispatch<SetStateAction<AgentConversationSummary[]>>
  setAssetProposals: Dispatch<SetStateAction<AssetProposal[]>>
}

export function usePendingAgentConversationPolling({
  selectedAgentConversation,
  selectedAgentConversationId,
  setSelectedAgentConversation,
  setAgentConversations,
  setAssetProposals,
}: UsePendingAgentConversationPollingArgs) {
  useEffect(() => {
    if (!selectedAgentConversationId) return
    if (!conversationHasPendingAssistant(selectedAgentConversation)) return
    let stopped = false
    const timer = window.setInterval(async () => {
      try {
        const conversation = await agentConversationApi.get(
          selectedAgentConversationId,
        )
        if (stopped) return
        setSelectedAgentConversation(conversation)
        setAgentConversations((current) =>
          current.map((item) =>
            item.id === conversation.id
              ? {
                  ...item,
                  status: conversation.status,
                  executionStatus: conversation.executionStatus,
                  updatedAt: conversation.updatedAt,
                }
              : item,
          ),
        )
        setAssetProposals(
          await assetProposalApi.listForConversation(selectedAgentConversationId),
        )
        if (!conversationHasPendingAssistant(conversation)) {
          window.clearInterval(timer)
        }
      } catch {
        // Keep the queued/running message visible; the next manual open can reload it.
      }
    }, 1000)
    return () => {
      stopped = true
      window.clearInterval(timer)
    }
  }, [
    selectedAgentConversation,
    selectedAgentConversationId,
    setAgentConversations,
    setAssetProposals,
    setSelectedAgentConversation,
  ])
}
