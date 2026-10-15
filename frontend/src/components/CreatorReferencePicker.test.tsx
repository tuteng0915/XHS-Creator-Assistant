import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react'
import {afterEach, beforeEach, expect, it, vi} from 'vitest'
import {analysisRunApi, audienceAnalysisApi, inputAssetApi} from '../api'
import {emptyCreatorContext, type CreatorContextSelection} from '../contentCollaboration'
import type {AnalysisRun, AudienceAnalysis, MediaAsset, TextInputAsset} from '../types'
import {CreatorReferencePicker} from './CreatorReferencePicker'

vi.mock('../api', () => ({analysisRunApi: {list: vi.fn(), get: vi.fn()}, audienceAnalysisApi: {list: vi.fn(), get: vi.fn()}, inputAssetApi: {get: vi.fn()}}))
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
const importedNotes = [
  {noteId: 'saved-1', title: '第一篇原笔记', desc: '第一篇的完整正文\n保留第二段。', coverMediaAssetId: 'cover-1', metrics: {liked: 3}, comments: [{content: '不进入助手的评论'}]},
  {noteId: 'saved-2', title: '第二篇原笔记', desc: '第二篇的保存原文。', metrics: {liked: 2}, comments: []},
]
function profile(notes: unknown[] = importedNotes, overrides: Partial<TextInputAsset> = {}): TextInputAsset {
  return {id: 'profile-1', workspaceId: 'workspace-1', type: 'xhs_creator_profile', name: '保存的账号', createdAt: '', updatedAt: '', content: JSON.stringify({notes}), ...overrides}
}
const image: MediaAsset = {id: 'cover-1', workspaceId: 'workspace-1', type: 'image', name: '保存封面', purpose: 'reference', sourceType: 'upload',
  originalFilename: 'cover.jpg', mediaType: 'image/jpeg', byteSize: 1, sha256: '', metadata: {noteId: 'saved-1'}, derived: {}, userNotes: '',
  fileUrl: '/saved-cover.jpg', createdAt: '', updatedAt: ''}
function setup(selection: CreatorContextSelection = emptyCreatorContext(), disabled = false, source?: TextInputAsset, mediaAssets: MediaAsset[] = []) {
  const onChange = vi.fn()
  const view = render(<CreatorReferencePicker workspaceId="workspace-1" selection={selection} onChange={onChange} disabled={disabled} profile={source} mediaAssets={mediaAssets} />)
  return {...view, onChange}
}
async function openPicker() {
  fireEvent.click(screen.getByRole('button', {name: '＋ 添加参考'}))
  await waitFor(() => expect(screen.getByRole('combobox', {name: '分析记录'})).not.toBeDisabled())
}
function choose(id: string) {fireEvent.change(screen.getByRole('combobox', {name: '分析记录'}), {target: {value: id}})}
async function openNoteType() {
  fireEvent.click(screen.getByRole('button', {name: '＋ 添加参考'}))
  fireEvent.change(screen.getByRole('combobox', {name: '资料类型'}), {target: {value: 'imported_note'}})
  await screen.findByRole('region', {name: '原笔记参考'})
}
function openNoteSelection() {
  expect(screen.getAllByRole('dialog')).toHaveLength(1)
  expect(screen.queryByRole('button', {name: '选择原笔记'})).not.toBeInTheDocument()
  return screen.getByRole('dialog', {name: '添加参考'})
}

it('starts with no implicit references and lists only completed account analyses for the active workspace', async () => {
  vi.mocked(analysisRunApi.list).mockResolvedValue([account(), account('running', {status: 'running'}),
    account('trend', {workflowType: 'trend_analysis'}), account('foreign', {workspaceId: 'workspace-2'})])
  const {onChange} = setup()
  expect(screen.getByText('本次参考 · 仅当前稿件')).toBeInTheDocument()
  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  fireEvent.mouseEnter(screen.getByRole('button', {name: '创作参考说明'}))
  expect(screen.getByRole('tooltip')).toHaveTextContent('不添加参考时，只读取当前稿件与这段对话。')
  fireEvent.keyDown(document, {key: 'Escape'})
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

it.each(['account_analysis', 'audience_analysis'] as const)('keeps %s reference choices unlabelled and its source available in the preview', async kind => {
  const record = kind === 'account_analysis'
    ? account('saved-oracle', {origin: 'oracle_showcase', modelMetadata: {origin: 'oracle_showcase', provider: 'none', modelCalled: false}})
    : audience('saved-oracle', {result: {...audience().result, origin: 'oracle_showcase'}})
  const original = JSON.stringify(record)
  if (kind === 'account_analysis') {
    vi.mocked(analysisRunApi.list).mockResolvedValue([record as AnalysisRun])
    vi.mocked(analysisRunApi.get).mockResolvedValue(record as AnalysisRun)
  } else {
    vi.mocked(audienceAnalysisApi.list).mockResolvedValue([record as AudienceAnalysis])
    vi.mocked(audienceAnalysisApi.get).mockResolvedValue(record as AudienceAnalysis)
  }
  const {onChange} = setup()
  await openPicker()
  if (kind === 'audience_analysis') fireEvent.change(screen.getByRole('combobox', {name: '资料类型'}), {target: {value: kind}})
  await waitFor(() => expect(within(screen.getByRole('combobox', {name: '分析记录'})).getAllByRole('option')).toHaveLength(2))
  expect(screen.queryByText(/预写示例/)).not.toBeInTheDocument()
  choose('saved-oracle')
  const hint = await screen.findByRole('button', {name: '参考来源说明'})
  expect(screen.queryByText(/预写示例|人工编排/)).not.toBeInTheDocument()
  fireEvent.focus(hint)
  expect(screen.getByRole('tooltip')).toHaveTextContent('基于本账号已保存笔记人工编排，未调用模型。')
  fireEvent.keyDown(document, {key: 'Escape'})
  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  expect(screen.getByRole('button', {name: '添加这份材料'})).toBeEnabled()
  expect(onChange).not.toHaveBeenCalled()
  expect(JSON.stringify(record)).toBe(original)
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

it('starts original-note selection empty, previews saved images and full text, and cancels without adding', async () => {
  const {onChange} = setup(emptyCreatorContext(), false, profile(), [image])
  await openNoteType()
  const picker = openNoteSelection()
  expect(within(picker).getByRole('status')).toHaveTextContent('已选 0 / 2 条笔记')
  expect(within(picker).getByRole('button', {name: '完成'})).toBeDisabled()
  expect(within(picker).getByRole('img', {name: '第一篇原笔记'})).toHaveAttribute('src', '/saved-cover.jpg')
  fireEvent.click(within(picker).getByRole('button', {name: /第一篇原笔记 赞/}))
  const detail = screen.getByRole('dialog', {name: '第一篇原笔记'})
  expect(within(detail).getByText(/第一篇的完整正文/)).toHaveTextContent('保留第二段。')
  expect(within(detail).getByRole('img')).toHaveAttribute('src', '/saved-cover.jpg')
  expect(within(detail).queryByRole('region', {name: '笔记评论'})).not.toBeInTheDocument()
  expect(within(detail).queryByText('不进入助手的评论')).not.toBeInTheDocument()
  expect(within(detail).queryByText(/指标时间未记录|暂未读取到评论|评论 ·/)).not.toBeInTheDocument()
  fireEvent.click(within(detail).getByRole('button', {name: '关闭'}))
  fireEvent.click(within(picker).getByRole('checkbox', {name: '选择笔记：第一篇原笔记'}))
  fireEvent.click(within(picker).getByRole('button', {name: '取消'}))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(onChange).not.toHaveBeenCalled()
  expect(inputAssetApi.get).not.toHaveBeenCalled()
  await openNoteType()
  expect(within(openNoteSelection()).getByRole('status')).toHaveTextContent('已选 0 / 2 条笔记')
})

it('confirms exact original-note IDs alongside existing analyses and keeps each chip removable', async () => {
  vi.mocked(analysisRunApi.get).mockResolvedValue(account())
  const selection: CreatorContextSelection = {...emptyCreatorContext(), references: [{kind: 'account_analysis', id: 'account-1'}]}
  const source = profile()
  const {onChange, rerender} = setup(selection, false, source)
  await openNoteType()
  const picker = openNoteSelection()
  fireEvent.click(within(picker).getByRole('checkbox', {name: '选择笔记：第二篇原笔记'}))
  fireEvent.click(within(picker).getByRole('checkbox', {name: '选择笔记：第一篇原笔记'}))
  expect(onChange).not.toHaveBeenCalled()
  fireEvent.click(within(picker).getByRole('button', {name: '完成'}))
  const expected: CreatorContextSelection = {...selection, references: [...selection.references,
    {kind: 'imported_note', id: 'profile-1', noteId: 'saved-2'}, {kind: 'imported_note', id: 'profile-1', noteId: 'saved-1'}]}
  expect(onChange).toHaveBeenCalledExactlyOnceWith(expected)
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  rerender(<CreatorReferencePicker workspaceId="workspace-1" selection={expected} onChange={onChange} disabled={false} profile={source} />)
  expect(screen.getByRole('button', {name: '原笔记 · 第二篇原笔记'})).toBeVisible()
  expect(screen.getByRole('button', {name: '原笔记 · 第一篇原笔记'})).toBeVisible()
  fireEvent.click(screen.getByRole('button', {name: '移除原笔记 · 第二篇原笔记'}))
  expect(onChange).toHaveBeenLastCalledWith({...selection, references: [selection.references[0], expected.references[2]]})
})

it('does not offer already referenced original notes again or duplicate them in a new selection', async () => {
  vi.mocked(inputAssetApi.get).mockResolvedValue(profile())
  const selection: CreatorContextSelection = {...emptyCreatorContext(), references: [{kind: 'imported_note', id: 'profile-1', noteId: 'saved-1'}]}
  const {onChange} = setup(selection, false, profile())
  await openNoteType()
  const picker = openNoteSelection()
  expect(within(picker).queryByRole('checkbox', {name: '选择笔记：第一篇原笔记'})).not.toBeInTheDocument()
  fireEvent.click(within(picker).getByRole('checkbox', {name: '选择笔记：第二篇原笔记'}))
  fireEvent.click(within(picker).getByRole('button', {name: '完成'}))
  expect(onChange).toHaveBeenCalledExactlyOnceWith({...selection, references: [...selection.references, {kind: 'imported_note', id: 'profile-1', noteId: 'saved-2'}]})
})

it.each([undefined, profile(undefined, {workspaceId: 'foreign'}), profile(undefined, {type: 'comments'})])('does not silently add any content without an imported profile in this workspace', async source => {
  const {onChange} = setup(emptyCreatorContext(), false, source)
  await openNoteType()
  expect(screen.getByText('请先导入账号笔记，再添加原笔记参考。')).toBeVisible()
  expect(screen.queryByRole('button', {name: '完成'})).not.toBeInTheDocument()
  expect(screen.queryByRole('button', {name: '添加这份材料'})).not.toBeInTheDocument()
  expect(onChange).not.toHaveBeenCalled()
  expect(inputAssetApi.get).not.toHaveBeenCalled()
})

it('counts notes and analyses together at the eight-reference limit without silently truncating the note choice', async () => {
  vi.mocked(analysisRunApi.get).mockRejectedValue(new Error('未读取'))
  const selection: CreatorContextSelection = {...emptyCreatorContext(), references: Array.from({length: 7}, (_, index) => ({kind: 'account_analysis', id: `a-${index}`}))}
  const {onChange} = setup(selection, false, profile())
  await openNoteType()
  const picker = openNoteSelection()
  fireEvent.click(within(picker).getByRole('button', {name: '全选当前范围'}))
  expect(within(picker).getByRole('status')).toHaveTextContent('已选 2 / 2 条笔记')
  expect(within(picker).getByRole('alert')).toHaveTextContent('本次最多还能添加 1 篇原笔记')
  expect(within(picker).getByRole('button', {name: '完成'})).toBeDisabled()
  expect(onChange).not.toHaveBeenCalled()
  fireEvent.click(within(picker).getByRole('checkbox', {name: '选择笔记：第二篇原笔记'}))
  fireEvent.click(within(picker).getByRole('button', {name: '完成'}))
  expect(onChange).toHaveBeenCalledExactlyOnceWith({...selection, references: [...selection.references, {kind: 'imported_note', id: 'profile-1', noteId: 'saved-1'}]})
})

it('fetches a note chip again for a full saved-source preview and leaves comments outside the preview', async () => {
  vi.mocked(inputAssetApi.get).mockResolvedValue(profile())
  const selection: CreatorContextSelection = {...emptyCreatorContext(), references: [{kind: 'imported_note', id: 'profile-1', noteId: 'saved-1'}]}
  setup(selection, false, profile(), [image, {...image, id: 'foreign', workspaceId: 'foreign', fileUrl: '/foreign.jpg'}])
  const chip = await screen.findByRole('button', {name: '原笔记 · 第一篇原笔记'})
  vi.mocked(inputAssetApi.get).mockResolvedValue(profile([{...importedNotes[0], desc: '重新读取的保存正文。'.repeat(300) + '\n末段原文。'}]))
  fireEvent.click(chip)
  const preview = await screen.findByRole('region', {name: '原笔记原文'})
  expect(preview).toHaveTextContent('末段原文。')
  expect(within(preview).getByRole('img')).toHaveAttribute('src', '/saved-cover.jpg')
  expect(within(preview).queryByText('不进入助手的评论')).not.toBeInTheDocument()
  expect(inputAssetApi.get).toHaveBeenCalledWith('profile-1')
  expect(inputAssetApi.get).toHaveBeenCalledTimes(2)
})

it('keeps unavailable original-note chips removable and retries a failed detail read', async () => {
  vi.mocked(inputAssetApi.get).mockRejectedValue(new Error('读取原笔记失败'))
  const selection: CreatorContextSelection = {...emptyCreatorContext(), references: [{kind: 'imported_note', id: 'profile-1', noteId: 'saved-1'}]}
  const {onChange} = setup(selection, false, profile())
  fireEvent.click(screen.getByRole('button', {name: '原笔记 1'}))
  expect(await screen.findByRole('alert')).toHaveTextContent('读取原笔记失败')
  vi.mocked(inputAssetApi.get).mockResolvedValue(profile())
  fireEvent.click(screen.getByRole('button', {name: '重试读取'}))
  expect(await screen.findByRole('region', {name: '原笔记原文'})).toHaveTextContent('保留第二段。')
  fireEvent(screen.getByRole('dialog', {name: '参考材料'}), new Event('cancel', {bubbles: true, cancelable: true}))
  fireEvent.click(screen.getByRole('button', {name: '移除原笔记 · 第一篇原笔记'}))
  expect(onChange).toHaveBeenCalledExactlyOnceWith(emptyCreatorContext())
})

it('discards a late original-note response after the workspace changes', async () => {
  const slow = deferred<TextInputAsset>()
  vi.mocked(inputAssetApi.get).mockImplementation(id => id === 'profile-1' ? slow.promise : Promise.resolve(profile([{noteId: 'other-note', title: '另一个账号的笔记', desc: '新账号的保存正文'}], {id: 'profile-2', workspaceId: 'workspace-2'})))
  const selection: CreatorContextSelection = {...emptyCreatorContext(), references: [{kind: 'imported_note', id: 'profile-1', noteId: 'saved-1'}]}
  const {rerender, onChange} = setup(selection, false, profile())
  fireEvent.click(screen.getByRole('button', {name: '原笔记 1'}))
  const nextSelection: CreatorContextSelection = {...emptyCreatorContext(), references: [{kind: 'imported_note', id: 'profile-2', noteId: 'other-note'}]}
  rerender(<CreatorReferencePicker workspaceId="workspace-2" selection={nextSelection} onChange={onChange} disabled={false} profile={profile(undefined, {id: 'profile-2', workspaceId: 'workspace-2'})} />)
  const nextChip = await screen.findByRole('button', {name: '原笔记 · 另一个账号的笔记'})
  fireEvent.click(nextChip)
  expect(await screen.findByRole('region', {name: '原笔记原文'})).toHaveTextContent('新账号的保存正文')
  await act(async () => {slow.resolve(profile()); await slow.promise})
  expect(screen.queryByText(/第一篇的完整正文/)).not.toBeInTheDocument()
  expect(screen.getByRole('region', {name: '原笔记原文'})).toHaveTextContent('新账号的保存正文')
  expect(onChange).not.toHaveBeenCalled()
})

it('discards a pending note choice when changes are disabled or the profile source changes', async () => {
  const source = profile()
  const {rerender, onChange} = setup(emptyCreatorContext(), false, source)
  await openNoteType()
  const picker = openNoteSelection()
  fireEvent.click(within(picker).getByRole('checkbox', {name: '选择笔记：第一篇原笔记'}))
  rerender(<CreatorReferencePicker workspaceId="workspace-1" selection={emptyCreatorContext()} onChange={onChange} disabled profile={source} />)
  expect(screen.queryByRole('button', {name: '完成'})).not.toBeInTheDocument()
  expect(onChange).not.toHaveBeenCalled()
  rerender(<CreatorReferencePicker workspaceId="workspace-1" selection={emptyCreatorContext()} onChange={onChange} disabled={false} profile={source} />)
  expect(within(openNoteSelection()).getByRole('status')).toHaveTextContent('已选 0 / 2 条笔记')
  fireEvent.click(screen.getByRole('checkbox', {name: '选择笔记：第一篇原笔记'}))
  rerender(<CreatorReferencePicker workspaceId="workspace-1" selection={emptyCreatorContext()} onChange={onChange} disabled={false} profile={profile(undefined, {id: 'replacement'})} />)
  expect(screen.getByRole('status')).toHaveTextContent('已选 0 / 2 条笔记')
  expect(onChange).not.toHaveBeenCalled()
})

it('rejects a selected note removed from the same source while its picker is open', async () => {
  const {rerender, onChange} = setup(emptyCreatorContext(), false, profile())
  await openNoteType()
  const picker = openNoteSelection()
  fireEvent.click(within(picker).getByRole('checkbox', {name: '选择笔记：第一篇原笔记'}))
  rerender(<CreatorReferencePicker workspaceId="workspace-1" selection={emptyCreatorContext()} onChange={onChange} disabled={false} profile={profile([importedNotes[1]])} />)
  fireEvent.click(within(picker).getByRole('button', {name: '完成'}))
  expect(screen.getByRole('status')).toHaveTextContent('已选 0 / 1 条笔记')
  expect(screen.getByRole('alert')).toHaveTextContent('所选原笔记已变化，请重新选择。')
  expect(onChange).not.toHaveBeenCalled()
})
