import { useEffect, type RefObject } from 'react'

import type { ActivePage } from '../components/WorkspaceShell'

export function useAgentConversationAutoFocus({
  activePage,
  selectedAgentConversationId,
  composerRef,
}: {
  activePage: ActivePage
  selectedAgentConversationId?: string
  composerRef: RefObject<HTMLTextAreaElement | null>
}) {
  useEffect(() => {
    if (activePage !== 'agents' || !selectedAgentConversationId) return
    window.setTimeout(() => {
      const composer = composerRef.current
      if (!composer) return
      if (typeof composer.scrollIntoView === 'function') {
        composer.scrollIntoView({ block: 'center', behavior: 'smooth' })
      }
      composer.focus()
    }, 0)
  }, [activePage, composerRef, selectedAgentConversationId])
}
