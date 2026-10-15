import { useEffect, useState } from 'react'
import { panelTaskKey, useReaderSelection } from '../hooks/useReaderSelection'
import type { useSimulatedFans } from '../hooks/useSimulatedFans'
import type { ReaderSelectionLink } from '../readerSelection'
import type { AccountNoteSelection, PanelTask, Topic, TextInputAsset, SimulationCategory, SimulationPersonaOverrides, MediaAsset } from '../types'
import {creatorNotes, type AnalysisScope} from '../creatorNotes'
import {ReaderAvatar} from './ReaderAvatar'
import {InfoHint} from './InfoHint'
import './TrialRoom.css'
import './SimulationHub.css'
import { SimulatedFanPicker } from './SimulatedFansPage'
import { CreatorNoteSelectionDialog } from './CreatorNoteSelectionDialog'

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
  mediaAssets?: MediaAsset[]
  onRunNote?: (note: {sourceMaterialId:string;noteId:string}, recommendation:ReaderSelectionLink|undefined, task:PanelTask, personaOverrides?: SimulationPersonaOverrides)=>void
  onRunAccount?: (selection:AccountNoteSelection, recommendation:ReaderSelectionLink|undefined, task:PanelTask, personaOverrides?: SimulationPersonaOverrides)=>void
  category?: SimulationCategory
}

export function CreatorSimulationSetup(props: Props) {
  const {workspaceId, positioning, topic, topics, fans, running, onSelect, onRun, onAddFans} = props
  const [legacyTargetKind,setLegacyTargetKind]=useState<'topic'|'note'>('topic')
  const targetKind=props.category==='account'?'account':props.category==='published_note'?'note':props.category==='creation'?'topic':legacyTargetKind
  const [noteId,setNoteId]=useState('')
  const [notePickerOpen,setNotePickerOpen]=useState(false)
  const [accountScope,setAccountScope]=useState<AnalysisScope>('recent_10')
  const [accountSelection,setAccountSelection]=useState<(AccountNoteSelection&{workspaceId:string})|null>(null)
  const notes=creatorNotes(props.profile)
  const note=targetKind==='note'?notes.find(n=>n.noteId===noteId):null
  const noteRef=note&&props.profile?{sourceMaterialId:props.profile.id,noteId:note.noteId}:undefined
  const confirmedAccountSelection=accountSelection?.workspaceId===workspaceId&&accountSelection.sourceMaterialId===props.profile?.id?accountSelection:null
  const selectedAccountNotes=confirmedAccountSelection?.selectedNoteIds.map(id=>notes.find(note=>note.noteId===id)).filter(note=>!!note)||[]
  const staleAccountSelection=!!confirmedAccountSelection&&selectedAccountNotes.length!==confirmedAccountSelection.selectedNoteIds.length
  const accountNoteSelection=targetKind==='account'&&confirmedAccountSelection&&!staleAccountSelection
    ?{sourceMaterialId:confirmedAccountSelection.sourceMaterialId,selectedNoteIds:confirmedAccountSelection.selectedNoteIds}:undefined
  let accountName=props.profile?.name||'当前账号'
  try {const name=JSON.parse(props.profile?.content||'{}').creator?.displayName;if(typeof name==='string'&&name.trim())accountName=name} catch { /* Keep the saved asset name. */ }
  const target=targetKind==='account'&&accountNoteSelection&&selectedAccountNotes.length?{title:accountName,body:''}:targetKind==='topic'?topic:note?{title:note.title,body:note.desc}:null
  const scope = JSON.stringify([workspaceId,targetKind,targetKind==='account'
    ?[props.profile?.id,confirmedAccountSelection?.selectedNoteIds]
    :targetKind==='note'?[props.profile?.id,note?.noteId]:topic?.id])
  const [personaOverrides,setPersonaOverrides]=useState<SimulationPersonaOverrides>({})
  const [readingMode, setReadingMode] = useState<PanelTask['readingMode']>('natural')
  const [discussionEnabled, setDiscussionEnabled] = useState(true)
  const [questions, setQuestions] = useState([''])
  const panelTask: PanelTask = {protocolVersion: 'panel/v1', readingMode, discussionEnabled,
    focusQuestions: readingMode === 'guided' ? questions.map(q => q.trim()) : []}
  const taskValid = readingMode === 'natural' || panelTask.focusQuestions.every(q => q.length > 0 && [...q].length <= 300)
  const revision = JSON.stringify([target?.title, target?.body, positioning, targetKind==='account'?selectedAccountNotes.map(note=>[note.noteId,note.title,note.desc]):null,
    fans.rows.map(f => [f.id, f.status, f.updatedAt])])
  const recommendation = useReaderSelection(workspaceId, targetKind==='topic'?topic?.id || '':'', revision, panelTask,noteRef,undefined,accountNoteSelection)
  const [adopted, setAdopted] = useState<(ReaderSelectionLink & {scope: string}) | null>(null)
  const [applyError, setApplyError] = useState('')
  const [applying, setApplying] = useState(false)
  const [manualChoice,setManualChoice]=useState(false)
  const [waited,setWaited]=useState(0)
  useEffect(()=>{setNoteId('');setNotePickerOpen(false);setAccountScope('recent_10');setAccountSelection(null)},[workspaceId,props.profile?.id])
  useEffect(()=>{setNotePickerOpen(false)},[targetKind,running])
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
    if(!activeAdoption)setManualChoice(true)
  }

  async function apply() {
    if(!target)return
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
  const checkingAdoption=!!activeAdoption&&recommendation.busy
  const startLabel=checkingAdoption?'正在核验推荐…':activeAdoption&&!adoptionReady?'按当前名单开始':!selectionDecided&&fans.ids.length&&target?'确认名单并开始':'开始模拟'
  const hasActiveFans=fans.rows.some(f=>f.status==='active')
  const proposalCards=<ul>{proposals.map(p => <li key={p.fanId}>
    <div className="reader-card-heading"><ReaderAvatar id={(() => {const fan=fans.rows.find(f=>f.id===p.fanId);return fan?`${fan.sourceAnalysisId}:${fan.sourceGroupId}`:p.fanId})()} name={record?.inputSnapshot.candidates.find(f=>f.id===p.fanId)?.name||'读者'}/><strong>{record?.inputSnapshot.candidates.find(f => f.id === p.fanId)?.name || '已保存读者'}</strong></div>
    <p>{p.fitReason}</p><p className="muted">{p.contribution}</p>
  </li>)}</ul>

  return <section className="creator-diagnosis-controls creator-simulation-setup" aria-label="模拟准备">
    {!props.category&&!!props.profile&&<div className="simulation-target-kind"><button aria-pressed={targetKind==='topic'} disabled={running||applying} onClick={()=>{setLegacyTargetKind('topic');resetTarget()}}>创作中的选题</button><button aria-pressed={targetKind==='note'} disabled={running||applying} onClick={()=>{setLegacyTargetKind('note');resetTarget()}}>已发布的笔记</button></div>}
    {targetKind==='topic'?<label className="simulation-target">选题
      <select aria-label="模拟选题" value={topic?.id || ''} disabled={running || applying}
        onChange={e => {resetTarget();onSelect(topics.find(t => t.id === e.target.value) || null)}}>
        <option value="">选择选题</option>
        {topics.filter(t => t.status !== 'archived').map(t => <option key={t.id} value={t.id}>{t.title}</option>)}
      </select>
    </label>:targetKind==='note'?<section className="simulation-note-target" aria-label="待试读笔记"><div><h3>{note?.title||'选择一篇已发布笔记'}</h3>{note&&<p className="muted">{note.metrics.liked??'—'} 赞 · {note.metrics.collected??'—'} 收藏</p>}</div><button type="button" disabled={running||applying||!notes.length} onClick={()=>setNotePickerOpen(true)}>{note?'更换笔记':'选择笔记'}</button>{!notes.length&&<p role="status">先导入账号笔记，再选择试读内容。</p>}</section>:<section className="simulation-account-preview" aria-label="待模拟账号">
      <div className="simulation-account-range"><div><h3>{accountName}</h3><p>{confirmedAccountSelection?`已选 ${selectedAccountNotes.length} / ${notes.length} 篇笔记`:`${notes.length} 篇已导入笔记 · 尚未选择`}
        {!!notes.length&&<InfoHint label="账号笔记范围说明">只使用你确认的笔记，每篇都会参与；较长文字每篇最多节选 1200 字。</InfoHint>}</p></div>
        <button type="button" disabled={running||applying||!notes.length} onClick={()=>setNotePickerOpen(true)}>{confirmedAccountSelection?'更改笔记':'选择笔记'}</button></div>
      {!notes.length&&<p role="status">先导入账号笔记，再邀请读者讨论这个账号。</p>}
      {staleAccountSelection&&<p role="alert">已选笔记有变动，范围已过期，请重新选择。</p>}
    </section>}
    {notePickerOpen&&targetKind==='note'&&!running&&!applying&&<CreatorNoteSelectionDialog notes={notes} mediaAssets={props.mediaAssets||[]} scope="all" selectedIds={noteId?[noteId]:[]} selectionMode="single" title="选择试读笔记"
      onClose={()=>setNotePickerOpen(false)} onConfirm={(_scope,ids)=>{
        const selected=ids?.[0]
        if(!selected||!notes.some(n=>n.noteId===selected))return
        if(selected!==noteId){setNoteId(selected);resetTarget()}
        setNotePickerOpen(false)
      }}/>}
    {notePickerOpen&&targetKind==='account'&&!running&&!applying&&<CreatorNoteSelectionDialog notes={notes} mediaAssets={props.mediaAssets||[]} scope={accountScope} selectedIds={confirmedAccountSelection?.selectedNoteIds} title="选择账号模拟笔记" includeComments={false}
      onClose={()=>setNotePickerOpen(false)} onConfirm={(nextScope,ids)=>{
        const selectedNoteIds=[...new Set(ids||[])].sort()
        if(!props.profile||!selectedNoteIds.length||selectedNoteIds.some(id=>!notes.some(note=>note.noteId===id)))return
        if(JSON.stringify(selectedNoteIds)!==JSON.stringify(confirmedAccountSelection?.selectedNoteIds))resetTarget()
        setAccountScope(nextScope)
        setAccountSelection({workspaceId,sourceMaterialId:props.profile.id,selectedNoteIds})
        setNotePickerOpen(false)
      }}/>}
    {targetKind!=='account'&&target&&!target.body&&<p className="muted">只测标题吸引力与阅读期待，写出正文后可再做全文试读。</p>}
    {targetKind!=='account'&&target && <details className="simulation-target-preview"><summary>{target.body ? '查看待测正文' : '仅预演选题概念'}</summary>
      <p><strong>{target.title}</strong>{target.body && <><br />{target.body}</>}</p></details>}
    <fieldset className="panel-task-controls" disabled={running || applying}>
      <legend>{targetKind==='account'?'讨论方式':'试读方式'} <InfoHint label="模拟范围说明">{targetKind==='account'
        ?'从所选笔记出发，聊聊为什么关注、期待什么，以及哪些方向值得持续讲。'
        :targetKind==='note'?'这次复盘用于下一篇同类内容，不会修改已发布的原文。'
          :'读者会分别表达阅读感受，你可以在讨论后继续追问。'}</InfoHint></legend>
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
      <div className="panel-task-discussion"><label><input type="checkbox" checked={discussionEnabled}
        onChange={e => changeTask(() => setDiscussionEnabled(e.target.checked))} />互相回应</label>
        <InfoHint label="互相回应说明">{discussionEnabled ? '先各自表达，再回应其他人的公开留言。' : '只做独立表达，省去互相回应。'}</InfoHint>
      </div>
    </fieldset>
    <section className="simulation-final-readers" aria-label="确认实际参与者">
      <div className="simulation-participant-heading"><div className="reader-card-heading"><h3>参与读者 · {fans.ids.length} 位</h3>
        {activeAdoption&&adoptionReady&&<span className="muted simulation-selection-origin" role="status">{changed?'推荐后调整':'已采用推荐'}</span>}
        {!activeAdoption&&manualChoice&&<span className="muted simulation-selection-origin" role="status">手选</span>}
        {!!selectedFans.length&&<InfoHint label="本次角色说明">可调整本次角色，不影响读者档案里的长期画像。</InfoHint>}
      </div>
      <div className="reader-recommendation-actions">
        <button type="button" disabled={!target || !taskValid || running || recommendation.busy || applying || !hasActiveFans}
          onClick={() => {setApplyError('');setAdopted(null); void recommendation.recommend(Math.max(1, fans.slots.length))}}>
          {recommendation.busy ? '正在读取推荐…' : record ? '重新推荐读者' : '推荐读者'}</button>
        {recommendation.error && <button type="button" disabled={!target || !taskValid || running || applying}
          onClick={() => void (recommendation.hasReceipt ? recommendation.refresh() : recommendation.recommend(fans.slots.length))}>
          {recommendation.hasReceipt ? '重试读取' : '重试原请求'}</button>}
      </div>
      </div>
    <div className="reader-recommendation simulation-recommendation-inline" aria-label="读者推荐">
      {recommendation.busy&&<p className="trial-progress" role="status">正在比较读者的需求与当前内容 · {waited} 秒</p>}
      {recommendation.error && <p role="alert">{recommendation.error}</p>}
      {record?.freshness?.status === 'stale' && <p role="status">内容或读者已变化，请重新推荐，或继续手动选择。</p>}
      {record?.freshness?.status === 'unavailable' && <p role="status">这份推荐的来源暂不可核验，仍可手动选择。</p>}
      {record?.status === 'failed' && <p role="status">{record.errorCode === 'input_too_large' ? '资料较长，请先手动选择读者。' : '本次推荐未完成，可重新推荐或手动选择。'}</p>}
      {record?.status === 'partially_completed' && <p role="status">部分完成，已保留有效读者。</p>}
      {!!proposals.length && (activeAdoption?<details className="simulation-recommendation-details"><summary>查看推荐依据 · {proposals.length} 位</summary>{proposalCards}</details>:proposalCards)}
      {record?.status === 'completed' && !proposals.length && <p role="status">{record.result?.unmatchedReason || '暂未找到合适读者。'}</p>}
      {!!proposals.length && !activeAdoption && <button type="button" disabled={!target || !valid || running || applying} onClick={() => void apply()}>采用这组读者</button>}
      {applyError && <p role="alert">{applyError}</p>}
    </div>
      {fans.loading&&<p role="status">{fans.loaded?'正在刷新读者，已选名单保留。':'正在读取已保存读者…'}</p>}
      {fans.error&&<div className="simulation-readers-error"><p role="alert">读者列表暂时未能读取。{fans.loaded?'已保留当前名单。':''}</p><button type="button" disabled={fans.loading||running||applying} onClick={()=>void fans.refresh()}>{fans.loading?'正在重试…':'重试读取读者'}</button></div>}
      {hasActiveFans&&<>
      <fieldset className="simulation-reader-controls" disabled={running || applying}>
      <SimulatedFanPicker compactSlots rows={fans.rows} slots={fans.slots} onSlotChange={(index,id)=>{fans.setSlot(index,id);clearRemovedOverrides(fans.slots.map((value,i)=>i===index?id:value));if(!activeAdoption)setManualChoice(true)}} onAddSlot={fans.addSlot} onRemoveSlot={index=>{fans.removeSlot(index);clearRemovedOverrides(fans.slots.filter((_,i)=>i!==index));if(!activeAdoption)setManualChoice(true)}}
        renderSelected={f=><details className="simulation-role-editor" key={f.id}>
        <summary>调整 {f.editable.name} 的本次角色{invalidPersonaIds.includes(f.id)?' · 请补全':personaOverrides[f.id]?' · 已调整':''}</summary>
        <fieldset disabled={running||applying}>
          <label>本次视角<textarea aria-label={`${f.editable.name}的本次视角`} maxLength={4000} rows={2} value={personaOverrides[f.id]?.profile??f.editable.profile} onChange={e=>editPersona(f.id,'profile',e.target.value)}/></label>
          <label>具体关切<textarea aria-label={`${f.editable.name}的本次关切`} maxLength={2000} rows={2} value={personaOverrides[f.id]?.coreConcern??f.editable.coreConcern} onChange={e=>editPersona(f.id,'coreConcern',e.target.value)}/></label>
          <label>表达方式<textarea aria-label={`${f.editable.name}的本次表达`} maxLength={2000} rows={2} value={personaOverrides[f.id]?.expressionStyle??f.editable.expressionStyle} onChange={e=>editPersona(f.id,'expressionStyle',e.target.value)}/></label>
          {invalidPersonaIds.includes(f.id)&&<p role="status">请补全调整后的角色设定，或恢复已保存画像；本次视角最多 4000 字，关切和表达各最多 2000 字。</p>}
          {personaOverrides[f.id]&&<button className="simulation-role-reset" type="button" onClick={()=>setPersonaOverrides(current=>Object.fromEntries(Object.entries(current).filter(([id])=>id!==f.id)))}>恢复已保存画像</button>}
        </fieldset>
      </details>} />
      </fieldset>
      </>}
      {fans.loaded&&!fans.loading&&!fans.error&&!hasActiveFans&&<div className="simulation-readers-empty"><p>还没有可用的模拟读者。</p><button type="button" onClick={onAddFans}>从受众分析添加模拟粉丝</button></div>}
      {!!invalidPersonaIds.length&&<p role="status">还有 {invalidPersonaIds.length} 位读者的本次设定需要补全，完成或恢复后即可开始。</p>}
    <button className="primary simulation-start" disabled={running || applying || checkingAdoption || !taskValid || !!invalidPersonaIds.length || !fans.ids.length || !target}
      onClick={() => {const link=activeAdoption&&adoptionReady ? {
        readerSelectionId: activeAdoption.readerSelectionId,
        readerSelectionInputHash: activeAdoption.readerSelectionInputHash,
      } : undefined;
        if(!link){setAdopted(null);setManualChoice(true)}
        const overrides=Object.fromEntries(Object.entries(personaOverrides).filter(([id])=>fans.ids.includes(id)))
        const extra: [SimulationPersonaOverrides?]=Object.keys(overrides).length?[overrides]:[]
        if(accountNoteSelection)props.onRunAccount?.(accountNoteSelection,link,panelTask,...extra)
        else if(noteRef)props.onRunNote?.(noteRef,link,panelTask,...extra)
        else if(topic)onRun(topic,link,panelTask,...extra)
      }}>{startLabel}</button>
    </section>
  </section>
}
