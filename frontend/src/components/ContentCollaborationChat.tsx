import { useEffect, useRef, useState } from 'react'
import { agentConversationApi } from '../api'
import type { AgentConversation, Topic } from '../types'
import { collaborationCandidates, collaborationSummary, contentCollaborationApi, creatorContextSignature, emptyCreatorContext } from '../contentCollaboration'
import { readCreatorMessage, writeCreatorCache } from '../creatorDraftCache'
import type { CollaborationCandidate, CollaborationComposeIntent, CollaborationRole, CollaborationSession, CollaborationSummary, CreatorContextSelection, WritingFocusRequest } from '../contentCollaboration'
import { CreatorEditSnapshot } from './CreatorEditSnapshot'
import { PendingSuggestions } from './PendingSuggestions'
import { ReaderAvatar } from './ReaderAvatar'
import { CreatorReferencePicker } from './CreatorReferencePicker'
import './ContentCollaborationChat.css'

const roleNames: Record<CollaborationRole, string> = {creator: '你', research: '研究伙伴', writing: '写作伙伴', review: '审稿伙伴', system: '协作提示'}
const candidateNames = {evidence: '可用材料', open_question: '等你补充', outline: '写作提纲', copy_option: '表述建议', review_note: '修改建议'}
const isRunning = (session: CollaborationSession | null) => !!session && ['queued', 'running'].includes(session.executionStatus)
const errorText = (error: unknown) => error instanceof Error ? error.message : String(error)

export function ContentCollaborationChat({workspaceId, topic, blocked, beforeSend, onActivityChange, onPreview, composeIntent, onDraftStorageIssue}: {
  workspaceId: string; topic: Topic; blocked: boolean
  beforeSend: () => Promise<{topic: Topic; assertCurrent: () => void; writingFocus?: WritingFocusRequest}>
  onActivityChange: (busy: boolean) => void
  onPreview: (candidate: CollaborationCandidate) => void
  composeIntent?: CollaborationComposeIntent | null
  onDraftStorageIssue?: (unavailable: boolean) => void
}) {
  const [initialCache] = useState(() => readCreatorMessage(workspaceId, topic.id))
  const [cacheUnavailable, setCacheUnavailable] = useState(initialCache.unavailable)
  const [session, setSession] = useState<CollaborationSession | null>(null)
  const [legacy, setLegacy] = useState<AgentConversation[]>([])
  const [teamHistory, setTeamHistory] = useState<CollaborationSummary[]>([])
  const [teamHistoryId, setTeamHistoryId] = useState('')
  const [teamRecord, setTeamRecord] = useState<CollaborationSession | null>(null)
  const [teamError, setTeamError] = useState('')
  const [ready, setReady] = useState(false)
  const [loadVersion, setLoadVersion] = useState(0)
  const [message, setMessage] = useState(initialCache.value?.message || '')
  const [selection, setSelection] = useState<CreatorContextSelection>(() => initialCache.value?.selection || emptyCreatorContext())
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [pollPaused, setPollPaused] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [composeFocusRequest, setComposeFocusRequest] = useState('')
  const active = useRef(true)
  const sendLock = useRef(false)
  const creationKey = useRef(crypto.randomUUID())
  const requestRef = useRef<{content: string; focusSignature: string; contextSignature: string; key: string} | null>(null)
  const selectionTouched = useRef(!!initialCache.value)
  const composedId = useRef('')
  const focusedComposeId = useRef('')
  const composerRef = useRef<HTMLTextAreaElement>(null)
  const transcriptRef = useRef<HTMLDivElement>(null)
  const running = isRunning(session)
  const lastRun = session?.runs.at(-1)
  const referenceChanged = !!session?.messages.length && creatorContextSignature(selection) !== creatorContextSignature(session.creatorContextSelection || emptyCreatorContext())

  useEffect(() => {active.current = true; return () => {active.current = false}}, [])
  useEffect(() => {
    setCacheUnavailable(!writeCreatorCache('message', workspaceId, topic.id, message ? {version: 1, message, selection} : null))
  }, [workspaceId, topic.id, message, selection])
  useEffect(() => {onDraftStorageIssue?.(cacheUnavailable && !!message)}, [cacheUnavailable, message, onDraftStorageIssue])
  useEffect(() => () => onDraftStorageIssue?.(false), [onDraftStorageIssue])
  useEffect(() => {
    if (!message) return
    const guard = (event: BeforeUnloadEvent) => {event.preventDefault(); event.returnValue = ''}
    window.addEventListener('beforeunload', guard)
    return () => window.removeEventListener('beforeunload', guard)
  }, [message])
  useEffect(() => {
    if (!composeIntent || composeIntent.id === composedId.current) return
    composedId.current = composeIntent.id
    setMessage(value => value.trim() ? `${value}\n\n${composeIntent.text}` : composeIntent.text)
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
      const related = rows.filter(row => row.workspaceId === workspaceId && row.contextTarget.assetType === 'topic' && row.contextTarget.assetId === topic.id)
      const previous = related.find(row => row.status === 'active' && row.assistantMode === 'single_writer')
      const loaded = previous ? await contentCollaborationApi.get(workspaceId, previous.id) : null
      if (loaded && (loaded.id !== previous?.id || loaded.workspaceId !== workspaceId || loaded.contextTarget.assetId !== topic.id || loaded.assistantMode !== 'single_writer')) throw new Error('返回的对话不属于当前稿件。')
      if (current) {
        setSession(loaded); setTeamHistory(related.filter(row => row.assistantMode !== 'single_writer'))
        if (!selectionTouched.current) setSelection(loaded?.creatorContextSelection || emptyCreatorContext())
        setError(''); setPollPaused(false); setReady(true)
      }
    }).catch(e => {if (current) setError(`创作记录未能载入：${errorText(e)}`)})
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
    if (!teamHistoryId) return
    let current = true
    setTeamRecord(null); setTeamError('')
    void contentCollaborationApi.get(workspaceId, teamHistoryId).then(value => {
      if (value.workspaceId !== workspaceId || value.contextTarget.assetId !== topic.id || value.assistantMode === 'single_writer') throw new Error('这份旧记录不属于当前稿件。')
      if (current) setTeamRecord(value)
    }).catch(e => {if (current) setTeamError(errorText(e))})
    return () => {current = false}
  }, [workspaceId, topic.id, teamHistoryId])
  useEffect(() => {
    if (!running || !session || pollPaused) return
    let current = true
    let timer: ReturnType<typeof setTimeout>
    const id = session.id
    async function poll() {
      try {
        const latest = await contentCollaborationApi.get(workspaceId, id)
        if (!current) return
        if (latest.id !== id || latest.workspaceId !== workspaceId || latest.contextTarget.assetId !== topic.id || latest.assistantMode !== 'single_writer') throw new Error('返回的进度不属于当前对话。')
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
    const submittedSelection = {schemaVersion: selection.schemaVersion, references: selection.references.map(item => ({...item}))}
    try {
      const prepared = await beforeSend()
      if (!active.current) return
      const focusSignature = JSON.stringify(prepared.writingFocus || null)
      const contextSignature = creatorContextSignature(submittedSelection)
      const request = requestRef.current?.content === content && requestRef.current.contextSignature === contextSignature && requestRef.current.focusSignature === focusSignature
        ? requestRef.current : {content, focusSignature, contextSignature, key: crypto.randomUUID()}
      requestRef.current = request
      const current = session || await contentCollaborationApi.create(workspaceId, topic.id, prepared.topic.title, creationKey.current)
      if (!active.current) return
      if (current.workspaceId !== workspaceId || current.contextTarget.assetId !== topic.id || current.assistantMode !== 'single_writer') throw new Error('创作会话未准备好，请重新载入后再试。')
      setSession(current)
      prepared.assertCurrent()
      const result = await contentCollaborationApi.send(workspaceId, current.id, content, 'writing', request.key, prepared.writingFocus, submittedSelection)
      if (!active.current) return
      if (result.id !== current.id || result.workspaceId !== workspaceId || result.contextTarget.assetId !== topic.id || result.assistantMode !== 'single_writer') throw new Error('返回的创作结果不属于当前对话，请重新载入。')
      setSession(result); requestRef.current = null
      setMessage(value => value === submittedMessage ? '' : value)
    } catch (e) {if (active.current) setError(errorText(e))}
    finally {sendLock.current = false; if (active.current) setSending(false)}
  }

  function retryLastInstruction() {
    const previous = [...(session?.messages || [])].reverse().find(item => item.sender === 'creator')
    if (!previous) return
    appendInstruction(previous.content)
    requestRef.current = null
  }

  function appendInstruction(text: string) {
    setMessage(value => !value.trim() ? text : value.trim() === text.trim() ? value : `${value}\n\n${text}`)
    setComposeFocusRequest(crypto.randomUUID())
  }

  return <section className="canvas-chat collaboration-chat" aria-label="创作对话区">
    <header className="collaboration-header"><strong>一起把这篇写好</strong>
      <CreatorReferencePicker key={workspaceId} workspaceId={workspaceId} selection={selection} disabled={!ready || sending} onChange={value => {selectionTouched.current = true; setSelection(value)}} />
      {referenceChanged && <p>{running ? '本轮仍按发送时的参考生成。' : ''}参考已调整，下次发送会开启一段新对话。</p>}
    </header>
    <div ref={transcriptRef} className="canvas-messages collaboration-messages" aria-label="创作对话" aria-live="polite" aria-relevant="additions text">
      {!session?.messages.length && <div className="collaboration-empty"><div className="collaboration-quick-actions">
        <button type="button" disabled={running || sending} onClick={() => appendInstruction('围绕这篇内容，帮我找一个清晰、有辨识度的表达角度。')}>先聊角度</button>
        <button type="button" disabled={running || sending} onClick={() => appendInstruction('请根据当前稿件和我选择的参考，起草一版正文；确实缺少关键经历时先问我一个问题。')}>帮我起草</button>
      </div></div>}
      {session?.messages.map((item, itemIndex) => <article key={item.id} className={`collaboration-message ${item.sender === 'creator' ? 'is-creator' : ''}`}>
        {item.sender !== 'creator' && <ReaderAvatar id="creator-writing-assistant" name="创作助手" size={30} />}
        <div className="collaboration-message-content">
          {item.sender === 'creator' && Number(item.modelMetadata.contextRevision) > 1 && item.modelMetadata.contextRevision !== session.messages[itemIndex - 1]?.modelMetadata.contextRevision && <p className="collaboration-context-break">更换参考后的新对话</p>}
          <div className="collaboration-message-byline"><strong>{item.sender === 'creator' ? '你' : '创作助手'}</strong></div>
          <div className="collaboration-bubble"><p>{collaborationSummary(item)}</p>
            {collaborationCandidates(item).map((candidate, index) => <section className="collaboration-candidate" key={index}>
              <small>{candidateNames[candidate.kind]}</small>
              <h3>{candidate.title}</h3><p>{candidate.body}</p>
              {['outline', 'copy_option'].includes(candidate.kind) && <button type="button" disabled={blocked || sending || running || candidate.focusUnavailable} onClick={() => onPreview(candidate)}>{candidate.writingFocus?.selection ? '对比并修改这一段' : '预览并编辑这条建议'}</button>}
              {candidate.focusUnavailable && <p>这条建议的原文定位不完整，不能直接替换。请重新选择段落后发送。</p>}
              {candidate.kind === 'open_question' && <button type="button" disabled={sending || running} onClick={() => appendInstruction(`关于“${candidate.title}”：`)}>补充说明</button>}
            </section>)}
          </div>
        </div>
      </article>)}
      {running && <div className="collaboration-progress" role="status"><span className="collaboration-pulse" /> <strong>{pollPaused ? '等待恢复进度连接' : session?.executionStatus === 'queued' ? '正在准备这次创作' : '创作助手正在整理'}</strong><small>已等待 {elapsed} 秒</small>{elapsed > 45 && <p>耗时较久，可继续编辑稿件。</p>}</div>}
      {session?.executionStatus === 'failed' && <div className="collaboration-error" role="alert"><p>{session.failureDetail || lastRun?.errorDetail || '这一轮没有完成，前面已完成的结果已经保留。'}</p><button type="button" onClick={retryLastInstruction}>把上次要求放回输入框</button><small>检查后点击发送会开始新一轮，不会自动重试。</small></div>}
    </div>
    {error && <div className="collaboration-error" role="alert"><p>{error}</p>{(!ready || pollPaused) && <button type="button" onClick={() => {setPollPaused(false); setError(''); setLoadVersion(value => value + 1)}}>重新载入进度</button>}</div>}
    <form className="collaboration-composer" onSubmit={event => {event.preventDefault(); void send()}}>
      <textarea ref={composerRef} aria-label="给创作助手的消息" maxLength={8000} value={message} onChange={event => setMessage(event.target.value)} placeholder="例如：开头更像我的口吻，保留第二段的经历。" />
      {cacheUnavailable && !!message && !onDraftStorageIssue && <p role="alert">本页无法暂存，请在离开前复制未发送的消息。</p>}
      {message.trim().length > 8000 && <p role="alert">已保留完整输入，请精简至 8000 字以内再发送。</p>}
      <div><small>发送时保存当前稿件。</small><button className="primary" disabled={blocked || !ready || sending || running || !message.trim() || message.trim().length > 8000}>{sending ? '正在提交…' : running ? '正在创作…' : '发送'}</button></div>
    </form>
    {!!teamHistory.length && <details className="collaboration-legacy" onToggle={event => {if (event.currentTarget.open && !teamHistoryId) setTeamHistoryId(teamHistory[0].id)}}><summary>旧版多人协作（只读）</summary><select aria-label="旧协作记录" value={teamHistoryId} onChange={event => setTeamHistoryId(event.target.value)}><option value="">选择记录</option>{teamHistory.map(row => <option key={row.id} value={row.id}>{row.title}</option>)}</select>{teamError && <p role="alert">{teamError}</p>}{teamHistoryId && !teamRecord && !teamError && <p>正在读取…</p>}{teamRecord?.messages.map(item => <article key={item.id}><small>{roleNames[item.sender]}</small><p>{item.content}</p></article>)}</details>}
    {!!legacy.length && <details className="collaboration-legacy"><summary>旧版创作对话（只读）</summary>{legacy.map(chat => <div key={chat.id}>{chat.messages.map(item => <article key={item.id}><small>{item.role === 'user' ? '你' : '旧版创作助手'}</small><p>{item.content}</p>{item.role === 'assistant' && <CreatorEditSnapshot metadata={item.modelMetadata} workspaceId={workspaceId} topicId={topic.id} />}<PendingSuggestions value={item.modelMetadata.pendingSuggestions} /></article>)}</div>)}</details>}
  </section>
}
