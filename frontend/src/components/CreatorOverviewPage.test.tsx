import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { TextInputAsset, Workspace } from '../types'
import { CreatorOverviewPage } from './CreatorOverviewPage'

afterEach(cleanup)

const workspace: Workspace = {
  id: 'account', name: '测试工作区', accountPositioning: '', positioningVersion: 1,
  currentTopicId: null, createdAt: '', updatedAt: '',
}

function profile(creator: Record<string, unknown>): TextInputAsset {
  return {
    id: 'source', workspaceId: workspace.id, type: 'xhs_creator_profile', name: '笔记', createdAt: '', updatedAt: '',
    content: JSON.stringify({ schemaVersion: 'xhs-creator-profile/v1', creator, notes: [
      { noteId: 'one', title: '真实的笔记标题', metrics: { liked: 0, collected: 4 }, comments: [] },
    ] }),
  }
}

it('separates metric labels and values without changing zero or combined-count meaning', () => {
  render(<CreatorOverviewPage workspace={workspace} profile={profile({ displayName: '测试作者', followers: 0, likesAndCollections: 124 })}
    onNotes={vi.fn()} onAnalyze={vi.fn()} onImport={vi.fn()} />)
  expect(screen.getByRole('heading', { name: '测试作者', level: 1 })).toBeInTheDocument()
  const metrics = screen.getByLabelText('账号数据')
  expect(within(metrics).getAllByRole('term')).toHaveLength(4)
  expect(within(metrics).getByText('粉丝').nextElementSibling).toHaveTextContent(/^0$/)
  expect(within(metrics).getByText('获赞与收藏')).toBeInTheDocument()
  expect(within(metrics).getByText('124')).toBeInTheDocument()
  expect(within(metrics).queryByText('总获赞')).not.toBeInTheDocument()
  expect(screen.getByRole('heading', { name: '高互动笔记', level: 2 })).toBeInTheDocument()
  expect(screen.getByText('真实的笔记标题')).toBeInTheDocument()
})

it('keeps notes, import and analysis actions available and unknown counts distinct from zero', () => {
  const onNotes = vi.fn(), onImport = vi.fn(), onAnalyze = vi.fn()
  render(<CreatorOverviewPage workspace={workspace} profile={profile({ displayName: '测试作者' })}
    onNotes={onNotes} onAnalyze={onAnalyze} onImport={onImport} />)
  expect(within(screen.getByLabelText('账号数据')).getAllByText('未获取')).toHaveLength(2)
  fireEvent.click(screen.getByRole('button', { name: '查看已抓取笔记' }))
  fireEvent.click(screen.getByRole('button', { name: '抓取更多笔记' }))
  fireEvent.click(screen.getByRole('button', { name: '分析账号' }))
  expect(onNotes).toHaveBeenCalledOnce()
  expect(onImport).toHaveBeenCalledOnce()
  expect(onAnalyze).toHaveBeenCalledOnce()
})

it('keeps the empty account simple and routes its primary action to import', () => {
  const onImport = vi.fn()
  render(<CreatorOverviewPage workspace={workspace} onNotes={vi.fn()} onAnalyze={vi.fn()} onImport={onImport} />)
  expect(screen.queryByLabelText('账号数据')).not.toBeInTheDocument()
  expect(screen.getByText('粘贴主页链接，开始了解你的账号。')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '导入账号' }))
  expect(onImport).toHaveBeenCalledOnce()
})
