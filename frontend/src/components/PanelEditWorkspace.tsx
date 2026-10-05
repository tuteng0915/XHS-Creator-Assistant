import {useEffect, useRef, useState} from 'react'
import {panelEditApi, simulationRunApi} from '../api'
import {object, text, type Row} from '../editorFeedback'
import {editOperationLabels, type PanelEditOperation, type PanelEditProposal} from '../panelEdits'
import type {SimulationRun, SimulationRunSummary, Topic} from '../types'
import {CreatorDialog} from './CreatorDialog'
import {EditorFeedbackView} from './EditorFeedbackView'

type Props = {
  workspaceId: string; topic: Topic; runs: SimulationRunSummary[]; blocked: string
  onApply: (proposal: PanelEditProposal) => Promise<PanelEditProposal>
  onUndo?: (proposal: PanelEditProposal) => Promise<PanelEditProposal>
}

export function PanelEditWorkspace(props: Props) {
  const runs = props.runs.filter(r => r.workspaceId === props.workspaceId && r.topicId === props.topic.id
    && !r.draftId && ['completed','partially_completed'].includes(r.status))
  const [open, setOpen] = useState(false)
  const [chosen, setChosen] = useState('')
  const runId = runs.some(r => r.id === chosen) ? chosen : runs[0]?.id
  if (!runs.length) return null
  return <section className="panel-edit-workspace">
    <button aria-expanded={open} onClick={() => setOpen(v => !v)}>试读反馈改稿</button>
    {open && <>
      <label>选择试读记录<select aria-label="改稿依据的试读记录" value={runId} onChange={e => setChosen(e.target.value)}>
        {runs.map(r => <option key={r.id} value={r.id}>{new Date(r.createdAt).toLocaleString()} · {r.status === 'completed' ? '已完成' : '部分完成'}</option>)}
      </select></label>
      {runId && <RunEdits key={`${props.workspaceId}:${runId}`} {...props} runId={runId}/>}
    </>}
  </section>
}

function RunEdits({workspaceId, topic, runId, blocked, onApply, onUndo}: Props & {runId: string}) {
  const [run, setRun] = useState<SimulationRun | null>(null)
  const [proposals, setProposals] = useState<PanelEditProposal[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [reload, setReload] = useState(0)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [dialog, setDialog] = useState<{card:Row} | {proposal:PanelEditProposal} | null>(null)
  const [operation, setOperation] = useState<PanelEditOperation | ''>('')
  const [replacement, setReplacement] = useState('')
  const [undoConfirmId, setUndoConfirmId] = useState('')
  const active = useRef(true), lock = useRef(false)
  const request = useRef({signature:'',key:''})
  useEffect(() => {active.current = true; return () => {active.current = false}}, [])
  useEffect(() => {
    let current = true
    Promise.all([simulationRunApi.get(runId), panelEditApi.list(workspaceId, runId)]).then(([loaded, saved]) => {
      if (!current) return
      if (loaded.id !== runId || loaded.workspaceId !== workspaceId || loaded.topicId !== topic.id
        || saved.some(p => p.workspaceId !== workspaceId || p.topicId !== topic.id || p.simulationId !== runId)) throw new Error('记录归属不匹配，请重新打开。')
      setRun(loaded); setProposals(saved); setLoading(false)
    }).catch(e => {if (current) {setLoadError(String(e)); setLoading(false)}})
    return () => {current = false}
  }, [workspaceId, topic.id, runId, reload])
  function remember(p: PanelEditProposal) {
    if (p.workspaceId !== workspaceId || p.topicId !== topic.id || p.simulationId !== runId) throw new Error('提案归属不匹配')
    // A confirmed response ends this attempt; only uncertain retries reuse its key.
    request.current = {signature:'', key:''}
    setUndoConfirmId('')
    setProposals(items => [p, ...items.filter(i => i.id !== p.id)])
    setDialog(current => current ? {proposal:p} : null)
  }
  async function perform(action: () => Promise<PanelEditProposal>) {
    if (lock.current) return
    lock.current = true; setBusy(true); setError('')
    try {const p = await action(); if (active.current) remember(p)}
    catch (e) {if (active.current) setError(e instanceof Error ? e.message : String(e))}
    finally {lock.current = false; if (active.current) setBusy(false)}
  }
  function matches(before: {title?:unknown; body?:unknown; updatedAt?:unknown}) {
    return before.title === topic.title && before.body === (topic.body || '')
      && typeof before.updatedAt === 'string' && Date.parse(before.updatedAt) === Date.parse(topic.updatedAt)
  }
  const frozen = object(run?.inputSnapshot.topic)
  const supported = !!run && object(run.inputSnapshot.panelTask).protocolVersion === 'panel/v1'
    && ['validated','partial'].includes(text(object(run.synthesis.editorFeedbackValidation).status))
  const unavailable = blocked || (!matches(frozen) ? '稿件已变化，请先用当前版本重新试读。' : '')
  function create() {
    if (!dialog || !('card' in dialog) || !operation || unavailable || busy) return
    const payload = {feedbackId:text(dialog.card.id), expectedUpdatedAt:topic.updatedAt, operation, text:replacement}
    const signature = JSON.stringify(payload)
    if (request.current.signature !== signature) request.current = {signature, key:crypto.randomUUID()}
    void perform(() => panelEditApi.create(workspaceId, runId, {...payload, requestKey:request.current.key}))
  }
  const proposal = dialog && 'proposal' in dialog ? dialog.proposal : null
  const stale = proposal && (!matches(proposal.snapshot.before) || proposal.freshness === 'stale')
  const undoUnavailable = blocked || (proposal && (proposal.freshness === 'stale' || !matches(proposal.receipt.after || {}))
    ? '采用后稿件已有变化，不能撤销覆盖当前版本。' : '')
  return <div>
    {loading && <p role="status">正在读取试读反馈与改稿提案…</p>}
    {loadError && <p role="alert">{loadError}</p>}
    <button disabled={loading || busy} onClick={() => {setLoading(true); setLoadError(''); setReload(n => n+1)}}>刷新提案</button>
    {error && !dialog && <p role="alert">{error} 可刷新提案核对结果。</p>}
    {run && !loadError && <>
      {unavailable && <p role="status">{unavailable}</p>}
      {!supported && <p>这次记录没有可直接改稿的新版反馈，请重新试读；原记录仍可在历史中查看。</p>}
      {supported && <EditorFeedbackView data={run.synthesis} run={run} editDisabled={!!unavailable || busy || loading}
        onPrepare={card => {setError(''); setOperation(''); setReplacement(text(card.suggestedText)); setDialog({card})}}/>}
    </>}
    {!!proposals.length && <section aria-label="已保存的改稿提案"><h3>改稿提案</h3>
      {proposals.map(p => <button className="panel-edit-record" key={p.id} disabled={busy || loading} onClick={() => {setError(''); setUndoConfirmId(''); setDialog({proposal:p})}}>
        <span>{text(p.snapshot.feedback.observation) || '局部修改'}</span>
        <small>{p.status === 'undone' ? '已撤销' : p.status === 'applied' ? '已采用' : p.status === 'rejected' ? '未采用' : '待确认'} · {editOperationLabels[p.snapshot.edit.operation]}</small>
      </button>)}
    </section>}
    {dialog && <CreatorDialog title={proposal ? '确认改稿提案' : '准备局部修改'} wide onClose={() => {setDialog(null); setUndoConfirmId('')}}>
      {error && <p role="alert">{error} 请求结果不确定时，可刷新提案核对或重试同一操作。</p>}
      {'card' in dialog && <>
        <p>{text(dialog.card.observation)}</p>
        <label>原句<blockquote className="panel-edit-text">{text(object(dialog.card.target).quote)}</blockquote></label>
        <label>修改方式<select aria-label="修改方式" value={operation} disabled={busy} onChange={e => setOperation(e.target.value as PanelEditOperation | '')}>
          <option value="">请选择插入或替换</option>
          {Object.entries(editOperationLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </select></label>
        <label>建议文字<textarea aria-label="建议文字" value={replacement} maxLength={50000} disabled={busy} onChange={e => setReplacement(e.target.value)}/></label>
        <p className="muted">可先调整文字。预览只保存提案，不修改原稿，也不调用模型。</p>
        {unavailable && <p role="status">{unavailable}</p>}
        <button className="primary" disabled={busy || !operation || !!unavailable} onClick={create}>{busy ? '正在保存提案…' : '保存提案并预览'}</button>
      </>}
      {proposal && <>
        <p>{editOperationLabels[proposal.snapshot.edit.operation]} · {proposal.snapshot.edit.field === 'title' ? '标题' : '正文'}</p>
        <div className="panel-edit-compare">
          <section><h3>修改前</h3><h4>{proposal.snapshot.before.title}</h4><p className="panel-edit-text">{proposal.snapshot.before.body || '（空正文）'}</p></section>
          <section><h3>{['applied','undone'].includes(proposal.status) ? '当时采用后' : '建议稿'}</h3><h4>{proposal.snapshot.proposed.title}</h4><p className="panel-edit-text">{proposal.snapshot.proposed.body || '（空正文）'}</p></section>
        </div>
        {proposal.status === 'pending' ? <>
          {(blocked || stale) && <p role="status">{blocked || '稿件版本已变化，这份提案不能覆盖当前稿。请重新试读。'}</p>}
          <div className="panel-edit-actions"><button className="primary" disabled={busy || !!blocked || !!stale} onClick={() => void perform(() => onApply(proposal))}>{busy ? '正在处理…' : '确认采用'}</button>
            <button disabled={busy} onClick={() => void perform(() => panelEditApi.reject(workspaceId, proposal.id))}>不采用这份提案</button></div>
        </> : <p role="status">{proposal.status === 'undone' ? '已撤销，撤销时恢复了“修改前”的标题与正文。原采用记录和撤销回执均保留。' : proposal.status === 'applied' ? '已采用，回执已保存。后续编辑不会改写这份对照。' : '未采用，原稿未因这份提案改变。'}</p>}
        {proposal.status === 'applied' && onUndo && <>
          {undoUnavailable && <p role="status">{undoUnavailable}</p>}
          {undoConfirmId === proposal.id ? <section aria-label="撤销确认">
            <p>将恢复为“修改前”的标题与正文。请确认这是你希望保留的版本。</p>
            <div className="panel-edit-actions">
              <button disabled={busy || !!undoUnavailable} onClick={() => void perform(() => onUndo(proposal))}>{busy ? '正在撤销…' : '确认恢复修改前内容'}</button>
              <button disabled={busy} onClick={() => setUndoConfirmId('')}>保留当前版本</button>
            </div>
          </section> : <button disabled={busy || !!undoUnavailable} onClick={() => setUndoConfirmId(proposal.id)}>撤销这次采用</button>}
        </>}
      </>}
    </CreatorDialog>}
  </div>
}
