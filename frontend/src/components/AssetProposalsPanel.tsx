import { useEffect, useState } from 'react'

import type { AssetProposal } from '../types'

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
  onUpdate: (
    proposal: AssetProposal,
    patch: {
      title: string
      description: string
      proposedAction: Record<string, unknown>
    },
  ) => Promise<void>
  onApply: (proposal: AssetProposal) => Promise<void>
  onReject: (proposal: AssetProposal) => Promise<void>
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

export function AssetProposalsPanel({
  proposals,
  onUpdate,
  onApply,
  onReject,
}: AssetProposalsPanelProps) {
  const [drafts, setDrafts] = useState<Record<string, AssetProposalDraft>>({})

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
  }

  async function saveProposal(proposal: AssetProposal) {
    const draft = drafts[proposal.id]
    if (!draft) return
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
      return
    }
    updateDraft(proposal.id, { saving: true, error: '', dirty: draft.dirty })
    try {
      await onUpdate(proposal, {
        title: draft.title,
        description: draft.description,
        proposedAction,
      })
      setDrafts((current) => ({
        ...current,
        [proposal.id]: {
          ...current[proposal.id],
          saving: false,
          dirty: false,
          error: '',
        },
      }))
    } catch (error) {
      updateDraft(proposal.id, {
        saving: false,
        error: error instanceof Error ? error.message : '保存 proposal 失败。',
        dirty: true,
      })
    }
  }

  return (
    <div className="source-editor-card">
      <label>Asset Proposals</label>
      {proposals.map((proposal) => {
        const draft = drafts[proposal.id] || draftFromProposal(proposal)
        const isPending = proposal.status === 'pending'
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
                    <button type="button" onClick={() => onApply(proposal)}>
                      Apply
                    </button>
                    <button type="button" onClick={() => onReject(proposal)}>
                      Reject
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
