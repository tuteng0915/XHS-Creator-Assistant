import { useCallback, useEffect, useRef, useState } from 'react'
import { panelEditApi, simulationRunApi, topicApi } from '../api'
import type { PanelRetestRequest, SimulationRun, SimulationRunSummary, Topic } from '../types'
import type { PanelEditProposal } from '../panelEdits'
import type { CollaborationCandidate } from '../contentCollaboration'
import { ContentCollaborationChat } from './ContentCollaborationChat'
import { PanelEditWorkspace } from './PanelEditWorkspace'
import { PendingSuggestions } from './PendingSuggestions'

export function CreatorCanvasPage({workspaceId, topic, topics, onSelect, onUpdated, onSimulate, onRetestCreated, simulationRuns = []}: {
  workspaceId: string; topic: Topic | null; topics: Topic[]; agentId?: string;
  onSelect: (topic: Topic) => void; onUpdated: (topic: Topic) => void;
  onSimulate?: (topic: Topic) => void;
  onRetestCreated?: (run: SimulationRun, navigate: boolean) => void;
  simulationRuns?: SimulationRunSummary[];
}) {
  return <section className="creator-canvas-page">
    <div className="creator-page-head"><h1>AI 创作助手</h1><select aria-label="创作选题" value={topic?.id || ''} onChange={e => {const selected = topics.find(t => t.id === e.target.value); if (selected) onSelect(selected)}}><option value="">选择选题</option>{topics.filter(t => t.status !== 'archived').map(t => <option key={t.id} value={t.id}>{t.title}</option>)}</select></div>
    {topic ? <Canvas key={`${workspaceId}:${topic.id}`} workspaceId={workspaceId} topic={topic} onUpdated={onUpdated} onSimulate={onSimulate} onRetestCreated={onRetestCreated} simulationRuns={simulationRuns} /> : <p>先从选题库选择一个题目。</p>}
  </section>
}

function Canvas({workspaceId, topic, onUpdated, onSimulate, onRetestCreated, simulationRuns}: {workspaceId: string; topic: Topic; onUpdated: (t: Topic) => void; onSimulate?: (t: Topic) => void; onRetestCreated?: (run: SimulationRun, navigate: boolean) => void; simulationRuns: SimulationRunSummary[]}) {
  const [saved, setSaved] = useState(topic)
  const [title, setTitle] = useState(topic.title)
  const [body, setBody] = useState(topic.body || '')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [collaborating, setCollaborating] = useState(false)
  const [split, setSplit] = useState(52)
  const [preparing, setPreparing] = useState(false)
  const [applying, setApplying] = useState(false)
  const [retesting, setRetesting] = useState(false)
  const [preview, setPreview] = useState<{candidate: CollaborationCandidate; body: string; revision: number} | null>(null)
  const [previewText, setPreviewText] = useState('')
  const [previewTarget, setPreviewTarget] = useState<'body' | 'title'>('body')
  const [previewMode, setPreviewMode] = useState<'append' | 'replace'>('append')
  const retestLock = useRef(false)
  const applyLock = useRef(false)
  const prepareLock = useRef(false)
  const collaborationLock = useRef(false)
  const editRevision = useRef(0)
  const active = useRef(true)
  useEffect(() => {active.current = true; return () => {active.current = false}}, [])
  const dirty = title !== saved.title || body !== (saved.body || '')
  const dirtyRef = useRef(dirty)
  const onUpdatedRef = useRef(onUpdated)
  useEffect(() => {dirtyRef.current = dirty; onUpdatedRef.current = onUpdated}, [dirty, onUpdated])
  const onActivityChange = useCallback((busy: boolean) => {collaborationLock.current = busy; setCollaborating(busy)}, [])

  async function save() {
    if (applyLock.current || retestLock.current) throw new Error('当前操作正在提交，请稍候再保存。')
    const savingRevision = editRevision.current
    setSaving(true)
    try {
      const updated = await topicApi.update(topic.id, {title, body, expectedUpdatedAt:saved.updatedAt})
      if (active.current) {setSaved(updated); onUpdatedRef.current(updated); dirtyRef.current = editRevision.current !== savingRevision}
      return updated
    } finally {if (active.current) setSaving(false)}
  }
  async function prepareSimulation() {
    if (!onSimulate || retestLock.current || applyLock.current || prepareLock.current || collaborationLock.current || saving || !title.trim()) return
    prepareLock.current = true; setPreparing(true); setError('')
    try {
      const target = dirty ? await save() : saved
      if (active.current) onSimulate(target)
    } catch (e) {if (active.current) setError(e instanceof Error ? e.message : String(e))}
    finally {prepareLock.current = false; if (active.current) setPreparing(false)}
  }
  async function prepareCollaboration() {
    if (applyLock.current || retestLock.current || prepareLock.current || saving || !title.trim()) throw new Error('请先完成当前操作并填写标题。')
    const revision = editRevision.current
    const assertCurrent = () => {
      if (!active.current || revision !== editRevision.current) throw new Error('准备期间稿件有新修改，已保留；请确认后再次发送。')
    }
    const current = dirty ? await save() : saved
    assertCurrent()
    return {topic: current, assertCurrent}
  }
  function previewCandidate(candidate: CollaborationCandidate) {
    setPreview({candidate, body, revision: editRevision.current})
    setPreviewText(candidate.body); setPreviewMode('append'); setPreviewTarget('body'); setError('')
  }
  function putCandidateInEditor() {
    if (!preview || !previewText.trim()) return
    if (editRevision.current !== preview.revision) {setError('预览期间画布有新修改，请关闭后重新预览，避免覆盖新文字。'); return}
    editRevision.current++; dirtyRef.current = true
    if (previewTarget === 'title') setTitle(previewText.trim())
    else setBody(previewMode === 'replace' ? previewText : [preview.body, previewText].filter(Boolean).join('\n\n'))
    setPreview(null)
  }
  async function applyPanelEdit(proposal: PanelEditProposal, operation: 'apply' | 'undo' = 'apply') {
    if (!active.current || retestLock.current || applyLock.current || dirtyRef.current || collaborationLock.current || prepareLock.current || saving) throw new Error('请先完成当前编辑或等待正在执行的操作。')
    if (proposal.workspaceId !== workspaceId || proposal.topicId !== topic.id) throw new Error('提案不属于当前稿件。')
    applyLock.current = true; setApplying(true); setError('')
    const revision = editRevision.current
    try {
      const result = await panelEditApi[operation](workspaceId, proposal.id)
      if (!active.current) return result
      const after = operation === 'undo' ? result.undoReceipt?.after : result.receipt.after
      if (result.workspaceId !== workspaceId || result.topicId !== topic.id || result.id !== proposal.id
        || result.status !== (operation === 'undo' ? 'undone' : 'applied') || !after || result.freshness !== 'current') throw new Error('提案回执不是当前稿件版本，请重新打开选题核对；画布未被覆盖。')
      if (editRevision.current !== revision || dirtyRef.current) {
        setError(`提案已${operation === 'undo' ? '撤销' : '采用'}，但等待期间你又编辑了稿件。已保留画布中的新文字，请先对照提案回执；保存时会检查版本冲突。`)
      } else {
        const updated = {...saved, title:after.title, body:after.body, updatedAt:after.updatedAt}
        setSaved(updated); setTitle(updated.title); setBody(updated.body); dirtyRef.current = false
        onUpdatedRef.current(updated)
      }
      return result
    } finally {applyLock.current = false; if (active.current) setApplying(false)}
  }
  async function createRetest(parentId: string, payload: PanelRetestRequest) {
    if (!active.current || retestLock.current || applyLock.current || dirtyRef.current || collaborationLock.current || prepareLock.current || saving) throw new Error('请先保存稿件并等待当前操作完成。')
    if (Date.parse(payload.expectedUpdatedAt) !== Date.parse(saved.updatedAt)) throw new Error('确认中的稿件版本已变化，请重新核对。')
    retestLock.current = true; setRetesting(true); setError('')
    const revision = editRevision.current
    try {
      const run = await simulationRunApi.createRetest(workspaceId, parentId, payload)
      const frozen = run.inputSnapshot.topic as {title?: string; body?: string; updatedAt?: string} | undefined
      if (run.workspaceId !== workspaceId || run.topicId !== topic.id || run.parentSimulationId !== parentId
        || frozen?.title !== saved.title || frozen.body !== (saved.body || '')
        || Date.parse(frozen.updatedAt || '') !== Date.parse(saved.updatedAt)) throw new Error('复测回执与本次稿件不一致，请到模拟历史核对。')
      const canNavigate = active.current && revision === editRevision.current && !dirtyRef.current
      if (active.current && !canNavigate) setError('复测已按提交时的保存稿创建。你在等待时新写的文字仍留在画布中，未自动跳转。')
      return {run, canNavigate}
    } finally {retestLock.current = false; if (active.current) setRetesting(false)}
  }
  return <>
    {error && <p role="alert">{error}</p>}
    {preview && <section className="canvas-candidate-preview" aria-label="写作建议预览"><h2>{preview.candidate.title}</h2><p>先调整这条建议，再放入画布。放入后仍需点击“保存”。</p>
      <details><summary>查看当前正文</summary><p>{preview.body || '当前还没有正文。'}</p></details>
      <label>用于<select aria-label="建议用于" value={previewTarget} onChange={event => setPreviewTarget(event.target.value as 'body' | 'title')}><option value="body">正文</option><option value="title">标题</option></select></label>
      {previewTarget === 'body' ? <label>放入方式<select aria-label="建议放入方式" value={previewMode} onChange={event => setPreviewMode(event.target.value as 'append' | 'replace')}><option value="append">追加在当前正文后</option><option value="replace">替换当前正文</option></select></label> : <p>当前标题：{title} → 确认后替换为下方文字。</p>}
      <label>建议内容<textarea aria-label="编辑写作建议" value={previewText} onChange={event => setPreviewText(event.target.value)} /></label>
      <div className="canvas-candidate-preview-actions"><button className="primary" disabled={!previewText.trim() || applying || retesting || saving || collaborating} onClick={putCandidateInEditor}>确认放入画布</button><button onClick={() => setPreview(null)}>关闭预览</button></div>
    </section>}
    <div className="creator-canvas" style={{gridTemplateColumns:`minmax(0, ${split}fr) 12px minmax(0, ${100-split}fr)`}}>
      <section className="canvas-editor">
        <PendingSuggestions value={topic.generatedSnapshot.pendingSuggestions} />
        <input aria-label="创作标题" value={title} disabled={preparing} onChange={e => {editRevision.current++; dirtyRef.current = true; setTitle(e.target.value)}} />
        <textarea aria-label="创作正文" value={body} disabled={preparing} placeholder="写下你的想法，或请右侧伙伴一起起草。" onChange={e => {editRevision.current++; dirtyRef.current = true; setBody(e.target.value)}} />
        <div className="save-row"><button className="primary" disabled={retesting || applying || !dirty || saving || preparing || !title.trim()} onClick={() => {setError(''); void save().catch(e => setError(String(e)))}}>保存</button><small>{saving ? '保存中…' : dirty ? '有未保存修改' : '已保存'}</small>
          {onSimulate && <button disabled={retesting || applying || preparing || saving || collaborating || !title.trim()} onClick={() => void prepareSimulation()}>{preparing ? '正在保存…' : '选择模拟读者'}</button>}
        </div>
      </section>
      <div className="canvas-divider" role="separator" aria-label="调整画布和对话宽度" aria-valuenow={split} aria-valuemin={30} aria-valuemax={70} aria-orientation="vertical" tabIndex={0}
        onKeyDown={e => {if(e.key === 'ArrowLeft') setSplit(v => Math.max(30,v-5)); if(e.key === 'ArrowRight') setSplit(v => Math.min(70,v+5))}}
        onPointerDown={e => e.currentTarget.setPointerCapture(e.pointerId)}
        onPointerMove={e => {if (!e.currentTarget.hasPointerCapture(e.pointerId)) return; const rect=e.currentTarget.parentElement!.getBoundingClientRect(); setSplit(Math.min(70,Math.max(30,(e.clientX-rect.left)/rect.width*100)))}}
        onPointerUp={e => e.currentTarget.releasePointerCapture(e.pointerId)} />
      <ContentCollaborationChat workspaceId={workspaceId} topic={saved} blocked={retesting || applying || preparing || saving || !title.trim()}
        beforeSend={prepareCollaboration} onActivityChange={onActivityChange} onPreview={previewCandidate} />
    </div>
    <PanelEditWorkspace workspaceId={workspaceId} topic={saved} runs={simulationRuns} onApply={applyPanelEdit}
      onUndo={proposal => applyPanelEdit(proposal, 'undo')}
      onRetest={createRetest} onRetestCreated={onRetestCreated}
      blocked={dirty ? '画布有未保存修改，请先保存；若稿件有变化，需要重新试读。' : retesting || applying || saving || collaborating || preparing ? '请等待当前操作完成。' : ''}/>
  </>
}
