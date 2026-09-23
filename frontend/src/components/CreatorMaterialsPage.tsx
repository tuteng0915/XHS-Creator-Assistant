import { useState } from 'react'

import type { MediaAsset, TextInputAsset } from '../types'
import { CreatorDialog } from './CreatorDialog'
import { creatorNotes, notePublishedAt } from '../creatorNotes'

export function CreatorMaterialsPage({ profile, mediaAssets, onImport, onAnalyze }: {
  profile?: TextInputAsset
  mediaAssets: MediaAsset[]
  onImport: () => void
  onAnalyze: () => void
}) {
  const notes = creatorNotes(profile)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const selected = notes.find((note) => note.noteId === selectedId)
  const coverUrl = (note: typeof notes[number]) => (
    mediaAssets.find((asset) => asset.id === note.coverMediaAssetId) ||
    mediaAssets.find((asset) => asset.metadata.noteId === note.noteId)
  )?.fileUrl
  return (
    <section className="creator-materials-page">
      <div className="creator-page-head">
        <h1>我的笔记</h1>
        <div>
          <button type="button" onClick={onImport}>抓取更多笔记</button>
          <button type="button" className="primary" disabled={!notes.length} onClick={onAnalyze}>分析账号</button>
        </div>
      </div>
      {!notes.length && <p className="empty-card">导入账号后，你的笔记会出现在这里。</p>}
      <div className="creator-note-grid">
        {notes.map((note) => (
          <button key={note.noteId} className="creator-note-card" onClick={() => setSelectedId(note.noteId)}>
            {coverUrl(note) ? <img src={coverUrl(note)} alt={note.title} loading="lazy" /> : <div className="creator-note-placeholder">暂无封面</div>}
            <div><strong>{note.title}</strong><p>赞 {note.metrics.liked ?? '—'} · 收藏 {note.metrics.collected ?? '—'} · 评论 {note.metrics.comments ?? '—'}</p></div>
          </button>
        ))}
      </div>
      {selected && <CreatorDialog title={selected.title} onClose={() => setSelectedId(null)}>
        <div className="creator-note-detail">
          {coverUrl(selected) && <img src={coverUrl(selected)} alt={selected.title} />}
          {notePublishedAt(selected) && <time>{new Date(notePublishedAt(selected)!).toLocaleDateString('zh-CN')}</time>}
          <p className="creator-note-body">{selected.desc || '暂未读取到正文'}</p>
          <section aria-label="笔记评论">
            <h3>评论 · {selected.comments.length}</h3>
            {selected.comments.length ? selected.comments.map((comment, index) => <p className="creator-note-comment" key={comment.commentId || index}>{comment.content || '图片评论'}<small>赞 {comment.likeCount ?? '—'}</small></p>) : <p>暂未读取到评论</p>}
          </section>
        </div>
      </CreatorDialog>}
    </section>
  )
}
