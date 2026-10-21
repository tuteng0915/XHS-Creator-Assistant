import { useState } from 'react'
import type { MediaAsset } from '../types'
import { filterCreatorNotes, noteCommentsTimeLabel, noteDataTimeLabel, notePublishedAt, selectTopCreatorNotes, validNoteMetric, type CreatorNote, type CreatorNoteRange, type CreatorNoteSort } from '../creatorNotes'
import { CreatorDialog } from './CreatorDialog'
import { CreatorNoteFilters } from './CreatorNoteFilters'

// Shared browsing surface for My Notes and the diagnosis selection dialog.
export function CreatorNoteBrowser({ notes, mediaAssets, selectedIds, onToggle, showFilters = false, selectionMode = 'multiple', showComments = true, showObservationTimes = true }: {
  notes: CreatorNote[]; mediaAssets: MediaAsset[];
  selectedIds?: string[]; onToggle?: (id: string) => void;
  showFilters?: boolean; selectionMode?: 'single' | 'multiple';
  showComments?: boolean; showObservationTimes?: boolean;
}) {
  const [detailId, setDetailId] = useState<string | null>(null)
  const [range, setRange] = useState<CreatorNoteRange>('all')
  const [sort, setSort] = useState<CreatorNoteSort>('newest')
  const [limit, setLimit] = useState(0)
  const detail = notes.find(note => note.noteId === detailId)
  const visibleNotes = showFilters ? limit ? selectTopCreatorNotes(notes, range, sort, limit) : filterCreatorNotes(notes, range, sort) : notes
  const coverUrl = (note: CreatorNote) => (
    mediaAssets.find(asset => asset.id === note.coverMediaAssetId) ||
    mediaAssets.find(asset => asset.metadata.noteId === note.noteId)
  )?.fileUrl
  const images = (note: CreatorNote) => [...new Set([
    coverUrl(note), ...mediaAssets.filter(asset => asset.metadata.noteId === note.noteId && asset.mediaType.startsWith('image/')).map(asset => asset.fileUrl),
  ].filter((url): url is string => Boolean(url)))]
  return <>
    {showFilters && <CreatorNoteFilters range={range} sort={sort} onRangeChange={setRange} onSortChange={setSort} limit={limit} onLimitChange={setLimit} />}
    {!visibleNotes.length && notes.length > 0 && <p className="creator-note-range-count">当前范围没有笔记，可调整范围。</p>}
    <div className="creator-note-grid">
      {visibleNotes.map(note => <article key={note.noteId} className={`creator-note-item ${selectedIds?.includes(note.noteId) ? 'is-selected' : ''}`}>
        {onToggle && <label className="creator-note-check">
          <input type={selectionMode === 'single' ? 'radio' : 'checkbox'} name={selectionMode === 'single' ? 'published-note-selection' : undefined} aria-label={`选择笔记：${note.title}`} checked={selectedIds?.includes(note.noteId) || false} onChange={() => onToggle(note.noteId)} />
          {selectedIds?.includes(note.noteId) ? '已选择' : '选择'}
        </label>}
        <button type="button" className="creator-note-card" onClick={() => setDetailId(note.noteId)}>
          {coverUrl(note) ? <img src={coverUrl(note)} alt={note.title} loading="lazy" /> : <div className="creator-note-placeholder">暂无封面</div>}
          <div><strong>{note.title}</strong><p className="creator-note-metrics">
            <span className="creator-note-metric-row"><span>赞 {validNoteMetric(note.metrics.liked) ?? '—'}</span><span>收藏 {validNoteMetric(note.metrics.collected) ?? '—'}</span></span>
            <span className="creator-note-metric-row"><span>评论 {validNoteMetric(note.metrics.comments) ?? '—'}</span><span>分享 {validNoteMetric(note.metrics.shares) ?? '—'}</span></span>
          </p>
            {notePublishedAt(note) !== null && <time>{new Date(notePublishedAt(note)!).toLocaleDateString('zh-CN')}</time>}
          </div>
        </button>
      </article>)}
    </div>
    {detail && <CreatorDialog title={detail.title} scrollBody className="creator-note-preview-dialog" onClose={() => setDetailId(null)}>
      <div className="creator-note-detail">
        {images(detail).length > 0 && <div className="creator-note-gallery">{images(detail).map((url, index) => <img key={url} src={url} alt={`${detail.title} · 图片 ${index + 1}`} />)}</div>}
        {notePublishedAt(detail) && <time>{new Date(notePublishedAt(detail)!).toLocaleDateString('zh-CN')}</time>}
        {showObservationTimes && <p className="creator-note-data-time">{noteDataTimeLabel(detail) || '指标时间未记录'}</p>}
        <p className="creator-note-body">{detail.desc || '暂未读取到正文'}</p>
        {showComments && <section aria-label="笔记评论">
          <h3>评论 · {detail.comments.length}</h3>
          {showObservationTimes && noteCommentsTimeLabel(detail) && <p className="creator-note-data-time">{noteCommentsTimeLabel(detail)}</p>}
          {detail.comments.length ? detail.comments.map((comment, index) => <p className="creator-note-comment" key={comment.commentId || index}>{comment.content || '图片评论'}<small>赞 {comment.likeCount ?? '—'}</small></p>) : <p>暂未读取到评论</p>}
        </section>}
      </div>
    </CreatorDialog>}
  </>
}
