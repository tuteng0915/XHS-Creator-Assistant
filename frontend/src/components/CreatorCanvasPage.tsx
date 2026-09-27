import { useEffect, useRef, useState } from 'react'
import { agentConversationApi, topicApi } from '../api'
import type { AgentConversation, Topic } from '../types'

export function CreatorCanvasPage({workspaceId, topic, topics, agentId, onSelect, onUpdated}: {
  workspaceId: string; topic: Topic | null; topics: Topic[]; agentId?: string;
  onSelect: (topic: Topic) => void; onUpdated: (topic: Topic) => void;
}) {
  return <section className="creator-canvas-page">
    <div className="creator-page-head"><h1>AI 创作助手</h1><select aria-label="创作选题" value={topic?.id || ''} onChange={e => {const selected = topics.find(t => t.id === e.target.value); if (selected) onSelect(selected)}}><option value="">选择选题</option>{topics.filter(t => t.status !== 'archived').map(t => <option key={t.id} value={t.id}>{t.title}</option>)}</select></div>
    {topic ? <Canvas key={topic.id} workspaceId={workspaceId} topic={topic} agentId={agentId} onUpdated={onUpdated} /> : <p>先从选题库选择一个题目。</p>}
  </section>
}

function Canvas({workspaceId, topic, agentId, onUpdated}: {workspaceId: string; topic: Topic; agentId?: string; onUpdated: (t: Topic) => void}) {
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
  const dirty = title !== saved.title || body !== (saved.body || '')
  const dirtyRef = useRef(dirty)
  const onUpdatedRef = useRef(onUpdated)
  useEffect(() => {dirtyRef.current = dirty; onUpdatedRef.current = onUpdated}, [dirty, onUpdated])
  useEffect(() => {
    let active = true
    void agentConversationApi.list(workspaceId).then(async rows => {
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
    setSaving(true)
    try {
      const updated = await topicApi.update(topic.id, {title, body, expectedUpdatedAt:saved.updatedAt})
      setSaved(updated); onUpdated(updated); dirtyRef.current = false
      return updated
    } finally {setSaving(false)}
  }
  async function send() {
    if (!message.trim() || !agentId || sending || running || !ready) return
    setSending(true); setError('')
    try {
      if (dirty) await save()
      const current = conversation || await agentConversationApi.create(workspaceId, agentId, title, {assetType:'topic',assetId:topic.id})
      setConversation(current)
      const updated = await agentConversationApi.sendMessage(current.id, message, 'live', crypto.randomUUID())
      setConversation(updated); setMessage('')
      if (updated.executionStatus !== 'running') {
        const latest = await topicApi.get(topic.id)
        if (!dirtyRef.current) {setSaved(latest); setTitle(latest.title); setBody(latest.body || ''); onUpdated(latest)}
      }
    } catch (e) {setError(e instanceof Error ? e.message : String(e))}
    finally {setSending(false)}
  }
  return <>
    {error && <p role="alert">{error}</p>}
    <div className="creator-canvas" style={{gridTemplateColumns:`minmax(0, ${split}fr) 12px minmax(0, ${100-split}fr)`}}>
      <section className="canvas-editor">
        <input aria-label="创作标题" value={title} onChange={e => setTitle(e.target.value)} />
        <textarea aria-label="创作正文" value={body} placeholder="写下你的想法，或请右侧 AI 帮你开始。" onChange={e => setBody(e.target.value)} />
        <div className="save-row"><button disabled={!dirty || saving || sending || !title.trim()} onClick={() => {setError(''); void save().catch(e => setError(String(e)))}}>保存</button><small>{saving ? '保存中…' : dirty ? '有未保存修改' : '已保存'}</small></div>
      </section>
      <div className="canvas-divider" role="separator" aria-label="调整画布和对话宽度" aria-valuenow={split} aria-valuemin={30} aria-valuemax={70} aria-orientation="vertical" tabIndex={0}
        onKeyDown={e => {if(e.key === 'ArrowLeft') setSplit(v => Math.max(30,v-5)); if(e.key === 'ArrowRight') setSplit(v => Math.min(70,v+5))}}
        onPointerDown={e => e.currentTarget.setPointerCapture(e.pointerId)}
        onPointerMove={e => {if (!e.currentTarget.hasPointerCapture(e.pointerId)) return; const rect=e.currentTarget.parentElement!.getBoundingClientRect(); setSplit(Math.min(70,Math.max(30,(e.clientX-rect.left)/rect.width*100)))}}
        onPointerUp={e => e.currentTarget.releasePointerCapture(e.pointerId)} />
      <section className="canvas-chat">
        <div className="canvas-messages" aria-label="创作对话" aria-live="polite">{conversation?.messages.map(m => <article key={m.id} className={`canvas-message ${m.role}`}><small>{m.role === 'user' ? '你' : 'AI 创作助手'}</small><p>{m.content}</p>
          {m.modelMetadata.canvasApplyStatus === 'applied' && <small>已更新画布</small>}
          {m.modelMetadata.canvasApplyStatus === 'conflict' && <details><summary>画布有新修改，AI 建议未覆盖</summary><h3>{String((m.modelMetadata.canvasUpdate as Record<string,unknown>)?.title || '')}</h3><p>{String((m.modelMetadata.canvasUpdate as Record<string,unknown>)?.body || '')}</p></details>}
        </article>)}{!conversation?.messages.length && <p className="muted">可以讨论角度，也可以直接要求修改标题和正文。</p>}</div>
        <form onSubmit={e => {e.preventDefault(); void send()}}><textarea aria-label="给创作助手的消息" value={message} onChange={e=>setMessage(e.target.value)} placeholder="例如：开头更像我的口吻，少一点说教。" /><button className="primary" disabled={!ready || !agentId || sending || running || !message.trim() || !title.trim()}>{sending || running ? '正在回复…' : '发送'}</button></form>
      </section>
    </div>
  </>
}
