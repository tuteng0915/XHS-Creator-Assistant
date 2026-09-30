import { useState } from 'react'
import type { MediaAsset } from '../types'
import { notePublishedAt, type CreatorNote } from '../creatorNotes'
import { CreatorDialog } from './CreatorDialog'

// Shared browsing surface for My Notes and the diagnosis selection dialog.
export function CreatorNoteBrowser({ notes, mediaAssets, selectedIds, onToggle }: {
  notes: CreatorNote[]; mediaAssets: MediaAsset[];
  selectedIds?: string[]; onToggle?: (id: string) => void;
}) {
  const [detailId, setDetailId] = useState<string | null>(null)
  const detail = notes.find(note => note.noteId === detailId)
  const coverUrl = (note: CreatorNote) => (
    mediaAssets.find(asset => asset.id === note.coverMediaAssetId) ||
    mediaAssets.find(asset => asset.metadata.noteId === note.noteId)
  )?.fileUrl
  return <>
    <div className="creator-note-grid">
      {notes.map(note => <article key={note.noteId} className={`creator-note-item ${selectedIds?.includes(note.noteId) ? 'is-selected' : ''}`}>
        {onToggle && <label className="creator-note-check">
          <input type="checkbox" aria-label={`选择笔记：${note.title}`} checked={selectedIds?.includes(note.noteId) || false} onChange={() => onToggle(note.noteId)} />
          {selectedIds?.includes(note.noteId) ? '已选择' : '选择'}
        </label>}
        <button type="button" className="creator-note-card" onClick={() => setDetailId(note.noteId)}>
          {coverUrl(note) ? <img src={coverUrl(note)} alt={note.title} loading="lazy" /> : <div className="creator-note-placeholder">暂无封面</div>}
          <div><strong>{note.title}</strong><p>赞 {note.metrics.liked ?? '—'} · 收藏 {note.metrics.collected ?? '—'} · 评论 {note.metrics.comments ?? '—'}</p></div>
        </button>
      </article>)}
    </div>
    {detail && <CreatorDialog title={detail.title} onClose={() => setDetailId(null)}>
      <div className="creator-note-detail">
        {coverUrl(detail) && <img src={coverUrl(detail)} alt={detail.title} />}
        {notePublishedAt(detail) && <time>{new Date(notePublishedAt(detail)!).toLocaleDateString('zh-CN')}</time>}
        <p className="creator-note-body">{detail.desc || '暂未读取到正文'}</p>
        <section aria-label="笔记评论">
          <h3>评论 · {detail.comments.length}</h3>
          {detail.comments.length ? detail.comments.map((comment, index) => <p className="creator-note-comment" key={comment.commentId || index}>{comment.content || '图片评论'}<small>赞 {comment.likeCount ?? '—'}</small></p>) : <p>暂未读取到评论</p>}
        </section>
      </div>
    </CreatorDialog>}
  </>
}
