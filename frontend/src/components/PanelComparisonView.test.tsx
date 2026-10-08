import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react'
import {afterEach, expect, it, vi} from 'vitest'
import {simulationRunApi} from '../api'
import type {PanelComparison, PanelReadingSide, SimulationRun} from '../types'
import {PanelComparisonView} from './PanelComparisonView'

afterEach(() => {cleanup(); vi.restoreAllMocks()})
const run = {id:'child', parentSimulationId:'parent', workspaceId:'w',status:'completed'} as SimulationRun
const side:PanelReadingSide = {initialStatus:'comment',understanding:'理解了第一步',stance:'愿意试试',quote:'我今晚试一下',
  concerns:['需要一个例子'],opportunities:['行动成本低'],replyStatus:'disabled',reply:'',newConcerns:[],strongerSignals:[],changeReason:''}
const info = {status:'completed' as const,createdAt:'2026-10-05T00:00:00Z',title:'练习',body:'从一句话开始。',mode:'live',recordedModels:[]}
const data:PanelComparison = {workspaceId:'w',simulationId:'child',parentSimulationId:'parent',
  before:{...info,id:'parent'}, after:{...info,id:'child',body:'先写一句话，记录具体场景。'},
  readers:[{id:'a',name:'先尝试的读者',profile:'愿意先做一小步',before:side,after:{...side,initialStatus:'no_comment',quote:'',concerns:[]}}],
  limitations:['固定人物不保证反应相同。']}

it('loads only on request and separates private concerns, public quotes, and silence',async () => {
  const api=vi.spyOn(simulationRunApi,'comparison').mockResolvedValue(data)
  render(<PanelComparisonView run={run}/>)
  expect(api).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button',{name:'逐人前后对照'}))
  expect(await screen.findByText('先尝试的读者')).toBeVisible()
  fireEvent.click(screen.getByText('先尝试的读者'))
  const before=within(screen.getByRole('region',{name:'上次试读'})), after=within(screen.getByRole('region',{name:'本次复测'}))
  expect(before.getByText('我今晚试一下')).toBeVisible()
  expect(after.queryByText('我今晚试一下')).not.toBeInTheDocument()
  expect(after.getByText('读后未留言')).toBeVisible()
  expect(screen.getByText(/新版未提及不等于已经解决/)).toBeVisible()
  expect(before.getByText('需要一个例子')).toBeVisible()
  expect(screen.getAllByText(/未开启互相回应/)).toHaveLength(2)
  fireEvent.click(screen.getByText('两版稿件与模型记录'))
  expect(screen.getAllByText('未保存实际模型与系统提示信息')).toHaveLength(2)
})

it('allows read retry without creating a run',async () => {
  const api=vi.spyOn(simulationRunApi,'comparison').mockRejectedValueOnce(new Error('读取中断')).mockResolvedValue(data)
  const create=vi.spyOn(simulationRunApi,'createRetest')
  render(<PanelComparisonView run={run}/>)
  fireEvent.click(screen.getByRole('button',{name:'逐人前后对照'}))
  expect(await screen.findByRole('alert')).toHaveTextContent('读取中断')
  fireEvent.click(screen.getByRole('button',{name:'重新读取对照'}))
  await screen.findByText('先尝试的读者')
  expect(api).toHaveBeenCalledTimes(2)
  expect(create).not.toHaveBeenCalled()
})

it('rejects another workspace or parent receipt',async () => {
  vi.spyOn(simulationRunApi,'comparison').mockResolvedValue({...data,parentSimulationId:'other'})
  render(<PanelComparisonView run={run}/>)
  fireEvent.click(screen.getByRole('button',{name:'逐人前后对照'}))
  expect(await screen.findByRole('alert')).toHaveTextContent('不属于当前试读')
  expect(screen.queryByText('先尝试的读者')).not.toBeInTheDocument()
})

it('discards a delayed response after close and a newer open',async () => {
  let resolve!:(value:PanelComparison)=>void
  vi.spyOn(simulationRunApi,'comparison').mockReturnValueOnce(new Promise(yes=>{resolve=yes})).mockResolvedValue(data)
  render(<PanelComparisonView run={run}/>)
  fireEvent.click(screen.getByRole('button',{name:'逐人前后对照'}))
  fireEvent.click(screen.getByRole('button',{name:'关闭'}))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'逐人前后对照'}))
  await screen.findByText('先尝试的读者')
  await act(async()=>resolve({...data,readers:[]}))
  expect(screen.getByText('先尝试的读者')).toBeVisible()
})

it('blocks unfinished runs and does not reuse another run dialog',async () => {
  const api=vi.spyOn(simulationRunApi,'comparison').mockResolvedValue(data)
  const page=render(<PanelComparisonView key="child" run={{...run,status:'running'}}/>)
  expect(screen.getByRole('button',{name:'逐人前后对照'})).toBeDisabled()
  expect(api).not.toHaveBeenCalled()
  page.rerender(<PanelComparisonView key="child" run={run}/>)
  fireEvent.click(screen.getByRole('button',{name:'逐人前后对照'}))
  await screen.findByText('先尝试的读者')
  page.rerender(<PanelComparisonView key="other" run={{...run,id:'other'}}/>)
  await waitFor(()=>expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
})
