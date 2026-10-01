import { useState } from 'react'
import { simulatedFanApi } from '../api'
import type { FanDefinition, FanVoiceTemplate, SimulatedFan } from '../types'
import { CreatorDialog } from './CreatorDialog'

export function SimulatedFansPage({rows, error, onRefresh, onAnalyze}: {
  rows:SimulatedFan[]; error:string; onRefresh:()=>Promise<void>; onAnalyze:()=>void;
}) {
  const [selectedId,setSelectedId] = useState('')
  const selected = rows.find(r => r.id === selectedId)
  return <div className="workspace-page">
    <section className="history-list"><div className="panel-title">模拟粉丝</div>
      {error && <p role="alert">{error}</p>}
      {!rows.length && <><p>先分析受众，生成模拟粉丝。</p><button onClick={onAnalyze}>分析受众</button></>}
      {rows.map(f => <button key={f.id} className={`run-row ${f.id === selectedId ? 'active' : ''}`} onClick={() => setSelectedId(f.id)}><span>{f.editable.name}</span><small>{f.original.origin === 'curated_preset' ? '预置整理 · ' : f.original.origin === 'voice_template' ? '预设声音 · ' : ''}{f.status === 'archived' ? '已归档' : '可用于模拟'}</small></button>)}
    </section>
    <section className="history-detail">{selected ? <FanEditor key={selected.id} fan={selected} onRefresh={onRefresh} onCreated={async id => {await onRefresh();setSelectedId(id)}} /> : <p>选择一位模拟粉丝查看档案。</p>}</section>
  </div>
}

function FanEditor({fan,onRefresh,onCreated}:{fan:SimulatedFan;onRefresh:()=>Promise<void>;onCreated:(id:string)=>Promise<void>}) {
  const [saved,setSaved] = useState(fan)
  const [draft,setDraft] = useState(fan.editable)
  const [busy,setBusy] = useState(false)
  const [error,setError] = useState('')
  const [voices,setVoices] = useState<FanVoiceTemplate[] | null>(null)
  const [chosenVoices,setChosenVoices] = useState<string[]>([])
  const [voiceBusy,setVoiceBusy] = useState(false)
  const dirty = JSON.stringify(draft) !== JSON.stringify(saved.editable)
  async function save(status:SimulatedFan['status']) {
    setBusy(true); setError('')
    try {const updated = await simulatedFanApi.update(fan.id,{...draft,status,expectedUpdatedAt:saved.updatedAt});setSaved(updated);await onRefresh()}
    catch(e) {setError(String(e))} finally {setBusy(false)}
  }
  async function openVoices() {
    setVoiceBusy(true);setError('')
    try {const options = await simulatedFanApi.voices();setVoices(options);setChosenVoices(options.map(option => option.id))}
    catch(e) {setError(String(e))} finally {setVoiceBusy(false)}
  }
  async function addVoices() {
    setVoiceBusy(true);setError('')
    try {
      const added = await simulatedFanApi.createVariants(fan.id,chosenVoices)
      await onCreated(added[0].id)
      setVoices(null)
    } catch(e) {setError(String(e))} finally {setVoiceBusy(false)}
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
      <button disabled={busy || voiceBusy || dirty || saved.status !== 'active'} onClick={() => void openVoices()}>{voiceBusy && !voices ? '加载中…' : '添加不同声音'}</button>
    </div>{error && <p role="alert">{error}</p>}
    {voices && <CreatorDialog title="添加不同声音" onClose={() => !voiceBusy && setVoices(null)}>
      <p>从这位粉丝的关注点出发，组合不同性格与表达方式。已有角色不会被覆盖。</p>
      <div className="fan-voice-grid">{voices.map(voice => <label key={voice.id} className="fan-voice-option">
        <input type="checkbox" checked={chosenVoices.includes(voice.id)} disabled={voiceBusy} onChange={() => setChosenVoices(current => current.includes(voice.id) ? current.filter(id => id !== voice.id) : [...current,voice.id])} />
        <span><strong>{voice.name}</strong><small>{voice.outlook} {voice.expressionStyle}</small></span>
      </label>)}</div>
      {error && <p role="alert">{error}</p>}
      <button className="primary" disabled={voiceBusy || !chosenVoices.length} onClick={() => void addVoices()}>{voiceBusy ? '添加中…' : `加入 ${chosenVoices.length} 位`}</button>
    </CreatorDialog>}
    <details><summary>原始依据与未知项</summary><p>来源分析：{fan.sourceAnalysisId}</p>
      <pre className="json-preview">{JSON.stringify({evidenceRefs:fan.original.evidenceRefs,unknowns:fan.original.unknowns,limitations:fan.original.limitations,profile:fan.original.profile},null,2)}</pre>
    </details>
  </>
}

export function SimulatedFanPicker({rows,slots,onSlotChange,onAddSlot,onRemoveSlot}:{
  rows:SimulatedFan[]; slots:string[]; onSlotChange:(index:number,id:string)=>void;
  onAddSlot:()=>void; onRemoveSlot:(index:number)=>void;
}) {
  const active = rows.filter(f => f.status === 'active')
  return <fieldset className="simulated-fan-picker"><legend>模拟粉丝</legend>
    {slots.map((id,index) => <div className="simulated-fan-slot" key={index}>
      <label htmlFor={`simulated-fan-slot-${index}`}>第 {index + 1} 位</label>
      <select id={`simulated-fan-slot-${index}`} aria-label={`第 ${index + 1} 位模拟粉丝`} value={id} onChange={event => onSlotChange(index,event.target.value)}>
        <option value="">选择模拟粉丝</option>
        {active.map(f => <option key={f.id} value={f.id} disabled={f.id !== id && slots.includes(f.id)}>{f.editable.name}</option>)}
      </select>
      {index >= 3 && <button type="button" aria-label={`移除第 ${index + 1} 位`} onClick={() => onRemoveSlot(index)}>移除</button>}
    </div>)}
    <button type="button" className="simulated-fan-add" onClick={onAddSlot}>＋ 新增</button>
  </fieldset>
}
