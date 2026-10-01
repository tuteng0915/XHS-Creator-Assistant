import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { CreatorStartPage } from './CreatorStartPage'
import type { TextInputAsset, Workspace, XhsCaptureJob } from '../types'

afterEach(cleanup)

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

function renderPage(
  captureJob: XhsCaptureJob | null = null,
  currentProfile: TextInputAsset | null = profile,
  profileUrl = 'https://www.xiaohongshu.com/user/profile/test-user',
) {
  const onSubmit = vi.fn((event) => event.preventDefault())
  const { container } = render(
    <CreatorStartPage
      workspace={workspace}
      xhsCreatorProfile={currentProfile}
      profileUrl={profileUrl}
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
  it('reuses the saved URL without asking for it again', () => {
    const { onSubmit } = renderPage()

    expect(screen.getByText('账号：QSheep')).toBeInTheDocument()
    expect(screen.getByText('笔记：1')).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: /小红书用户主页 URL/ })).not.toBeInTheDocument()
    expect(screen.getByText('https://www.xiaohongshu.com/user/profile/test-user')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '继续读取' }))
    expect(onSubmit).toHaveBeenCalledTimes(1)
  })

  it('asks for a URL only when no account URL was recorded', () => {
    renderPage(null, profile, '')
    expect(screen.getByRole('textbox', { name: '补充小红书用户主页 URL' })).toBeRequired()
  })

  it('keeps the URL field for a newly added account', () => {
    renderPage(null, null, '')
    expect(screen.getByRole('textbox', { name: '小红书用户主页 URL' })).toBeRequired()
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
