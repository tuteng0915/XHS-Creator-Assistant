import { useState, type ReactNode } from 'react'
import type { MediaAsset, TextInputAsset } from '../types'
import { ANALYSIS_SCOPE_LABELS, creatorNotes, selectCreatorNotes, type AnalysisScope } from '../creatorNotes'
import { CreatorNoteSelectionDialog } from './CreatorNoteSelectionDialog'

export function CreatorDiagnosisPage({ profile, mediaAssets = [], scope, selectedNoteIds, onScopeChange, running, onRun, onImport, children }: {
  profile?: TextInputAsset
  mediaAssets?: MediaAsset[]
  selectedNoteIds?: string[]
  scope: AnalysisScope
  onScopeChange: (scope: AnalysisScope, selectedIds?: string[]) => void
  running: boolean
  onRun: () => void
  onImport: () => void
  children: ReactNode
}) {
  const [settingsOpen, setSettingsOpen] = useState(false)
  const notes = creatorNotes(profile)
  const count = selectedNoteIds ? notes.filter(note => selectedNoteIds.includes(note.noteId)).length : selectCreatorNotes(notes, scope).length
  const stale = selectedNoteIds !== undefined && count !== selectedNoteIds.length
  return <section className="creator-diagnosis-page">
    <div className="creator-page-head"><h1>账号诊断</h1></div>
    <div className="creator-diagnosis-controls">
      <span>{selectedNoteIds ? '手动选择' : ANALYSIS_SCOPE_LABELS[scope]} · {count} 条笔记</span>
      <button type="button" disabled={running} onClick={() => setSettingsOpen(true)}>调整范围</button>
      {notes.length ? <button type="button" className="primary" disabled={running || !count || stale} onClick={onRun}>{running ? '正在分析…' : '开始分析'}</button> : <button type="button" className="primary" onClick={onImport}>导入账号</button>}
    </div>
    {stale && <p role="alert">已选笔记有变动，请重新选择。</p>}
    {settingsOpen && <CreatorNoteSelectionDialog notes={notes} mediaAssets={mediaAssets} scope={scope} selectedIds={selectedNoteIds}
      onClose={() => setSettingsOpen(false)} onConfirm={(nextScope, ids) => {onScopeChange(nextScope, ids); setSettingsOpen(false)}} />}
    {children}
  </section>
}
