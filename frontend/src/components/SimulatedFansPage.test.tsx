import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { simulatedFanApi } from '../api'
import type { SimulatedFan } from '../types'
import { SimulatedFanPicker, SimulatedFansPage } from './SimulatedFansPage'

const fan: SimulatedFan = {id:'f',workspaceId:'w',sourceAnalysisId:'a',sourceGroupId:'g',original:{profile:'原始视角',unknowns:['身份未知']},editable:{name:'费用观察员',profile:'关心预算',coreConcern:'费用口径',contentPreference:'清单',expressionStyle:''},status:'active',createdAt:'2026-09-28',updatedAt:'2026-09-28'}
afterEach(() => {cleanup();vi.restoreAllMocks()})

it('distinguishes curated presets from model analyses', () => {
  render(<SimulatedFansPage rows={[{...fan,original:{...fan.original,origin:'curated_preset'}}]} error="" onRefresh={vi.fn()} onAnalyze={vi.fn()} />)
  expect(screen.getByText('预置整理 · 可用于模拟')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:/费用观察员/}))
  expect(screen.getByText(/非模型接口分析/)).toBeInTheDocument()
})

it('opens an instance and explicitly saves edits with optimistic concurrency', async () => {
  const refresh = vi.fn()
  const update = vi.spyOn(simulatedFanApi,'update').mockResolvedValue({...fan,editable:{...fan.editable,name:'新名称'},updatedAt:'2026-09-29'})
  render(<SimulatedFansPage rows={[fan]} error="" onRefresh={refresh} onAnalyze={vi.fn()} />)
  expect(screen.queryByLabelText('名称')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:/费用观察员/}))
  fireEvent.change(screen.getByLabelText('名称'),{target:{value:'新名称'}})
  expect(update).not.toHaveBeenCalled()
  expect(screen.getByRole('button',{name:'归档'})).toBeDisabled()
  fireEvent.click(screen.getByRole('button',{name:'保存修改'}))
  await waitFor(() => expect(refresh).toHaveBeenCalledOnce())
  expect(update).toHaveBeenCalledWith('f',expect.objectContaining({name:'新名称',expectedUpdatedAt:fan.updatedAt,status:'active'}))
  expect(screen.getByText('已保存')).toBeInTheDocument()
})

it('keeps unsaved text on conflict and supports restoring archived profiles', async () => {
  vi.spyOn(simulatedFanApi,'update').mockRejectedValue(new Error('记录已被修改'))
  render(<SimulatedFansPage rows={[{...fan,status:'archived'}]} error="" onRefresh={vi.fn()} onAnalyze={vi.fn()} />)
  fireEvent.click(screen.getByRole('button',{name:/费用观察员/}))
  expect(screen.getByRole('button',{name:'恢复'})).toBeEnabled()
  fireEvent.change(screen.getByLabelText('阅读视角'),{target:{value:'我的修改'}})
  fireEvent.click(screen.getByRole('button',{name:'保存修改'}))
  await screen.findByRole('alert')
  expect(screen.getByLabelText('阅读视角')).toHaveValue('我的修改')
  expect(screen.getByText('保存失败')).toBeInTheDocument()
})

it('adds multiple distinct voices from one saved fan without editing it', async () => {
  const refresh = vi.fn().mockResolvedValue(undefined)
  vi.spyOn(simulatedFanApi,'voices').mockResolvedValue([
    {id:'action_first',name:'直球行动派',outlook:'先试',decisionStyle:'看步骤',expressionStyle:'直说',participationStyle:'提问'},
    {id:'fact_checker',name:'较真查证派',outlook:'先查',decisionStyle:'看依据',expressionStyle:'冷静',participationStyle:'追问'},
  ])
  const created = {...fan,id:'variant',editable:{...fan.editable,name:'较真查证派'}}
  const create = vi.spyOn(simulatedFanApi,'createVariants').mockResolvedValue([created])
  render(<SimulatedFansPage rows={[fan]} error="" onRefresh={refresh} onAnalyze={vi.fn()} />)
  fireEvent.click(screen.getByRole('button',{name:/费用观察员/}))
  fireEvent.click(screen.getByRole('button',{name:'添加不同声音'}))
  await screen.findByText('直球行动派')
  fireEvent.click(screen.getByRole('button',{name:'加入 2 位'}))
  await waitFor(() => expect(create).toHaveBeenCalledWith('f',['action_first','fact_checker']))
  expect(refresh).toHaveBeenCalledOnce()
})

it('shows three default dropdown slots and lets users add a fourth', () => {
  const rows = Array.from({length:5},(_,i) => ({...fan,id:String(i),editable:{...fan.editable,name:`粉丝${i}`},status:i===4 ? 'archived' as const : 'active' as const}))
  const change = vi.fn(), add = vi.fn(), remove = vi.fn()
  const props = {rows,slots:['0','1','2'],onSlotChange:change,onAddSlot:add,onRemoveSlot:remove}
  const {rerender} = render(<SimulatedFanPicker {...props} />)
  expect(screen.getAllByRole('combobox')).toHaveLength(3)
  expect(screen.getByRole('combobox',{name:'第 1 位模拟粉丝'})).toHaveValue('0')
  const first = screen.getByRole('combobox',{name:'第 1 位模拟粉丝'})
  expect(within(first).getByRole('option',{name:'粉丝1'})).toBeDisabled()
  expect(within(first).queryByRole('option',{name:'粉丝4'})).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'＋ 新增'}))
  expect(add).toHaveBeenCalledOnce()
  rerender(<SimulatedFanPicker {...props} slots={['0','1','2','']} />)
  fireEvent.change(screen.getByRole('combobox',{name:'第 4 位模拟粉丝'}),{target:{value:'3'}})
  expect(change).toHaveBeenCalledWith(3,'3')
  fireEvent.click(screen.getByRole('button',{name:'移除第 4 位'}))
  expect(remove).toHaveBeenCalledWith(3)
})
