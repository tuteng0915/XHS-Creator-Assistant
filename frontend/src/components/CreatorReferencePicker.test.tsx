import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react'
import {afterEach, beforeEach, expect, it, vi} from 'vitest'
import {analysisRunApi, audienceAnalysisApi} from '../api'
import {emptyCreatorContext, type CreatorContextSelection} from '../contentCollaboration'
import type {AnalysisRun, AudienceAnalysis} from '../types'
import {CreatorReferencePicker} from './CreatorReferencePicker'

vi.mock('../api', () => ({analysisRunApi: {list: vi.fn(), get: vi.fn()}, audienceAnalysisApi: {list: vi.fn(), get: vi.fn()}}))
afterEach(cleanup)
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(analysisRunApi.list).mockResolvedValue([])
  vi.mocked(audienceAnalysisApi.list).mockResolvedValue([])
})
function account(id = 'account-1', overrides: Partial<AnalysisRun> = {}): AnalysisRun {
  return {id, workspaceId: 'workspace-1', workflowType: 'account_diagnosis', status: 'completed', userNotes: '',
    reviewStatus: 'unreviewed', createdAt: '2026-10-10T10:00:00Z', startedAt: null, completedAt: null,
    updatedAt: '2026-10-10T10:01:00Z', inputSnapshot: {analysisRange: {selectedNoteCount: 4}},
    stageResults: {profile: {profile: {accountPortrait: {summary: {statement: `${id} 的保存结论`}}}}},
    stageErrors: {}, modelMetadata: {}, ...overrides}
}
function audience(id = 'audience-1', overrides: Partial<AudienceAnalysis> = {}): AudienceAnalysis {
  return {id, workspaceId: 'workspace-1', sourceMaterialId: 'material-1', status: 'completed',
    inputSnapshot: {scope: {scope: 'all', selectedNoteCount: 4}}, createdAt: '2026-10-10T10:00:00Z', error: '',
    result: {summary: '关注不同决策条件', groups: [{id: 'reader-1', name: '先看成本', coreConcern: '能不能省时间', profile: '时间有限', evidence: []}]}, ...overrides}
}
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => {resolve = done})
  return {promise, resolve}
}
function setup(selection: CreatorContextSelection = emptyCreatorContext(), disabled = false) {
  const onChange = vi.fn()
  const view = render(<CreatorReferencePicker workspaceId="workspace-1" selection={selection} onChange={onChange} disabled={disabled} />)
  return {...view, onChange}
}
async function openPicker() {
  fireEvent.click(screen.getByRole('button', {name: '＋ 添加参考'}))
  await waitFor(() => expect(screen.getByRole('combobox', {name: '分析记录'})).not.toBeDisabled())
}
function choose(id: string) {fireEvent.change(screen.getByRole('combobox', {name: '分析记录'}), {target: {value: id}})}

it('starts with no implicit references and lists only completed account analyses for the active workspace', async () => {
  vi.mocked(analysisRunApi.list).mockResolvedValue([account(), account('running', {status: 'running'}),
    account('trend', {workflowType: 'trend_analysis'}), account('foreign', {workspaceId: 'workspace-2'})])
  const {onChange} = setup()
  expect(screen.getByText('只参考当前稿件与这段对话。')).toBeInTheDocument()
  expect(analysisRunApi.list).not.toHaveBeenCalled()
  await openPicker()
  const values = within(screen.getByRole('combobox', {name: '分析记录'})).getAllByRole('option').map(option => (option as HTMLOptionElement).value)
  expect(values).toEqual(['', 'account-1'])
  expect(screen.getByRole('button', {name: '添加这份材料'})).toBeDisabled()
  expect(onChange).not.toHaveBeenCalled()
})

it('previews saved content and cancels without committing a reference', async () => {
  vi.mocked(analysisRunApi.list).mockResolvedValue([account()])
  vi.mocked(analysisRunApi.get).mockResolvedValue(account())
  const {onChange} = setup()
  await openPicker(); choose('account-1')
  expect(await screen.findByText('account-1 的保存结论')).toBeInTheDocument()
  expect(screen.getByText('4 篇笔记')).toBeInTheDocument()
  expect(onChange).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', {name: '取消'}))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(onChange).not.toHaveBeenCalled()
})

it('adds an exact audience record only on confirmation and keeps account and audience choices separate', async () => {
  vi.mocked(audienceAnalysisApi.list).mockResolvedValue([audience(), audience('failed', {status: 'failed'}), audience('foreign', {workspaceId: 'workspace-2'})])
  vi.mocked(audienceAnalysisApi.get).mockResolvedValue(audience())
  const {onChange} = setup()
  await openPicker()
  fireEvent.change(screen.getByRole('combobox', {name: '资料类型'}), {target: {value: 'audience_analysis'}})
  await waitFor(() => expect(within(screen.getByRole('combobox', {name: '分析记录'})).getAllByRole('option')).toHaveLength(2))
  choose('audience-1')
  expect(await screen.findByText('先看成本 · 能不能省时间')).toBeInTheDocument()
  expect(onChange).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', {name: '添加这份材料'}))
  expect(onChange).toHaveBeenCalledExactlyOnceWith({...emptyCreatorContext(), references: [{kind: 'audience_analysis', id: 'audience-1'}]})
  expect(analysisRunApi.get).not.toHaveBeenCalled()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})

it('prevents duplicate additions and removes only the chosen reference', async () => {
  vi.mocked(analysisRunApi.list).mockResolvedValue([account()])
  vi.mocked(analysisRunApi.get).mockResolvedValue(account())
  const selection: CreatorContextSelection = {...emptyCreatorContext(), references: [{kind: 'account_analysis', id: 'account-1'}]}
  const {onChange} = setup(selection)
  await openPicker(); choose('account-1')
  expect(await screen.findByRole('button', {name: '已添加'})).toBeDisabled()
  expect(onChange).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', {name: '取消'}))
  fireEvent.click(screen.getByRole('button', {name: /^移除账号分析/}))
  expect(onChange).toHaveBeenCalledExactlyOnceWith(emptyCreatorContext())
})

it('keeps missing selected references removable and gives an error when previewed', async () => {
  vi.mocked(analysisRunApi.get).mockRejectedValue(new Error('原记录已删除'))
  const {onChange} = setup({...emptyCreatorContext(), references: [{kind: 'account_analysis', id: 'missing'}]})
  fireEvent.click(screen.getByRole('button', {name: '账号分析 1'}))
  expect(await screen.findByRole('alert')).toHaveTextContent('原记录已删除')
  fireEvent(screen.getByRole('dialog'), new Event('cancel', {bubbles: true, cancelable: true}))
  fireEvent.click(screen.getByRole('button', {name: '移除账号分析 1'}))
  expect(onChange).toHaveBeenCalledWith(emptyCreatorContext())
})

it('retries a failed list load and does not turn a transport failure into an empty state', async () => {
  vi.mocked(analysisRunApi.list).mockRejectedValueOnce(new Error('网络暂不可用')).mockResolvedValueOnce([account()])
  setup(); await openPicker()
  expect(await screen.findByRole('alert')).toHaveTextContent('网络暂不可用')
  expect(screen.queryByText(/还没有已完成/)).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', {name: '重试读取'}))
  await waitFor(() => expect(within(screen.getByRole('combobox', {name: '分析记录'})).getAllByRole('option')).toHaveLength(2))
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

it('retries the same chosen preview after a detail load failure', async () => {
  vi.mocked(analysisRunApi.list).mockResolvedValue([account()])
  vi.mocked(analysisRunApi.get).mockRejectedValueOnce(new Error('读取中断')).mockResolvedValueOnce(account())
  setup(); await openPicker(); choose('account-1')
  expect(await screen.findByRole('alert')).toHaveTextContent('读取中断')
  fireEvent.click(screen.getByRole('button', {name: '重试读取'}))
  expect(await screen.findByText('account-1 的保存结论')).toBeInTheDocument()
  expect(screen.getByRole('combobox', {name: '分析记录'})).toHaveValue('account-1')
})

it('ignores a slow previous preview when the author has selected another record', async () => {
  const slow = deferred<AnalysisRun>()
  vi.mocked(analysisRunApi.list).mockResolvedValue([account('a'), account('b')])
  vi.mocked(analysisRunApi.get).mockImplementation(id => id === 'a' ? slow.promise : Promise.resolve(account('b')))
  setup(); await openPicker(); choose('a'); choose('b')
  expect(await screen.findByText('b 的保存结论')).toBeInTheDocument()
  await act(async () => {slow.resolve(account('a')); await slow.promise})
  expect(screen.getByText('b 的保存结论')).toBeInTheDocument()
  expect(screen.queryByText('a 的保存结论')).not.toBeInTheDocument()
})

it('does not display a detail response belonging to another workspace', async () => {
  vi.mocked(analysisRunApi.list).mockResolvedValue([account()])
  vi.mocked(analysisRunApi.get).mockResolvedValue(account('account-1', {workspaceId: 'workspace-2'}))
  const {onChange} = setup(); await openPicker(); choose('account-1')
  expect(await screen.findByRole('alert')).toHaveTextContent('不可用')
  expect(screen.queryByRole('region', {name: '参考摘要'})).not.toBeInTheDocument()
  expect(screen.queryByText('account-1 的保存结论')).not.toBeInTheDocument()
  expect(screen.getByRole('button', {name: '添加这份材料'})).toBeDisabled()
  expect(onChange).not.toHaveBeenCalled()
})

it('ignores a late list response after switching workspaces', async () => {
  const slow = deferred<AnalysisRun[]>()
  vi.mocked(analysisRunApi.list).mockImplementation(id => id === 'workspace-1' ? slow.promise
    : Promise.resolve([account('account-2', {workspaceId: 'workspace-2'})]))
  const {rerender, onChange} = setup()
  fireEvent.click(screen.getByRole('button', {name: '＋ 添加参考'}))
  rerender(<CreatorReferencePicker workspaceId="workspace-2" selection={emptyCreatorContext()} onChange={onChange} disabled={false} />)
  await waitFor(() => expect(within(screen.getByRole('combobox', {name: '分析记录'})).getAllByRole('option')).toHaveLength(2))
  await act(async () => {slow.resolve([account('account-1')]); await slow.promise})
  const values = within(screen.getByRole('combobox', {name: '分析记录'})).getAllByRole('option').map(option => (option as HTMLOptionElement).value)
  expect(values).toEqual(['', 'account-2'])
  expect(onChange).not.toHaveBeenCalled()
})

it('caps the reference set at eight while allowing removals, and locks changes during a run', () => {
  vi.mocked(analysisRunApi.get).mockRejectedValue(new Error('not loaded'))
  const selection: CreatorContextSelection = {...emptyCreatorContext(), references: Array.from({length: 8}, (_, index) => ({kind: 'account_analysis', id: `a-${index}`}))}
  const {rerender, onChange} = setup(selection)
  expect(screen.getByRole('button', {name: '＋ 添加参考'})).toBeDisabled()
  expect(screen.getAllByRole('button', {name: /^移除/})).toHaveLength(8)
  expect(screen.getAllByRole('button', {name: /^移除/})[0]).not.toBeDisabled()
  rerender(<CreatorReferencePicker workspaceId="workspace-1" selection={selection} onChange={onChange} disabled />)
  for (const button of screen.getAllByRole('button', {name: /^移除/})) expect(button).toBeDisabled()
})
