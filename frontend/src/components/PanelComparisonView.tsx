import {useEffect, useRef, useState} from 'react'
import {simulationRunApi} from '../api'
import type {PanelComparison, PanelComparisonRun, PanelReadingSide, SimulationRun} from '../types'
import {CreatorDialog} from './CreatorDialog'

const initialLabels: Record<string,string> = {
  comment:'留下评论', no_comment:'读后未留言', skip:'略过', failed:'试读失败', missing:'没有试读结果',
}
const replyLabels: Record<string,string> = {
  replied:'参与回应', silent:'未公开回应', disabled:'未开启互相回应', failed:'回应失败', not_recorded:'没有回应记录',
}
const operationLabels: Record<string,string> = {
  simulation_personas:'人物准备', simulation_reaction:'独立试读', simulation_debate:'互相回应', simulation_synthesis:'编辑汇总',
}

function TextList({title, items}: {title:string; items:string[]}) {
  return <section><b>{title}</b>{items.length ? <ul>{items.map((item,i) => <li key={i}>{item}</li>)}</ul> : <p className="muted">未记录</p>}</section>
}

function ReadingSide({label, side}: {label:string; side:PanelReadingSide}) {
  return <section className="panel-reading-side" aria-label={label}>
    <h4>{label}</h4><span className="muted">{initialLabels[side.initialStatus] || '未记录参与方式'}</span>
    <p><b>理解</b> {side.understanding || '未记录'}</p>
    {side.stance && <p><b>态度</b> {side.stance}</p>}
    {side.quote && <blockquote aria-label="公开评论">{side.quote}</blockquote>}
    <TextList title="顾虑记录" items={side.concerns}/>
    <TextList title="吸引点与机会" items={side.opportunities}/>
    <details><summary>互相回应 · {replyLabels[side.replyStatus] || '状态未记录'}</summary>
      {side.reply && <blockquote aria-label="公开回应">{side.reply}</blockquote>}
      <TextList title="回应后的顾虑" items={side.newConcerns}/>
      <TextList title="强化的信号" items={side.strongerSignals}/>
      {side.changeReason && <p>{side.changeReason}</p>}
    </details>
  </section>
}

function RunInfo({run,label}: {run:PanelComparisonRun; label:string}) {
  return <section className="panel-reading-side"><h4>{label}</h4><b>{run.title}</b>
    <p className="panel-edit-text">{run.body || '（空正文）'}</p>
    <p>{run.mode === 'demo' ? '演示模式' : '模型模式'}</p>
    {run.recordedModels.length ? run.recordedModels.map((m,i) => <p key={i}>
      {operationLabels[m.operation || ''] || '未知阶段'} · {m.provider || '服务商未记录'} / {m.model || '模型未记录'}
      {m.modelSource === 'configured' ? '（配置值，响应未提供模型名）' : m.modelSource !== 'response' ? '（模型名来源未记录）' : ''}
      <br/>系统提示指纹：{m.systemPromptHash || '未记录'}
    </p>) : <p className="muted">未保存实际模型与系统提示信息</p>}
  </section>
}

export function PanelComparisonView({run}: {run:SimulationRun}) {
  const [open,setOpen] = useState(false), [data,setData] = useState<PanelComparison|null>(null)
  const [loading,setLoading] = useState(false), [error,setError] = useState('')
  const request = useRef(0)
  useEffect(() => () => {request.current += 1}, [])
  const close = () => {request.current += 1; setOpen(false); setLoading(false)}
  async function load() {
    const ticket = ++request.current
    setOpen(true); setLoading(true); setError(''); setData(null)
    try {
      const result = await simulationRunApi.comparison(run.workspaceId,run.id)
      if (ticket !== request.current) return
      if (result.workspaceId !== run.workspaceId || result.simulationId !== run.id
        || result.parentSimulationId !== run.parentSimulationId
        || result.before.id !== run.parentSimulationId || result.after.id !== run.id) {
        throw new Error('返回的对照不属于当前试读。')
      }
      setData(result)
    } catch(e) {if(ticket === request.current) setError(e instanceof Error ? e.message : String(e))}
    finally {if(ticket === request.current) setLoading(false)}
  }
  return <>
    <button disabled={!['completed','partially_completed','failed'].includes(run.status)} onClick={() => void load()}>逐人前后对照</button>
    {open && <CreatorDialog title="逐人前后对照" wide scrollBody onClose={close}>
      {loading && <p role="status">正在读取两次试读…</p>}
      {error && <><p role="alert">{error}</p><button onClick={() => void load()}>重新读取对照</button></>}
      {data && <>
        <p>同一组 {data.readers.length} 位读者，分别阅读两版稿件。展开一位读者，看理解、顾虑和回应有哪些变化。</p>
        <p className="muted">顾虑记录是模拟阅读感受，不是公开留言；新版未提及不等于已经解决。</p>
        <div className="panel-comparison-readers">{data.readers.map(reader => <details key={reader.id}>
          <summary>{reader.name}</summary><p className="muted">{reader.profile}</p>
          <div className="panel-comparison-columns"><ReadingSide label="上次试读" side={reader.before}/><ReadingSide label="本次复测" side={reader.after}/></div>
        </details>)}</div>
        <details><summary>两版稿件与模型记录</summary><div className="panel-comparison-columns"><RunInfo label="上次稿件" run={data.before}/><RunInfo label="本次稿件" run={data.after}/></div></details>
        <details><summary>比较说明</summary><ul>{data.limitations.map((text,i) => <li key={i}>{text}</li>)}</ul></details>
      </>}
    </CreatorDialog>}
  </>
}
