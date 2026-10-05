import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
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
  expect(screen.getByText('先考虑投入，再决定行动。')).not.toBeVisible()
  fireEvent.click(screen.getByText('推荐理由'))
  expect(screen.getByText('先考虑投入，再决定行动。')).toBeVisible()
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
  fireEvent.click(screen.getByText('推荐理由'))
  expect(screen.getByText('先考虑投入，再决定行动。')).toBeVisible()
  rerender(<SimulationHistoryPage {...props} selectedSimulationRun={{...run,id:'other',personaDefinitions:[{id:'b',name:'另一运行的名字'}]}} />)
  expect(screen.getByText('先考虑投入，再决定行动。')).not.toBeVisible()
  const section = screen.getByRole('region',{name:'本次读者选择'})
  expect(within(section).getByText('另一运行的名字')).toBeInTheDocument()
  expect(screen.queryByText('当时的行动派')).not.toBeInTheDocument()
})
