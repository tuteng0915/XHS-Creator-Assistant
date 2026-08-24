import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { WorkspaceShell, type ActivePage } from './WorkspaceShell'
import type { InputAssetPanel } from '../inputAssets'
import type { WorkflowAssetSummary, Workspace } from '../types'
import type { WorkflowTab } from '../workflows'

const workspace: Workspace = {
  id: 'workspace-1',
  name: '默认工作区',
  accountPositioning: '服务留学生',
  positioningVersion: 1,
  currentTopicId: null,
  createdAt: '2026-07-11T10:00:00Z',
  updatedAt: '2026-07-11T10:00:00Z',
}

const workflowAssets: WorkflowAssetSummary[] = [
  {
    id: 'workflow-account',
    workspaceId: 'workspace-1',
    workflowId: 'account_diagnosis',
    displayName: '账号诊断',
    purpose: '诊断账号',
    entryAgentIds: [],
    artifactEffect: 'AnalysisRun',
    source: 'builtin',
    status: 'enabled',
    version: 'v1',
    callBinding: 'account',
    updatedAt: '2026-07-11T10:00:00Z',
  },
  {
    id: 'workflow-trend',
    workspaceId: 'workspace-1',
    workflowId: 'trend_analysis',
    displayName: '热点分析',
    purpose: '分析趋势',
    entryAgentIds: [],
    artifactEffect: 'AnalysisRun',
    source: 'builtin',
    status: 'enabled',
    version: 'v1',
    callBinding: 'trend',
    updatedAt: '2026-07-11T10:00:00Z',
  },
]

function renderShell(overrides: Partial<Parameters<typeof WorkspaceShell>[0]> = {}) {
  const props = {
    workspace,
    activePage: 'account-diagnosis' as ActivePage,
    inputAssetPanel: 'historical_posts' as InputAssetPanel,
    showHelp: false,
    helpContent: {
      title: '整体帮助',
      description: '这里是帮助内容',
      bullets: ['第一条帮助'],
    },
    workflowAssets,
    children: <div>页面内容</div>,
    onOpenInputAsset: vi.fn(),
    onSetActivePage: vi.fn(),
    onSetWorkflowTab: vi.fn(),
    onToggleHelp: vi.fn(),
    ...overrides,
  }
  render(<WorkspaceShell {...props} />)
  return props
}

afterEach(() => cleanup())

describe('WorkspaceShell', () => {
  it('renders content and capability navigation around the current page', () => {
    renderShell()

    expect(screen.getByText('创作者工作区')).toBeInTheDocument()
    expect(screen.getByText('内容资产')).toBeInTheDocument()
    expect(screen.getAllByText('能力资产').length).toBeGreaterThan(0)
    expect(screen.getByText('页面内容')).toBeInTheDocument()
  })

  it('routes input asset and workflow navigation through callbacks', () => {
    const props = renderShell()
    const contentNav = screen.getByRole('navigation', { name: '内容资产导航' })
    const capabilityNav = screen.getByRole('navigation', { name: '能力资产导航' })

    fireEvent.click(within(contentNav).getByRole('button', { name: /创作者档案/ }))
    expect(props.onOpenInputAsset).toHaveBeenCalledWith('historical_posts')

    fireEvent.click(within(capabilityNav).getByRole('button', { name: /热点分析/ }))
    expect(props.onSetWorkflowTab).toHaveBeenCalledWith('trend' satisfies WorkflowTab)
    expect(props.onSetActivePage).toHaveBeenCalledWith('trend-analysis')
  })

  it('routes media asset navigation through the content sidebar', () => {
    const props = renderShell()
    const contentNav = screen.getByRole('navigation', { name: '内容资产导航' })

    fireEvent.click(within(contentNav).getByRole('button', { name: /图文素材/ }))
    expect(props.onSetActivePage).toHaveBeenCalledWith('image-assets')

    fireEvent.click(within(contentNav).getByRole('button', { name: /视频素材/ }))
    expect(props.onSetActivePage).toHaveBeenCalledWith('video-assets')

    fireEvent.click(within(contentNav).getByRole('button', { name: /对话记录/ }))
    expect(props.onSetActivePage).toHaveBeenCalledWith('conversations')
  })

  it('toggles and displays help content when requested', () => {
    const props = renderShell({ showHelp: true })

    expect(screen.getByRole('button', { name: '帮助' })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
    expect(screen.getByText('整体帮助')).toBeInTheDocument()
    expect(screen.getByText('这里是帮助内容')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '帮助' }))
    expect(props.onToggleHelp).toHaveBeenCalledTimes(1)
  })
})
