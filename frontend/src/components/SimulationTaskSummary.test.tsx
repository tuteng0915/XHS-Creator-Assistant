import {cleanup, fireEvent, render, screen} from '@testing-library/react'
import {afterEach, expect, it, vi} from 'vitest'
import type {SimulationRun} from '../types'
import {SimulationTaskSummary} from './SimulationTaskSummary'
import {SimulationHistoryPage} from './SimulationHistoryPage'

afterEach(cleanup)
const task = {protocolVersion:'panel/v1',readingMode:'guided',discussionEnabled:true,focusQuestions:['第一步清楚吗？','哪些地方想跳过？']}
const run:SimulationRun = {id:'r',workspaceId:'w',topicId:'t',draftId:null,status:'failed',
  inputSnapshot:{panelTask:task,readerSelection:{source:'manual',actualFanIds:['a']}},
  personaDefinitions:[{id:'a',name:'当时的读者'}],reactionResults:[],debateResults:[],synthesis:{},
  stageErrors:{debate:'请求失败'},modelMetadata:{},userNotes:'',reviewStatus:'unreviewed',createdAt:'2026-10-05',updatedAt:'2026-10-05',startedAt:null,completedAt:null}

it('shows frozen guided questions in order without claiming discussion succeeded',()=>{
  const before=JSON.stringify(run)
  render(<SimulationTaskSummary run={run} />)
  expect(screen.getByText('定向试读')).toBeInTheDocument()
  expect(screen.getByText('互相回应：开启')).toBeInTheDocument()
  expect(screen.getAllByRole('listitem').map(li=>li.textContent)).toEqual(task.focusQuestions)
  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  fireEvent.focus(screen.getByRole('button',{name:'试读设置说明'}))
  expect(screen.getByRole('tooltip')).toHaveTextContent('这是当时的设置；是否完成回应见下方结果。')
  expect(JSON.stringify(run)).toBe(before)
})

it('shows natural reading with discussion off and does not invent questions',()=>{
  render(<SimulationTaskSummary run={{...run,inputSnapshot:{panelTask:{...task,readingMode:'natural',discussionEnabled:false,focusQuestions:[]}}}} />)
  expect(screen.getByText('自然全文试读')).toBeInTheDocument()
  expect(screen.getByText('互相回应：关闭')).toBeInTheDocument()
  expect(screen.queryByText('当时的重点问题')).not.toBeInTheDocument()
  fireEvent.mouseEnter(screen.getByRole('button',{name:'试读设置说明'}))
  expect(screen.getByRole('tooltip')).toHaveTextContent('本次设置为只做独立试读。')
})

it.each([true,false])('distinguishes selected account notes from legacy account samples (%s)',explicit=>{
  render(<SimulationTaskSummary run={{...run,simulationCategory:'account',inputSnapshot:{
    panelTask:{...task,readingMode:'natural',focusQuestions:[]},
    sourceAccount:{scope:explicit?{selectionMethod:'explicit_ids',selectedNoteIds:['n1','n2']}:{}},
  }}} />)
  expect(screen.getByText(explicit?'所选笔记阅读':'账号整体阅读')).toBeVisible()
  expect(screen.queryByText(explicit?'账号整体阅读':'所选笔记阅读')).not.toBeInTheDocument()
})

it.each([undefined,null])('keeps legacy missing task %s unknown',panelTask=>{
  render(<SimulationTaskSummary run={{...run,inputSnapshot:{panelTask}}} />)
  expect(screen.getByText('旧记录未保存试读设置。')).toBeInTheDocument()
  expect(screen.queryByText('自然全文试读')).not.toBeInTheDocument()
  expect(screen.queryByText('互相回应：开启')).not.toBeInTheDocument()
})

it.each([
  [],'guided',{}, {...task,protocolVersion:'panel/v2'}, {...task,readingMode:'other'},
  {...task,readingMode:['guided']}, {...task,discussionEnabled:'false'}, {...task,focusQuestions:['']},
  {...task,focusQuestions:['x'.repeat(301)]}, {...task,focusQuestions:[{},'有效问题']},
  {...task,focusQuestions:['一','二','三']}, {...task,readingMode:'natural'},
])('does not guess malformed or unknown task %#',panelTask=>{
  render(<SimulationTaskSummary run={{...run,inputSnapshot:{panelTask}}} />)
  expect(screen.getByText(/设置不完整或版本暂不支持/)).toBeInTheDocument()
  expect(screen.queryByText('定向试读')).not.toBeInTheDocument()
})

it('history switches task and reader snapshots together and never fetches current settings',()=>{
  const fetch=vi.spyOn(globalThis,'fetch')
  const props={publicMode:true,simulationRuns:[],selectedSimulationRun:run,
    simulationReviewDraft:{reviewStatus:'unreviewed' as const,userNotes:''},simulationReviewSaveState:{phase:'idle' as const},
    reviewStatusLabel:(s:string)=>s,onOpenSimulationRun:vi.fn(),onSimulationReviewDraftChange:vi.fn(),
    onSaveSimulationRunReview:vi.fn(),stageSeedFromSimulation:()=>[],renderStageResult:()=>null}
  const {rerender}=render(<SimulationHistoryPage {...props} />)
  expect(screen.getByText('第一步清楚吗？')).toBeInTheDocument()
  expect(screen.getByLabelText('本次参与读者')).toHaveTextContent('当时的读者')
  rerender(<SimulationHistoryPage {...props} selectedSimulationRun={{...run,id:'old',inputSnapshot:{},personaDefinitions:[]}} />)
  expect(screen.getByText('旧记录未保存试读设置。')).not.toBeVisible()
  fireEvent.click(screen.getByText('推荐依据与备注',{selector:'summary'}))
  expect(screen.getByText('旧记录未保存试读设置。')).toBeVisible()
  expect(screen.queryByText('第一步清楚吗？')).not.toBeInTheDocument()
  expect(screen.queryByText('当时的读者')).not.toBeInTheDocument()
  expect(fetch).not.toHaveBeenCalled()
  fetch.mockRestore()
})
