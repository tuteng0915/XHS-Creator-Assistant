import { useState } from 'react'
import type { MediaAsset } from '../types'
import { filterCreatorNotes, noteCommentsTimeLabel, noteCoverUrl, noteDataTimeLabel, notePublishedAt, selectTopCreatorNotes, validNoteMetric, type CreatorNote, type CreatorNoteRange, type CreatorNoteSort } from '../creatorNotes'
import { CreatorDialog } from './CreatorDialog'
import { CreatorNoteFilters } from './CreatorNoteFilters'

const METRIC_ICONS = {
  liked: <path d="M12 20s-7-4.4-7-9.6A3.9 3.9 0 0 1 12 8a3.9 3.9 0 0 1 7 2.4C19 15.6 12 20 12 20Z" />,
  collected: <path d="m12 4 2.5 5 5.5.8-4 3.9.9 5.5-4.9-2.6-4.9 2.6.9-5.5-4-3.9 5.5-.8Z" />,
  comments: <path d="M5 5h14a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1h-7l-4 3.5V16H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Z" />,
  shares: <path d="M12 15V4M8 8l4-4 4 4M5 13v5a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-5" />,
}

// The label stays in the text for screen readers and copy; the icon carries it visually.
function NoteMetric({ icon, label, value }: { icon: keyof typeof METRIC_ICONS; label: string; value: unknown }) {
  return <span title={label}>
    <svg className="creator-note-metric-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">{METRIC_ICONS[icon]}</svg>
    <span className="visually-hidden">{label} </span>{validNoteMetric(value) ?? '—'}
  </span>
}

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
  const coverUrl = (note: CreatorNote) => noteCoverUrl(note, mediaAssets)
  const images = (note: CreatorNote) => [...new Set([
    coverUrl(note), ...mediaAssets.filter(asset => asset.metadata.noteId === note.noteId && asset.mediaType.startsWith('image/') && (!note.imageMediaAssetIds || note.imageMediaAssetIds.includes(asset.id))).sort((a,b) => Number(a.metadata.imageIndex || 1) - Number(b.metadata.imageIndex || 1)).map(asset => asset.fileUrl),
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
            <span className="creator-note-metric-row"><NoteMetric icon="liked" label="赞" value={note.metrics.liked} /><NoteMetric icon="collected" label="收藏" value={note.metrics.collected} /></span>
            <span className="creator-note-metric-row"><NoteMetric icon="comments" label="评论" value={note.metrics.comments} /><NoteMetric icon="shares" label="分享" value={note.metrics.shares} /></span>
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
