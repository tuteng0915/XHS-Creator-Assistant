import type { ReactNode } from 'react'

import {
  INPUT_ASSET_DEFINITIONS,
  isCreatorInputAssetPanel,
  type InputAssetPanel,
} from '../inputAssets'
import type { WorkflowAssetSummary, Workspace } from '../types'
import type { WorkflowTab } from '../workflows'
import { CreatorNavIcon, type CreatorNavIconName } from './CreatorNavIcon'
import { InfoHint } from './InfoHint'
import './CreatorShell.css'

export type ActivePage =
  | 'creator-start'
  | 'creator-overview'
  | 'account-profile'
  | 'source-materials'
  | 'image-assets'
  | 'video-assets'
  | 'account-diagnosis'
  | 'trend-analysis'
  | 'video-quality'
  | 'history'
  | 'topics'
  | 'drafts'
  | 'simulations'
  | 'audience-analysis'
  | 'simulated-fans'
  | 'conversations'
  | 'skills'
  | 'agents'
  | 'workflows'

export type HelpContent = {
  title: string
  description: string
  bullets: string[]
}

type WorkspaceShellProps = {
  workspace: Workspace | null
  workspaces: Workspace[]
  selectedWorkspaceId: string
  activePage: ActivePage
  inputAssetPanel: InputAssetPanel
  showHelp: boolean
  helpContent: HelpContent
  internalMode?: boolean
  busy?: boolean
  workflowAssets?: WorkflowAssetSummary[]
  children: ReactNode
  onOpenInputAsset: (panel: InputAssetPanel) => void
  onSetActivePage: (page: ActivePage) => void
  onSelectWorkspace: (workspaceId: string) => void
  onCreateCreatorProfile: () => void
  onSetWorkflowTab?: (tab: WorkflowTab) => void
  onToggleHelp: () => void
}

const CREATOR_NAVIGATION: Array<{
  label: string
  items: Array<{ page: ActivePage; label: string; icon: CreatorNavIconName; child?: boolean }>
}> = [
  {
    label: '账号',
    items: [
      { page: 'creator-overview', label: '账号概览', icon: 'overview' },
      { page: 'source-materials', label: '我的笔记', icon: 'notes', child: true },
      { page: 'account-diagnosis', label: '账号诊断', icon: 'analysis' },
    ],
  },
  {
    label: '读者',
    items: [
      { page: 'audience-analysis', label: '受众分析', icon: 'audience' },
      { page: 'simulated-fans', label: '模拟粉丝', icon: 'readers', child: true },
      { page: 'simulations', label: '受众模拟', icon: 'conversation' },
    ],
  },
  {
    label: '创作',
    items: [
      { page: 'drafts', label: 'AI 创作助手', icon: 'writing' },
    ],
  },
]

export function WorkspaceShell({
  workspace,
  workspaces,
  selectedWorkspaceId,
  activePage,
  inputAssetPanel,
  showHelp,
  helpContent,
  internalMode = false,
  busy = false,
  workflowAssets = [],
  children,
  onOpenInputAsset,
  onSetActivePage,
  onSelectWorkspace,
  onCreateCreatorProfile,
  onSetWorkflowTab,
  onToggleHelp,
}: WorkspaceShellProps) {
  const navigationPage = activePage === 'history' ? 'account-diagnosis' : activePage === 'topics' ? 'drafts' : activePage
  if (internalMode) {
    return (
      <DeveloperWorkspaceShell
        workspace={workspace}
        activePage={activePage}
        inputAssetPanel={inputAssetPanel}
        showHelp={showHelp}
        helpContent={helpContent}
        workflowAssets={workflowAssets}
        onOpenInputAsset={onOpenInputAsset}
        onSetActivePage={onSetActivePage}
        onSetWorkflowTab={onSetWorkflowTab || (() => undefined)}
        onToggleHelp={onToggleHelp}
      >
        {children}
      </DeveloperWorkspaceShell>
    )
  }

  return (
    <div className="app-shell creator-focused-shell">
      <aside className="workspace-sidebar">
        <div className="brand-row">
          <div className="logo">薯</div>
          <div>
            <strong>创作者诊断助手</strong>
          </div>
        </div>

        <section className="creator-switcher" aria-label="账号档案选择">
          <label htmlFor="creator-workspace-select">当前账号档案</label>
          <select
            id="creator-workspace-select"
            value={selectedWorkspaceId}
            disabled={busy}
            onChange={(event) => onSelectWorkspace(event.target.value)}
          >
            {workspaces.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
          <button type="button" className="creator-add-button" disabled={busy} onClick={onCreateCreatorProfile}>
            ＋ 添加账号
          </button>
        </section>

        <nav className="creator-navigation" aria-label="创作者功能导航">
          {CREATOR_NAVIGATION.map((group) => (
            <div className="creator-nav-group" role="group" aria-label={group.label} key={group.label}>
              <span className="creator-nav-group-label" aria-hidden="true">{group.label}</span>
              {group.items.map((item) => (
                <button
                  key={item.page}
                  type="button"
                  className={`${item.child ? 'creator-nav-child ' : ''}${navigationPage === item.page ? 'active' : ''}`}
                  aria-current={navigationPage === item.page ? 'page' : undefined}
                  onClick={() => item.page === 'source-materials'
                    ? onOpenInputAsset('xhs_creator_profiles')
                    : onSetActivePage(item.page)}
                >
                  <CreatorNavIcon name={item.icon} />
                  <span>{item.label}</span>
                </button>
              ))}
            </div>
          ))}
        </nav>

      </aside>

      <main className="workspace-main">
        <header className="topbar">
          <InfoHint key={activePage} label="页面帮助">{helpContent.description}</InfoHint>
        </header>

        {children}
      </main>
    </div>
  )
}

type DeveloperWorkspaceShellProps = {
  workspace: Workspace | null
  activePage: ActivePage
  inputAssetPanel: InputAssetPanel
  showHelp: boolean
  helpContent: HelpContent
  workflowAssets: WorkflowAssetSummary[]
  children: ReactNode
  onOpenInputAsset: (panel: InputAssetPanel) => void
  onSetActivePage: (page: ActivePage) => void
  onSetWorkflowTab: (tab: WorkflowTab) => void
  onToggleHelp: () => void
}

function DeveloperWorkspaceShell({
  workspace,
  activePage,
  inputAssetPanel,
  showHelp,
  helpContent,
  workflowAssets,
  children,
  onOpenInputAsset,
  onSetActivePage,
  onSetWorkflowTab,
  onToggleHelp,
}: DeveloperWorkspaceShellProps) {
  const fallbackWorkflows: Array<{
    id: string
    label: string
    binding: WorkflowTab
    page: ActivePage
    icon: string
  }> = [
    { id: 'account', label: '账号诊断', binding: 'account', page: 'account-diagnosis', icon: '📊' },
    { id: 'trend', label: '热点分析', binding: 'trend', page: 'trend-analysis', icon: '🔥' },
    { id: 'video', label: '视频博主质量诊断', binding: 'video', page: 'video-quality', icon: '🎬' },
  ]
  const registeredWorkflows = workflowAssets
    .filter((item) => item.status === 'enabled' && item.callBinding)
    .map((item) => {
      const binding = item.callBinding as WorkflowTab
      const fallback = fallbackWorkflows.find((entry) => entry.binding === binding)
      const builtinLabel =
        item.workflowId === 'account_diagnosis'
          ? '账号诊断'
          : item.workflowId === 'trend_analysis'
            ? '热点分析'
            : item.workflowId === 'video_creator_quality'
              ? '视频博主质量诊断'
              : item.displayName
      return {
        id: item.id,
        label: builtinLabel,
        binding,
        page: fallback?.page || ('account-diagnosis' as ActivePage),
        icon: fallback?.icon || '⌘',
      }
    })
  const runnableWorkflows = registeredWorkflows.length > 0
    ? registeredWorkflows
    : fallbackWorkflows

  return (
    <div className="app-shell">
      <aside className="workspace-sidebar">
        <div className="brand-row">
          <div className="logo">薯</div>
          <div>
            <strong>创作者工作区</strong>
            <span>{workspace?.name || '默认工作区'}</span>
          </div>
        </div>
        <nav aria-label="内容资产导航">
          <div className="nav-section-title">内容资产</div>
          <button
            className={activePage === 'source-materials' && isCreatorInputAssetPanel(inputAssetPanel) ? 'active' : ''}
            onClick={() => onOpenInputAsset(isCreatorInputAssetPanel(inputAssetPanel) ? inputAssetPanel : 'xhs_creator_profiles')}
          >
            <span>👤</span> 创作者档案
          </button>
          {INPUT_ASSET_DEFINITIONS.filter((definition) => !isCreatorInputAssetPanel(definition.panel)).map((definition) => (
            <button
              key={definition.panel}
              className={activePage === 'source-materials' && inputAssetPanel === definition.panel ? 'active' : ''}
              onClick={() => onOpenInputAsset(definition.panel)}
            >
              <span>{definition.icon}</span> {definition.label}
            </button>
          ))}
          <button className={activePage === 'image-assets' ? 'active' : ''} onClick={() => onSetActivePage('image-assets')}><span>🖼</span> 图文素材</button>
          <button className={activePage === 'video-assets' ? 'active' : ''} onClick={() => onSetActivePage('video-assets')}><span>🎞</span> 视频素材</button>
          <button className={activePage === 'history' ? 'active' : ''} onClick={() => onSetActivePage('history')}><span>◷</span> 分析结果</button>
          <button className={activePage === 'topics' ? 'active' : ''} onClick={() => onSetActivePage('topics')}><span>◇</span> 选题库</button>
          <button className={activePage === 'drafts' ? 'active' : ''} onClick={() => onSetActivePage('drafts')}><span>▱</span> 创作输出</button>
          <button className={activePage === 'simulations' ? 'active' : ''} onClick={() => onSetActivePage('simulations')}><span>👥</span> 受众模拟</button>
          <button className={activePage === 'conversations' ? 'active' : ''} onClick={() => onSetActivePage('conversations')}><span>💬</span> 对话记录</button>
        </nav>
      </aside>
      <main className="workspace-main">
        <header className="topbar">
          <div>
            <h1>创作者内容诊断与选题共创助手</h1>
            <p>左侧管理内容资产；右侧发起 workflow 调用并查看能力资产。</p>
          </div>
          <button className={`help-button ${showHelp ? 'active' : ''}`} type="button" aria-expanded={showHelp} aria-controls="workspace-help-panel" onClick={onToggleHelp}>帮助</button>
        </header>
        {showHelp && (
          <section id="workspace-help-panel" className="help-panel" aria-label="当前页面帮助">
            <div><span>整体说明</span><p>左侧管理内容资产；右侧发起 workflow 调用并查看 Skills、Agents、Workflows。</p></div>
            <div><span>{helpContent.title}</span><p>{helpContent.description}</p><ul>{helpContent.bullets.map((item) => <li key={item}>{item}</li>)}</ul></div>
          </section>
        )}
        {children}
      </main>
      <aside className="capability-sidebar">
        <div className="capability-header"><strong>能力资产</strong><span>调用 workflow · 查看能力组合</span></div>
        <nav aria-label="能力资产导航">
          <div className="nav-section-title">workflow 调用</div>
          {runnableWorkflows.map((item) => (
            <button key={item.id} className={activePage === item.page ? 'active' : ''} onClick={() => { onSetWorkflowTab(item.binding); onSetActivePage(item.page) }}>
              <span>{item.icon}</span> {item.label}
            </button>
          ))}
          <div className="nav-section-title">能力资产</div>
          <button className={activePage === 'skills' ? 'active' : ''} onClick={() => onSetActivePage('skills')}><span>✦</span> Skills</button>
          <button className={activePage === 'agents' ? 'active' : ''} onClick={() => onSetActivePage('agents')}><span>◉</span> Agents</button>
          <button className={activePage === 'workflows' ? 'active' : ''} onClick={() => onSetActivePage('workflows')}><span>⌘</span> Workflows</button>
        </nav>
      </aside>
    </div>
  )
}
