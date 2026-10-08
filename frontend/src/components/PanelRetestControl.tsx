import {useEffect, useRef, useState} from 'react'
import {simulationRunApi} from '../api'
import type {PanelRetestPreview, PanelRetestRequest, SimulationRun, Topic} from '../types'
import {CreatorDialog} from './CreatorDialog'

export type RetestAction = (parentId: string, payload: PanelRetestRequest) => Promise<{
  run: SimulationRun; canNavigate: boolean
}>

export function PanelRetestControl({workspaceId, runId, topic, blocked, onCreate, onCreated}: {
  workspaceId: string; runId: string; topic: Topic; blocked: string
  onCreate: RetestAction; onCreated: (run: SimulationRun, navigate: boolean) => void
}) {
  const [preview, setPreview] = useState<PanelRetestPreview | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [created, setCreated] = useState(false)
  const active = useRef(true), lock = useRef(false)
  useEffect(() => {active.current = true; return () => {active.current = false}}, [])
  const stale = !!preview && (preview.title !== topic.title || preview.body !== (topic.body || '')
    || Date.parse(preview.expectedUpdatedAt) !== Date.parse(topic.updatedAt))
  async function prepare() {
    if (blocked || lock.current) return
    lock.current = true; setLoading(true); setError(''); setCreated(false)
    try {
      const next = await simulationRunApi.previewRetest(workspaceId, runId)
      if (!active.current) return
      if (next.workspaceId !== workspaceId || next.parentSimulationId !== runId || next.topicId !== topic.id) {
        throw new Error('复测预览与当前账号或稿件不一致，请重新打开。')
      }
      setPreview(next)
    } catch (e) {if (active.current) setError(e instanceof Error ? e.message : String(e))}
    finally {lock.current = false; if (active.current) setLoading(false)}
  }
  async function confirm() {
    if (!preview || blocked || stale || lock.current) return
    lock.current = true; setBusy(true); setError('')
    try {
      // Persist only the opaque identity, so closing/reloading after a lost response
      // cannot silently start another paid run for the same saved version.
      const storageKey = `panel-retest:${workspaceId}:${runId}:${preview.expectedUpdatedAt}`
      let requestKey = sessionStorage.getItem(storageKey)
      if (!requestKey) {requestKey = crypto.randomUUID(); sessionStorage.setItem(storageKey, requestKey)}
      const result = await onCreate(runId, {
        requestKey, expectedUpdatedAt: preview.expectedUpdatedAt, confirmed: true,
      })
      if (!active.current) return
      setPreview(null); setCreated(true)
      onCreated(result.run, result.canNavigate)
    } catch (e) {if (active.current) setError(e instanceof Error ? e.message : String(e))}
    finally {lock.current = false; if (active.current) setBusy(false)}
  }
  return <div className="panel-retest-control">
    <button disabled={!!blocked || busy || loading} onClick={() => void prepare()}>
      {loading ? '正在核对复测条件…' : '用同组读者复测'}
    </button>
    {error && !preview && <p role="alert">{error}</p>}
    {created && <p role="status">复测已创建，可在受众模拟历史中查看；原试读记录保留。</p>}
    {preview && <CreatorDialog title="用同组读者复测" onClose={() => {if (!busy) {setPreview(null); setError('')}}}>
      <p>沿用上次 {preview.readers.length} 位读者，只更换为当前已保存的稿件。读者不会看到上次评价。</p>
      <div className="retest-reader-list" aria-label="固定的模拟读者">
        {preview.readers.map((reader, index) => <div key={reader.id}><b>{index + 1}. {reader.name}</b><p>{reader.profile}</p></div>)}
      </div>
      <section aria-label="沿用的阅读任务">
        <p>{preview.panelTask.readingMode === 'guided' ? '定向试读' : '自然全文试读'} · 互相回应{preview.panelTask.discussionEnabled ? '开启' : '关闭'}</p>
        {!!preview.panelTask.focusQuestions.length && <ol>{preview.panelTask.focusQuestions.map((q, i) => <li key={i}>{q}</li>)}</ol>}
      </section>
      <details><summary>本次已保存稿件：{preview.title}</summary><p className="panel-edit-text">{preview.body || '（空正文）'}</p></details>
      <p className="muted">{preview.mode === 'live' ? '确认后调用当前模型，会产生模型费用。' : '本次沿用演示模式，不调用真实模型。'}固定人物不保证每次反应一致。</p>
      <details><summary>比较时需要注意</summary><ul>{preview.limitations.map((item, i) => <li key={i}>{item}</li>)}</ul></details>
      {(blocked || stale) && <p role="status">{blocked || '画布与服务器稿件版本不一致，请重新打开选题后再复测。'}</p>}
      {error && <p role="alert">{error} 结果不确定时可重试，将沿用本次请求标识。</p>}
      <div className="panel-edit-actions">
        <button className="primary" disabled={!!blocked || stale || busy} onClick={() => void confirm()}>{busy ? '正在创建复测…' : '确认开始复测'}</button>
        <button disabled={busy} onClick={() => {setPreview(null); setError('')}}>暂不复测</button>
      </div>
    </CreatorDialog>}
  </div>
}
