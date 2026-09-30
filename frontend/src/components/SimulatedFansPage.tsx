import { useState } from 'react'
import { simulatedFanApi } from '../api'
import type { FanDefinition, SimulatedFan } from '../types'

export function SimulatedFansPage({rows, error, onRefresh, onAnalyze}: {
  rows:SimulatedFan[]; error:string; onRefresh:()=>Promise<void>; onAnalyze:()=>void;
}) {
  const [selectedId,setSelectedId] = useState('')
  const selected = rows.find(r => r.id === selectedId)
  return <div className="workspace-page">
    <section className="history-list"><div className="panel-title">模拟粉丝</div>
      {error && <p role="alert">{error}</p>}
      {!rows.length && <><p>先分析受众，生成模拟粉丝。</p><button onClick={onAnalyze}>分析受众</button></>}
      {rows.map(f => <button key={f.id} className={`run-row ${f.id === selectedId ? 'active' : ''}`} onClick={() => setSelectedId(f.id)}><span>{f.editable.name}</span><small>{f.original.origin === 'curated_preset' ? '预置整理 · ' : ''}{f.status === 'archived' ? '已归档' : '可用于模拟'}</small></button>)}
    </section>
    <section className="history-detail">{selected ? <FanEditor key={selected.id} fan={selected} onRefresh={onRefresh} /> : <p>选择一位模拟粉丝查看档案。</p>}</section>
  </div>
}

function FanEditor({fan,onRefresh}:{fan:SimulatedFan;onRefresh:()=>Promise<void>}) {
  const [saved,setSaved] = useState(fan)
  const [draft,setDraft] = useState(fan.editable)
  const [busy,setBusy] = useState(false)
  const [error,setError] = useState('')
  const dirty = JSON.stringify(draft) !== JSON.stringify(saved.editable)
  async function save(status:SimulatedFan['status']) {
    setBusy(true); setError('')
    try {const updated = await simulatedFanApi.update(fan.id,{...draft,status,expectedUpdatedAt:saved.updatedAt});setSaved(updated);await onRefresh()}
    catch(e) {setError(String(e))} finally {setBusy(false)}
  }
  const fields: [keyof FanDefinition,string][] = [['name','名称'],['profile','阅读视角'],['coreConcern','关注的问题'],['contentPreference','内容偏好'],['expressionStyle','表达习惯']]
  return <><h2>{saved.editable.name}</h2><p className="muted">模拟角色，不代表某位真实粉丝。编辑内容属于人工设定。</p>
    {fan.original.origin === 'curated_preset' && <p className="muted">依据已保存评论预置整理，非模型接口分析；角色偏好和表达习惯是模拟假设。</p>}
    {fields.map(([key,label]) => <label key={key}>{label}{key === 'name'
      ? <input value={draft[key]} onChange={e => setDraft({...draft,[key]:e.target.value})} />
      : <textarea rows={3} value={draft[key]} onChange={e => setDraft({...draft,[key]:e.target.value})} />}</label>)}
    <div className="save-row"><button disabled={busy || !dirty || !draft.name.trim() || !draft.profile.trim()} onClick={() => void save(saved.status)}>保存修改</button>
      <span>{busy ? '保存中…' : error ? '保存失败' : dirty ? '有未保存修改' : '已保存'}</span>
      <button disabled={busy || dirty} onClick={() => void save(saved.status === 'active' ? 'archived' : 'active')}>{saved.status === 'active' ? '归档' : '恢复'}</button>
    </div>{error && <p role="alert">{error}</p>}
    <details><summary>原始依据与未知项</summary><p>来源分析：{fan.sourceAnalysisId}</p>
      <pre className="json-preview">{JSON.stringify({evidenceRefs:fan.original.evidenceRefs,unknowns:fan.original.unknowns,limitations:fan.original.limitations,profile:fan.original.profile},null,2)}</pre>
    </details>
  </>
}

export function SimulatedFanPicker({rows,ids,onToggle}:{rows:SimulatedFan[];ids:string[];onToggle:(id:string)=>void}) {
  return <fieldset><legend>模拟粉丝（最多三位）</legend>{rows.filter(f => f.status === 'active').map(f => <label className="checkbox-line" key={f.id}>
    <input type="checkbox" checked={ids.includes(f.id)} disabled={!ids.includes(f.id) && ids.length >= 3} onChange={() => onToggle(f.id)} />{f.editable.name}
  </label>)}</fieldset>
}
