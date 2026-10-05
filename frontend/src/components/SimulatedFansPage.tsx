import { Fragment, useEffect, useId, useImperativeHandle, useRef, useState, type Ref } from 'react'
import { simulatedFanApi } from '../api'
import type { FanDefinition, FanVoiceTemplate, SimulatedFan } from '../types'
import { CreatorDialog } from './CreatorDialog'

type FanEditorHandle = { requestSwitch: (id: string) => void }

export function SimulatedFansPage({rows, error, onRefresh, onAnalyze}: {
  rows:SimulatedFan[]; error:string; onRefresh:()=>Promise<void>; onAnalyze:()=>void;
}) {
  const [selectedId,setSelectedId] = useState('')
  const [editorBusy,setEditorBusy] = useState(false)
  const editor = useRef<FanEditorHandle>(null)
  const selected = rows.find(r => r.id === selectedId)
  return <div className="workspace-page">
    <section className="history-list"><div className="panel-title">模拟粉丝</div>
      {error && <p role="alert">{error}</p>}
      {!rows.length && <><p>先分析受众，生成模拟粉丝。</p><button onClick={onAnalyze}>分析受众</button></>}
      {rows.map(f => <button key={f.id} disabled={editorBusy} className={`run-row ${f.id === selectedId ? 'active' : ''}`} onClick={() => editor.current ? editor.current.requestSwitch(f.id) : setSelectedId(f.id)}><span>{f.editable.name}</span><small>{f.original.origin === 'curated_preset' ? '预置整理 · ' : f.original.origin === 'voice_template' ? '预设声音 · ' : ''}{f.status === 'archived' ? '已归档' : '可用于模拟'}</small></button>)}
    </section>
    <section className="history-detail">{selected ? <FanEditor key={selected.id} ref={editor} fan={selected} onBusyChange={setEditorBusy} onSelect={setSelectedId} onRefresh={onRefresh} /> : <p>选择一位模拟粉丝查看档案。</p>}</section>
  </div>
}

function FanEditor({fan,onRefresh,onSelect,onBusyChange,ref}:{fan:SimulatedFan;onRefresh:()=>Promise<void>;onSelect:(id:string)=>void;onBusyChange:(busy:boolean)=>void;ref:Ref<FanEditorHandle>}) {
  const [saved,setSaved] = useState(fan)
  const [draft,setDraft] = useState(fan.editable)
  const [interestsText,setInterestsText] = useState(fan.editable.interests?.join('、') || '')
  const [busy,setBusy] = useState(false)
  const [refreshing,setRefreshing] = useState(false)
  const [refreshError,setRefreshError] = useState('')
  const [error,setError] = useState('')
  const [voices,setVoices] = useState<FanVoiceTemplate[] | null>(null)
  const [chosenVoices,setChosenVoices] = useState<string[]>([])
  const [voiceBusy,setVoiceBusy] = useState(false)
  const [voiceError,setVoiceError] = useState('')
  const [createdVoices,setCreatedVoices] = useState<SimulatedFan[] | null>(null)
  const voiceTrigger = useRef<HTMLButtonElement>(null)
  const voiceDescriptionPrefix = useId()
  const [pendingId,setPendingId] = useState<string | null>(null)
  const interestsUnchanged = interestsText === (draft.interests?.join('、') || '')
  const interests = interestsUnchanged ? (draft.interests || [])
    : interestsText.split(/[,，、]/).map(value => value.trim()).filter(Boolean)
  const interestsError = interests.length > 6 ? '兴趣领域最多 6 项。'
    : interests.some(value => Array.from(value).length > 30) ? '每项兴趣领域最多 30 字。' : ''
  const edited = draft.interests !== undefined || interestsText.trim() ? {...draft,interests} : draft
  const dirty = JSON.stringify(edited) !== JSON.stringify(saved.editable)
  const canSave = !interestsError && Boolean(draft.name.trim() && draft.profile.trim())
  useEffect(() => {
    onBusyChange(busy || voiceBusy)
    return () => onBusyChange(false)
  }, [busy, voiceBusy, onBusyChange])
  useImperativeHandle(ref, () => ({requestSwitch(id) {
    if (id === fan.id || busy || voiceBusy) return
    if (dirty || refreshError) {setPendingId(id); setError('')}
    else onSelect(id)
  }}))
  async function refreshList() {
    setRefreshing(true)
    try {await onRefresh(); setRefreshError(''); return true}
    catch(e) {setRefreshError(String(e)); return false}
    finally {setRefreshing(false)}
  }
  async function retryRefresh(targetId: string | null = null) {
    if (busy || voiceBusy) return
    setBusy(true)
    try {if (await refreshList()) {if (targetId !== null) onSelect(targetId)}}
    finally {setBusy(false)}
  }
  async function save(status:SimulatedFan['status']) {
    if (busy || voiceBusy || !canSave) return false
    setBusy(true); setError('')
    try {
      const updated = await simulatedFanApi.update(fan.id,{...edited,status,expectedUpdatedAt:saved.updatedAt})
      setSaved(updated);setDraft(updated.editable);setInterestsText(updated.editable.interests?.join('、') || '')
      return await refreshList()
    }
    catch(e) {setError(String(e)); return false} finally {setBusy(false)}
  }
  async function openVoices() {
    if (busy || voiceBusy) return
    if (createdVoices) {setVoices([]);return}
    setVoiceBusy(true);setVoiceError('')
    try {const options = await simulatedFanApi.voices();setVoices(options);setChosenVoices(options.map(option => option.id))}
    catch(e) {setVoiceError(String(e))} finally {setVoiceBusy(false)}
  }
  async function refreshCreatedVoices(added:SimulatedFan[]) {
    try {
      await onRefresh()
      setVoices(null);setCreatedVoices(null);setVoiceError('')
      // Closing the recovery dialog may allow further edits to the source fan.
      if (!dirty) onSelect(added[0].id)
    } catch {
      setVoiceError('角色已加入，列表暂未刷新，请重试刷新。')
    }
  }
  async function retryCreatedVoices() {
    if (busy || voiceBusy || !createdVoices) return
    setVoiceBusy(true)
    try {await refreshCreatedVoices(createdVoices)} finally {setVoiceBusy(false)}
  }
  async function addVoices() {
    if (busy || voiceBusy || createdVoices || !chosenVoices.length) return
    setVoiceBusy(true);setVoiceError('')
    try {
      const added = await simulatedFanApi.createVariants(fan.id,chosenVoices)
      if (!added.length) {setVoiceError('未返回可用角色，请刷新列表后检查。');return}
      setCreatedVoices(added)
      await refreshCreatedVoices(added)
    } catch(e) {setVoiceError(String(e))} finally {setVoiceBusy(false)}
  }
  const fields: [Exclude<keyof FanDefinition,'interests'>,string][] = [['name','名称'],['profile','阅读视角'],['coreConcern','具体需求'],['contentPreference','内容偏好'],['expressionStyle','表达习惯']]
  return <><h2>{saved.editable.name}</h2><p className="muted">模拟角色，不代表某位真实粉丝。编辑内容属于人工设定。</p>
    {fan.original.origin === 'curated_preset' && <p className="muted">依据已保存评论预置整理，非模型接口分析；角色偏好和表达习惯是模拟假设。</p>}
    {fields.map(([key,label]) => <Fragment key={key}><label>{label}{key === 'name'
      ? <input aria-label={label} disabled={busy || voiceBusy} value={draft[key]} onChange={e => setDraft({...draft,[key]:e.target.value})} />
      : <textarea aria-label={label} disabled={busy || voiceBusy} rows={3} value={draft[key]} onChange={e => setDraft({...draft,[key]:e.target.value})} />}</label>
      {key === 'profile' && <><label>兴趣领域<input disabled={busy || voiceBusy} value={interestsText} placeholder="如：留学、职业发展、个人成长" aria-invalid={Boolean(interestsError)} aria-describedby={interestsError ? 'fan-interests-error' : undefined} onChange={e => setInterestsText(e.target.value)} /></label>
        {interestsError && <p id="fan-interests-error" role="alert">{interestsError}</p>}</>}
    </Fragment>)}
    <div className="save-row fan-editor-actions"><button disabled={busy || voiceBusy || Boolean(interestsError) || !dirty || !draft.name.trim() || !draft.profile.trim()} onClick={() => void save(saved.status)}>保存修改</button>
      <span>{refreshing ? '刷新列表中…' : busy ? '保存中…' : error ? '保存失败' : dirty ? '有未保存修改' : '已保存'}</span>
      <button disabled={busy || voiceBusy || dirty || Boolean(refreshError)} onClick={() => void save(saved.status === 'active' ? 'archived' : 'active')}>{saved.status === 'active' ? '归档' : '恢复'}</button>
      <button ref={voiceTrigger} disabled={busy || voiceBusy || (!createdVoices && (dirty || Boolean(refreshError) || saved.status !== 'active'))} onClick={() => void openVoices()}>{createdVoices ? '查看加入结果' : voiceBusy && !voices ? '加载中…' : '添加不同声音'}</button>
    </div>{error && <p role="alert">{error}</p>}
    {!voices && (createdVoices ? <div role="status">
      <p>已加入 {createdVoices.length} 位角色，列表暂未刷新。</p>
    </div> : voiceError && <p role="alert">{voiceError}</p>)}
    {refreshError && pendingId === null && <div role="status">
      <p>上次修改已保存，列表暂未刷新。{dirty && '后续编辑尚未保存。'}</p>
      <button type="button" disabled={busy || voiceBusy} onClick={() => void retryRefresh()}>重试刷新</button>
    </div>}
    {pendingId !== null && <CreatorDialog title={refreshError && !dirty ? '修改已保存' : '保留这次修改？'} onClose={() => !busy && setPendingId(null)}>
      <p>{refreshError ? `上次修改已保存，列表暂未刷新。${dirty ? '后续编辑尚未保存。' : '刷新成功后继续切换。'}` : '当前粉丝有未保存的修改。'}</p>
      {!canSave && <p>请先返回，检查名称、阅读视角和兴趣领域。</p>}
      {error && <p role="alert">{error}</p>}
      <div className="save-row fan-switch-actions">
        <button type="button" disabled={busy} onClick={() => setPendingId(null)}>继续编辑</button>
        {!refreshError && <button type="button" disabled={busy} onClick={() => onSelect(pendingId)}>放弃修改并切换</button>}
        {refreshError && !dirty
          ? <button type="button" className="primary" disabled={busy} onClick={() => void retryRefresh(pendingId)}>{refreshing ? '刷新中…' : '重试刷新并切换'}</button>
          : <button type="button" className="primary" disabled={busy || !canSave} onClick={async () => {if (await save(saved.status)) onSelect(pendingId)}}>{refreshing ? '刷新中…' : busy ? '保存中…' : '保存并切换'}</button>}
      </div>
    </CreatorDialog>}
    {voices && <CreatorDialog className="fan-voice-dialog" title={createdVoices ? '角色已加入' : '添加不同声音'} returnFocusRef={voiceTrigger} onClose={() => !voiceBusy && setVoices(null)}>
      {createdVoices ? <>
        <p>已加入 {createdVoices.length} 位角色，无需再次创建。</p>
        <ul className="fan-created-list">{createdVoices.map(created => <li key={created.id}>{created.editable.name}</li>)}</ul>
        {voiceError && <p role="status">{voiceError}</p>}
        <button type="button" className="primary" disabled={voiceBusy} onClick={() => void retryCreatedVoices()}>{voiceBusy ? '刷新中…' : '重试刷新'}</button>
      </> : <>
      <p>从这位粉丝的关注点出发，组合不同性格与表达方式。已有角色不会被覆盖。</p>
      <div className="fan-voice-grid">{voices.map(voice => <label key={voice.id} className={`fan-voice-option${chosenVoices.includes(voice.id) ? ' selected' : ''}`}>
        <input type="checkbox" aria-label={voice.name} aria-describedby={`${voiceDescriptionPrefix}-${voice.id}`} checked={chosenVoices.includes(voice.id)} disabled={voiceBusy} onChange={() => setChosenVoices(current => current.includes(voice.id) ? current.filter(id => id !== voice.id) : [...current,voice.id])} />
        <span><strong>{voice.name}</strong><small id={`${voiceDescriptionPrefix}-${voice.id}`}>{voice.decisionStyle || voice.outlook}</small><small className="fan-voice-expression">{voice.expressionStyle}</small></span>
      </label>)}</div>
      {voiceError && <p role="alert">{voiceError}</p>}
      <button className="primary" disabled={voiceBusy || !chosenVoices.length} onClick={() => void addVoices()}>{voiceBusy ? '添加中…' : `加入 ${chosenVoices.length} 位`}</button>
      </>}
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
    {slots.map((id,index) => {
      const selected = active.find(f => f.id === id)
      return <div className="simulated-fan-slot" key={index}>
      <div className="simulated-fan-slot-controls">
      <label htmlFor={`simulated-fan-slot-${index}`}>第 {index + 1} 位</label>
      <select id={`simulated-fan-slot-${index}`} aria-label={`第 ${index + 1} 位模拟粉丝`} value={id} onChange={event => onSlotChange(index,event.target.value)}>
        <option value="">选择模拟粉丝</option>
        {id && !selected && <option value={id} disabled>该粉丝已不可用，请重新选择</option>}
        {active.map(f => <option key={f.id} value={f.id} disabled={f.id !== id && slots.includes(f.id)}>{f.editable.name}</option>)}
      </select>
      {index >= 3 && <button type="button" aria-label={`移除第 ${index + 1} 位`} onClick={() => onRemoveSlot(index)}>移除</button>}
      </div>
      {selected && <FanPreview key={selected.id} fan={selected.editable} />}
    </div>})}
    <button type="button" className="simulated-fan-add" onClick={onAddSlot}>＋ 新增</button>
  </fieldset>
}

function FanPreview({fan}:{fan:FanDefinition}) {
  const [expanded,setExpanded] = useState(false)
  return <div className={`simulated-fan-preview${expanded ? ' expanded' : ''}`} role="group" aria-label={`${fan.name}的画像预览`}>
    {Boolean(fan.interests?.length) && <p className="simulated-fan-interests">{fan.interests?.join(' · ')}</p>}
    <dl>
      {fan.coreConcern && <><dt>需要</dt><dd>{fan.coreConcern}</dd></>}
      {fan.profile && <><dt>特点</dt><dd>{fan.profile}</dd></>}
      {expanded && <>
        {fan.contentPreference && <><dt>偏好</dt><dd>{fan.contentPreference}</dd></>}
        {fan.expressionStyle && <><dt>表达</dt><dd>{fan.expressionStyle}</dd></>}
      </>}
    </dl>
    <button type="button" aria-expanded={expanded} onClick={() => setExpanded(value => !value)}>{expanded ? '收起画像' : '展开画像'}</button>
  </div>
}
