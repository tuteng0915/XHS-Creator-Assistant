import {useEffect, useRef, useState} from 'react'
import {simulationRunApi} from '../api'
import {simulationCategoryFor} from '../simulationChat'
import type {SimulationRun, Topic} from '../types'
import {EditorFeedbackView} from './EditorFeedbackView'
import './SimulationReviewSummary.css'

const text = (value:unknown) => typeof value==='string'?value:''
const object = (value:unknown):Record<string,unknown> => value && typeof value==='object' && !Array.isArray(value)?value as Record<string,unknown>:{}
const strings = (value:unknown) => Array.isArray(value)?value.filter((item):item is string=>typeof item==='string'&&!!item.trim()):[]

export function SimulationReviewSummary({run,onTopicAdded,topics=[],readOnly=false}:{run:SimulationRun;onTopicAdded?:(topic:Topic)=>void;topics?:Topic[];readOnly?:boolean}) {
  const account=simulationCategoryFor(run)==='account'
  const review=object(run.synthesis.review)
  const ideas=Array.isArray(review.topicIdeas)?review.topicIdeas.map(object).filter(idea=>text(idea.id).trim()&&text(idea.title).trim()):[]
  const summary=text(review.summary)
  const readerNeeds=strings(review.readerNeeds)
  const keepDoing=strings(review.keepDoing)
  const nextTimeSuggestions=strings(review.nextTimeSuggestions)
  const hasReview=!!summary.trim()||readerNeeds.length>0||keepDoing.length>0||nextTimeSuggestions.length>0||ideas.length>0
  const hasLegacyFeedback=Array.isArray(run.synthesis.editorFeedback)?run.synthesis.editorFeedback.length>0:Object.keys(object(run.synthesis.editorFeedback)).length>0
  const hasLegacy=[run.synthesis.verdict,run.synthesis.mainResistance,run.synthesis.strongestAngle].some(value=>text(value).trim())
    ||strings(run.synthesis.contentAdjustments).length>0||strings(run.synthesis.riskWarnings).length>0||hasLegacyFeedback
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
    if(readOnly||!ready||adoptedIds.has(ideaId)||locks.current.has(ideaId)||states[ideaId]?.phase==='saved')return
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
  return <section className="simulation-review-summary" aria-label={account?'账号访谈结论':'已发布笔记复盘结论'}>
    <h3>{account?'读者期待这个账号持续做什么':'下一篇同类型内容，可以这样做'}</h3>
    {hasReview?<>
      {!!summary.trim()&&<p className="simulation-review-lead">{summary}</p>}
      {nextTimeSuggestions.length>0&&<section className="simulation-review-directions">
        <h4>{account?'后续内容方向':'下次可以尝试'}</h4>
        <ul>{nextTimeSuggestions.map((item,index)=><li key={index}>{item}</li>)}</ul>
      </section>}
      {(readerNeeds.length>0||keepDoing.length>0)&&<div className="simulation-review-observations">
        {([{label:'读者在意什么',items:readerNeeds},{label:'值得继续保持',items:keepDoing}]).map(({label,items})=>items.length>0&&<details key={label}>
          <summary>{label}</summary><ul>{items.map((item,index)=><li key={index}>{item}</li>)}</ul>
        </details>)}
      </div>}
      {ideas.length>0&&<section className="simulation-review-ideas" aria-label="待选选题">
        <h4>可以带走的选题</h4>
        {ideas.map(idea=>{
          const id=text(idea.id),state=states[id]
          const saved=adoptedIds.has(id)||state?.phase==='saved'
          return <article className="simulation-review-idea" key={id}>
            <div className="simulation-review-idea-copy"><h5>{text(idea.title)}</h5>{text(idea.angle).trim()&&<p>{text(idea.angle)}</p>}
              {text(idea.whyItFits).trim()&&<details><summary>为什么适合</summary><p>{text(idea.whyItFits)}</p></details>}
            </div>
            {!readOnly&&<button disabled={!ready||state?.phase==='saving'||saved} onClick={()=>void adopt(id)}>{saved?'已加入选题库':state?.phase==='saving'?'正在加入…':!ready?'等待复盘完成':'加入选题库'}</button>}
            {state?.phase==='error'&&<p className="simulation-review-error" role="alert">{state.message}</p>}
          </article>
        })}
      </section>}
    </>:hasLegacy?<>
      <p className="simulation-review-note">这是旧版记录，原有结论仍可查看。</p>
      <details><summary>查看旧版结论</summary>
        {text(run.synthesis.verdict)&&<p>{text(run.synthesis.verdict)}</p>}
        {text(run.synthesis.mainResistance)&&<p>{text(run.synthesis.mainResistance)}</p>}
        {text(run.synthesis.strongestAngle)&&<p>{text(run.synthesis.strongestAngle)}</p>}
        {strings(run.synthesis.contentAdjustments).map((item,index)=><p key={index}>{item}</p>)}
        {strings(run.synthesis.riskWarnings).map((item,index)=><p key={`risk:${index}`}>{item}</p>)}
        <EditorFeedbackView data={run.synthesis} run={run}/>
      </details>
    </>:<p className="simulation-review-note">暂未生成复盘结论。</p>}
  </section>
}
