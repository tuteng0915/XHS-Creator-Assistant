import { useState } from 'react'
import { audienceAnalysisApi } from '../api'
import { ANALYSIS_SCOPE_LABELS, type AnalysisScope } from '../creatorNotes'
import type { AudienceAnalysis, TextInputAsset } from '../types'
import { CreatorDialog } from './CreatorDialog'

export function AudienceAnalysisPage({workspaceId, profile, analyses, selectedId, onSelect, onRefresh, onSimulate}: {
  workspaceId: string; profile?: TextInputAsset; analyses: AudienceAnalysis[]; selectedId: string;
  onSelect: (id: string) => void; onRefresh: () => Promise<void>; onSimulate: () => void;
}) {
  const [scope, setScope] = useState<AnalysisScope>('recent_10')
  const [settings, setSettings] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const selected = analyses.find(r => r.id === selectedId) || analyses[0]
  const running = analyses.some(r => ['pending', 'running'].includes(r.status))
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
    {analyses.length > 0 && <select className="audience-history-select" aria-label="受众分析历史" value={selected?.id || ''} onChange={e => onSelect(e.target.value)}>{analyses.map(r => <option key={r.id} value={r.id}>{new Date(r.createdAt).toLocaleString()} · {r.inputSnapshot.scope.selectedNoteCount} 条 · {({completed:'已完成', running:'分析中', pending:'等待中', failed:'失败'} as Record<string,string>)[r.status]}</option>)}</select>}
    {selected?.error && <p role="alert">{selected.error}</p>}
    {selected?.status === 'completed' && <>
      <p>{selected.result.summary}</p>
      <p className="muted">有依据的阅读视角，可相互重叠；非平台真实粉丝统计。</p>
      {selected.result.sampling && <p className="muted">依据 {selected.result.sampling.sentNotes} 条笔记、{selected.result.sampling.sentComments} 条已采集评论。</p>}
      <div className="audience-groups">{selected.result.groups?.map((g,i) => <article className="asset-detail-card" key={g.id}>
        <div className="creator-page-head"><strong>{g.name}{i < 3 ? ' · 模拟角色' : ''}</strong></div>
        <p>{g.profile}</p><p>{g.coreConcern}</p><details><summary>依据</summary>
          {g.evidenceRefs?.length ? g.evidenceRefs.map((e,j) => <p key={j}>
            {e.sourceType === 'comment' ? '评论直接表达' : '从笔记推断'} · 笔记 {e.noteId}{e.commentId ? ` / 评论 ${e.commentId}` : ''}<br />{e.quote}
          </p>) : <><p className="muted">历史分析依据，尚未核验来源引用。</p>{g.evidence.map((e,j) => <p key={j}>{e}</p>)}</>}
        </details>
      </article>)}</div>
      <p className="muted">{selected.result.limitations}</p><button onClick={onSimulate}>选择选题进行模拟</button>
    </>}
  </section>
}
