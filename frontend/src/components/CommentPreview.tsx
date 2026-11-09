import { useState } from 'react'
import { commentPreviewApi } from '../api'
import type { CommentPreview as Preview, CommentPreviewTarget } from '../types'
import { InfoHint } from './InfoHint'
import './CommentPreview.css'

export function CommentPreview({workspaceId, target, disabled}: {
  workspaceId: string
  target: CommentPreviewTarget
  disabled?: boolean
}) {
  const [preview, setPreview] = useState<Preview | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function run() {
    setBusy(true); setError('')
    try { setPreview(await commentPreviewApi.create(workspaceId, target)) }
    catch (e) { setError(e instanceof Error ? e.message : String(e)) }
    finally { setBusy(false) }
  }
  return <section className="comment-preview" aria-label="评论区预览">
    <div className="comment-preview-heading">
      <h3>评论区预览 <InfoHint label="评论区预览说明">根据帖子场合从反应标签库中选择可能出现的留言，是模拟结果，不代表真实评论。只读文字，看不到配图。</InfoHint></h3>
      <button type="button" disabled={disabled || busy} onClick={() => void run()}>
        {busy ? '正在生成…' : preview ? '重新预览' : '预览评论区'}</button>
    </div>
    {error && <p role="alert">{error}</p>}
    {preview && <>
      <p className="comment-preview-occasion"><span>{preview.occasion}</span>{preview.occasionReason}</p>
      <ul>{preview.comments.map((comment, index) => <li key={`${index}-${comment.text}`}>
        <p>{comment.text}</p>
        <div className="comment-preview-tags">
          <span className={comment.isNewTag ? 'comment-preview-tag is-new' : 'comment-preview-tag'}>
            {comment.tag}{comment.detail && ` · ${comment.detail}`}{comment.isNewTag && '（现场新增）'}</span>
          {comment.reader && <small>{comment.reader}</small>}
          {comment.target && <small>{comment.target}</small>}
        </div>
      </li>)}</ul>
    </>}
  </section>
}
