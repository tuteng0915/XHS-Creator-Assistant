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
