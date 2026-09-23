import { useState, type ReactNode } from 'react'
import type { TextInputAsset } from '../types'
import { ANALYSIS_SCOPE_LABELS, creatorNotes, notePublishedAt, selectCreatorNotes, type AnalysisScope } from '../creatorNotes'
import { CreatorDialog } from './CreatorDialog'

export function CreatorDiagnosisPage({ profile, scope, onScopeChange, running, onRun, onImport, children }: {
  profile?: TextInputAsset
  scope: AnalysisScope
  onScopeChange: (scope: AnalysisScope) => void
  running: boolean
  onRun: () => void
  onImport: () => void
  children: ReactNode
}) {
  const [settingsOpen, setSettingsOpen] = useState(false)
  const notes = creatorNotes(profile)
  const count = selectCreatorNotes(notes, scope).length
  const unknownDates = notes.filter((note) => notePublishedAt(note) === null).length
  return <section className="creator-diagnosis-page">
    <div className="creator-page-head"><h1>账号诊断</h1></div>
    <div className="creator-diagnosis-controls">
      <span>{ANALYSIS_SCOPE_LABELS[scope]} · {count} 条笔记</span>
      <button type="button" disabled={running} onClick={() => setSettingsOpen(true)}>调整范围</button>
      {notes.length ? <button type="button" className="primary" disabled={running || !count} onClick={onRun}>{running ? '正在分析…' : '开始分析'}</button> : <button type="button" className="primary" onClick={onImport}>导入账号</button>}
    </div>
    {settingsOpen && <CreatorDialog title="分析范围" onClose={() => setSettingsOpen(false)}>
      <label htmlFor="creator-analysis-scope">从已导入笔记中选择</label>
      <select id="creator-analysis-scope" value={scope} onChange={(event) => onScopeChange(event.target.value as AnalysisScope)}>
        {Object.entries(ANALYSIS_SCOPE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}{value === 'recent_10' ? '（推荐）' : ''}</option>)}
      </select>
      <p>本次分析 {count} 条笔记及其评论。</p>
      {scope.startsWith('last_') && unknownDates > 0 && <p>{unknownDates} 条笔记没有发布时间，未纳入此范围。</p>}
      {!count && <p role="status">没有符合范围的笔记，请调整范围或重新导入。</p>}
      <button type="button" className="primary" onClick={() => setSettingsOpen(false)}>完成</button>
    </CreatorDialog>}
    {children}
  </section>
}
