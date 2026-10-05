type TextVersion = {title: string; body: string}

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
export function CreatorEditSnapshot({metadata, workspaceId, topicId}: {
  metadata: Record<string, unknown>; workspaceId: string; topicId: string;
}) {
  const status = metadata.canvasApplyStatus
  if (metadata.status === 'failed' || (status !== 'applied' && status !== 'conflict')) return null
  const snapshot = object(metadata.canvasEditSnapshot)
  if (snapshot.workspaceId !== undefined && snapshot.workspaceId !== workspaceId
    || snapshot.topicId !== undefined && snapshot.topicId !== topicId) {
    return <small className="muted">此修改记录与当前选题不符，未展示内容。</small>
  }
  const supported = snapshot.schemaVersion === 'creator-edit/v1'
    && snapshot.workspaceId === workspaceId && snapshot.topicId === topicId
  const before = supported ? version(snapshot.before) : null
  const suggested = supported ? version(snapshot.suggested) : version(metadata.canvasUpdate)
  const after = supported && status === 'applied' ? version(snapshot.after) : null
  const different = after && suggested && (after.title !== suggested.title || after.body !== suggested.body)

  return <details className="creator-edit-snapshot">
    <summary>{status === 'applied' ? '当时已应用 · 查看修改' : '未应用 · 查看原稿与建议'}</summary>
    {before ? <Version label="修改前" value={before} />
      : <p className="muted">此记录未保存可读的修改前快照。</p>}
    {after ? <Version label="当时应用后" value={after} /> : status === 'applied'
      ? <p className="muted">此记录未保存可读的应用后快照。</p> : null}
    {suggested && (!after || different) && <Version
      label={status === 'conflict' ? 'AI 建议（未应用）' : '当时的 AI 建议'} value={suggested} />}
    {!suggested && !after && <p className="muted">此记录未保存可读的建议正文。</p>}
    <small className="muted">{status === 'conflict'
      ? '建议没有覆盖稿件；这里的原稿是 AI 执行前的版本。'
      : '这是该次修改的历史记录，不代表当前稿件。'}</small>
  </details>
}
