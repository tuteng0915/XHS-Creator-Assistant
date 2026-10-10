import { useState } from 'react'
import { filterCreatorNotes, notePublishedAt, selectCreatorNotes, selectTopCreatorNotes, validNoteMetric, type AnalysisScope, type CreatorNote, type CreatorNoteRange, type CreatorNoteSort } from '../creatorNotes'
import type { MediaAsset } from '../types'
import { CreatorDialog } from './CreatorDialog'
import { CreatorNoteBrowser } from './CreatorNoteBrowser'
import { CreatorNoteFilters } from './CreatorNoteFilters'

export function CreatorNoteSelectionDialog({notes, mediaAssets, scope, selectedIds, onConfirm, onClose, selectionMode = 'multiple', title = '分析范围', includeComments = true, maxSelection, contentOnlyPreview = false}: {
  notes: CreatorNote[]; mediaAssets: MediaAsset[]; scope: AnalysisScope; selectedIds?: string[];
  onConfirm: (scope: AnalysisScope, ids?: string[]) => void; onClose: () => void;
  selectionMode?: 'single' | 'multiple'; title?: string;
  includeComments?: boolean;
  maxSelection?: number;
  contentOnlyPreview?: boolean;
}) {
  const [range, setRange] = useState<CreatorNoteRange>(scope.startsWith('last_') ? scope as CreatorNoteRange : 'all')
  const [sort, setSort] = useState<CreatorNoteSort>(scope === 'most_liked_10' ? 'liked' : scope === 'most_engaged_10' ? 'engagement' : 'newest')
  const [quantity, setQuantity] = useState('10')
  const [customQuantity, setCustomQuantity] = useState('10')
  const [ids, setIds] = useState(() => (selectedIds
    ? selectedIds.filter(id => notes.some(note => note.noteId === id))
    : selectionMode === 'single' ? [] : selectCreatorNotes(notes, scope).map(note => note.noteId)).slice(0, selectionMode === 'single' ? 1 : notes.length))
  const visibleNotes = filterCreatorNotes(notes, range, sort)
  const visibleIds = new Set(visibleNotes.map(note => note.noteId))
  const hiddenSelectionCount = ids.filter(id => !visibleIds.has(id)).length
  const count = Number(quantity === 'custom' ? customQuantity : quantity)
  const validCount = Number.isInteger(count) && count > 0 && count <= 10000
  const overLimit = maxSelection !== undefined && ids.length > maxSelection
  const preset: AnalysisScope = range !== 'all' ? range : sort === 'liked' ? 'most_liked_10' : sort === 'engagement' ? 'most_engaged_10' : scope === 'all' ? 'all' : 'recent_10'
  function toggle(id: string) {
    setIds(previous => selectionMode === 'single' ? [id] : previous.includes(id) ? previous.filter(value => value !== id) : [...previous, id])
  }
  const unknownDates = notes.filter(note => notePublishedAt(note) === null).length
  const partialMetrics = sort !== 'newest' && visibleNotes.some(note => sort === 'liked'
    ? validNoteMetric(note.metrics.liked) === null
    : [note.metrics.liked, note.metrics.collected, note.metrics.comments, note.metrics.shares].some(value => validNoteMetric(value) === null))
  return <CreatorDialog title={title} onClose={onClose} wide>
    <CreatorNoteFilters range={range} sort={sort} onRangeChange={setRange} onSortChange={setSort} />
    <div className="creator-note-quick-actions">
      {selectionMode === 'multiple' && <>
        <label>数量<select value={quantity} onChange={event => setQuantity(event.target.value)}>
          <option value="10">10 篇</option><option value="20">20 篇</option><option value="50">50 篇</option><option value="custom">自定义</option>
        </select></label>
        {quantity === 'custom' && <input aria-label="自定义篇数" type="number" min="1" max="10000" step="1" value={customQuantity} onChange={event => setCustomQuantity(event.target.value)} />}
        <button type="button" disabled={!validCount} onClick={() => setIds(selectTopCreatorNotes(notes, range, sort, count).map(note => note.noteId))}>选前 {validCount ? count : 'N'} 篇</button>
        <button type="button" disabled={!visibleNotes.length} onClick={() => setIds(previous => [...new Set([...previous, ...visibleIds])])}>全选当前范围</button>
        <button type="button" disabled={!visibleNotes.length} onClick={() => setIds(previous => [...previous.filter(id => !visibleIds.has(id)), ...visibleNotes.filter(note => !previous.includes(note.noteId)).map(note => note.noteId)])}>反选当前范围</button>
      </>}
      <button type="button" disabled={!ids.length} onClick={() => setIds([])}>取消选择</button>
    </div>
    <p className="creator-note-range-count">当前范围 {visibleNotes.length} 篇{partialMetrics ? ' · 部分互动数据未获取' : ''}{range !== 'all' && unknownDates > 0 ? ` · ${unknownDates} 篇未记录发布时间` : ''}</p>
    <CreatorNoteBrowser notes={visibleNotes} mediaAssets={mediaAssets} selectedIds={ids} onToggle={toggle} selectionMode={selectionMode} showComments={!contentOnlyPreview} showObservationTimes={!contentOnlyPreview} />
    {!visibleNotes.length && <p>当前范围没有笔记，可调整范围。</p>}
    {overLimit && <p role="alert">本次最多还能添加 {maxSelection} 篇原笔记，请减少选择后再完成。</p>}
    <div className="creator-note-selection-footer">
      <span role="status">已选 {ids.length} / {notes.length} 条笔记{hiddenSelectionCount ? ` · ${hiddenSelectionCount} 篇不在当前范围` : ''}{selectionMode === 'multiple' && includeComments ? '，包含对应评论。' : ''}</span>
      <button type="button" onClick={onClose}>取消</button>
      <button type="button" className="primary" disabled={!ids.length || overLimit} onClick={() => onConfirm(preset, ids)}>完成</button>
    </div>
  </CreatorDialog>
}
