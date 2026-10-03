import { useState } from 'react'
import { audienceAnalysisApi, simulatedFanApi } from '../api'
import { ANALYSIS_SCOPE_LABELS, type AnalysisScope } from '../creatorNotes'
import type { AudienceAnalysis, TextInputAsset } from '../types'
import { CreatorDialog } from './CreatorDialog'
import { AudienceGroups } from './AudienceGroups'

export function AudienceAnalysisPage({workspaceId, profile, analyses, selectedId, onSelect, onRefresh, onSimulate, savedFanKeys = [], onFansChanged, loadError = ''}: {
  workspaceId: string; profile?: TextInputAsset; analyses: AudienceAnalysis[]; selectedId: string;
  onSelect: (id: string) => void; onRefresh: () => Promise<void>; onSimulate: () => void;
  savedFanKeys?: string[]; onFansChanged?: () => Promise<void>;
  loadError?: string;
}) {
  const [scope, setScope] = useState<AnalysisScope>('recent_10')
  const [settings, setSettings] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [savingGroup, setSavingGroup] = useState('')
  const workspaceAnalyses = analyses.filter(r => r.workspaceId === workspaceId)
  const selected = workspaceAnalyses.find(r => r.id === selectedId) || workspaceAnalyses[0]
  const running = workspaceAnalyses.some(r => ['pending', 'running'].includes(r.status))
  async function saveFan(groupId: string) {
    if (!selected) return
    setSavingGroup(groupId); setError('')
    try {await simulatedFanApi.create(workspaceId, selected.id, groupId); await onFansChanged?.()}
    catch(e) {setError(String(e))} finally {setSavingGroup('')}
  }
  async function start() {
    if (!profile) return
    setBusy(true); setError('')
    try { const run = await audienceAnalysisApi.create(workspaceId, profile.id, scope); await onRefresh(); onSelect(run.id) }
    catch (e) { setError(e instanceof Error ? e.message : String(e)) }
    finally { setBusy(false) }
  }
  return <section className="creator-materials-page">
    <div className="creator-page-head"><h1>受众分析</h1><button className="primary" disabled={!profile || busy || running} onClick={() => void start()}>{running ? '正在分析…' : '分析受众'}</button></div>
    <div className="creator-range-row"><span>{ANALYSIS_SCOPE_LABELS[scope]}</span><button onClick={() => setSettings(true)}>调整范围</button></div>
    {settings && <CreatorDialog title="分析范围" onClose={() => setSettings(false)}><select aria-label="受众分析范围" value={scope} onChange={e => setScope(e.target.value as AnalysisScope)}>{Object.entries(ANALYSIS_SCOPE_LABELS).map(([k,v]) => <option value={k} key={k}>{v}</option>)}</select><button onClick={() => setSettings(false)}>完成</button></CreatorDialog>}
    {!profile && <p>请先导入账号笔记。</p>}{error && <p role="alert">{error}</p>}
    {loadError && <p role="alert">受众分析历史加载失败：{loadError}</p>}
    {workspaceAnalyses.length > 0 && <select className="audience-history-select" aria-label="受众分析历史" value={selected?.id || ''} onChange={e => onSelect(e.target.value)}>{workspaceAnalyses.map(r => <option key={r.id} value={r.id}>{new Date(r.createdAt).toLocaleString()} · {r.inputSnapshot.scope.selectedNoteCount} 条 · {({completed:'已完成', partially_completed:'部分完成', running:'分析中', pending:'等待中', failed:'失败'} as Record<string,string>)[r.status]}</option>)}</select>}
    {selected?.error && <p role="alert">{selected.error}</p>}
    {selected?.result.origin === 'curated_preset' && <p className="muted">预置整理 · 基于已保存评论，未调用模型接口。</p>}
    {!!selected?.diagnostics?.rejectedGroups?.length && <details>
      <summary>{selected.diagnostics.rejectedGroups.length} 个分组未通过核验</summary>
      {selected.diagnostics.rejectedGroups.map(group => <p key={group.groupIndex}>
        {group.groupName || `分组 ${group.groupIndex + 1}`}：{group.issues.map(issue => `${issue.referenceIndex === undefined ? '' : `引用 ${issue.referenceIndex + 1}：`}${issue.message}`).join('；')}
      </p>)}
    </details>}
    {selected && ['completed', 'partially_completed'].includes(selected.status) && <>
      <p>{selected.result.summary}</p>
      <p className="muted">这些角色用于模拟不同声音，并非真实粉丝的个人档案。</p>
      <AudienceGroups key={`${workspaceId}:${selected.id}`} run={selected} savingGroup={savingGroup} savedFanKeys={savedFanKeys} onSave={id => void saveFan(id)} />
      {(selected.result.sampling || selected.result.limitations) && <details className="audience-analysis-notes"><summary>分析说明</summary>
        {selected.result.sampling && <p className="muted">依据 {selected.result.sampling.sentNotes} 条笔记、{selected.result.sampling.sentComments} 条已采集评论。</p>}
        {selected.result.limitations && <p className="muted">{selected.result.limitations}</p>}
      </details>}
      <button onClick={onSimulate}>选择选题进行模拟</button>
    </>}
  </section>
}
