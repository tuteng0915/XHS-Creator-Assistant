import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
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

it('allows choosing up to three active profiles and excludes archived profiles', () => {
  const rows = Array.from({length:5},(_,i) => ({...fan,id:String(i),editable:{...fan.editable,name:`粉丝${i}`},status:i===4 ? 'archived' as const : 'active' as const}))
  const toggle = vi.fn()
  render(<SimulatedFanPicker rows={rows} ids={['0','1','2']} onToggle={toggle} />)
  expect(screen.getByLabelText('粉丝0')).toBeChecked()
  expect(screen.getByLabelText('粉丝3')).toBeDisabled()
  expect(screen.queryByLabelText('粉丝4')).not.toBeInTheDocument()
  fireEvent.click(screen.getByLabelText('粉丝1'))
  expect(toggle).toHaveBeenCalledWith('1')
})
