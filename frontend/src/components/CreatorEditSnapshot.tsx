import type { AssetProposalStatus } from '../types'

type TextVersion = {title: string; body: string}
type CanvasEditStatus = 'applied' | 'conflict' | 'pending_confirmation' | 'failed' | 'rejected'

function object(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

function version(value: unknown): TextVersion | null {
  const row = object(value)
  return typeof row.title === 'string' && typeof row.body === 'string'
    ? {title: row.title, body: row.body} : null
}

function Version({label, value}: {label: string; value: TextVersion}) {
  return <section className="creator-edit-version" aria-label={label}>
    <small className="muted">{label}</small>
    <strong>{value.title || '（空标题）'}</strong>
    <p>{value.body || '（正文为空）'}</p>
  </section>
}

/** Read only: historical text must never come from the current editable Topic. */
export function CreatorEditSnapshot({
  metadata,
  workspaceId,
  topicId,
  confirmationStatus: proposalStatus,
  confirmationResult: proposalResult,
}: {
  metadata: Record<string, unknown>; workspaceId: string; topicId: string;
  confirmationStatus?: AssetProposalStatus;
  confirmationResult?: Record<string, unknown>;
}) {
  const requestedStatus = metadata.canvasApplyStatus
  if (metadata.status === 'failed' || (requestedStatus !== 'applied' && requestedStatus !== 'conflict' && requestedStatus !== 'pending_confirmation')) return null
  const confirmationStatus = requestedStatus === 'pending_confirmation'
    ? proposalStatus : undefined
  const confirmationResult = requestedStatus === 'pending_confirmation'
    ? proposalResult : undefined
  const status: CanvasEditStatus = confirmationStatus === 'applied'
    ? 'applied'
    : confirmationStatus === 'failed' || confirmationStatus === 'rejected'
      ? confirmationStatus
      : requestedStatus
  const snapshot = object(metadata.canvasEditSnapshot)
  if (snapshot.workspaceId !== undefined && snapshot.workspaceId !== workspaceId
    || snapshot.topicId !== undefined && snapshot.topicId !== topicId) {
    return <small className="muted">此修改记录与当前选题不符，未展示内容。</small>
  }
  const supported = snapshot.schemaVersion === 'creator-edit/v1'
    && snapshot.workspaceId === workspaceId && snapshot.topicId === topicId
  const before = supported ? version(snapshot.before) : null
  const suggested = supported ? version(snapshot.suggested) : version(metadata.canvasUpdate)
  const appliedReceipt = object(confirmationResult)
  const after = supported && status === 'applied'
    ? version(snapshot.after) || version(appliedReceipt.after) : null
  const different = after && suggested && (after.title !== suggested.title || after.body !== suggested.body)
  const summary = status === 'applied' ? '当时已应用 · 查看修改'
    : status === 'pending_confirmation' ? '待你确认 · 查看原稿与建议'
      : status === 'rejected' ? '已忽略 · 查看原稿与建议'
        : '未应用 · 查看原稿与建议'
  const suggestionLabel = status === 'conflict' || status === 'failed' || status === 'rejected'
    ? 'AI 建议（未应用）'
    : status === 'pending_confirmation' ? 'AI 建议（待你确认）'
      : '当时的 AI 建议'
  const note = status === 'pending_confirmation'
    ? '建议尚未写入稿件，请在消息下方确认是否采用。'
    : status === 'conflict' || status === 'failed' || status === 'rejected'
      ? '建议没有覆盖稿件；这里的原稿是 AI 执行前的版本。'
      : '这是该次修改的历史记录，不代表当前稿件。'

  return <details className="creator-edit-snapshot">
    <summary>{summary}</summary>
    {before ? <Version label="修改前" value={before} />
      : <p className="muted">此记录未保存可读的修改前快照。</p>}
    {after ? <Version label="当时应用后" value={after} /> : status === 'applied'
      ? <p className="muted">此记录未保存可读的应用后快照。</p> : null}
    {suggested && (!after || different) && <Version
      label={suggestionLabel} value={suggested} />}
    {!suggested && !after && <p className="muted">此记录未保存可读的建议正文。</p>}
    <small className="muted">{note}</small>
  </details>
}
