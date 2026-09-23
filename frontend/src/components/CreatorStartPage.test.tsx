import { fireEvent, render, screen } from '@testing-library/react'
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
  render(
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
  return { onSubmit }
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
  })
})
