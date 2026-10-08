import {useEffect, useRef, useState} from 'react'
import {simulationRunApi} from '../api'
import {simulationCategoryFor} from '../simulationChat'
import type {SimulationRun, Topic} from '../types'
import {EditorFeedbackView} from './EditorFeedbackView'

const text = (value:unknown) => typeof value==='string'?value:''
const object = (value:unknown):Record<string,unknown> => value && typeof value==='object' && !Array.isArray(value)?value as Record<string,unknown>:{}
const strings = (value:unknown) => Array.isArray(value)?value.filter((item):item is string=>typeof item==='string'&&!!item.trim()):[]

export function SimulationReviewSummary({run,onTopicAdded,topics=[]}:{run:SimulationRun;onTopicAdded?:(topic:Topic)=>void;topics?:Topic[]}) {
  const account=simulationCategoryFor(run)==='account'
  const review=object(run.synthesis.review)
  const ideas=Array.isArray(review.topicIdeas)?review.topicIdeas.map(object).filter(idea=>text(idea.id)&&text(idea.title)):[]
  const ready=['completed','partially_completed'].includes(run.status)
  const adoptedIds=new Set(topics.filter(topic=>topic.workspaceId===run.workspaceId&&topic.generatedSnapshot.sourceSimulationId===run.id).map(topic=>topic.generatedSnapshot.sourceTopicIdeaId))
  const [states,setStates]=useState<Record<string,{phase:'saving'|'saved'|'error';message?:string}>>({})
  const locks=useRef(new Set<string>())
  const active=useRef(true)
  const identity=useRef(`${run.workspaceId}:${run.id}`)
  useEffect(()=>{active.current=true;return()=>{active.current=false}},[])
  useEffect(()=>{
    identity.current=`${run.workspaceId}:${run.id}`
    locks.current.clear()
    setStates({})
  },[run.workspaceId,run.id])

  async function adopt(ideaId:string) {
    if(!ready||adoptedIds.has(ideaId)||locks.current.has(ideaId)||states[ideaId]?.phase==='saved')return
    const requestIdentity=`${run.workspaceId}:${run.id}`
    locks.current.add(ideaId)
    setStates(previous=>({...previous,[ideaId]:{phase:'saving'}}))
    try {
      const topic=await simulationRunApi.adoptTopicIdea(run.workspaceId,run.id,ideaId)
      if(!active.current||identity.current!==requestIdentity)return
      if(topic.workspaceId!==run.workspaceId)throw new Error('选题返回的账号不匹配，请重新打开记录检查。')
      setStates(previous=>({...previous,[ideaId]:{phase:'saved'}}))
      onTopicAdded?.(topic)
    } catch(error) {
      if(active.current&&identity.current===requestIdentity)setStates(previous=>({...previous,[ideaId]:{phase:'error',message:error instanceof Error?error.message:'暂时没能加入，请重试。'}}))
    } finally {
      if(identity.current===requestIdentity)locks.current.delete(ideaId)
    }
  }
  return <section className="trial-takeaways" aria-label={account?'账号访谈结论':'已发布笔记复盘结论'}>
    <h3>{account?'读者期待这个账号持续做什么':'下一篇同类型内容，可以这样做'}</h3>
    {text(review.summary)?<>
      <p>{text(review.summary)}</p>
      <div className="trial-review-grid">
        {[
          ['读者在意什么',review.readerNeeds],
          ['值得继续保持',review.keepDoing],
          [account?'后续内容方向':'下次可以尝试',review.nextTimeSuggestions],
        ].map(([label,items])=>strings(items).length>0&&<section key={text(label)}><h4>{text(label)}</h4><ul>{strings(items).map((item,index)=><li key={index}>{item}</li>)}</ul></section>)}
      </div>
      {ideas.length>0&&<section className="trial-topic-ideas" aria-label="待选选题">
        <h4>可以带走的选题</h4><p className="muted">选择你想继续的方向，点选后加入选题库。</p>
        {ideas.map(idea=>{
          const id=text(idea.id),state=states[id]
          const saved=adoptedIds.has(id)||state?.phase==='saved'
          return <article className="trial-topic-idea" key={id}>
            <div><h5>{text(idea.title)}</h5>{text(idea.angle)&&<p>{text(idea.angle)}</p>}{text(idea.whyItFits)&&<small>{text(idea.whyItFits)}</small>}</div>
            <button disabled={!ready||state?.phase==='saving'||saved} onClick={()=>void adopt(id)}>{saved?'已加入选题库':state?.phase==='saving'?'正在加入…':!ready?'等待复盘完成':'加入选题库'}</button>
            {state?.phase==='error'&&<p className="trial-topic-error" role="alert">{state.message}</p>}
          </article>
        })}
      </section>}
    </>:<>
      <p className="muted">这是旧版记录，尚未生成{account?'账号内容方向':'下一篇同类内容建议'}，原有结论仍保留在下方。</p>
      <details><summary>查看旧版结论</summary>
        {text(run.synthesis.verdict)&&<p>{text(run.synthesis.verdict)}</p>}
        {text(run.synthesis.mainResistance)&&<p>{text(run.synthesis.mainResistance)}</p>}
        {text(run.synthesis.strongestAngle)&&<p>{text(run.synthesis.strongestAngle)}</p>}
        {strings(run.synthesis.contentAdjustments).map((item,index)=><p key={index}>{item}</p>)}
        {strings(run.synthesis.riskWarnings).map((item,index)=><p key={`risk:${index}`}>{item}</p>)}
        <EditorFeedbackView data={run.synthesis} run={run}/>
      </details>
    </>}
  </section>
}
