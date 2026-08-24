import { useEffect, useState } from 'react'

import type { AssetProposal, AssetProposalPreview } from '../types'

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

export function AssetProposalsPanel({
  proposals,
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
