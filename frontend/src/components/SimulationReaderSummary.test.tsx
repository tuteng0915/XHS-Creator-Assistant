import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { SimulationRun } from '../types'
import { SimulationReaderSummary } from './SimulationReaderSummary'
import { SimulationHistoryPage } from './SimulationHistoryPage'

afterEach(cleanup)
const run:SimulationRun = {
  id:'run',workspaceId:'w',topicId:null,draftId:null,status:'completed',
  inputSnapshot:{audiencePersonas:[{id:'b',name:'当时的行动派'}],readerSelection:{source:'adjusted',proposedReaders:[{fanId:'a',name:'当时的核对派',fitReason:'先考虑投入，再决定行动。',contribution:'提供另一种判断。'}],actualFanIds:['b']}},
  personaDefinitions:[{id:'b',name:'当时的行动派'}],reactionResults:[],debateResults:[],synthesis:{},stageErrors:{},modelMetadata:{},userNotes:'',reviewStatus:'unreviewed',createdAt:'2026-10-03',updatedAt:'2026-10-03',startedAt:null,completedAt:null,
}

it('distinguishes proposed from actual readers and collapses historical reasons', () => {
  render(<SimulationReaderSummary run={run} />)
  expect(screen.getByText('推荐后调整')).toBeInTheDocument()
  expect(screen.getByText('当时的核对派')).toBeInTheDocument()
  expect(screen.getByText('当时的行动派')).toBeInTheDocument()
  expect(screen.getByText(/未选用/)).toBeInTheDocument()
  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  fireEvent.focus(screen.getByRole('button',{name:'读者名单说明'}))
  expect(screen.getByRole('tooltip')).toHaveTextContent('按本次保存的名单展示，反应是否完成见下方结果。')
  fireEvent.blur(screen.getByRole('button',{name:'读者名单说明'}))
  expect(screen.getByText('先考虑投入，再决定行动。')).not.toBeVisible()
  fireEvent.click(screen.getByText('推荐理由'))
  expect(screen.getByText('先考虑投入，再决定行动。')).toBeVisible()
})

it('shows the frozen session-only persona adjustment without reading current assets',()=>{
  render(<SimulationReaderSummary run={{...run,inputSnapshot:{...run.inputSnapshot,personaOverrides:{b:{coreConcern:'想先知道能不能在下班后开始'}}}}}/>)
  expect(screen.getByText('本次画像已调整')).toBeVisible()
  expect(screen.getByText('想先知道能不能在下班后开始')).not.toBeVisible()
  fireEvent.click(screen.getByText('本次画像已调整'))
  expect(screen.getByText('想先知道能不能在下班后开始')).toBeVisible()
  expect(screen.getByText('仅用于这次讨论，未修改长期读者画像。')).toBeVisible()
})

it('uses frozen participant names for old recommendations but does not invent omitted names', () => {
  render(<SimulationReaderSummary run={{...run,inputSnapshot:{readerSelection:{source:'recommended',proposedReaders:[{fanId:'b'},{fanId:'gone'}],actualFanIds:['b']}}}} />)
  expect(screen.getAllByText('当时的行动派')).toHaveLength(2)
  expect(screen.getByText('读者 2（姓名未保存）')).toBeInTheDocument()
})

it('distinguishes manual selection from histories with no source record', () => {
  const {rerender} = render(<SimulationReaderSummary run={{...run,inputSnapshot:{readerSelection:{source:'manual',actualFanIds:['b']}}}} />)
  expect(screen.getByText('本次未使用推荐')).toBeInTheDocument()
  rerender(<SimulationReaderSummary run={{...run,inputSnapshot:{}}} />)
  expect(screen.getByText('旧记录未保存选择方式')).toBeInTheDocument()
  expect(screen.getByText('此记录未保存推荐名单')).toBeInTheDocument()
  expect(screen.getByText('当时的行动派')).toBeInTheDocument()
  expect(screen.queryByText('手动选择')).not.toBeInTheDocument()
})

it('shows a saved participant list without an example label or invented recommendation',()=>{
  render(<SimulationReaderSummary run={{...run,inputSnapshot:{readerSelection:{source:'oracle_showcase',proposedReaders:[],actualFanIds:['b']}}}}/>)
  expect(screen.queryByText(/预写示例/)).not.toBeInTheDocument()
  expect(screen.getByText('已保存名单')).toBeVisible()
  expect(screen.getByText('本次未执行读者推荐')).toBeVisible()
  expect(screen.getByText('当时的行动派')).toBeVisible()
  expect(screen.queryByText(/推荐后调整|使用推荐|手动选择|旧记录未保存选择方式/)).not.toBeInTheDocument()
})

it('does not overwrite actual definitions with the recommended name if historical snapshots differ', () => {
  render(<SimulationReaderSummary run={{...run,inputSnapshot:{readerSelection:{source:'recommended',proposedReaders:[{fanId:'b',name:'推荐时的名字'}],actualFanIds:['b']}}}} />)
  expect(screen.getByText('推荐时的名字')).toBeInTheDocument()
  expect(screen.getByText('当时的行动派')).toBeInTheDocument()
})

it('keeps selection order, disambiguates duplicate names, and handles not-started runs', () => {
  render(<SimulationReaderSummary run={{...run,personaDefinitions:[],inputSnapshot:{audiencePersonas:[{id:'a',name:'观察者'},{id:'b',name:'观察者'}],readerSelection:{source:'manual',actualFanIds:['b','a']}}}} />)
  expect(screen.getByText('本次选择')).toBeInTheDocument()
  expect(screen.queryByText('实际参与者')).not.toBeInTheDocument()
  expect(screen.getAllByRole('listitem').map(el=>el.textContent)).toEqual(['观察者（1）','观察者（2）'])
})

it('handles empty or malformed legacy selection without making a recommendation', () => {
  render(<SimulationReaderSummary run={{...run,personaDefinitions:[],inputSnapshot:{readerSelection:{proposedReaders:[null,3,{}],actualFanIds:null}}}} />)
  expect(screen.getByText('未保存参与者名单')).toBeInTheDocument()
  expect(screen.getByText('此记录未保存推荐名单')).toBeInTheDocument()
})

it('history page resets expanded reasons when switching runs and uses only its frozen props', () => {
  const props = {publicMode:true,simulationRuns:[],selectedSimulationRun:run,simulationReviewDraft:{reviewStatus:'unreviewed' as const,userNotes:''},simulationReviewSaveState:{phase:'idle' as const},reviewStatusLabel:(s:string)=>s,onOpenSimulationRun:vi.fn(),onSimulationReviewDraftChange:vi.fn(),onSaveSimulationRunReview:vi.fn(),stageSeedFromSimulation:()=>[],renderStageResult:()=>null}
  const {rerender} = render(<SimulationHistoryPage {...props} />)
  expect(screen.getByLabelText('本次参与读者')).toHaveTextContent('当时的行动派')
  expect(screen.getByText('先考虑投入，再决定行动。')).not.toBeVisible()
  expect(screen.getByRole('region',{name:'读者试读群聊'}).compareDocumentPosition(screen.getByText('推荐依据与备注',{selector:'summary'}))&Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(screen.queryByText('实际参与者')).not.toBeInTheDocument()
  fireEvent.click(screen.getByText('推荐依据与备注',{selector:'summary'}))
  expect(screen.queryByText('推荐理由',{selector:'summary'})).not.toBeInTheDocument()
  expect(screen.getByText('先考虑投入，再决定行动。')).toBeVisible()
  rerender(<SimulationHistoryPage {...props} selectedSimulationRun={{...run,id:'other',personaDefinitions:[{id:'b',name:'另一运行的名字'}]}} />)
  expect(screen.getByText('先考虑投入，再决定行动。')).not.toBeVisible()
  expect(screen.getByLabelText('本次参与读者')).toHaveTextContent('另一运行的名字')
  expect(screen.queryByText('当时的行动派')).not.toBeInTheDocument()
})

it('keeps not-yet-started selections distinct from actual participation in compact history',()=>{
  render(<SimulationReaderSummary variant="compact" run={{...run,status:'pending',personaDefinitions:[]}}/>)
  expect(screen.getByText('已选读者')).toBeVisible()
  expect(screen.queryByText('参与读者')).not.toBeInTheDocument()
  expect(screen.getByLabelText('本次参与读者')).toHaveTextContent('当时的行动派')
})
