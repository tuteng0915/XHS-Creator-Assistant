import { useState } from 'react'
import { ANALYSIS_SCOPE_LABELS, notePublishedAt, selectCreatorNotes, type AnalysisScope, type CreatorNote } from '../creatorNotes'
import type { MediaAsset } from '../types'
import { CreatorDialog } from './CreatorDialog'
import { CreatorNoteBrowser } from './CreatorNoteBrowser'

export function CreatorNoteSelectionDialog({notes, mediaAssets, scope, selectedIds, onConfirm, onClose}: {
  notes: CreatorNote[]; mediaAssets: MediaAsset[]; scope: AnalysisScope; selectedIds?: string[];
  onConfirm: (scope: AnalysisScope, ids?: string[]) => void; onClose: () => void;
}) {
  const [preset, setPreset] = useState(scope)
  const [manual, setManual] = useState(selectedIds !== undefined)
  const [ids, setIds] = useState(() => selectedIds
    ? selectedIds.filter(id => notes.some(note => note.noteId === id))
    : selectCreatorNotes(notes, scope).map(note => note.noteId))
  function quickSelect(value: AnalysisScope) {
    setPreset(value); setManual(false)
    setIds(selectCreatorNotes(notes, value).map(note => note.noteId))
  }
  function toggle(id: string) {
    setManual(true)
    setIds(previous => previous.includes(id) ? previous.filter(value => value !== id) : [...previous, id])
  }
  const unknownDates = notes.filter(note => notePublishedAt(note) === null).length
  return <CreatorDialog title="分析范围" onClose={onClose} wide>
    <div className="creator-note-selection-toolbar">
      <label>从已导入笔记中选择
        <select value={manual ? 'custom' : preset} onChange={event => {
          if (event.target.value !== 'custom') quickSelect(event.target.value as AnalysisScope)
        }}>
          {manual && <option value="custom">手动选择</option>}
          {Object.entries(ANALYSIS_SCOPE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}{value === 'recent_10' ? '（推荐）' : ''}</option>)}
        </select>
      </label>
      <button type="button" onClick={() => quickSelect('all')}>全选</button>
      <button type="button" onClick={() => {setManual(true); setIds([])}}>清空</button>
    </div>
    {!manual && preset.startsWith('last_') && unknownDates > 0 && <p>{unknownDates} 条笔记没有发布时间，未纳入此范围。</p>}
    <CreatorNoteBrowser notes={notes} mediaAssets={mediaAssets} selectedIds={ids} onToggle={toggle} />
    <div className="creator-note-selection-footer">
      <span role="status">已选 {ids.length} / {notes.length} 条笔记，包含对应评论。</span>
      <button type="button" onClick={onClose}>取消</button>
      <button type="button" className="primary" disabled={!ids.length} onClick={() => onConfirm(preset, manual ? ids : undefined)}>完成</button>
    </div>
  </CreatorDialog>
}
