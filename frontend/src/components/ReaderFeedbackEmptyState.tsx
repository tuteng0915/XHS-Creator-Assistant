import './ReaderFeedbackEmptyState.css'

function record(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown> : null
}

function authorHash(value: unknown): string {
  const hash = typeof value === 'string' ? value.trim().toLowerCase() : ''
  return /^[0-9a-f]{16}$/.test(hash) ? hash : ''
}

function readerCommentSample(profile: unknown) {
  const notes = record(profile)?.notes
  if (!Array.isArray(notes)) return null
  let candidates = 0
  const comments: Array<{ content: string; title: string }> = []
  for (const value of notes) {
    const note = record(value)
    if (!note || !Array.isArray(note.comments)) continue
    const owner = authorHash(note.authorHash)
    for (const value of note.comments) {
      const comment = record(value)
      // Match the backend: unknown identities remain eligible, only a verified
      // note-author hash match is excluded. Never infer roles from wording.
      if (!comment || (owner && owner === authorHash(comment.authorHash))) continue
      candidates += 1
      if (typeof comment.content === 'string' && comment.content.trim()) {
        comments.push({ content: comment.content.trim(), title: typeof note.title === 'string' ? note.title : '' })
      }
    }
  }
  return { candidates, comments }
}

export function ReaderFeedbackEmptyState({ profile }: { profile?: unknown }) {
  const sample = readerCommentSample(profile)
  if (!sample) return <p className="muted">本次未提炼出读者反馈。</p>
  if (!sample.comments.length) {
    return <p className="muted">{sample.candidates
      ? '本次评论没有可分析的文字。'
      : '本次所选笔记没有可用的读者评论。'}</p>
  }
  const preview = sample.comments.slice(0, 6)
  return <div className="reader-feedback-empty">
    <p className="muted">本次有 {sample.comments.length} 条文字评论，但未提炼出反馈主题。</p>
    <h4>评论原文</h4>
    <ul className="reader-feedback-source-list">
      {preview.map((comment, index) => <li key={index}>
        <blockquote>{comment.content}</blockquote>
        {comment.title && <span className="reader-feedback-source-title">《{comment.title}》</span>}
      </li>)}
    </ul>
    {sample.comments.length > preview.length && <details>
      <summary>其余 {sample.comments.length - preview.length} 条评论原文</summary>
      <ul className="reader-feedback-source-list">
        {sample.comments.slice(preview.length).map((comment, index) => <li key={index}>
          <blockquote>{comment.content}</blockquote>
          {comment.title && <span className="reader-feedback-source-title">《{comment.title}》</span>}
        </li>)}
      </ul>
    </details>}
  </div>
}
