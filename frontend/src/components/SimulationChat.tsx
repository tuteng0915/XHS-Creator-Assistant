import {useEffect, useRef, useState} from 'react'
import type {SimulationRun, Topic} from '../types'
import {simulationRunApi} from '../api'
import {panelInterviewApi, type PanelInterview} from '../panelInterview'
import {ReaderAvatar} from './ReaderAvatar'
import {EditorFeedbackView} from './EditorFeedbackView'
import {SimulationReviewSummary} from './SimulationReviewSummary'
import {InfoHint} from './InfoHint'
import './TrialRoom.css'
import {simulationCategoryFor, visibleReply} from '../simulationChat'
import type {ReaderFeedbackIntent} from '../contentCollaboration'
import {isOracleShowcase} from '../recordOrigin'

const text = (v:unknown) => typeof v === 'string' ? v : ''
const obj = (v:unknown):Record<string,unknown> => v && typeof v === 'object' && !Array.isArray(v) ? v as Record<string,unknown> : {}
const strings = (v:unknown) => Array.isArray(v) ? v.filter((x):x is string=>typeof x==='string') : []

export function SimulationChat({run, onObserved,onTopicAdded,topics,onUseReaderFeedback,readOnly=false}:{run:SimulationRun; onObserved?:(run:SimulationRun)=>void;onTopicAdded?:(topic:Topic)=>void;topics?:Topic[];onUseReaderFeedback?:(feedback:ReaderFeedbackIntent)=>void;readOnly?:boolean}) {
  const oracle=isOracleShowcase(run)
  const viewOnly=readOnly||oracle
  const observing = useRef(onObserved)
  useEffect(()=>{observing.current=onObserved},[onObserved])
  const [now,setNow]=useState(Date.now())
  const [loadError,setLoadError]=useState('')
  const [retry,setRetry]=useState(0)
  const [recovering,setRecovering]=useState('')
  const [recoveryError,setRecoveryError]=useState('')
  const recoveryReceipt=useRef<{stageKey:string;requestKey:string}|null>(null)
  const recoveryLock=useRef(false)
  const currentScope=useRef('')
  useEffect(()=>{currentScope.current=`${run.workspaceId}:${run.id}`;return()=>{currentScope.current=''}},[run.workspaceId,run.id])
  const running = !oracle&&['pending','running'].includes(run.status)
  useEffect(()=>{
    if(!running)return
    const timer=setInterval(()=>setNow(Date.now()),1000)
    return()=>clearInterval(timer)
  },[running])
  const category=simulationCategoryFor(run)
  const review=category!=='creation'
  const feedbackReaderIds=new Set(run.personaDefinitions.map(person=>text(person.id)).filter(Boolean))
  const canUseFeedback=!viewOnly&&category==='creation'&&!run.draftId&&!run.inputSnapshot.draft&&run.inputSnapshot.targetType!=='draft'&&!!run.topicId
    &&['completed','partially_completed'].includes(run.status)&&!!onUseReaderFeedback
    &&!!topics?.some(topic=>topic.id===run.topicId&&topic.workspaceId===run.workspaceId&&topic.status!=='archived')
  function handleFeedback(stage:ReaderFeedbackIntent['stage'], messageId:string, senderName:string, quote:string, interviewId?:string, authorQuestion?:string) {
    if(!canUseFeedback||!run.topicId||!quote.trim())return
    onUseReaderFeedback?.({id:crypto.randomUUID(),workspaceId:run.workspaceId,topicId:run.topicId,
      simulationId:run.id,stage,messageId,senderName,quote,...(interviewId?{interviewId}:{}),...(authorQuestion?{authorQuestion}:{})})
  }
  useEffect(()=>{
    if(viewOnly||!running) return
    let active=true; let timer:ReturnType<typeof setTimeout>
    async function poll(){try {
      const latest=await simulationRunApi.get(run.id)
      if(!active) return
      if(latest.id!==run.id||latest.workspaceId!==run.workspaceId)throw new Error('记录不匹配')
      setNow(Date.now());setLoadError('');observing.current?.(latest)
      if(['pending','running'].includes(latest.status))timer=setTimeout(()=>void poll(),1300)
    } catch {if(active)setLoadError('连接暂时中断，已收到的发言保留。')}}
    timer=setTimeout(()=>void poll(),500)
    return()=>{active=false;clearTimeout(timer)}
  },[run.id,run.workspaceId,running,retry,viewOnly])
  const people = run.personaDefinitions.length ? run.personaDefinitions : Array.isArray(run.inputSnapshot.audiencePersonas) ? run.inputSnapshot.audiencePersonas.map(obj) : []
  const name = (id:unknown) => {
    const p=people.find(p=>p.id===id)
    return text(p?.name) || text(p?.archetype) || '读者'
  }
  const avatarId = (id:unknown) => {
    const p=people.find(p=>p.id===id)
    return p?.sourceAnalysisId && p?.sourceGroupId ? `${p.sourceAnalysisId}:${p.sourceGroupId}` : text(id)
  }
  const elapsed = Math.max(0,Math.round((now-Date.parse(run.startedAt || run.createdAt))/1000))
  const task=obj(run.inputSnapshot.panelTask)
  const recovery=obj(run.modelMetadata?.recovery)
  const summaryStale=recovery.summaryStale===true
  function partName(key:string) {
    if(key==='synthesis')return review?'复盘结论':'修改建议'
    if(key==='personas')return '读者准备'
    const initial=key.startsWith('initial_reactions.')
    const id=key.slice((initial?'initial_reactions.':'debate_responses.').length)
    return `${name(id)}的${initial?'试读':'回应'}`
  }
  async function recoverPart(stageKey:string) {
    if(viewOnly||running||recoveryLock.current||!observing.current)return
    recoveryLock.current=true;setRecovering(stageKey);setRecoveryError('')
    const scope=`${run.workspaceId}:${run.id}`
    if(recoveryReceipt.current?.stageKey!==stageKey)recoveryReceipt.current={stageKey,requestKey:crypto.randomUUID()}
    try {
      const next=await simulationRunApi.recover(run.workspaceId,run.id,recoveryReceipt.current)
      if(currentScope.current!==scope)return
      if(next.workspaceId!==run.workspaceId||obj(next.modelMetadata?.recovery).sourceRunId!==run.id)throw new Error('重试记录不匹配')
      observing.current?.(next)
      recoveryReceipt.current=null
    } catch(e) {if(currentScope.current===scope)setRecoveryError(e instanceof Error?e.message:'重试未提交，请再试一次。')}
    finally {recoveryLock.current=false;if(currentScope.current===scope)setRecovering('')}
  }
  const settledReaders=new Set([
    ...run.reactionResults.map(r=>text(r.personaId)),
    ...Object.keys(run.stageErrors).filter(key=>key.startsWith('initial_reactions.')).map(key=>key.slice('initial_reactions.'.length)),
  ])
  const stage = !run.personaDefinitions.length ? '正在准备这次试读'
    : people.some(p=>!settledReaders.has(text(p.id))) ? `读者独立试读 · ${run.reactionResults.length}/${people.length} 已返回`
      : !Object.keys(run.synthesis).length ? (task.discussionEnabled === false ? `正在整理${review?'复盘结论':'修改建议'}` : `互相回应并整理${review?'复盘结论':'修改建议'}`) : '正在完成记录'
  function bubble(item:Record<string,unknown>,reply=false) {
    const speaker=name(item.personaId)
    const target=text(item.replyToId).replace(/^initial:|^reply:/,'') || text(item.targetedAt)
    const content=reply ? text(item.response)||text(item.text) : (item.action === 'no_comment' || item.action === 'skip') ? '' : text(item.quote)||text(item.text)
    if(reply&&!content)return null
    return <article className={`trial-message${!content?' trial-silent':''}`} key={text(item.messageId)||`${reply}:${text(item.personaId)}`}>
      <ReaderAvatar id={avatarId(item.personaId)} name={speaker}/><div className="trial-message-main">
        <div className="trial-message-meta"><b>{speaker}</b>{reply&&target&&<span>回复 {name(target)}</span>}</div>
        {content ? <p className="trial-bubble">{visibleReply(content,people)}</p> : <p className="trial-silent-note">{item.action==='skip'?'选择划走':'读完了，暂时没有留言'}</p>}
        {canUseFeedback&&feedbackReaderIds.has(text(item.personaId))&&content&&<button className="text-button trial-use-feedback" onClick={()=>handleFeedback(reply?'reply':'initial',text(item.messageId)||`${reply?'reply':'initial'}:${text(item.personaId)}`,speaker,content)}>拿这条意见改稿</button>}
        {!reply&&(text(item.understanding)||strings(item.concerns).length>0)&&<details className="trial-reading-notes"><summary>查看试读记录</summary>
          {text(item.understanding)&&<p><b>读到了什么</b><br/>{text(item.understanding)}</p>}
          {strings(item.concerns).length>0&&<p><b>困惑或阻力</b><br/>{strings(item.concerns).join('；')}</p>}
        </details>}
      </div>
    </article>
  }
  const topic=obj(run.inputSnapshot.topic)
  const scope=obj(obj(run.inputSnapshot.sourceAccount).scope)
  const oracleInterview=oracle?obj(run.inputSnapshot.oracleInterview):{}
  const oracleAnswers=Array.isArray(oracleInterview.answers)?oracleInterview.answers.map(obj)
    .filter(answer=>text(answer.quote).trim()&&people.some(person=>person.id===answer.personaId)):[]
  return <section className="trial-room" aria-label="读者试读群聊">
    <header className="trial-room-head"><div><div className="reader-card-heading"><h3>{category==='account'?'账号读者群聊':category==='published_note'?'笔记复盘群聊':'试读讨论'}</h3>{review&&<InfoHint label="讨论范围说明">{category==='account'?'基于账号样本，讨论读者为何留下、接下来想看什么。':'讨论下一篇同类内容；已发布笔记不作修改。'}</InfoHint>}</div><p>{run.targetTitle||text(topic.title)}</p></div><span>{people.length} 位读者</span></header>
    {category==='account'&&text(scope.omissionNotice)&&<p className="trial-context">{text(scope.omissionNotice)}</p>}
    {category==='creation'&&!text(topic.body)&&!run.inputSnapshot.draft&&<p className="trial-context">本次只看标题，讨论阅读意愿与期待。</p>}
    <div className="trial-conversation" role="log" aria-label="试读发言" aria-live="polite">
      {!run.reactionResults.length&&!running&&<p className="muted">这次还没有读者发言。</p>}
      {run.reactionResults.map(item=>bubble(item))}
      {!!run.debateResults.length&&<div className="trial-divider">读者互相回应</div>}
      {run.debateResults.map(item=>bubble(item,true))}
    </div>
    {oracle&&text(oracleInterview.question).trim()&&<section className="trial-interview" aria-label="作者访谈记录">
      <div className="trial-divider">作者访谈记录 <InfoHint label="访谈记录说明">此处展示已保存的访谈内容，仅供阅读，不能继续追问。</InfoHint></div>
      <div role="log" aria-label="访谈记录发言">
        <article className="trial-message trial-author">
          <ReaderAvatar id="creator" name="作者"/>
          <div className="trial-message-main"><div className="trial-message-meta"><b>作者</b><span>询问 参与读者</span></div><p className="trial-bubble">{text(oracleInterview.question)}</p></div>
        </article>
        {oracleAnswers.map((answer,index)=><article className="trial-message" key={`${text(answer.personaId)}:${index}`}>
          <ReaderAvatar id={avatarId(answer.personaId)} name={name(answer.personaId)}/>
          <div className="trial-message-main"><div className="trial-message-meta"><b>{name(answer.personaId)}</b><span>回复 作者</span></div><p className="trial-bubble">{visibleReply(text(answer.quote),people)}</p></div>
        </article>)}
      </div>
    </section>}
    {running&&<div className="trial-progress" role="status"><span className="trial-working-dot"/><div><b>{recovery.stageKey?`正在恢复${partName(text(recovery.stageKey))}`:stage}</b><small>已等待 {elapsed} 秒</small></div></div>}
    {!viewOnly&&loadError&&<p role="alert">{loadError} <button onClick={()=>setRetry(x=>x+1)}>恢复查看</button></p>}
    {Object.keys(run.stageErrors).length>0&&<section className="trial-errors" aria-label="未完成环节"><p>部分环节未完成，已保留现有发言</p>{Object.entries(run.stageErrors).map(([key,e])=>{
      const supported=key==='synthesis'||key==='personas'||key.startsWith('initial_reactions.')||key.startsWith('debate_responses.')
      return <div className="trial-recovery-row" key={key}><div><b>{supported?partName(key):'未完成环节'}</b><p>{text(e)}</p></div>
        {!viewOnly&&!running&&onObserved&&supported&&<button disabled={!!recovering} aria-label={`重试${partName(key)}`} onClick={()=>void recoverPart(key)}>{recovering===key?'正在提交…':'仅重试此项'}</button>}</div>
    })}</section>}
    {!viewOnly&&recoveryError&&<p className="trial-context" role="alert">{recoveryError}</p>}
    {!viewOnly&&!running&&onObserved&&run.reactionResults.length>0&&(summaryStale||!Object.keys(run.synthesis).length)&&!run.stageErrors.synthesis&&<div className="trial-progress">
      <div><b>{summaryStale?'有新发言尚未纳入汇总':'发言已保留，可单独整理结论'}</b></div>
      <button disabled={!!recovering} onClick={()=>void recoverPart('synthesis')}>{recovering==='synthesis'?'正在提交…':'更新汇总'}</button>
    </div>}
    {!viewOnly&&!running&&people.length>0&&['completed','partially_completed'].includes(run.status)&&<InterviewComposer key={run.id} run={run} people={people} name={name} avatarId={avatarId} feedbackReaderIds={feedbackReaderIds} onUseFeedback={canUseFeedback?handleFeedback:undefined}/>}
    {summaryStale&&Object.keys(run.synthesis).length>0&&<p className="trial-context">以下是补回发言前的汇总，更新后再采用；原记录仍保留。</p>}
    {Object.keys(run.synthesis).length>0&&(review?<SimulationReviewSummary key={`review:${run.workspaceId}:${run.id}`} run={run} onTopicAdded={onTopicAdded} topics={topics} readOnly={readOnly||summaryStale}/>:<section className="trial-takeaways"><h3>修改方向</h3>
      {text(run.synthesis.verdict)&&<p>{text(run.synthesis.verdict)}</p>}
      {text(run.synthesis.mainResistance)&&<p><b>最需要解决</b><br/>{text(run.synthesis.mainResistance)}</p>}
      <EditorFeedbackView data={run.synthesis} run={run}/>
    </section>)}
  </section>
}

function InterviewComposer({run,people,name,avatarId,feedbackReaderIds,onUseFeedback}:{run:SimulationRun;people:Array<Record<string,unknown>>;name:(id:unknown)=>string;avatarId:(id:unknown)=>string;feedbackReaderIds:ReadonlySet<string>;onUseFeedback?:(stage:'interview',messageId:string,senderName:string,quote:string,interviewId:string,authorQuestion:string)=>void}){
  const [rounds,setRounds]=useState<PanelInterview[]>([])
  const [question,setQuestion]=useState('')
  const [recipient,setRecipient]=useState(text(people[0]?.id))
  const [error,setError]=useState('')
  const [sending,setSending]=useState(false)
  const [refresh,setRefresh]=useState(0)
  const receipt=useRef<{question:string;recipient:string;key:string}|null>(null)
  const lock=useRef(false)
  const active=useRef(true)
  useEffect(()=>{active.current=true;return()=>{active.current=false}},[])
  const busy=rounds.some(r=>['pending','running'].includes(r.status))
  useEffect(()=>{
    let current=true;let timer:ReturnType<typeof setTimeout>
    async function load(){try{const data=await panelInterviewApi.list(run.workspaceId,run.id);if(!current)return;setRounds(data);setError('');if(data.some(r=>['pending','running'].includes(r.status)))timer=setTimeout(()=>void load(),1200)}catch(e){if(current)setError(String(e))}}
    void load();return()=>{current=false;clearTimeout(timer)}
  },[run.workspaceId,run.id,refresh])
  async function send(){
    if(lock.current||busy||!question.trim())return
    lock.current=true;setSending(true);setError('')
    const sent=question.trim()
    if(!receipt.current||receipt.current.question!==sent||receipt.current.recipient!==recipient)receipt.current={question:sent,recipient,key:crypto.randomUUID()}
    try{const created=await panelInterviewApi.create(run.workspaceId,run.id,{requestKey:receipt.current.key,question:sent,recipientPersonaId:recipient||null})
      if(active.current){setRounds(rows=>rows.some(r=>r.id===created.id)?rows:[...rows,created]);setQuestion('');receipt.current=null;setRefresh(v=>v+1)}
    }catch(e){if(active.current)setError(e instanceof Error?e.message:String(e))}finally{lock.current=false;if(active.current)setSending(false)}
  }
  async function cancel(id:string){try{await panelInterviewApi.cancel(run.workspaceId,run.id,id);setRefresh(v=>v+1)}catch(e){setError(String(e))}}
  return <section className="trial-interview" aria-label="作者访谈">
    {!!rounds.length&&<div className="trial-divider">作者加入讨论</div>}
    <div role="log" aria-label="访谈发言" aria-live="polite">{rounds.map(round=><div key={round.id}>
      {round.messages.map(m=><article key={m.id} className={`trial-message ${m.role==='author'?'trial-author':''}`}>
        <ReaderAvatar id={m.role==='author'?'creator':avatarId(m.personaId)} name={m.role==='author'?'作者':m.senderName}/>
        <div className="trial-message-main"><div className="trial-message-meta"><b>{m.role==='author'?'作者 · 你':m.senderName}</b><span>{m.role==='author'?`询问 ${m.recipientName||'所有读者'}`:'回复 作者'}</span></div><p className="trial-bubble">{visibleReply(m.content,people)}</p>
          {m.role==='reader'&&feedbackReaderIds.has(text(m.personaId))&&onUseFeedback&&m.content.trim()&&<button className="text-button trial-use-feedback" onClick={()=>onUseFeedback('interview',m.id,m.senderName,m.content,round.id,round.question)}>拿这条意见改稿</button>}
        </div>
      </article>)}
      {['pending','running'].includes(round.status)&&<div className="trial-progress" role="status"><span className="trial-working-dot"/><div><b>{round.currentParticipantName||'读者'} 正在回应</b><small>{round.completedReplies}/{round.totalReplies} 已回复 · {Math.round(round.elapsedSeconds)} 秒</small></div><button onClick={()=>void cancel(round.id)}>停止等待</button></div>}
      {round.error&&<p role="status">{round.error}</p>}
    </div>)}</div>
    {feedbackReaderIds.size>0?<><label className="trial-composer-target">向谁追问<select aria-label="访谈对象" value={recipient} disabled={busy||sending} onChange={e=>setRecipient(e.target.value)}>
      {people.map(p=><option key={text(p.id)} value={text(p.id)}>{name(p.id)}</option>)}<option value="">所有参与读者</option>
    </select></label>
    <textarea aria-label="作者追问" value={question} maxLength={2000} rows={3} disabled={busy||sending} placeholder="例如：哪句话让你犹豫？" onChange={e=>setQuestion(e.target.value)} onKeyDown={e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter'){e.preventDefault();void send()}}}/>
    <div className="trial-composer-footer"><small>Ctrl/⌘ + Enter 发送</small><button className="primary" disabled={busy||sending||!question.trim()} onClick={()=>void send()}>{sending?'正在发送…':'加入讨论'}</button></div>
    </>:<p className="muted">这次旧记录只有展示用的读者资料，原发言仍可阅读。重新试读后即可继续访谈或使用意见改稿。</p>}
    {error&&<p role="alert">{error} <button onClick={()=>setRefresh(v=>v+1)}>重新读取</button></p>}
  </section>
}
