import { useEffect, useState } from 'react'
import { panelTaskKey, useReaderSelection } from '../hooks/useReaderSelection'
import type { useSimulatedFans } from '../hooks/useSimulatedFans'
import type { ReaderSelectionLink } from '../readerSelection'
import type { PanelTask, Topic, TextInputAsset, SimulationCategory, SimulationPersonaOverrides } from '../types'
import {creatorNotes} from '../creatorNotes'
import {ReaderAvatar} from './ReaderAvatar'
import './TrialRoom.css'
import './SimulationHub.css'
import { SimulatedFanPicker } from './SimulatedFansPage'

interface Props {
  workspaceId: string
  positioning: string
  topics: Topic[]
  topic: Topic | null
  fans: ReturnType<typeof useSimulatedFans>
  running: boolean
  onSelect: (topic: Topic | null) => void
  onRun: (topic: Topic, recommendation: ReaderSelectionLink | undefined, task: PanelTask, personaOverrides?: SimulationPersonaOverrides) => void
  onAddFans: () => void
  profile?: TextInputAsset
  onRunNote?: (note: {sourceMaterialId:string;noteId:string}, recommendation:ReaderSelectionLink|undefined, task:PanelTask, personaOverrides?: SimulationPersonaOverrides)=>void
  onRunAccount?: (accountProfileId:string, recommendation:ReaderSelectionLink|undefined, task:PanelTask, personaOverrides?: SimulationPersonaOverrides)=>void
  category?: SimulationCategory
}

export function CreatorSimulationSetup(props: Props) {
  const {workspaceId, positioning, topic, topics, fans, running, onSelect, onRun, onAddFans} = props
  const [legacyTargetKind,setLegacyTargetKind]=useState<'topic'|'note'>('topic')
  const targetKind=props.category==='account'?'account':props.category==='published_note'?'note':props.category==='creation'?'topic':legacyTargetKind
  const [noteId,setNoteId]=useState('')
  const notes=creatorNotes(props.profile)
  const note=targetKind==='note'?notes.find(n=>n.noteId===noteId):null
  const noteRef=note&&props.profile?{sourceMaterialId:props.profile.id,noteId:note.noteId}:undefined
  const accountProfileId=targetKind==='account'?props.profile?.id:undefined
  let accountName=props.profile?.name||'当前账号'
  try {const name=JSON.parse(props.profile?.content||'{}').creator?.displayName;if(typeof name==='string'&&name.trim())accountName=name} catch { /* Keep the saved asset name. */ }
  const target=targetKind==='account'&&props.profile&&notes.length?{title:accountName,body:''}:targetKind==='topic'?topic:note?{title:note.title,body:note.desc}:null
  const scope = `${workspaceId}:${targetKind}:${accountProfileId || note?.noteId || topic?.id || ''}`
  const [personaOverrides,setPersonaOverrides]=useState<SimulationPersonaOverrides>({})
  const [readingMode, setReadingMode] = useState<PanelTask['readingMode']>('natural')
  const [discussionEnabled, setDiscussionEnabled] = useState(true)
  const [questions, setQuestions] = useState([''])
  const panelTask: PanelTask = {protocolVersion: 'panel/v1', readingMode, discussionEnabled,
    focusQuestions: readingMode === 'guided' ? questions.map(q => q.trim()) : []}
  const taskValid = readingMode === 'natural' || panelTask.focusQuestions.every(q => q.length > 0 && [...q].length <= 300)
  const revision = JSON.stringify([target?.title, target?.body, positioning, targetKind==='account'?props.profile?.updatedAt:null,
    fans.rows.map(f => [f.id, f.status, f.updatedAt])])
  const recommendation = useReaderSelection(workspaceId, targetKind==='topic'?topic?.id || '':'', revision, panelTask,noteRef,accountProfileId)
  const [adopted, setAdopted] = useState<(ReaderSelectionLink & {scope: string}) | null>(null)
  const [applyError, setApplyError] = useState('')
  const [applying, setApplying] = useState(false)
  const [manualChoice,setManualChoice]=useState(false)
  const [waited,setWaited]=useState(0)
  useEffect(()=>{setPersonaOverrides({});setManualChoice(false);setAdopted(null);setApplyError('')},[scope])
  useEffect(()=>{if(!recommendation.busy){setWaited(0);return}const started=Date.now();const timer=setInterval(()=>setWaited(Math.round((Date.now()-started)/1000)),1000);return()=>clearInterval(timer)},[recommendation.busy])
  const record = recommendation.record
  const proposals = record?.result?.proposedReaders || []
  const valid = !recommendation.busy && !recommendation.error && record?.freshness?.status === 'current'
    && ['completed', 'partially_completed'].includes(record.status) && proposals.length > 0
  const activeAdoption = adopted?.scope === scope ? adopted : null
  const adoptionReady = !activeAdoption || (valid && record?.id === activeAdoption.readerSelectionId
    && record.inputHash === activeAdoption.readerSelectionInputHash)
  function changeTask(change: () => void) {
    change(); setAdopted(null); setApplyError('')
  }
  function resetTarget() {
    setAdopted(null); setManualChoice(false); setPersonaOverrides({}); setApplyError('')
  }
  function clearRemovedOverrides(nextIds:string[]) {
    setPersonaOverrides(current=>Object.fromEntries(Object.entries(current).filter(([id])=>nextIds.includes(id))))
  }
  function editPersona(id:string,field:keyof SimulationPersonaOverrides[string],value:string) {
    setPersonaOverrides(current=>({...current,[id]:{...current[id],[field]:value}}))
  }

  async function apply() {
    setApplyError(''); setApplying(true)
    try {
      const checked = await recommendation.refresh()
      if (!checked || checked.freshness?.status !== 'current' || !checked.result?.proposedReaders.length
        || panelTaskKey(checked.inputSnapshot.panelTask) !== panelTaskKey(panelTask)) {
        setApplyError('推荐已变化或暂时无法核验，名单未改变。'); return
      }
      const ids = checked.result.proposedReaders.map(p => p.fanId)
      if (!fans.applySelection(ids)) { setApplyError('读者已不可用，请刷新名单后重试。'); return }
      clearRemovedOverrides(ids)
      setAdopted({scope, readerSelectionId: checked.id, readerSelectionInputHash: checked.inputHash})
      setManualChoice(false)
    } catch(e) {setApplyError(e instanceof Error?e.message:String(e))} finally { setApplying(false) }
  }
  const selectedFans=fans.ids.map(id=>fans.rows.find(f=>f.id===id)).filter(f=>!!f)
  const selectionDecided=Boolean(activeAdoption)||manualChoice
  const selectedOverrides=Object.entries(personaOverrides).filter(([id])=>fans.ids.includes(id))
  const rolesChanged=selectedOverrides.length>0
  const invalidPersonaIds=selectedOverrides.filter(([,fields])=>Object.entries(fields).some(([field,value])=>!value?.trim()||value.length>(field==='profile'?4000:2000))).map(([id])=>id)
  const changed=activeAdoption&&(JSON.stringify(proposals.map(p=>p.fanId))!==JSON.stringify(fans.ids)||rolesChanged)

  return <section className="creator-diagnosis-controls creator-simulation-setup" aria-label="模拟准备">
    <ol className="simulation-flow-steps" aria-label="试读步骤"><li>1 选择内容</li><li>2 推荐或手选读者</li><li>3 确认名单，进入讨论</li></ol>
    {!props.category&&!!props.profile&&<div className="simulation-target-kind"><button aria-pressed={targetKind==='topic'} disabled={running} onClick={()=>{setLegacyTargetKind('topic');resetTarget()}}>创作中的选题</button><button aria-pressed={targetKind==='note'} disabled={running} onClick={()=>{setLegacyTargetKind('note');resetTarget()}}>已发布的笔记</button></div>}
    {targetKind==='topic'?<label className="simulation-target">选题
      <select aria-label="模拟选题" value={topic?.id || ''} disabled={running || applying}
        onChange={e => {resetTarget();onSelect(topics.find(t => t.id === e.target.value) || null)}}>
        <option value="">选择选题</option>
        {topics.filter(t => t.status !== 'archived').map(t => <option key={t.id} value={t.id}>{t.title}</option>)}
      </select>
    </label>:targetKind==='note'?<label className="simulation-target">已导入笔记<select aria-label="试读历史笔记" value={noteId} disabled={running||applying} onChange={e=>{setNoteId(e.target.value);resetTarget()}}><option value="">选择一篇笔记</option>{notes.map(n=><option key={n.noteId} value={n.noteId}>{n.title} · {n.metrics.liked??'—'} 赞 / {n.metrics.collected??'—'} 收藏</option>)}</select></label>:<section className="simulation-account-preview" aria-label="待模拟账号">
      <h3>{accountName}</h3><p>{notes.length} 篇已导入笔记</p>
      {notes.length?<p>从整个账号的内容出发，聊聊为什么关注、期待什么，以及哪些方向值得持续讲。</p>:<p role="status">先导入账号笔记，再邀请读者讨论这个账号。</p>}
      {!!notes.length&&<p className="muted">本次最多选取 12 篇文字样本，较长正文会节选。</p>}
    </section>}
    {targetKind==='note'&&<p className="muted">这次复盘用于下一篇同类内容，不会修改已发布的原文。</p>}
    {targetKind!=='account'&&target&&<p className="muted">{target.body?'读者会看到标题和正文，逐条给出反应，你可以继续追问。':'只测标题吸引力与阅读期待，写出正文后可再做全文试读。'}</p>}
    {targetKind!=='account'&&target && <details className="simulation-target-preview"><summary>{target.body ? '查看待测正文' : '仅预演选题概念'}</summary>
      <p><strong>{target.title}</strong>{target.body && <><br />{target.body}</>}</p></details>}
    <fieldset className="panel-task-controls" disabled={running || applying}>
      <legend>{targetKind==='account'?'讨论方式':'试读方式'}</legend>
      <div className="panel-task-modes">
        <label><input type="radio" name="panel-reading-mode" checked={readingMode === 'natural'}
          onChange={() => changeTask(() => setReadingMode('natural'))} />{targetKind==='account'?'自由表达期待':target?.body?'自然全文试读':'自然试读'}</label>
        <label><input type="radio" name="panel-reading-mode" checked={readingMode === 'guided'}
          onChange={() => changeTask(() => setReadingMode('guided'))} />{targetKind==='account'?'围绕问题讨论':'定向试读'}</label>
      </div>
      {readingMode === 'guided' && <div className="panel-task-questions">
        {questions.map((question, index) => <label key={index}>重点问题 {index + 1}
          <textarea rows={2} maxLength={300} value={question} placeholder={targetKind==='account'?'例如：你最期待这个账号持续分享什么？':'例如：读完能否知道第一步怎么做？'}
            onChange={e => changeTask(() => setQuestions(current => current.map((q, i) => i === index ? e.target.value : q)))} />
        </label>)}
        <button type="button" onClick={() => changeTask(() => setQuestions(current => current.length === 1 ? [...current, ''] : current.slice(0, 1)))}>
          {questions.length === 1 ? '＋ 添加第二个问题' : '移除第二个问题'}</button>
        {!taskValid && <p role="status">请填写每个重点问题，最多两个，每个不超过 300 字。</p>}
      </div>}
      <label className="panel-task-discussion"><input type="checkbox" checked={discussionEnabled}
        onChange={e => changeTask(() => setDiscussionEnabled(e.target.checked))} />互相回应</label>
      <p className="muted">{discussionEnabled ? '先各自表达，再回应其他人的公开留言。' : '只做独立表达，省去互相回应。'}</p>
    </fieldset>
    <div className="reader-recommendation" aria-label="读者推荐">
      <div className="reader-recommendation-actions">
        <button type="button" disabled={!target || !taskValid || running || recommendation.busy || applying || !fans.rows.some(f=>f.status==='active')}
          onClick={() => {setApplyError('');setManualChoice(false);setAdopted(null); void recommendation.recommend(Math.max(1, fans.slots.length))}}>
          {recommendation.busy ? '正在读取推荐…' : record ? '重新推荐读者' : '推荐读者'}</button>
        {recommendation.error && <button type="button" disabled={!taskValid || running || applying}
          onClick={() => void (recommendation.hasReceipt ? recommendation.refresh() : recommendation.recommend(fans.slots.length))}>
          {recommendation.hasReceipt ? '重试读取' : '重试原请求'}</button>}
      </div>
      {recommendation.busy&&<p className="trial-progress" role="status">正在比较读者的需求与当前内容 · {waited} 秒</p>}
      <p className="muted">最多推荐 {fans.slots.length} 位；只有一位相关，也可以直接开始。</p>
      {recommendation.error && <p role="alert">{recommendation.error}</p>}
      {record?.freshness?.status === 'stale' && <p role="status">内容或读者已变化，请重新推荐，或继续手动选择。</p>}
      {record?.freshness?.status === 'unavailable' && <p role="status">这份推荐的来源暂不可核验，仍可手动选择。</p>}
      {record?.status === 'failed' && <p role="status">{record.errorCode === 'input_too_large' ? '资料较长，请先手动选择读者。' : '本次推荐未完成，可重新推荐或手动选择。'}</p>}
      {record?.status === 'partially_completed' && <p role="status">部分完成，已保留有效读者。</p>}
      {!!proposals.length && <ul>{proposals.map(p => <li key={p.fanId}>
        <div className="reader-card-heading"><ReaderAvatar id={(() => {const fan=fans.rows.find(f=>f.id===p.fanId);return fan?`${fan.sourceAnalysisId}:${fan.sourceGroupId}`:p.fanId})()} name={record?.inputSnapshot.candidates.find(f=>f.id===p.fanId)?.name||'读者'}/><strong>{record?.inputSnapshot.candidates.find(f => f.id === p.fanId)?.name || '已保存读者'}</strong></div>
        <p>{p.fitReason}</p><details><summary>试读角度</summary>{p.contribution}</details>
      </li>)}</ul>}
      {record?.status === 'completed' && !proposals.length && <p role="status">{record.result?.unmatchedReason || '暂未找到合适读者。'}</p>}
      {!!proposals.length && <button type="button" disabled={!valid || running || applying} onClick={() => void apply()}>使用这组</button>}
      {applyError && <p role="alert">{applyError}</p>}
      {activeAdoption && <div className="reader-recommendation-actions"><span role="status">{adoptionReady ? '已采用推荐，可继续调整名单。' : '已采用的推荐需要重新核验。'}</span>
        <button type="button" disabled={running} onClick={() => {setAdopted(null);setManualChoice(true)}}>仅按当前手选名单继续</button></div>}
      {!!proposals.length&&!activeAdoption&&!manualChoice&&<p role="status">推荐还未采用。点击“使用这组”，或明确选择下方的手选名单。</p>}
      {!activeAdoption&&<button disabled={running||applying} onClick={()=>setManualChoice(true)}>{manualChoice?'正在使用手选名单':'我来选择读者'}</button>}
    </div>
    {fans.error && <p role="alert">{fans.error}</p>}
    <fieldset className="simulation-reader-controls" disabled={running || applying}>
      <SimulatedFanPicker rows={fans.rows} slots={fans.slots} onSlotChange={(index,id)=>{fans.setSlot(index,id);clearRemovedOverrides(fans.slots.map((value,i)=>i===index?id:value));if(!activeAdoption)setManualChoice(true)}} onAddSlot={fans.addSlot} onRemoveSlot={index=>{fans.removeSlot(index);clearRemovedOverrides(fans.slots.filter((_,i)=>i!==index))}} />
    </fieldset>
    {!fans.rows.some(r => r.status === 'active') && <button type="button" onClick={onAddFans}>从受众分析添加模拟粉丝</button>}
    <section className="simulation-final-readers" aria-label="确认实际参与者"><h3>本次实际参与 · {fans.ids.length} 位</h3>
      <p className="muted">{activeAdoption?(changed?'已采用推荐，并调整了名单或本次角色':'使用推荐名单'):manualChoice?`使用你的手选名单${rolesChanged?' · 本次角色已调整':''}`:'尚未确认名单'}</p>
      <ul>{selectedFans.map(f=><li key={f.id}><ReaderAvatar id={`${f.sourceAnalysisId}:${f.sourceGroupId}`} name={f.editable.name} size={28}/>{f.editable.name}</li>)}</ul>
      {!!selectedFans.length&&<p className="muted">需要换个观察角度？可展开调整本次角色，不影响读者库里的长期画像。</p>}
      {selectedFans.map(f=><details className="simulation-role-editor" key={f.id}>
        <summary>调整 {f.editable.name} 的本次角色{invalidPersonaIds.includes(f.id)?' · 请补全':personaOverrides[f.id]?' · 已调整':''}</summary>
        <fieldset disabled={running||applying}>
          <label>本次视角<textarea aria-label={`${f.editable.name}的本次视角`} maxLength={4000} rows={2} value={personaOverrides[f.id]?.profile??f.editable.profile} onChange={e=>editPersona(f.id,'profile',e.target.value)}/></label>
          <label>具体关切<textarea aria-label={`${f.editable.name}的本次关切`} maxLength={2000} rows={2} value={personaOverrides[f.id]?.coreConcern??f.editable.coreConcern} onChange={e=>editPersona(f.id,'coreConcern',e.target.value)}/></label>
          <label>表达方式<textarea aria-label={`${f.editable.name}的本次表达`} maxLength={2000} rows={2} value={personaOverrides[f.id]?.expressionStyle??f.editable.expressionStyle} onChange={e=>editPersona(f.id,'expressionStyle',e.target.value)}/></label>
          {invalidPersonaIds.includes(f.id)&&<p role="status">请补全调整后的角色设定，或恢复已保存画像；本次视角最多 4000 字，关切和表达各最多 2000 字。</p>}
          {personaOverrides[f.id]&&<button className="simulation-role-reset" type="button" onClick={()=>setPersonaOverrides(current=>Object.fromEntries(Object.entries(current).filter(([id])=>id!==f.id)))}>恢复已保存画像</button>}
        </fieldset>
      </details>)}
      {!fans.ids.length&&<p>先采用推荐，或在上面选择至少一位读者。</p>}
      {!!invalidPersonaIds.length&&<p role="status">还有 {invalidPersonaIds.length} 位读者的本次设定需要补全，完成或恢复后即可开始。</p>}
    </section>
    <button className="primary" disabled={running || applying || recommendation.busy || !taskValid || !!invalidPersonaIds.length || !fans.ids.length || !target || !adoptionReady || !selectionDecided}
      onClick={() => {const link=activeAdoption ? {
        readerSelectionId: activeAdoption.readerSelectionId,
        readerSelectionInputHash: activeAdoption.readerSelectionInputHash,
      } : undefined;
        const overrides=Object.fromEntries(Object.entries(personaOverrides).filter(([id])=>fans.ids.includes(id)))
        const extra: [SimulationPersonaOverrides?]=Object.keys(overrides).length?[overrides]:[]
        if(accountProfileId)props.onRunAccount?.(accountProfileId,link,panelTask,...extra)
        else if(noteRef)props.onRunNote?.(noteRef,link,panelTask,...extra)
        else if(topic)onRun(topic,link,panelTask,...extra)
      }}>开始模拟</button>
  </section>
}
