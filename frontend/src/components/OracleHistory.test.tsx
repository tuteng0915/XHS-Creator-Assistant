import {cleanup, fireEvent, render, screen, within} from '@testing-library/react'
import {afterEach, expect, it, vi} from 'vitest'
import type {AnalysisRun, SimulationRun} from '../types'
import {isOracleShowcase} from '../recordOrigin'
import {stageSeedFromRun} from '../workflowStageViews'
import {AnalysisHistoryPage} from './AnalysisHistoryPage'
import {SimulationHistoryPage} from './SimulationHistoryPage'
import {WorkflowOutputPanel} from './WorkflowOutputPanel'

afterEach(cleanup)
const recordedAt='2026-10-09T00:00:00Z'
const analysis:AnalysisRun={id:'a',workspaceId:'w',workflowType:'account_diagnosis',status:'completed',
  userNotes:'',reviewStatus:'unreviewed',createdAt:recordedAt,updatedAt:recordedAt,startedAt:recordedAt,completedAt:recordedAt,
  inputSnapshot:{},stageResults:{profile:{profile:{}}},stageErrors:{},modelMetadata:{origin:'oracle_showcase',provider:'none',modelCalled:false}}
const simulation:SimulationRun={...analysis,id:'s',simulationCategory:'published_note',topicId:null,draftId:null,
  targetTitle:'本账号已经发布的一篇笔记',personaDefinitions:[],reactionResults:[],debateResults:[],synthesis:{}}
const idle={phase:'idle' as const}

it('recognizes only explicit prewritten origins, including summary-only records',()=>{
  for(const record of [{origin:'oracle_showcase'},{modelMetadata:{origin:'oracle_showcase'}},{inputSnapshot:{origin:'oracle_showcase'}},{result:{origin:'oracle_showcase'}}]) {
    expect(isOracleShowcase(record)).toBe(true)
  }
  for(const record of [null,{}, {origin:'demo'},{id:'oracle_showcase'},{modelMetadata:{model:'oracle_showcase'}},{result:{origin:'curated_preset'}}]) {
    expect(isOracleShowcase(record)).toBe(false)
  }
})

it('keeps analysis history clean and exposes unchanged provenance only on request',()=>{
  const props={analysisRuns:[{...analysis,origin:'oracle_showcase'}],selectedRun:analysis,
    analysisReviewDraft:{userNotes:'',reviewStatus:'unreviewed' as const},analysisReviewSaveState:idle,
    renderStageResult:(stage:{key:string})=> stage.key==='profile'?<p>账号认识正文</p>:null,onOpenRun:vi.fn(),onAnalysisReviewDraftChange:vi.fn(),onSaveAnalysisRunReview:vi.fn()}
  const page=render(<AnalysisHistoryPage {...props}/>)
  expect(screen.queryByText('预写示例')).not.toBeInTheDocument()
  expect(screen.queryByText(/人工编排/)).not.toBeInTheDocument()
  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  expect(screen.getAllByRole('button',{name:'记录来源说明'})).toHaveLength(1)
  fireEvent.focus(screen.getByRole('button',{name:'记录来源说明'}))
  expect(screen.getByRole('tooltip')).toHaveTextContent('基于本账号已保存笔记人工编排，未调用模型。')
  expect(analysis.modelMetadata).toEqual({origin:'oracle_showcase',provider:'none',modelCalled:false})
  expect(screen.getByText('账号认识正文')).toBeVisible()
  const normal={...analysis,modelMetadata:{}}
  page.rerender(<AnalysisHistoryPage {...props} analysisRuns={[normal]} selectedRun={normal}/>)
  expect(screen.queryByText('预写示例')).not.toBeInTheDocument()
  expect(screen.queryByText(/人工编排/)).not.toBeInTheDocument()
  expect(screen.getByText('账号认识正文')).toBeVisible()
})

it('omits the default diagnosis review badge while preserving explicit marks and editable notes',()=>{
  const props={publicMode:true,analysisRuns:[analysis],selectedRun:analysis,
    analysisReviewDraft:{userNotes:'',reviewStatus:'unreviewed' as const},analysisReviewSaveState:idle,
    renderStageResult:()=>null,onOpenRun:vi.fn(),onAnalysisReviewDraftChange:vi.fn(),onSaveAnalysisRunReview:vi.fn()}
  const page=render(<AnalysisHistoryPage {...props}/>)
  const row=screen.getByRole('button',{name:/账号诊断 已完成/})
  expect(within(row).queryByText('未标记')).not.toBeInTheDocument()
  expect(screen.queryByText('未复盘')).not.toBeInTheDocument()
  fireEvent.click(screen.getByText('复盘备注',{selector:'summary'}))
  expect(screen.getByRole('option',{name:'未标记'})).toHaveValue('unreviewed')
  fireEvent.change(screen.getByLabelText('复盘备注'),{target:{value:'保留这个发现'}})
  expect(props.onAnalysisReviewDraftChange).toHaveBeenCalledWith({userNotes:'保留这个发现',reviewStatus:'unreviewed'})
  fireEvent.change(screen.getByLabelText('复盘状态'),{target:{value:'useful'}})
  expect(props.onAnalysisReviewDraftChange).toHaveBeenCalledWith({userNotes:'',reviewStatus:'useful'})
  for(const [status,label] of [['useful','有用'],['rejected','弃用']] as const) {
    page.rerender(<AnalysisHistoryPage {...props} analysisRuns={[{...analysis,reviewStatus:status}]}/>)
    expect(within(screen.getByRole('button',{name:/账号诊断 已完成/})).getByText(label)).toBeVisible()
  }
  expect(analysis.reviewStatus).toBe('unreviewed')
})

it('keeps one on-demand provenance hint in the ordinary account output panel',()=>{
  const views=stageSeedFromRun(analysis)
  expect(views.map(stage=>stage.key)).toEqual(['profile'])
  const props={targetTab:'account' as const,views,outputKind:'analysis' as const,runError:'',renderStageResult:()=>null}
  const page=render(<WorkflowOutputPanel {...props}/>)
  expect(screen.queryByText('预写示例')).not.toBeInTheDocument()
  expect(screen.queryByText(/人工编排/)).not.toBeInTheDocument()
  expect(screen.getAllByRole('button',{name:'记录来源说明'})).toHaveLength(1)
  fireEvent.click(screen.getByRole('button',{name:'记录来源说明'}))
  expect(screen.getByRole('tooltip')).toHaveTextContent('未调用模型')
  expect(screen.queryByText('读者反馈')).not.toBeInTheDocument()
  expect(screen.queryByText('下一步 · 选题建议')).not.toBeInTheDocument()
  expect(screen.queryByText('等待中')).not.toBeInTheDocument()
  const normalViews=stageSeedFromRun({...analysis,modelMetadata:{}})
  expect(normalViews.map(stage=>stage.key)).toEqual(['profile','pain_points','topics'])
  page.rerender(<WorkflowOutputPanel {...props} views={normalViews}/>)
  expect(screen.queryByText('预写示例')).not.toBeInTheDocument()
  expect(screen.queryByRole('button',{name:'记录来源说明'})).not.toBeInTheDocument()
  expect(screen.getByText('读者反馈')).toBeVisible()
  expect(screen.getAllByText('等待中')).toHaveLength(2)
})

it('removes simulation labels while preserving its target, provenance hint and read-only behavior',()=>{
  render(<SimulationHistoryPage publicMode simulationRuns={[{...simulation,origin:'oracle_showcase'}]} selectedSimulationRun={simulation}
    simulationReviewDraft={{userNotes:'',reviewStatus:'unreviewed'}} simulationReviewSaveState={idle}
    reviewStatusLabel={()=>'未复盘'} onOpenSimulationRun={vi.fn()} onSimulationReviewDraftChange={vi.fn()}
    onSaveSimulationRunReview={vi.fn()} stageSeedFromSimulation={()=>[]} renderStageResult={()=>null}/>)
  expect(screen.queryByText('预写示例')).not.toBeInTheDocument()
  expect(screen.queryByText(/人工编排/)).not.toBeInTheDocument()
  const row=screen.getByRole('button',{name:/本账号已经发布的一篇笔记/})
  expect(within(row).queryByText('预写示例')).not.toBeInTheDocument()
  expect(within(row).queryByRole('button')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'记录来源说明'}))
  expect(screen.getByRole('tooltip')).toHaveTextContent('基于本账号已保存笔记人工编排，未调用模型。')
  expect(screen.queryByLabelText('作者追问')).not.toBeInTheDocument()
})

it('puts prewritten reader settings behind one disclosure without hiding the conversation',()=>{
  const run:SimulationRun={...simulation,personaDefinitions:[{id:'r',name:'先算投入'}],
    reactionResults:[{personaId:'r',quote:'我会先看看这一步需要多少时间。'}],
    inputSnapshot:{readerSelection:{source:'oracle_showcase',actualFanIds:['r'],proposedReaders:[]}}}
  const props={publicMode:true,simulationRuns:[run],selectedSimulationRun:run,
    simulationReviewDraft:{userNotes:'',reviewStatus:'unreviewed' as const},simulationReviewSaveState:idle,
    reviewStatusLabel:()=> '未复盘',onOpenSimulationRun:vi.fn(),onSimulationReviewDraftChange:vi.fn(),
    onSaveSimulationRunReview:vi.fn(),stageSeedFromSimulation:()=>[],renderStageResult:()=>null}
  const page=render(<SimulationHistoryPage {...props}/>)
  const settings=screen.getByText('本次读者与设置',{selector:'summary'})
  expect(settings.closest('details')).not.toHaveAttribute('open')
  expect(screen.getByText('我会先看看这一步需要多少时间。')).toBeVisible()
  expect(screen.getByText('实际参与者')).not.toBeVisible()
  fireEvent.click(settings)
  expect(screen.getByText('实际参与者')).toBeVisible()
  expect(screen.getByText('本次未执行读者推荐')).toBeVisible()
  fireEvent.click(screen.getByText('复盘备注',{selector:'summary'}))
  fireEvent.change(screen.getByLabelText('复盘备注'),{target:{value:'下次保留这个视角'}})
  expect(props.onSimulationReviewDraftChange).toHaveBeenCalledWith({userNotes:'下次保留这个视角',reviewStatus:'unreviewed'})
  page.rerender(<SimulationHistoryPage {...props} simulationReviewDraft={{userNotes:'下次保留这个视角',reviewStatus:'unreviewed'}}/>)
  fireEvent.click(screen.getByText(/本次读者与设置/,{selector:'summary'}))
  expect(screen.getByText(/复盘未保存/)).toBeVisible()
  fireEvent.click(screen.getByText(/本次读者与设置/,{selector:'summary'}))
  expect(screen.getByLabelText('复盘备注')).toHaveValue('下次保留这个视角')
  fireEvent.click(screen.getByRole('button',{name:'保存复盘'}))
  expect(props.onSaveSimulationRunReview).toHaveBeenCalledOnce()
  page.rerender(<SimulationHistoryPage {...props} selectedSimulationRun={{...run,id:'different'}}/>)
  expect(screen.getByText('本次读者与设置',{selector:'summary'}).closest('details')).not.toHaveAttribute('open')
})

it('shows frozen account source notes in public history without exposing raw payloads',()=>{
  const body='原始第一段。\n\n保留所有正文和换行。'
  const run={...analysis,inputSnapshot:{xhsCreatorProfile:{notes:[{noteId:'n',title:'本次冻结的真实笔记',desc:body}]}}}
  const props={publicMode:true,analysisRuns:[run],selectedRun:run,
    analysisReviewDraft:{userNotes:'',reviewStatus:'unreviewed' as const},analysisReviewSaveState:idle,
    renderStageResult:()=>null,onOpenRun:vi.fn(),onAnalysisReviewDraftChange:vi.fn(),onSaveAnalysisRunReview:vi.fn()}
  const page=render(<AnalysisHistoryPage {...props}/>)
  expect(screen.getAllByText('已完成',{exact:false}).length).toBeGreaterThan(0)
  expect(screen.queryByText(/completed/)).not.toBeInTheDocument()
  expect(screen.queryByRole('button',{name:'在输出区打开'})).not.toBeInTheDocument()
  expect(screen.queryByText('未保存笔记正文')).not.toBeInTheDocument()
  fireEvent.click(screen.getByText('本次分析的材料'))
  expect(screen.getByText('本次冻结的真实笔记')).toBeVisible()
  expect(screen.getByText(/原始第一段/).textContent).toBe(body)
  page.rerender(<AnalysisHistoryPage {...props} selectedRun={{...run,inputSnapshot:{historicalPosts:{content:'旧格式的完整正文'}}}}/>)
  expect(screen.getByText('旧格式的完整正文')).toBeVisible()
  page.rerender(<AnalysisHistoryPage {...props} publicMode={false}/>)
  expect(screen.getByRole('button',{name:'在输出区打开'})).toBeVisible()
  expect(screen.getByText(/"xhsCreatorProfile"/)).toBeVisible()
})

it('opens only the frozen published note and does not carry an open source across simulations',()=>{
  const body='冻结正文的第一段。\n\n保留当时的完整笔记。'
  const run={...simulation,inputSnapshot:{sourceNote:{title:'这次实际读的原题',body},topic:{title:'不要使用这个副本',body:'不应冒充原文的摘要'}}}
  const props={publicMode:true,simulationRuns:[run],selectedSimulationRun:run,
    simulationReviewDraft:{userNotes:'',reviewStatus:'unreviewed' as const},simulationReviewSaveState:idle,
    reviewStatusLabel:()=> '未复盘',onOpenSimulationRun:vi.fn(),onSimulationReviewDraftChange:vi.fn(),
    onSaveSimulationRunReview:vi.fn(),stageSeedFromSimulation:()=>[],renderStageResult:()=>null}
  const page=render(<SimulationHistoryPage {...props}/>)
  expect(screen.getByText(/冻结正文/)).not.toBeVisible()
  fireEvent.click(screen.getByText('查看本次笔记'))
  expect(screen.getByRole('article',{name:'本次笔记原文'})).toBeVisible()
  expect(screen.getByText(/冻结正文/).textContent).toBe(body)
  expect(screen.getByText('这次实际读的原题')).toBeVisible()
  expect(screen.queryByText('不应冒充原文的摘要')).not.toBeInTheDocument()
  page.rerender(<SimulationHistoryPage {...props} selectedSimulationRun={{...run,id:'other',inputSnapshot:{sourceNote:{title:'另一篇真实笔记',body:'另一篇的完整正文'}}}}/>)
  expect(screen.queryByText(/冻结正文/)).not.toBeInTheDocument()
  expect(screen.getByText('查看本次笔记').closest('details')).not.toHaveAttribute('open')
  fireEvent.click(screen.getByText('查看本次笔记'))
  expect(screen.getByText('另一篇的完整正文')).toBeVisible()
  page.rerender(<SimulationHistoryPage {...props} selectedSimulationRun={{...run,id:'legacy',inputSnapshot:{topic:{body:'不是来源的内容'}}}}/>)
  fireEvent.click(screen.getByText('查看本次笔记'))
  expect(screen.getByText('这条历史记录未保存笔记正文。')).toBeVisible()
  expect(screen.queryByText('不是来源的内容')).not.toBeInTheDocument()
})
