import { useEffect, useRef, useState } from 'react'
import { agentConversationApi, panelEditApi, topicApi } from '../api'
import type { AgentConversation, SimulationRunSummary, Topic } from '../types'
import type { PanelEditProposal } from '../panelEdits'
import { PanelEditWorkspace } from './PanelEditWorkspace'
import { CreatorEditSnapshot } from './CreatorEditSnapshot'
import { PendingSuggestions } from './PendingSuggestions'

export function CreatorCanvasPage({workspaceId, topic, topics, agentId, onSelect, onUpdated, onSimulate, simulationRuns = []}: {
  workspaceId: string; topic: Topic | null; topics: Topic[]; agentId?: string;
  onSelect: (topic: Topic) => void; onUpdated: (topic: Topic) => void;
  onSimulate?: (topic: Topic) => void;
  simulationRuns?: SimulationRunSummary[];
}) {
  return <section className="creator-canvas-page">
    <div className="creator-page-head"><h1>AI 创作助手</h1><select aria-label="创作选题" value={topic?.id || ''} onChange={e => {const selected = topics.find(t => t.id === e.target.value); if (selected) onSelect(selected)}}><option value="">选择选题</option>{topics.filter(t => t.status !== 'archived').map(t => <option key={t.id} value={t.id}>{t.title}</option>)}</select></div>
    {topic ? <Canvas key={`${workspaceId}:${topic.id}`} workspaceId={workspaceId} topic={topic} agentId={agentId} onUpdated={onUpdated} onSimulate={onSimulate} simulationRuns={simulationRuns} /> : <p>先从选题库选择一个题目。</p>}
  </section>
}

function Canvas({workspaceId, topic, agentId, onUpdated, onSimulate, simulationRuns}: {workspaceId: string; topic: Topic; agentId?: string; onUpdated: (t: Topic) => void; onSimulate?: (t: Topic) => void; simulationRuns: SimulationRunSummary[]}) {
  const [saved, setSaved] = useState(topic)
  const [title, setTitle] = useState(topic.title)
  const [body, setBody] = useState(topic.body || '')
  const [conversation, setConversation] = useState<AgentConversation | null>(null)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [sending, setSending] = useState(false)
  const [ready, setReady] = useState(false)
  const [split, setSplit] = useState(55)
  const [preparing, setPreparing] = useState(false)
  const [applying, setApplying] = useState(false)
  const applyLock = useRef(false)
  const prepareLock = useRef(false)
  const sendLock = useRef(false)
  const editRevision = useRef(0)
  const active = useRef(true)
  useEffect(() => {active.current = true; return () => {active.current = false}}, [])
  const dirty = title !== saved.title || body !== (saved.body || '')
  const dirtyRef = useRef(dirty)
  const onUpdatedRef = useRef(onUpdated)
  useEffect(() => {dirtyRef.current = dirty; onUpdatedRef.current = onUpdated}, [dirty, onUpdated])
  useEffect(() => {
    let active = true
    void agentConversationApi.list(workspaceId).then(async rows => {
      if (!active) return
      const previous = rows.find(r => r.contextTarget.assetType === 'topic' && r.contextTarget.assetId === topic.id && r.status === 'active')
      const loaded = previous ? await agentConversationApi.get(previous.id) : null
      if (active) {setConversation(loaded); setReady(true)}
    }).catch(e => {if(active) {setError(String(e)); setReady(true)}})
    return () => {active = false}
  }, [workspaceId, topic.id])
  const running = conversation?.executionStatus === 'running'
  useEffect(() => {
    if (!running || !conversation) return
    let active = true
    let timer: ReturnType<typeof setTimeout>
    async function poll() {
      try {
        const latest = await agentConversationApi.get(conversation!.id)
        if (!active) return
        if (latest.executionStatus !== 'running') {
          const updated = await topicApi.get(topic.id)
          if (!active) return
          if (!dirtyRef.current) {setSaved(updated); setTitle(updated.title); setBody(updated.body || ''); onUpdatedRef.current(updated)}
          else setError('AI 已回复。你有未保存的修改，已保留在画布中；保存时若出现冲突，请先对照 AI 建议。')
        } else timer = setTimeout(() => void poll(), 1200)
        setConversation(latest)
      } catch (e) {if (active) {setError(String(e)); timer = setTimeout(() => void poll(), 3000)}}
    }
    timer = setTimeout(() => void poll(), 800)
    return () => {active = false; clearTimeout(timer)}
  }, [running, conversation?.id, topic.id]) // eslint-disable-line react-hooks/exhaustive-deps
  async function save() {
    if (applyLock.current) throw new Error('改稿提案正在应用，请稍候再保存。')
    const savingRevision = editRevision.current
    setSaving(true)
    try {
      const updated = await topicApi.update(topic.id, {title, body, expectedUpdatedAt:saved.updatedAt})
      if (active.current) {setSaved(updated); onUpdatedRef.current(updated); dirtyRef.current = editRevision.current !== savingRevision}
      return updated
    } finally {if (active.current) setSaving(false)}
  }
  async function prepareSimulation() {
    if (!onSimulate || applyLock.current || prepareLock.current || sendLock.current || saving || sending || running || !ready || !title.trim()) return
    prepareLock.current = true; setPreparing(true); setError('')
    try {
      const target = dirty ? await save() : saved
      if (active.current) onSimulate(target)
    } catch (e) {if (active.current) setError(e instanceof Error ? e.message : String(e))}
    finally {prepareLock.current = false; if (active.current) setPreparing(false)}
  }
  async function send() {
    if (!active.current || applyLock.current || !message.trim() || !title.trim() || !agentId || sendLock.current || prepareLock.current || saving || preparing || sending || running || !ready) return
    sendLock.current = true
    const submittedMessage = message
    const submittedRevision = editRevision.current
    setSending(true); setError('')
    try {
      if (dirty) await save()
      if (!active.current) return
      if (editRevision.current !== submittedRevision) {setError('保存期间稿件有新修改，已保留；请确认后再次发送。'); return}
      const current = conversation || await agentConversationApi.create(workspaceId, agentId, title, {assetType:'topic',assetId:topic.id})
      if (!active.current) return
      setConversation(current)
      if (editRevision.current !== submittedRevision) {setError('稿件有新修改，已保留；请确认后再次发送。'); return}
      const updated = await agentConversationApi.sendMessage(current.id, submittedMessage, 'live', crypto.randomUUID())
      if (!active.current) return
      setConversation(updated); setMessage(value => value === submittedMessage ? '' : value)
      if (updated.executionStatus !== 'running') {
        const latest = await topicApi.get(topic.id)
        if (!active.current) return
        if (!dirtyRef.current) {setSaved(latest); setTitle(latest.title); setBody(latest.body || ''); onUpdatedRef.current(latest)}
        else setError('AI 已回复。你有未保存的修改，已保留在画布中；保存时若出现冲突，请先对照 AI 建议。')
      }
    } catch (e) {if (active.current) setError(e instanceof Error ? e.message : String(e))}
    finally {sendLock.current = false; if (active.current) setSending(false)}
  }
  async function applyPanelEdit(proposal: PanelEditProposal, operation: 'apply' | 'undo' = 'apply') {
    if (!active.current || applyLock.current || dirtyRef.current || sendLock.current || prepareLock.current || saving || running || !ready) throw new Error('请先完成当前编辑或等待正在执行的操作。')
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
  return <>
    {error && <p role="alert">{error}</p>}
    <div className="creator-canvas" style={{gridTemplateColumns:`minmax(0, ${split}fr) 12px minmax(0, ${100-split}fr)`}}>
      <section className="canvas-editor">
        <PendingSuggestions value={topic.generatedSnapshot.pendingSuggestions} />
        <input aria-label="创作标题" value={title} disabled={preparing} onChange={e => {editRevision.current++; dirtyRef.current = true; setTitle(e.target.value)}} />
        <textarea aria-label="创作正文" value={body} disabled={preparing} placeholder="写下你的想法，或请右侧 AI 帮你开始。" onChange={e => {editRevision.current++; dirtyRef.current = true; setBody(e.target.value)}} />
        <div className="save-row"><button disabled={applying || !dirty || saving || sending || preparing || !title.trim()} onClick={() => {setError(''); void save().catch(e => setError(String(e)))}}>保存</button><small>{saving ? '保存中…' : dirty ? '有未保存修改' : '已保存'}</small>
          {onSimulate && <button disabled={applying || preparing || saving || sending || running || !ready || !title.trim()} onClick={() => void prepareSimulation()}>{preparing ? '正在保存…' : '选择模拟读者'}</button>}
        </div>
      </section>
      <div className="canvas-divider" role="separator" aria-label="调整画布和对话宽度" aria-valuenow={split} aria-valuemin={30} aria-valuemax={70} aria-orientation="vertical" tabIndex={0}
        onKeyDown={e => {if(e.key === 'ArrowLeft') setSplit(v => Math.max(30,v-5)); if(e.key === 'ArrowRight') setSplit(v => Math.min(70,v+5))}}
        onPointerDown={e => e.currentTarget.setPointerCapture(e.pointerId)}
        onPointerMove={e => {if (!e.currentTarget.hasPointerCapture(e.pointerId)) return; const rect=e.currentTarget.parentElement!.getBoundingClientRect(); setSplit(Math.min(70,Math.max(30,(e.clientX-rect.left)/rect.width*100)))}}
        onPointerUp={e => e.currentTarget.releasePointerCapture(e.pointerId)} />
      <section className="canvas-chat">
        <div className="canvas-messages" aria-label="创作对话" aria-live="polite">{conversation?.messages.map(m => <article key={m.id} className={`canvas-message ${m.role}`}><small>{m.role === 'user' ? '你' : 'AI 创作助手'}</small><p>{m.content}</p>
          {m.role === 'assistant' && <CreatorEditSnapshot metadata={m.modelMetadata} workspaceId={workspaceId} topicId={topic.id} />}
          <PendingSuggestions value={m.modelMetadata.pendingSuggestions} />
          {m.modelMetadata.canvasApplyStatus === 'needs_confirmation' && <small>原稿未改动 · 请在对话中补充真实素材</small>}
        </article>)}{!conversation?.messages.length && <p className="muted">可以讨论角度，也可以直接要求修改标题和正文。</p>}</div>
        <form onSubmit={e => {e.preventDefault(); if (!preparing) void send()}}><textarea aria-label="给创作助手的消息" value={message} onChange={e=>setMessage(e.target.value)} placeholder="例如：开头更像我的口吻，少一点说教。" /><button className="primary" disabled={applying || preparing || saving || !ready || !agentId || sending || running || !message.trim() || !title.trim()}>{sending || running ? '正在回复…' : '发送'}</button></form>
      </section>
    </div>
    <PanelEditWorkspace workspaceId={workspaceId} topic={saved} runs={simulationRuns} onApply={applyPanelEdit}
      onUndo={proposal => applyPanelEdit(proposal, 'undo')}
      blocked={dirty ? '画布有未保存修改，请先保存；若稿件有变化，需要重新试读。' : applying || saving || sending || running || preparing || !ready ? '请等待当前操作完成。' : ''}/>
  </>
}
