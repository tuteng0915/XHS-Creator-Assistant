import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { WorkspaceShell, type ActivePage } from './WorkspaceShell'
import type { InputAssetPanel } from '../inputAssets'
import type { Workspace } from '../types'

const workspace: Workspace = {
  id: 'workspace-1',
  name: 'QSheep',
  accountPositioning: '服务留学生',
  positioningVersion: 1,
  currentTopicId: null,
  createdAt: '2026-07-11T10:00:00Z',
  updatedAt: '2026-07-11T10:00:00Z',
}

const workspaceTwo: Workspace = {
  ...workspace,
  id: 'workspace-2',
  name: '数字游民账号',
}

function renderShell(overrides: Partial<Parameters<typeof WorkspaceShell>[0]> = {}) {
  const props = {
    workspace,
    workspaces: [workspace, workspaceTwo],
    selectedWorkspaceId: workspace.id,
    activePage: 'creator-start' as ActivePage,
    inputAssetPanel: 'xhs_creator_profiles' as InputAssetPanel,
    showHelp: false,
    helpContent: {
      title: '整体帮助',
      description: '这里是帮助内容',
      bullets: ['第一条帮助'],
    },
    children: <div>页面内容</div>,
    onOpenInputAsset: vi.fn(),
    onSetActivePage: vi.fn(),
    onSelectWorkspace: vi.fn(),
    onCreateCreatorProfile: vi.fn(),
    onToggleHelp: vi.fn(),
    ...overrides,
  }
  render(<WorkspaceShell {...props} />)
  return props
}

afterEach(() => cleanup())

describe('WorkspaceShell', () => {
  it('renders the creator-focused navigation without developer entries', () => {
    renderShell()

    expect(screen.getByText('创作者诊断助手')).toBeInTheDocument()
    expect(screen.queryByText('导入小红书账号')).not.toBeInTheDocument()
    expect(screen.getByText('受众分析')).toBeInTheDocument()
    expect(screen.getByText('AI 创作助手')).toBeInTheDocument()
    expect(screen.getByText('账号诊断')).toBeInTheDocument()
    expect(screen.getByRole('button',{name:/受众模拟/})).not.toHaveClass('creator-nav-child')
    expect(screen.queryByText('热点分析')).not.toBeInTheDocument()
    expect(screen.queryByText('视频博主质量诊断')).not.toBeInTheDocument()
    expect(screen.queryByText('Skills')).not.toBeInTheDocument()
    expect(screen.queryByText('Agents')).not.toBeInTheDocument()
    expect(screen.queryByText('Workflows')).not.toBeInTheDocument()
    expect(screen.queryByRole('link', {name: /查看演示案例/})).not.toBeInTheDocument()
  })

  it('switches creator profiles and creates a new profile', () => {
    const props = renderShell()

    fireEvent.change(screen.getByLabelText('当前账号档案'), {
      target: { value: workspaceTwo.id },
    })
    expect(props.onSelectWorkspace).toHaveBeenCalledWith(workspaceTwo.id)

    fireEvent.click(screen.getByRole('button', { name: '＋ 添加账号' }))
    expect(props.onCreateCreatorProfile).toHaveBeenCalledTimes(1)
  })

  it('routes the public creator journey through the left navigation', () => {
    const props = renderShell()
    const navigation = screen.getByRole('navigation', {
      name: '创作者功能导航',
    })

    fireEvent.click(within(navigation).getByRole('button', { name: /我的笔记/ }))
    expect(props.onOpenInputAsset).toHaveBeenCalledWith('xhs_creator_profiles')

    fireEvent.click(within(navigation).getByRole('button', { name: /账号诊断/ }))
    expect(props.onSetActivePage).toHaveBeenCalledWith('account-diagnosis')
  })

  it('toggles and displays help content when requested', () => {
    const props = renderShell({ showHelp: true })

    expect(screen.getByRole('button', { name: '帮助' })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
    expect(screen.getByText('整体帮助')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '帮助' }))
    expect(props.onToggleHelp).toHaveBeenCalledTimes(1)
  })
})
