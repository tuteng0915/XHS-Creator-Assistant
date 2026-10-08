import { useEffect, useRef, useState } from 'react'
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
  const [adopted, setAdopted] = useState<{workspaceId: string; keys: string[]}>({workspaceId, keys: []})
  const [refreshNeeded, setRefreshNeeded] = useState(false)
  const saving = useRef(false)
  const currentWorkspace = useRef(workspaceId)
  const generation = useRef(0)
  useEffect(() => {
    currentWorkspace.current = workspaceId
    saving.current = false
    setSavingGroup(''); setError(''); setRefreshNeeded(false)
    return () => {currentWorkspace.current = ''; generation.current += 1}
  }, [workspaceId])
  const workspaceAnalyses = analyses.filter(r => r.workspaceId === workspaceId)
  const selected = workspaceAnalyses.find(r => r.id === selectedId) || workspaceAnalyses[0]
  const running = workspaceAnalyses.some(r => ['pending', 'running'].includes(r.status))
  const adoptedKeys = [...savedFanKeys, ...(adopted.workspaceId === workspaceId ? adopted.keys : [])]
  const adoptedCount = selected?.result.groups?.filter(group => adoptedKeys.includes(`${selected.id}:${group.id}`)).length || 0
  async function refreshFans() {
    const requestGeneration = generation.current
    try {
      await onFansChanged?.()
      if (currentWorkspace.current !== workspaceId || generation.current !== requestGeneration) return
      setRefreshNeeded(false); setError('')
    }
    catch {
      if (currentWorkspace.current !== workspaceId || generation.current !== requestGeneration) return
      setRefreshNeeded(true); setError('读者已收录，列表暂未刷新。请重试刷新后前往模拟。')
    }
  }
  async function saveFan(groupId: string) {
    if (!selected || saving.current || adoptedKeys.includes(`${selected.id}:${groupId}`)) return
    const key = `${selected.id}:${groupId}`
    const requestGeneration = generation.current
    saving.current = true
    setSavingGroup(groupId); setError('')
    try {
      await simulatedFanApi.create(workspaceId, selected.id, groupId)
      if (currentWorkspace.current !== workspaceId || generation.current !== requestGeneration) return
      setAdopted(previous => ({workspaceId, keys: [...(previous.workspaceId === workspaceId ? previous.keys : []), key]}))
      await refreshFans()
    }
    catch(e) {if (currentWorkspace.current === workspaceId && generation.current === requestGeneration) setError(e instanceof Error ? e.message : String(e))}
    finally {if (currentWorkspace.current === workspaceId && generation.current === requestGeneration) {saving.current = false; setSavingGroup('')}}
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
    <p className="muted">从已导入的历史图文和评论发现读者视角。先查看依据，再由你决定收录哪些读者。</p>
    <div className="creator-range-row"><span>{ANALYSIS_SCOPE_LABELS[scope]}</span><button onClick={() => setSettings(true)}>调整范围</button></div>
    {settings && <CreatorDialog title="分析范围" onClose={() => setSettings(false)}><select aria-label="受众分析范围" value={scope} onChange={e => setScope(e.target.value as AnalysisScope)}>{Object.entries(ANALYSIS_SCOPE_LABELS).map(([k,v]) => <option value={k} key={k}>{v}</option>)}</select><button className="primary" onClick={() => setSettings(false)}>完成</button></CreatorDialog>}
    {!profile && <p>请先导入账号笔记。</p>}{error && <p role="alert">{error}</p>}
    {loadError && <p role="alert">受众分析历史加载失败：{loadError}</p>}
    {refreshNeeded && <button disabled={Boolean(savingGroup)} onClick={() => void refreshFans()}>重试刷新读者列表</button>}
    {workspaceAnalyses.length > 0 && <select className="audience-history-select" aria-label="受众分析历史" value={selected?.id || ''} onChange={e => onSelect(e.target.value)}>{workspaceAnalyses.map(r => <option key={r.id} value={r.id}>{new Date(r.createdAt).toLocaleString()} · {r.inputSnapshot.scope.selectedNoteCount} 条 · {({completed:'已完成', partially_completed:'部分完成', running:'分析中', pending:'等待中', failed:'失败'} as Record<string,string>)[r.status]}</option>)}</select>}
    {selected?.error && <p role="alert">{selected.error}</p>}
    {selected && ['pending', 'running'].includes(selected.status) && <div className="audience-progress" role="status" aria-live="polite">
      <strong>{selected.status === 'pending' ? '准备阅读历史图文' : '正在整理读者视角'}</strong>
      <p>将结合笔记内容和已有评论提取关注点，完成后可逐位查看和收录。你可以先浏览其他页面，回来后继续。</p>
    </div>}
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
      <p className="audience-adoption-summary">{selected.result.groups?.length || 0} 位候选读者 · 已收录 {adoptedCount} 位。收录后可在模拟时邀请，不会自动加入讨论。</p>
      {selected.status === 'partially_completed' && <p className="muted">下方已核验的读者可以正常收录；其余候选缺少可靠依据，已略过。</p>}
      <AudienceGroups key={`${workspaceId}:${selected.id}`} run={selected} savingGroup={savingGroup} savedFanKeys={adoptedKeys} onSave={id => void saveFan(id)} />
      {(selected.result.sampling || selected.result.limitations) && <details className="audience-analysis-notes"><summary>分析说明</summary>
        {selected.result.sampling && <p className="muted">依据 {selected.result.sampling.sentNotes} 条笔记、{selected.result.sampling.sentComments} 条已采集评论。</p>}
        {selected.result.limitations && <p className="muted">{selected.result.limitations}</p>}
      </details>}
      <button className="primary" disabled={refreshNeeded} onClick={onSimulate}>选择内容，邀请读者试读</button>
    </>}
  </section>
}
