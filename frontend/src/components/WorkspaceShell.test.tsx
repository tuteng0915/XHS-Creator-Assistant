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

afterEach(() => { cleanup(); vi.restoreAllMocks() })

describe('WorkspaceShell', () => {
  it('offers page and workflow tours without navigating or starting work', () => {
    vi.spyOn(HTMLElement.prototype, 'getClientRects').mockReturnValue([{}] as unknown as DOMRectList)
    const props = renderShell({activePage: 'account-diagnosis', children: <div className="creator-diagnosis-controls"><button data-guide="diagnosis-range" disabled>调整范围</button></div>})
    fireEvent.click(screen.getByRole('button', {name: '帮助'}))
    fireEvent.click(screen.getByRole('button', {name: /看看当前页怎么用/}))
    expect(screen.getByRole('heading', {name: '选择分析范围'})).toBeInTheDocument()
    expect(screen.getByText('1 / 1')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', {name: '完成'}))
    expect(screen.getByRole('button', {name: '帮助'})).toHaveFocus()
    fireEvent.click(screen.getByRole('button', {name: '帮助'}))
    fireEvent.click(screen.getByRole('button', {name: /了解完整流程/}))
    expect(screen.getByText('1 / 7')).toBeInTheDocument()
    for (let index = 0; index < 6; index++) fireEvent.click(screen.getByRole('button', {name: '下一步'}))
    expect(screen.getByRole('heading', {name: '开始创作'})).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', {name: '完成'}))
    expect(props.onSetActivePage).not.toHaveBeenCalled()
    expect(props.onSelectWorkspace).not.toHaveBeenCalled()
    expect(props.onCreateCreatorProfile).not.toHaveBeenCalled()
    expect(props.onOpenInputAsset).not.toHaveBeenCalled()
  })
  it('renders the creator-focused navigation without developer entries', () => {
    renderShell()

    expect(screen.getByText('小红书创作助手')).toBeInTheDocument()
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

  it('groups the journey with creation after readers and keeps icons decorative', () => {
    renderShell({ activePage: 'simulations' })
    const navigation = screen.getByRole('navigation', { name: '创作者功能导航' })

    expect(within(navigation).getAllByRole('button').map((button) => button.textContent)).toEqual([
      '账号概览', '我的笔记', '账号诊断',
      '受众分析', '模拟粉丝', '受众模拟', 'AI 创作助手',
    ])
    expect(within(navigation).getAllByRole('group').map((group) => group.getAttribute('aria-label'))).toEqual([
      '账号', '读者', '创作',
    ])
    expect(within(navigation).getByRole('button', { name: '受众模拟' })).toHaveAttribute('aria-current', 'page')
    expect(within(navigation).queryByRole('button', { name: '选题库' })).not.toBeInTheDocument()
    expect(within(navigation).queryByRole('button', { name: '诊断历史' })).not.toBeInTheDocument()
    expect(navigation.querySelectorAll('svg[aria-hidden="true"][focusable="false"]')).toHaveLength(7)
  })

  it('preserves workspace switching protection while busy', () => {
    renderShell({ busy: true })

    expect(screen.getByLabelText('当前账号档案')).toBeDisabled()
    expect(screen.getByRole('button', { name: '＋ 添加账号' })).toBeDisabled()
  })

  it('explains disabled controls on hover, keyboard focus and touch without invoking actions', () => {
    const reason = '正在爬取笔记和评论。完成后可添加或切换账号。'
    const props = renderShell({ busy: true, busyReason: reason })
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()

    const addHint = screen.getByRole('group', { name: '添加账号暂不可用' })
    fireEvent.mouseEnter(addHint)
    expect(screen.getByRole('tooltip')).toHaveTextContent(reason)
    expect(addHint).toHaveAccessibleDescription(reason)
    fireEvent.click(screen.getByRole('button', { name: '＋ 添加账号' }))
    expect(props.onCreateCreatorProfile).not.toHaveBeenCalled()
    fireEvent.mouseLeave(addHint)
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()

    const switchHint = screen.getByRole('group', { name: '账号切换暂不可用' })
    expect(switchHint).toHaveAttribute('tabindex', '0')
    fireEvent.focus(switchHint)
    expect(screen.getByRole('tooltip')).toHaveTextContent(reason)
    fireEvent.keyDown(switchHint, { key: 'Escape' })
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    fireEvent.blur(switchHint)

    fireEvent.click(addHint)
    expect(screen.getByRole('tooltip')).toHaveTextContent(reason)
    expect(props.onSelectWorkspace).not.toHaveBeenCalled()
  })

  it('leaves developer navigation outside the public shell styling', () => {
    const { container } = render(<WorkspaceShell
      workspace={workspace}
      workspaces={[workspace]}
      selectedWorkspaceId={workspace.id}
      activePage="account-diagnosis"
      inputAssetPanel="xhs_creator_profiles"
      showHelp={false}
      helpContent={{ title: '帮助', description: '', bullets: [] }}
      internalMode
      onOpenInputAsset={vi.fn()}
      onSetActivePage={vi.fn()}
      onSelectWorkspace={vi.fn()}
      onCreateCreatorProfile={vi.fn()}
      onToggleHelp={vi.fn()}
    >页面内容</WorkspaceShell>)

    expect(container.querySelector('.creator-focused-shell')).not.toBeInTheDocument()
    expect(container.querySelector('.creator-navigation')).not.toBeInTheDocument()
    expect(screen.getByText('热点分析')).toBeInTheDocument()
  })

  it.each([['history', '账号诊断'], ['topics', 'AI 创作助手']] as const)('keeps %s within its parent task navigation', (activePage, label) => {
    renderShell({activePage})
    expect(within(screen.getByRole('navigation')).getByRole('button', {name: label})).toHaveAttribute('aria-current', 'page')
  })

  it.each(['creator-start', 'creator-overview', 'source-materials', 'account-diagnosis', 'history', 'audience-analysis', 'simulated-fans', 'simulations', 'drafts', 'topics'] as ActivePage[])('keeps help beside the brand without a separate header on %s', (activePage) => {
    renderShell({activePage})
    const help = screen.getByRole('button', {name: '帮助'})
    expect(help.closest('.brand-row')).toHaveTextContent('小红书创作助手')
    expect(screen.getByRole('main').firstElementChild).toHaveTextContent('页面内容')
    expect(screen.getByRole('main').querySelector('.topbar')).toBeNull()
    expect(screen.queryByRole('button', {name: '页面帮助'})).not.toBeInTheDocument()
  })

  it('keeps the help menu to two choices without repeated explanatory text', () => {
    renderShell({ showHelp: true })
    expect(screen.queryByLabelText('当前页面帮助')).not.toBeInTheDocument()
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    expect(screen.queryByText('这里是帮助内容')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '帮助' }))
    const menu = screen.getByRole('dialog')
    expect(menu).toHaveClass('guide-menu-dialog')
    expect(within(menu).getByRole('button', {name: '看看当前页怎么用'})).toBeInTheDocument()
    expect(within(menu).getByRole('button', {name: '了解完整流程'})).toBeInTheDocument()
    expect(menu.querySelector('.guide-options')?.children).toHaveLength(2)
    expect(menu.querySelector('p, .guide-options span, .guide-options small')).toBeNull()
    expect(screen.queryByText('这里是帮助内容')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', {name: '关闭'}))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByRole('button', {name: '帮助'})).toHaveFocus()
  })
})
