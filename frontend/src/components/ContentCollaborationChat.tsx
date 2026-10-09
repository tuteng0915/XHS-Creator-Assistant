import { useEffect, useRef, useState } from 'react'
import { agentConversationApi } from '../api'
import type { AgentConversation, Topic } from '../types'
import { collaborationCandidates, collaborationSummary, contentCollaborationApi } from '../contentCollaboration'
import type { CollaborationCandidate, CollaborationComposeIntent, CollaborationRole, CollaborationSession, SpecialistRole, WritingFocusRequest } from '../contentCollaboration'
import { CreatorEditSnapshot } from './CreatorEditSnapshot'
import { PendingSuggestions } from './PendingSuggestions'
import { ReaderAvatar } from './ReaderAvatar'
import './ContentCollaborationChat.css'

const roleNames: Record<CollaborationRole, string> = {creator: '你', research: '研究伙伴', writing: '写作伙伴', review: '审稿伙伴', system: '协作提示'}
const candidateNames = {evidence: '可用材料', open_question: '等你补充', outline: '写作提纲', copy_option: '表述建议', review_note: '修改建议'}
const isRunning = (session: CollaborationSession | null) => !!session && ['queued', 'running'].includes(session.executionStatus)
const errorText = (error: unknown) => error instanceof Error ? error.message : String(error)

export function ContentCollaborationChat({workspaceId, topic, blocked, beforeSend, onActivityChange, onPreview, composeIntent}: {
  workspaceId: string; topic: Topic; blocked: boolean
  beforeSend: () => Promise<{topic: Topic; assertCurrent: () => void; writingFocus?: WritingFocusRequest}>
  onActivityChange: (busy: boolean) => void
  onPreview: (candidate: CollaborationCandidate) => void
  composeIntent?: CollaborationComposeIntent | null
}) {
  const [session, setSession] = useState<CollaborationSession | null>(null)
  const [legacy, setLegacy] = useState<AgentConversation[]>([])
  const [ready, setReady] = useState(false)
  const [loadVersion, setLoadVersion] = useState(0)
  const [message, setMessage] = useState('')
  const [recipient, setRecipient] = useState<SpecialistRole>('research')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [pollPaused, setPollPaused] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [composeFocusRequest, setComposeFocusRequest] = useState('')
  const active = useRef(true)
  const sendLock = useRef(false)
  const creationKey = useRef(crypto.randomUUID())
  const requestRef = useRef<{content: string; recipient: SpecialistRole; focusSignature: string; key: string} | null>(null)
  const composedId = useRef('')
  const focusedComposeId = useRef('')
  const composerRef = useRef<HTMLTextAreaElement>(null)
  const transcriptRef = useRef<HTMLDivElement>(null)
  const running = isRunning(session)
  const lastRun = session?.runs.at(-1)
  const pending = session?.messages.find(item => item.id === lastRun?.graphState.pendingMessageId)
  const currentRole = pending?.recipient && pending.recipient !== 'creator' ? pending.recipient : 'research'
  const finishedRoles = session?.messages.filter(item => item.sender !== 'creator' && item.modelMetadata.runId === lastRun?.id).length || 0

  useEffect(() => {active.current = true; return () => {active.current = false}}, [])
  useEffect(() => {
    if (!composeIntent || composeIntent.id === composedId.current) return
    composedId.current = composeIntent.id
    setMessage(value => value.trim() ? `${value}\n\n${composeIntent.text}` : composeIntent.text)
    setRecipient(composeIntent.recipient)
    setComposeFocusRequest(composeIntent.id)
  }, [composeIntent])
  useEffect(() => {
    if (!composeFocusRequest || focusedComposeId.current === composeFocusRequest) return
    focusedComposeId.current = composeFocusRequest
    const composer = composerRef.current
    if (!composer) return
    composer.focus({preventScroll: true})
    composer.setSelectionRange(composer.value.length, composer.value.length)
    composer.scrollIntoView?.({block: 'nearest', behavior: 'auto'})
  }, [composeFocusRequest])
  useEffect(() => {onActivityChange(sending || running)}, [onActivityChange, sending, running])
  useEffect(() => {
    let current = true
    setReady(false)
    void contentCollaborationApi.list(workspaceId).then(async rows => {
      if (!current) return
      const previous = rows.find(row => row.status === 'active' && row.contextTarget.assetId === topic.id)
      const loaded = previous ? await contentCollaborationApi.get(workspaceId, previous.id) : null
      if (current) {setSession(loaded); setError(''); setPollPaused(false); setReady(true)}
    }).catch(e => {if (current) setError(`协作记录未能载入：${errorText(e)}`)})
    return () => {current = false}
  }, [workspaceId, topic.id, loadVersion])
  useEffect(() => {
    let current = true
    void agentConversationApi.list(workspaceId).then(async rows => {
      if (!current) return
      const previous = rows.filter(row => row.contextTarget.assetType === 'topic' && row.contextTarget.assetId === topic.id)
      const results = await Promise.allSettled(previous.map(row => agentConversationApi.get(row.id)))
      if (current) setLegacy(results.flatMap(result => result.status === 'fulfilled' ? [result.value] : []))
    }).catch(() => { /* Legacy history does not block the new room. */ })
    return () => {current = false}
  }, [workspaceId, topic.id])
  useEffect(() => {
    if (!running || !session || pollPaused) return
    let current = true
    let timer: ReturnType<typeof setTimeout>
    const id = session.id
    async function poll() {
      try {
        const latest = await contentCollaborationApi.get(workspaceId, id)
        if (!current) return
        setSession(latest)
        if (isRunning(latest)) timer = setTimeout(() => void poll(), 1000)
      } catch (e) {
        if (current) {setPollPaused(true); setError(`进度连接已中断，已显示的结果仍保留。${errorText(e)}`)}
      }
    }
    timer = setTimeout(() => void poll(), 500)
    return () => {current = false; clearTimeout(timer)}
  }, [workspaceId, session?.id, running, pollPaused]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!running) return
    const started = Date.parse(lastRun?.startedAt || lastRun?.createdAt || '') || Date.now()
    const update = () => setElapsed(Math.max(0, Math.floor((Date.now() - started) / 1000)))
    update()
    const timer = setInterval(update, 1000)
    return () => clearInterval(timer)
  }, [running, lastRun?.id, lastRun?.startedAt, lastRun?.createdAt])
  useEffect(() => {
    const element = transcriptRef.current
    if (element && element.scrollHeight - element.scrollTop - element.clientHeight < 350) element.scrollTop = element.scrollHeight
  }, [session?.messages.length])

  async function send() {
    if (sendLock.current || blocked || !ready || running || !message.trim() || message.trim().length > 8000) return
    sendLock.current = true; onActivityChange(true); setSending(true); setError('')
    const content = message.trim()
    const submittedMessage = message
    const submittedRecipient = recipient
    try {
      const prepared = await beforeSend()
      if (!active.current) return
      const focusSignature = JSON.stringify(prepared.writingFocus || null)
      const request = requestRef.current?.content === content && requestRef.current.recipient === submittedRecipient && requestRef.current.focusSignature === focusSignature
        ? requestRef.current : {content, recipient: submittedRecipient, focusSignature, key: crypto.randomUUID()}
      requestRef.current = request
      const current = session || await contentCollaborationApi.create(workspaceId, topic.id, prepared.topic.title, creationKey.current)
      if (!active.current) return
      setSession(current)
      prepared.assertCurrent()
      const result = prepared.writingFocus
        ? await contentCollaborationApi.send(workspaceId, current.id, content, submittedRecipient, request.key, prepared.writingFocus)
        : await contentCollaborationApi.send(workspaceId, current.id, content, submittedRecipient, request.key)
      if (!active.current) return
      setSession(result); requestRef.current = null
      setMessage(value => value === submittedMessage ? '' : value)
    } catch (e) {if (active.current) setError(errorText(e))}
    finally {sendLock.current = false; if (active.current) setSending(false)}
  }

  function retryLastInstruction() {
    const previous = [...(session?.messages || [])].reverse().find(item => item.sender === 'creator')
    if (!previous) return
    setMessage(previous.content)
    if (previous.recipient && ['research', 'writing', 'review'].includes(previous.recipient)) setRecipient(previous.recipient as SpecialistRole)
    requestRef.current = null
  }

  return <section className="canvas-chat collaboration-chat" aria-label="协作创作室">
    <header className="collaboration-header"><strong>一起把这篇写好</strong>
      <div className="collaboration-members">{(['research', 'writing', 'review'] as const).map(role => <span key={role}><ReaderAvatar id={`collaboration-${role}`} name={roleNames[role]} size={26} />{roleNames[role]}</span>)}</div>
    </header>
    <div ref={transcriptRef} className="canvas-messages collaboration-messages" aria-label="创作对话" aria-live="polite" aria-relevant="additions text">
      {!session?.messages.length && <div className="collaboration-empty"><div className="collaboration-quick-actions">
        <button type="button" disabled={running || sending} onClick={() => {setMessage('围绕这篇内容，帮我找一个清晰、有辨识度的表达角度。'); setRecipient('research')}}>先聊角度</button>
        <button type="button" disabled={running || sending} onClick={() => {setMessage('请根据已有材料起草一版正文，缺少的真实经历留空向我确认。'); setRecipient('writing')}}>帮我起草</button>
      </div></div>}
      {session?.messages.map(item => <article key={item.id} className={`collaboration-message ${item.sender === 'creator' ? 'is-creator' : ''}`}>
        <ReaderAvatar id={`collaboration-${item.sender}`} name={roleNames[item.sender]} size={32} />
        <div className="collaboration-message-content"><div className="collaboration-message-byline"><strong>{roleNames[item.sender]}</strong>{item.recipient && <span>回复 {roleNames[item.recipient]}</span>}</div>
          <div className="collaboration-bubble"><p>{collaborationSummary(item)}</p>
            {collaborationCandidates(item).map((candidate, index) => <section className="collaboration-candidate" key={index}>
              <small>{candidateNames[candidate.kind]}{candidate.confidence === 'needs_creator' ? ' · 待你确认' : candidate.confidence === 'inference' ? ' · 待验证' : ''}</small>
              <h3>{candidate.title}</h3><p>{candidate.body}</p>
              {['outline', 'copy_option'].includes(candidate.kind) && <button type="button" disabled={blocked || sending || running || candidate.focusUnavailable} onClick={() => onPreview(candidate)}>{candidate.writingFocus?.selection ? '对比并修改这一段' : '预览并编辑这条建议'}</button>}
              {candidate.focusUnavailable && <p>这条建议的原文定位不完整，不能直接替换。请重新选择段落后发送。</p>}
              {candidate.kind === 'open_question' && <button type="button" disabled={sending || running} onClick={() => {setRecipient(item.sender === 'system' || item.sender === 'creator' ? 'research' : item.sender); setMessage(`关于“${candidate.title}”：`)}}>补充给{roleNames[item.sender]}</button>}
            </section>)}
          </div>
        </div>
      </article>)}
      {running && <div className="collaboration-progress" role="status"><span className="collaboration-pulse" /> <strong>{pollPaused ? '等待恢复进度连接' : `${roleNames[currentRole]}正在整理${finishedRoles ? '下一部分' : '第一部分'}`}</strong><small>已等待 {elapsed} 秒 · {finishedRoles} 段结果</small>{elapsed > 45 && <p>耗时较久，可继续编辑稿件。</p>}</div>}
      {session?.executionStatus === 'waiting_creator' && <p className="collaboration-status-note">本轮完成，可继续追问。</p>}
      {session?.executionStatus === 'failed' && <div className="collaboration-error" role="alert"><p>{session.failureDetail || lastRun?.errorDetail || '这一轮没有完成，前面已完成的结果已经保留。'}</p><button type="button" onClick={retryLastInstruction}>把上次要求放回输入框</button><small>检查后点击发送会开始新一轮，不会自动重试。</small></div>}
    </div>
    {error && <div className="collaboration-error" role="alert"><p>{error}</p>{(!ready || pollPaused) && <button type="button" onClick={() => {setPollPaused(false); setError(''); setLoadVersion(value => value + 1)}}>重新载入进度</button>}</div>}
    <form className="collaboration-composer" onSubmit={event => {event.preventDefault(); void send()}}>
      <label>这次先请 <select aria-label="先交给哪位伙伴" value={recipient} onChange={event => setRecipient(event.target.value as SpecialistRole)}><option value="research">研究伙伴 · 讨论角度与材料</option><option value="writing">写作伙伴 · 起草与改写</option><option value="review">审稿伙伴 · 检查已有稿件</option></select></label>
      <textarea ref={composerRef} aria-label="给创作助手的消息" maxLength={8000} value={message} onChange={event => setMessage(event.target.value)} placeholder="例如：开头更像我的口吻，保留第二段的经历。" />
      <div><small>发送时保存当前稿件。</small><button className="primary" disabled={blocked || !ready || sending || running || !message.trim()}>{sending ? '正在提交…' : running ? '协作进行中…' : '发送'}</button></div>
    </form>
    {!!legacy.length && <details className="collaboration-legacy"><summary>旧版创作对话（只读）</summary><p>这些是升级前的记录。继续创作请使用上面的协作室。</p>{legacy.map(chat => <div key={chat.id}>{chat.messages.map(item => <article key={item.id}><small>{item.role === 'user' ? '你' : '旧版创作助手'}</small><p>{item.content}</p>{item.role === 'assistant' && <CreatorEditSnapshot metadata={item.modelMetadata} workspaceId={workspaceId} topicId={topic.id} />}<PendingSuggestions value={item.modelMetadata.pendingSuggestions} /></article>)}</div>)}</details>}
  </section>
}
