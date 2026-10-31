import { useState, type ReactNode } from 'react'
import type { MediaAsset, TextInputAsset } from '../types'
import { ANALYSIS_SCOPE_LABELS, creatorNotes, selectCreatorNotes, type AnalysisScope } from '../creatorNotes'
import { CreatorNoteSelectionDialog } from './CreatorNoteSelectionDialog'
import { InfoHint } from './InfoHint'

export function CreatorDiagnosisPage({ profile, mediaAssets = [], scope, selectedNoteIds, onScopeChange, running, onRun, onImport, onOpenHistory, children }: {
  profile?: TextInputAsset
  mediaAssets?: MediaAsset[]
  selectedNoteIds?: string[]
  scope: AnalysisScope
  onScopeChange: (scope: AnalysisScope, selectedIds?: string[]) => void
  running: boolean
  onRun: () => void
  onImport: () => void
  onOpenHistory?: () => void
  children: ReactNode
}) {
  const [settingsOpen, setSettingsOpen] = useState(false)
  const notes = creatorNotes(profile)
  const count = selectedNoteIds ? notes.filter(note => selectedNoteIds.includes(note.noteId)).length : selectCreatorNotes(notes, scope).length
  const stale = selectedNoteIds !== undefined && count !== selectedNoteIds.length
  return <section className="creator-diagnosis-page">
    <div className="creator-page-head"><h1>账号诊断 <InfoHint label="账号诊断说明">从选定笔记中了解账号的内容特点、历史表现、读者反馈和可改进的方向。</InfoHint></h1>
      {onOpenHistory && <button type="button" data-guide="diagnosis-history" onClick={onOpenHistory}>诊断历史</button>}
    </div>
    <div className="creator-diagnosis-controls">
      <span>{selectedNoteIds ? '手动选择' : ANALYSIS_SCOPE_LABELS[scope]} · {count} 条笔记</span>
      <button type="button" data-guide={notes.length ? 'diagnosis-range' : undefined} disabled={running} onClick={() => setSettingsOpen(true)}>调整范围</button>
      {notes.length ? <button type="button" data-guide="diagnosis-start" className="primary" disabled={running || !count || stale} onClick={onRun}>{running ? '正在分析…' : '开始分析'}</button> : <button type="button" data-guide="diagnosis-import" className="primary" onClick={onImport}>导入账号</button>}
    </div>
    {stale && <p role="alert">已选笔记有变动，请重新选择。</p>}
    {settingsOpen && <CreatorNoteSelectionDialog notes={notes} mediaAssets={mediaAssets} scope={scope} selectedIds={selectedNoteIds}
      onClose={() => setSettingsOpen(false)} onConfirm={(nextScope, ids) => {onScopeChange(nextScope, ids); setSettingsOpen(false)}} />}
    {children}
  </section>
}
