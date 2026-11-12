import {act, cleanup, fireEvent, render, screen, within} from '@testing-library/react'
import {afterEach, expect, it, vi} from 'vitest'
import type {TextInputAsset, Workspace} from '../types'
import {CreatorOverviewPage} from './CreatorOverviewPage'

afterEach(() => {cleanup(); vi.useRealTimers()})
const timestamp = '2026-10-16T00:00:00Z'
const workspace: Workspace = {id: 'w', name: '测试账号', accountPositioning: '', positioningVersion: 1,
  currentTopicId: null, createdAt: timestamp, updatedAt: timestamp}
const profile: TextInputAsset = {id: 'p', workspaceId: 'w', name: '笔记', type: 'xhs_creator_profile',
  createdAt: timestamp, updatedAt: timestamp, content: JSON.stringify({schemaVersion: 'xhs-creator-profile/v1',
    creator: {displayName: '当前账号'}, notes: [{noteId: 'n', title: '已导入笔记'}]})}
const props = () => ({workspace, profile, onNotes: vi.fn(), onAnalyze: vi.fn(), onImport: vi.fn()})

function metricProfile(creator: Record<string, unknown>): TextInputAsset {
  return {...profile, content: JSON.stringify({schemaVersion: 'xhs-creator-profile/v1', creator, notes: [
    {noteId: 'one', title: '真实的笔记标题', metrics: {liked: 0, collected: 4}, comments: []},
  ]})}
}

it('separates metric labels and values without changing zero or combined-count meaning', () => {
  render(<CreatorOverviewPage {...props()} profile={metricProfile({displayName: '测试作者', followers: 0, likesAndCollections: 124})} />)
  expect(screen.getByRole('heading', {name: '测试作者', level: 1})).toBeInTheDocument()
  const metrics = screen.getByLabelText('账号数据')
  expect(within(metrics).getAllByRole('term')).toHaveLength(4)
  expect(within(metrics).getByText('粉丝').nextElementSibling).toHaveTextContent(/^0$/)
  expect(within(metrics).getByText('获赞与收藏')).toBeInTheDocument()
  expect(within(metrics).getByText('124')).toBeInTheDocument()
  expect(within(metrics).queryByText('总获赞')).not.toBeInTheDocument()
  expect(screen.getByRole('heading', {name: '高互动笔记', level: 2})).toBeInTheDocument()
  expect(screen.getByText('真实的笔记标题')).toBeInTheDocument()
})

it('keeps notes, import and analysis actions available and unknown counts distinct from zero', () => {
  const callbacks = props()
  render(<CreatorOverviewPage {...callbacks} profile={metricProfile({displayName: '测试作者'})} />)
  expect(within(screen.getByLabelText('账号数据')).getAllByText('未获取')).toHaveLength(2)
  fireEvent.click(screen.getByRole('button', {name: '查看已抓取笔记'}))
  fireEvent.click(screen.getByRole('button', {name: '抓取更多笔记'}))
  fireEvent.click(screen.getByRole('button', {name: '分析账号'}))
  expect(callbacks.onNotes).toHaveBeenCalledOnce()
  expect(callbacks.onImport).toHaveBeenCalledOnce()
  expect(callbacks.onAnalyze).toHaveBeenCalledOnce()
})

it('shows concise guidance over the analyze action and removes it on pointer leave', () => {
  vi.useFakeTimers()
  render(<CreatorOverviewPage {...props()} />)
  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  const analyze = screen.getByRole('button', {name: '分析账号'})
  fireEvent.mouseEnter(analyze)
  expect(screen.getByRole('tooltip')).toHaveTextContent('先选想分析的笔记')
  expect(screen.getByRole('tooltip')).toHaveTextContent('内容特点、读者反馈，以及下一篇可以写什么')
  expect(analyze).toHaveAttribute('aria-describedby', screen.getByRole('tooltip').id)
  fireEvent.mouseLeave(analyze)
  act(() => vi.advanceTimersByTime(121))
  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
})

it('makes the analyze guidance keyboard readable and dismissible without activating the action', () => {
  const callbacks = props()
  render(<CreatorOverviewPage {...callbacks} />)
  const analyze = screen.getByRole('button', {name: '分析账号'})
  act(() => analyze.focus())
  expect(screen.getByRole('tooltip')).toBeVisible()
  fireEvent.keyDown(analyze, {key: 'Escape'})
  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  expect(analyze).toHaveFocus()
  expect(callbacks.onAnalyze).not.toHaveBeenCalled()
  fireEvent.click(analyze)
  expect(callbacks.onAnalyze).toHaveBeenCalledOnce()
})

it('keeps touch explanation separate from the first-tap analyze action', () => {
  const callbacks = props()
  render(<CreatorOverviewPage {...callbacks} />)
  const help = screen.getByRole('button', {name: '分析账号说明'})
  fireEvent.pointerDown(help, {pointerType: 'touch'})
  fireEvent.focus(help)
  fireEvent.click(help)
  expect(screen.getByRole('tooltip')).toBeVisible()
  expect(callbacks.onAnalyze).not.toHaveBeenCalled()
  fireEvent.click(help)
  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  const analyze = screen.getByRole('button', {name: '分析账号'})
  fireEvent.pointerDown(analyze, {pointerType: 'touch'})
  fireEvent.focus(analyze)
  fireEvent.pointerUp(analyze, {pointerType: 'touch'})
  fireEvent.click(analyze)
  expect(callbacks.onAnalyze).toHaveBeenCalledOnce()
  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
})

it('keeps the import entry unchanged before an account is available', () => {
  const callbacks = props()
  render(<CreatorOverviewPage {...callbacks} profile={undefined} />)
  expect(screen.queryByLabelText('账号数据')).not.toBeInTheDocument()
  expect(screen.getByText('粘贴主页链接，开始了解你的账号。')).toBeInTheDocument()
  expect(screen.queryByRole('button', {name: '分析账号说明'})).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', {name: '导入账号'}))
  expect(callbacks.onImport).toHaveBeenCalledOnce()
  expect(callbacks.onAnalyze).not.toHaveBeenCalled()
})

const media = (id: string, noteId: string) => ({id, workspaceId: 'w', type: 'image', name: id, purpose: '', sourceType: 'upload',
  originalFilename: `${id}.jpg`, mediaType: 'image/jpeg', byteSize: 1, sha256: '', metadata: {noteId}, derived: {}, userNotes: '',
  fileUrl: `/media/${id}.jpg`, createdAt: timestamp, updatedAt: timestamp}) as unknown as import('../types').MediaAsset

const datedProfile: TextInputAsset = {...profile, content: JSON.stringify({schemaVersion: 'xhs-creator-profile/v1', creator: {displayName: '测试作者'}, notes: [
  {noteId: 'late', title: '后发的笔记', publishedAt: 1780000000, metrics: {liked: 5, collected: 1}},
  {noteId: 'early', title: '先发的笔记', publishedAt: 1770000000, metrics: {liked: 90, collected: 10, comments: 3}},
  {noteId: 'undated', title: '没有日期的笔记', metrics: {liked: 1}},
]})}

it('shows note covers beside the top notes and plots dated notes in publish order', () => {
  const {container} = render(<CreatorOverviewPage {...props()} profile={datedProfile} mediaAssets={[media('c1', 'early')]} />)
  expect(container.querySelector('.creator-overview-notes img')).toHaveAttribute('src', '/media/c1.jpg')
  const slots = container.querySelectorAll('.overview-trend-slot')
  expect(slots).toHaveLength(2)
  expect(slots[0]).toHaveClass('is-top')
  expect(screen.getByRole('img', {name: /2 篇笔记互动量，最高 103/})).toBeInTheDocument()
  fireEvent.click(slots[0])
  expect(screen.getByText('先发的笔记', {selector: '.overview-trend-tip strong'})).toBeInTheDocument()
  expect(screen.getByText(/互动 103：赞 90 · 收藏 10 · 评论 3/)).toBeInTheDocument()
})

it('marks the first unfinished step as next and opens each step on click', () => {
  const open = vi.fn()
  const steps = [
    {key: 'import', label: '导入', icon: 'notes' as const, state: 'done' as const, detail: '3 篇笔记', onOpen: vi.fn()},
    {key: 'diagnosis', label: '诊断', icon: 'analysis' as const, state: 'running' as const, detail: '生成中', onOpen: vi.fn()},
    {key: 'readers', label: '读者', icon: 'readers' as const, state: 'todo' as const, detail: '0 份分析', onOpen: open},
    {key: 'simulation', label: '模拟', icon: 'conversation' as const, state: 'todo' as const, detail: '0 次模拟', onOpen: vi.fn()},
  ]
  render(<CreatorOverviewPage {...props()} steps={steps} />)
  const flow = screen.getByRole('navigation', {name: '创作流程'})
  expect(within(flow).getByText('3 篇笔记')).toBeInTheDocument()
  expect(within(flow).getByText('生成中')).toBeInTheDocument()
  const next = within(flow).getByRole('button', {name: /读者\s*下一步/})
  expect(next).toHaveAttribute('aria-current', 'step')
  expect(within(flow).getByText('0 次模拟')).toBeInTheDocument()
  fireEvent.click(next)
  expect(open).toHaveBeenCalledOnce()
})
