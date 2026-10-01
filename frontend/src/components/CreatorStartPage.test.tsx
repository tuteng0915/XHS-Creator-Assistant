import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { CreatorStartPage } from './CreatorStartPage'
import type { TextInputAsset, Workspace, XhsCaptureJob } from '../types'

const workspace: Workspace = {
  id: 'workspace-1',
  name: 'QSheep',
  accountPositioning: '',
  positioningVersion: 1,
  currentTopicId: null,
  createdAt: '2026-09-23T10:00:00Z',
  updatedAt: '2026-09-23T10:00:00Z',
}

const profile: TextInputAsset = {
  id: 'profile-1',
  workspaceId: workspace.id,
  type: 'xhs_creator_profile',
  name: 'QSheep 创作者主页',
  content: JSON.stringify({
    schemaVersion: 'xhs-creator-profile/v1',
    creator: { displayName: 'QSheep' },
    notes: [
      {
        noteId: 'note-1',
        type: 'normal',
        title: '测试笔记',
        comments: [{ content: '测试评论' }],
      },
    ],
  }),
  createdAt: '2026-09-23T10:00:00Z',
  updatedAt: '2026-09-23T10:00:00Z',
}

function renderPage(captureJob: XhsCaptureJob | null = null) {
  const onSubmit = vi.fn((event) => event.preventDefault())
  const { container } = render(
    <CreatorStartPage
      workspace={workspace}
      xhsCreatorProfile={profile}
      profileUrl="https://www.xiaohongshu.com/user/profile/test-user"
      captureJob={captureJob}
      submitting={false}
      error=""
      onProfileUrlChange={vi.fn()}
      onSubmit={onSubmit}
      onOpenMaterials={vi.fn()}
      onOpenDiagnosis={vi.fn()}
    />,
  )
  return { onSubmit, container }
}

describe('CreatorStartPage', () => {
  it('submits a creator profile URL and summarizes existing material', () => {
    const { onSubmit } = renderPage()

    expect(screen.getByText('账号：QSheep')).toBeInTheDocument()
    expect(screen.getByText('笔记：1')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '开始导入' }))
    expect(onSubmit).toHaveBeenCalledTimes(1)
  })

  it('shows the browser login instruction for a waiting job', () => {
    renderPage({
      id: 'job-1',
      workspaceId: workspace.id,
      profileUrl: 'https://xhslink.cn/m/example',
      resolvedUrl: '',
      status: 'waiting_for_login',
      noteLimit: 20,
      includeComments: true,
      statusMessage: '请扫码登录',
      progress: {
        phase: 'login', capturedNotes: 0, capturedComments: 0,
        commentNotesCompleted: 0, commentNotesTotal: null,
      },
      error: '',
      resultInputAssetId: null,
      createdAt: '2026-09-23T10:00:00Z',
      startedAt: '2026-09-23T10:00:01Z',
      completedAt: null,
      updatedAt: '2026-09-23T10:00:01Z',
    })

    expect(screen.getByText('请扫码登录')).toBeInTheDocument()
    expect(screen.getByText(/请查看本机新打开的浏览器窗口/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '正在导入' })).toBeDisabled()
    expect(screen.getByRole('progressbar', { name: '账号导入进度' })).not.toHaveAttribute('aria-valuenow')
  })

  it('shows observed counts and a bounded comment-stage percentage', () => {
    const { container } = renderPage({
      id: 'job-2', workspaceId: workspace.id,
      profileUrl: 'https://xhslink.cn/m/example', resolvedUrl: '',
      status: 'running', noteLimit: 0, includeComments: true,
      statusMessage: '笔记读取完成，正在读取评论。',
      progress: {
        phase: 'comments', capturedNotes: 92, capturedComments: 300,
        commentNotesCompleted: 23, commentNotesTotal: 92,
      },
      error: '', resultInputAssetId: null,
      createdAt: '2026-09-23T10:00:00Z', startedAt: '2026-09-23T10:00:01Z',
      completedAt: null, updatedAt: '2026-09-23T10:00:01Z',
    })

    expect(screen.getByText(/已读取 92 条笔记 · 300 条评论/)).toBeInTheDocument()
    expect(screen.getByText(/已完成 23\/92 个评论读取任务/)).toBeInTheDocument()
    expect(within(container).getByRole('progressbar', { name: '评论读取进度' })).toHaveAttribute('aria-valuenow', '25')
  })
})
