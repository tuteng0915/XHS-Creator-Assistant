import type { PanelTask, SimulationRun } from '../types'
import {simulationCategoryFor} from '../simulationChat'
import {InfoHint} from './InfoHint'

function savedTask(value: unknown): PanelTask | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const task = value as Record<string, unknown>
  if (task.protocolVersion !== 'panel/v1'
    || (task.readingMode !== 'natural' && task.readingMode !== 'guided')
    || typeof task.discussionEnabled !== 'boolean'
    || !Array.isArray(task.focusQuestions)
    || !task.focusQuestions.every(q => typeof q === 'string' && q.trim() && [...q].length <= 300)) return null
  if (task.readingMode === 'natural' ? task.focusQuestions.length !== 0
    : task.focusQuestions.length < 1 || task.focusQuestions.length > 2) return null
  return task as unknown as PanelTask
}

export function SimulationTaskSummary({run, compact = false, missingOnly = false}: {run: SimulationRun; compact?: boolean; missingOnly?: boolean}) {
  const raw = run.inputSnapshot.panelTask
  const task = savedTask(raw)
  if(missingOnly&&task)return null
  const topic=run.inputSnapshot.topic as Record<string,unknown>|undefined
  const titleOnly=topic&&typeof topic==='object'&&!topic.body&&!run.inputSnapshot.draft
  const category=simulationCategoryFor(run)
  const account=run.inputSnapshot.sourceAccount as {scope?:{selectionMethod?:string}}|undefined
  const selectedAccountNotes=category==='account'&&account?.scope?.selectionMethod==='explicit_ids'
  if(compact)return task?<div className="simulation-task-inline" aria-label="当次试读设置">
    {task.readingMode==='guided'?<ul>{task.focusQuestions.map((question,index)=><li key={index}>{question}</li>)}</ul>:null}
    <span>{task.readingMode==='guided'?'围绕问题讨论':category==='account'?selectedAccountNotes?'所选笔记阅读':'账号整体阅读':category==='published_note'?'已发布笔记复盘':titleOnly?'只看标题':'全文试读'} · {task.discussionEnabled?'互相回应':'独立表达'}</span>
  </div>:null
  return <section className="simulation-task-summary" aria-label="当次试读设置">
    <div className="reader-card-heading"><h3>当次试读</h3>{task&&<InfoHint label="试读设置说明">{task.discussionEnabled
      ? '这是当时的设置；是否完成回应见下方结果。'
      : '本次设置为只做独立试读。'}</InfoHint>}</div>
    {task ? <>
      <div className="simulation-task-labels">
        <span>{task.readingMode === 'guided' ? '定向试读' : category==='account'?selectedAccountNotes?'所选笔记阅读':'账号整体阅读':category==='published_note'?'已发布笔记复盘':titleOnly?'自然标题试读':'自然全文试读'}</span>
        <span>{task.discussionEnabled ? '互相回应：开启' : '互相回应：关闭'}</span>
      </div>
      {task.readingMode === 'guided' && <div className="simulation-task-questions">
        <b>当时的重点问题</b>
        <ol>{task.focusQuestions.map((question, index) => <li key={index}>{question}</li>)}</ol>
      </div>}
    </> : <p className="muted">{raw == null
      ? '旧记录未保存试读设置。'
      : '此记录的试读设置不完整或版本暂不支持，未推断阅读方式。'}</p>}
  </section>
}
