import { useCallback, useEffect, useRef, useState } from 'react'
import { panelEditApi, simulationRunApi, topicApi } from '../api'
import type { PanelRetestRequest, SimulationRun, SimulationRunSummary, Topic } from '../types'
import type { PanelEditProposal } from '../panelEdits'
import { replaceSelectedText, selectionFromTextarea, type CollaborationCandidate, type CollaborationComposeIntent, type ReaderFeedbackIntent, type WritingSelection } from '../contentCollaboration'
import { creatorDraftFrom, draftHasSameBase, draftMatchesSaved, readCreatorDraft, writeCreatorCache, type CreatorDraft } from '../creatorDraftCache'
import { ContentCollaborationChat } from './ContentCollaborationChat'
import { PanelEditWorkspace } from './PanelEditWorkspace'
import { PendingSuggestions } from './PendingSuggestions'
import { PanelRetestControl } from './PanelRetestControl'
import { InfoHint } from './InfoHint'
import './LocalRewrite.css'
import './CreatorCanvasPage.css'

const narrowCanvasQuery = '(max-width: 900px)'
type CanvasPane = 'chat' | 'draft'

export function CreatorCanvasPage({workspaceId, topic, topics, onSelect, onUpdated, onSimulate, onRetestCreated, simulationRuns = [], readerFeedback, onReaderFeedbackConsumed, onLeaveGuardChange}: {
  workspaceId: string; topic: Topic | null; topics: Topic[]; agentId?: string;
  onSelect: (topic: Topic) => void; onUpdated: (topic: Topic) => void;
  onSimulate?: (topic: Topic) => void;
  onRetestCreated?: (run: SimulationRun, navigate: boolean) => void;
  simulationRuns?: SimulationRunSummary[];
  readerFeedback?: ReaderFeedbackIntent | null; onReaderFeedbackConsumed?: () => void;
  onLeaveGuardChange?: (message: string | null) => void;
}) {
  return <section className="creator-canvas-page">
    <div className="creator-page-head"><h1>AI 创作助手</h1><select className="creator-topic-select" aria-label="创作选题" value={topic?.id || ''} onChange={e => {const selected = topics.find(t => t.id === e.target.value); if (selected) onSelect(selected)}}><option value="">选择选题</option>{topics.filter(t => t.status !== 'archived').map(t => <option key={t.id} value={t.id}>{t.title}</option>)}</select></div>
    {topic ? <Canvas key={`${workspaceId}:${topic.id}`} workspaceId={workspaceId} topic={topic} onUpdated={onUpdated} onSimulate={onSimulate} onRetestCreated={onRetestCreated} simulationRuns={simulationRuns} readerFeedback={readerFeedback} onReaderFeedbackConsumed={onReaderFeedbackConsumed} onLeaveGuardChange={onLeaveGuardChange} /> : <p>先从选题库选择一个题目。</p>}
  </section>
}

function Canvas({workspaceId, topic, onUpdated, onSimulate, onRetestCreated, simulationRuns, readerFeedback, onReaderFeedbackConsumed, onLeaveGuardChange}: {workspaceId: string; topic: Topic; onUpdated: (t: Topic) => void; onSimulate?: (t: Topic) => void; onRetestCreated?: (run: SimulationRun, navigate: boolean) => void; simulationRuns: SimulationRunSummary[]; readerFeedback?: ReaderFeedbackIntent | null; onReaderFeedbackConsumed?: () => void; onLeaveGuardChange?: (message: string | null) => void}) {
  const [initialCache] = useState(() => readCreatorDraft(workspaceId, topic.id))
  const recoverable = initialCache.value && !draftMatchesSaved(initialCache.value, topic) ? initialCache.value : null
  const [draftConflict, setDraftConflict] = useState<CreatorDraft | null>(() => recoverable && !draftHasSameBase(recoverable, topic) ? recoverable : null)
  const [cacheUnavailable, setCacheUnavailable] = useState(initialCache.unavailable)
  const [messageCacheUnavailable, setMessageCacheUnavailable] = useState(false)
  const [restoredDraft, setRestoredDraft] = useState(!!recoverable && !draftConflict)
  const [saved, setSaved] = useState(topic)
  const [title, setTitle] = useState(() => !draftConflict && recoverable ? recoverable.title : topic.title)
  const [body, setBody] = useState(() => !draftConflict && recoverable ? recoverable.body : topic.body || '')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [collaborating, setCollaborating] = useState(false)
  const [split, setSplit] = useState(44)
  const [narrow, setNarrow] = useState(() => window.matchMedia?.(narrowCanvasQuery).matches ?? window.innerWidth <= 900)
  const [pane, setPane] = useState<CanvasPane>('chat')
  const [preparing, setPreparing] = useState(false)
  const [applying, setApplying] = useState(false)
  const [retesting, setRetesting] = useState(false)
  const [preview, setPreview] = useState<{candidate: CollaborationCandidate; body: string; revision: number} | null>(null)
  const [previewText, setPreviewText] = useState('')
  const [previewTarget, setPreviewTarget] = useState<'body' | 'title'>('body')
  const [previewMode, setPreviewMode] = useState<'append' | 'replace'>('append')
  const [selection, setSelection] = useState<{value: WritingSelection; body: string} | null>(null)
  const [feedback, setFeedback] = useState<ReaderFeedbackIntent | null>(null)
  const [feedbackRunId, setFeedbackRunId] = useState('')
  const [composeIntent, setComposeIntent] = useState<CollaborationComposeIntent | null>(null)
  const previewRef = useRef<HTMLElement>(null)
  const editorRef = useRef<HTMLTextAreaElement>(null)
  const chatPaneRef = useRef<HTMLDivElement>(null)
  const draftPaneRef = useRef<HTMLElement>(null)
  const chatTabRef = useRef<HTMLButtonElement>(null)
  const draftTabRef = useRef<HTMLButtonElement>(null)
  const paneScroll = useRef(new Map<Element, number>())
  const consumedFeedbackId = useRef('')
  const retestLock = useRef(false)
  const applyLock = useRef(false)
  const prepareLock = useRef(false)
  const collaborationLock = useRef(false)
  const editRevision = useRef(0)
  const active = useRef(true)
  const seenTopic = useRef(topic)
  useEffect(() => {active.current = true; return () => {active.current = false}}, [])
  useEffect(() => {
    const media = window.matchMedia?.(narrowCanvasQuery)
    if (!media) return
    const resize = () => {
      if (media.matches && draftPaneRef.current?.contains(document.activeElement)) setPane('draft')
      setNarrow(media.matches)
    }
    media.addEventListener('change', resize)
    return () => media.removeEventListener('change', resize)
  }, [])
  useEffect(() => {
    const visible = pane === 'chat' ? chatPaneRef.current : draftPaneRef.current
    if (!visible) return
    for (const [element, scrollTop] of paneScroll.current) {
      if (visible === element || visible.contains(element)) element.scrollTop = scrollTop
    }
  }, [pane, narrow])
  useEffect(() => {
    if (!preview) return
    previewRef.current?.focus({preventScroll: true})
    previewRef.current?.scrollIntoView?.({block: 'start', behavior: 'auto'})
  }, [preview])
  useEffect(() => {
    if (!readerFeedback || readerFeedback.id === consumedFeedbackId.current || readerFeedback.workspaceId !== workspaceId || readerFeedback.topicId !== topic.id) return
    consumedFeedbackId.current = readerFeedback.id
    setFeedback(readerFeedback); setFeedbackRunId(readerFeedback.simulationId)
    onReaderFeedbackConsumed?.()
  }, [readerFeedback, workspaceId, topic.id, onReaderFeedbackConsumed])
  const dirty = title !== saved.title || body !== (saved.body || '')
  const dirtyRef = useRef(dirty)
  const onUpdatedRef = useRef(onUpdated)
  useEffect(() => {dirtyRef.current = dirty; onUpdatedRef.current = onUpdated}, [dirty, onUpdated])
  useEffect(() => {
    if (seenTopic.current.updatedAt === topic.updatedAt && seenTopic.current.title === topic.title && seenTopic.current.body === topic.body) return
    seenTopic.current = topic
    if (saved.updatedAt === topic.updatedAt && saved.title === topic.title && saved.body === topic.body) return
    const local = draftConflict || (dirty ? creatorDraftFrom(saved, title, body) : null)
    editRevision.current++
    setSaved(topic); setTitle(topic.title); setBody(topic.body || ''); setSelection(null); setPreview(null)
    setDraftConflict(local && !draftMatchesSaved(local, topic) ? local : null)
  }, [topic, saved, dirty, title, body, draftConflict])
  useEffect(() => {
    const value = draftConflict || (dirty ? creatorDraftFrom(saved, title, body) : null)
    setCacheUnavailable(!writeCreatorCache('draft', workspaceId, topic.id, value))
  }, [workspaceId, topic.id, saved, title, body, dirty, draftConflict])
  useEffect(() => {
    if (!dirty && !draftConflict) return
    const guard = (event: BeforeUnloadEvent) => {event.preventDefault(); event.returnValue = ''}
    window.addEventListener('beforeunload', guard)
    return () => window.removeEventListener('beforeunload', guard)
  }, [dirty, draftConflict])
  const leaveWarning = (cacheUnavailable && (dirty || !!draftConflict)) || messageCacheUnavailable
    ? '当前浏览器无法暂存这些修改，离开后未保存内容会丢失。确定离开吗？' : null
  useEffect(() => {onLeaveGuardChange?.(leaveWarning)}, [leaveWarning, onLeaveGuardChange])
  useEffect(() => () => onLeaveGuardChange?.(null), [onLeaveGuardChange])
  const onMessageStorageIssue = useCallback((unavailable: boolean) => setMessageCacheUnavailable(unavailable), [])
  const onActivityChange = useCallback((busy: boolean) => {collaborationLock.current = busy; setCollaborating(busy)}, [])
  const retestBlocked = draftConflict ? '请先处理待恢复的本地草稿。' : dirty ? '画布有未保存修改，请先保存，再邀请原班读者试读。' : retesting || applying || saving || collaborating || preparing ? '请等待当前操作完成。' : ''
  const focusedSelection = selection?.body === body ? selection.value : undefined
  function showPane(next: CanvasPane, focusTab = false) {
    const current = pane === 'chat' ? chatPaneRef.current : draftPaneRef.current
    if (current) {
      for (const element of [current, ...current.querySelectorAll('*')]) {
        if (element.scrollTop > 0 || paneScroll.current.has(element)) paneScroll.current.set(element, element.scrollTop)
      }
    }
    setPane(next)
    if (focusTab) (next === 'chat' ? chatTabRef : draftTabRef).current?.focus()
  }
  function requestRewrite(text: string) {
    showPane('chat')
    setComposeIntent({id: crypto.randomUUID(), recipient: 'writing', text})
  }

  async function save() {
    if (draftConflict) throw new Error('请先选择恢复本地草稿或使用已保存稿。')
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
    const writingFocus = focusedSelection || feedback ? {expectedUpdatedAt: current.updatedAt,
      ...(focusedSelection ? {selection: focusedSelection} : {}),
      ...(feedback ? {readerReference: {simulationId: feedback.simulationId, stage: feedback.stage, messageId: feedback.messageId,
        ...(feedback.interviewId ? {interviewId: feedback.interviewId} : {})}} : {})} : undefined
    return {topic: current, assertCurrent, writingFocus}
  }
  function previewCandidate(candidate: CollaborationCandidate) {
    if (candidate.focusUnavailable) {setError('这条建议的原文定位不完整，请重新选择段落后发送。'); return}
    if (candidate.writingFocus?.selection && (candidate.writingFocus.baseTopicId !== topic.id
      || candidate.writingFocus.baseTitle !== title || replaceSelectedText(body, candidate.writingFocus, candidate.body) === null)) {
      setError('这条局部建议依据的稿件已变化。当前文字已保留，请重新选择段落后生成建议。'); return
    }
    showPane('draft')
    setPreview({candidate, body, revision: editRevision.current})
    setPreviewText(candidate.body); setPreviewMode('append'); setPreviewTarget('body'); setError('')
  }
  function closePreview() {
    setPreview(null)
    editorRef.current?.focus({preventScroll: true})
  }
  function putCandidateInEditor() {
    if (!preview || !previewText.trim()) return
    if (editRevision.current !== preview.revision) {setError('预览期间画布有新修改，请关闭后重新预览，避免覆盖新文字。'); return}
    if (preview.candidate.writingFocus?.selection) {
      const updatedBody = replaceSelectedText(body, preview.candidate.writingFocus, previewText)
      if (updatedBody === null || preview.candidate.writingFocus.baseTopicId !== topic.id || preview.candidate.writingFocus.baseTitle !== title) {
        setError('原稿或选段已变化，这条建议未覆盖任何文字。请重新选择段落后发送。'); return
      }
      editRevision.current++; dirtyRef.current = true; setBody(updatedBody); setSelection(null); closePreview()
      const reference = preview.candidate.writingFocus.readerReference
      if (reference) setFeedbackRunId(reference.simulationId)
      return
    }
    editRevision.current++; dirtyRef.current = true
    if (previewTarget === 'title') setTitle(previewText.trim())
    else setBody(previewMode === 'replace' ? previewText : [preview.body, previewText].filter(Boolean).join('\n\n'))
    if (preview.candidate.writingFocus?.readerReference) setFeedbackRunId(preview.candidate.writingFocus.readerReference.simulationId)
    setSelection(null)
    closePreview()
  }
  async function applyPanelEdit(proposal: PanelEditProposal, operation: 'apply' | 'undo' = 'apply') {
    if (!active.current || draftConflict || retestLock.current || applyLock.current || dirtyRef.current || collaborationLock.current || prepareLock.current || saving) throw new Error('请先完成当前编辑或等待正在执行的操作。')
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
    if (!active.current || draftConflict || retestLock.current || applyLock.current || dirtyRef.current || collaborationLock.current || prepareLock.current || saving) throw new Error('请先保存稿件并等待当前操作完成。')
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
    {draftConflict && <section className="canvas-draft-recovery" aria-label="待恢复的本地草稿">
      <p>已保存稿有更新，本页还留着一份未保存草稿。</p>
      <details><summary>对照两份内容</summary><div className="canvas-draft-comparison"><section><h3>本地未保存</h3><strong>{draftConflict.title}</strong><p>{draftConflict.body || '正文为空'}</p></section><section><h3>当前已保存</h3><strong>{saved.title}</strong><p>{saved.body || '正文为空'}</p></section></div></details>
      <div className="canvas-draft-recovery-actions"><button type="button" onClick={() => {editRevision.current++; setTitle(draftConflict.title); setBody(draftConflict.body); setDraftConflict(null); setRestoredDraft(true)}}>恢复本地草稿</button><button type="button" onClick={() => {setDraftConflict(null); setRestoredDraft(false)}}>使用已保存稿</button></div>
    </section>}
    {leaveWarning && <p className="canvas-draft-storage-warning" role="alert">本页无法暂存，离开前请保存稿件，并复制未发送的消息。</p>}
    {narrow && <div className="canvas-pane-tabs" role="tablist" aria-label="创作工作区"
      onKeyDown={event => {
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
        event.preventDefault()
        showPane(event.key === 'Home' ? 'chat' : event.key === 'End' ? 'draft' : pane === 'chat' ? 'draft' : 'chat', true)
      }}>
      <button ref={chatTabRef} id="canvas-chat-tab" role="tab" type="button" aria-selected={pane === 'chat'} aria-controls="canvas-chat-pane" tabIndex={pane === 'chat' ? 0 : -1} onClick={() => showPane('chat')}>对话</button>
      <button ref={draftTabRef} id="canvas-draft-tab" role="tab" type="button" aria-selected={pane === 'draft'} aria-controls="canvas-draft-pane" tabIndex={pane === 'draft' ? 0 : -1} onClick={() => showPane('draft')}>稿件{dirty && <span className="canvas-unsaved-dot" aria-hidden="true" title="有未保存修改" />}</button>
    </div>}
    <div className="creator-canvas" style={{gridTemplateColumns:`minmax(0, ${split}fr) 12px minmax(0, ${100-split}fr)`}}>
      <div ref={chatPaneRef} id="canvas-chat-pane" className="canvas-dialogue-pane" role={narrow ? 'tabpanel' : undefined} aria-labelledby={narrow ? 'canvas-chat-tab' : undefined} hidden={narrow && pane !== 'chat'}>
    {feedback && <section className="canvas-reader-feedback" aria-label="带来的读者意见">
      <div className="canvas-focus-heading"><h2>读者意见 · {feedback.senderName}</h2><button type="button" className="text-button" onClick={() => setFeedback(null)}>移除引用</button></div>
      {feedback.authorQuestion && <p className="canvas-focus-question">你当时问：{feedback.authorQuestion}</p>}
      <blockquote>{feedback.quote}</blockquote>
      <button type="button" disabled={collaborating || saving || applying || retesting} onClick={() => requestRewrite(focusedSelection ? '请结合引用的读者意见，只改写我选中的这一段，保留其余内容。' : '请结合引用的读者意见，先讨论这篇稿件哪些地方值得调整，别直接重写整篇。')}>和助手讨论</button>
    </section>}
        <ContentCollaborationChat workspaceId={workspaceId} topic={saved} blocked={!!draftConflict || retesting || applying || preparing || saving || !title.trim()}
          beforeSend={prepareCollaboration} onActivityChange={onActivityChange} onPreview={previewCandidate} composeIntent={composeIntent} onDraftStorageIssue={onMessageStorageIssue} />
      </div>
      <div className="canvas-divider" role="separator" aria-label="调整对话和稿件宽度" aria-valuenow={split} aria-valuetext={`对话 ${split}% · 稿件 ${100 - split}%`} aria-valuemin={30} aria-valuemax={70} aria-orientation="vertical" tabIndex={0} hidden={narrow}
        onKeyDown={event => {
          if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
          event.preventDefault()
          setSplit(value => event.key === 'Home' ? 30 : event.key === 'End' ? 70 : Math.max(30, Math.min(70, value + (event.key === 'ArrowLeft' ? -5 : 5))))
        }}
        onPointerDown={event => {event.preventDefault(); event.currentTarget.focus(); event.currentTarget.setPointerCapture(event.pointerId)}}
        onPointerMove={event => {if (!event.currentTarget.hasPointerCapture(event.pointerId)) return; const rect = event.currentTarget.parentElement!.getBoundingClientRect(); if (rect.width) setSplit(Math.round(Math.min(70, Math.max(30, (event.clientX - rect.left) / rect.width * 100))))}}
        onPointerUp={event => {if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)}}
        onPointerCancel={event => {if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)}} />
      <section ref={draftPaneRef} id="canvas-draft-pane" className="canvas-editor" role={narrow ? 'tabpanel' : undefined} aria-labelledby={narrow ? 'canvas-draft-tab' : undefined} hidden={narrow && pane !== 'draft'}>
        <div className="canvas-editor-heading"><h2>稿件<InfoHint label="稿件编辑说明">选中文字可局部改写；点击改写方式会把要求填入对话，确认发送后才生成建议。预览并采用后，仍需保存稿件。</InfoHint></h2><span>{Array.from(body).length} 字</span></div>
    {preview && <section ref={previewRef} tabIndex={-1} className="canvas-candidate-preview" aria-label="写作建议预览"><h2>{preview.candidate.title}</h2><p className="canvas-preview-note">确认后仍需保存。</p>
      {typeof preview.candidate.writingFocus?.readerMessage?.content === 'string' && <details><summary>这条建议参考的读者意见</summary>
        <p>{preview.candidate.writingFocus.readerMessage.senderName}：{preview.candidate.writingFocus.readerMessage.content}</p>
        {preview.candidate.writingFocus.readerMessage.authorQuestion && <p>你当时问：{preview.candidate.writingFocus.readerMessage.authorQuestion}</p>}
      </details>}
      {preview.candidate.writingFocus?.selection ? <>
        <label>修改前<blockquote className="canvas-focus-original">{preview.candidate.writingFocus.selection.text}</blockquote></label>
      </> : <>
      <details><summary>查看当前正文</summary><p>{preview.body || '当前还没有正文。'}</p></details>
      <label>用于<select aria-label="建议用于" value={previewTarget} onChange={event => setPreviewTarget(event.target.value as 'body' | 'title')}><option value="body">正文</option><option value="title">标题</option></select></label>
      {previewTarget === 'body' ? <label>放入方式<select aria-label="建议放入方式" value={previewMode} onChange={event => setPreviewMode(event.target.value as 'append' | 'replace')}><option value="append">追加在当前正文后</option><option value="replace">替换当前正文</option></select></label> : <p>当前标题：{title} → 确认后替换为下方文字。</p>}
      </>}
      <label>{preview.candidate.writingFocus?.selection ? '修改后' : '建议内容'}<textarea aria-label="编辑写作建议" value={previewText} onChange={event => setPreviewText(event.target.value)} /></label>
      <div className="canvas-candidate-preview-actions"><button className="primary" disabled={!previewText.trim() || applying || retesting || saving || collaborating} onClick={putCandidateInEditor}>{preview.candidate.writingFocus?.selection ? '只替换这一段' : '确认放入画布'}</button><button onClick={closePreview}>关闭预览</button></div>
    </section>}
        <PendingSuggestions value={topic.generatedSnapshot.pendingSuggestions} />
        <input aria-label="创作标题" value={title} disabled={preparing || !!draftConflict} placeholder="给这篇内容一个标题" onChange={e => {editRevision.current++; dirtyRef.current = true; setTitle(e.target.value)}} />
        <textarea ref={editorRef} aria-label="创作正文" value={body} disabled={preparing || !!draftConflict} placeholder="写下想法，或和助手一起起草。" onChange={e => {editRevision.current++; dirtyRef.current = true; setBody(e.target.value); setSelection(null)}}
          onSelect={event => {const node = event.currentTarget, value = selectionFromTextarea(body, node.selectionStart, node.selectionEnd); setSelection(value ? {value, body} : null)}} />
        {focusedSelection ? <section className="canvas-selection-tools" aria-label="选段改写">
          <div className="canvas-focus-heading"><strong>已选 {Array.from(focusedSelection.text).length} 字</strong><button type="button" className="text-button" onClick={() => setSelection(null)}>取消选段</button></div>
          <details><summary>查看选段</summary><blockquote>{focusedSelection.text}</blockquote></details>
          <div className="canvas-selection-actions">{[
            ['更像我的口吻', '请只改写我选中的这一段，让它更贴近当前原稿的口吻和表达习惯，不补造经历或事实。'],
            ['更简洁', '请只改写我选中的这一段，删去重复和绕弯，让表达更简洁，保留原有信息。'],
            ['把观点讲清楚', '请只改写我选中的这一段，把观点与逻辑讲清楚；缺少事实请先问我，不补造例子或数据。'],
          ].map(([label, request]) => <button key={label} type="button" disabled={collaborating || saving || applying || retesting} onClick={() => requestRewrite(request)}>{label}</button>)}</div>
        </section> : null}
        {restoredDraft && dirty && <p className="canvas-draft-restored">已恢复本页未保存草稿。</p>}
        <div className="save-row"><button className="primary" disabled={!!draftConflict || retesting || applying || !dirty || saving || preparing || !title.trim()} onClick={() => {setError(''); void save().catch(e => setError(String(e)))}}>保存</button><small>{saving ? '保存中…' : dirty ? '有未保存修改' : '已保存'}</small>
          {onSimulate && <button disabled={!!draftConflict || retesting || applying || preparing || saving || collaborating || !title.trim()} onClick={() => void prepareSimulation()}>{preparing ? '正在保存…' : '选择模拟读者'}</button>}
        </div>
      </section>
    </div>
    {feedbackRunId && onRetestCreated && <section className="canvas-feedback-retest" aria-label="意见修改后复测"><h2>原班读者复测</h2>
      <PanelRetestControl key={feedbackRunId} workspaceId={workspaceId} runId={feedbackRunId} topic={saved} blocked={retestBlocked} onCreate={createRetest} onCreated={onRetestCreated} />
    </section>}
    <PanelEditWorkspace workspaceId={workspaceId} topic={saved} runs={simulationRuns} onApply={applyPanelEdit}
      onUndo={proposal => applyPanelEdit(proposal, 'undo')}
      onRetest={createRetest} onRetestCreated={onRetestCreated}
      blocked={draftConflict ? '请先处理待恢复的本地草稿。' : dirty ? '画布有未保存修改，请先保存；若稿件有变化，需要重新试读。' : retesting || applying || saving || collaborating || preparing ? '请等待当前操作完成。' : ''}/>
  </>
}
