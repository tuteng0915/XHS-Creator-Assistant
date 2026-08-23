import type { ReactNode } from 'react'

import {
  INPUT_ASSET_DEFINITIONS,
  isCreatorInputAssetPanel,
  type InputAssetPanel,
} from '../inputAssets'
import type { Workspace } from '../types'
import type { WorkflowTab } from '../workflows'

export type ActivePage =
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
  activePage: ActivePage
  inputAssetPanel: InputAssetPanel
  showHelp: boolean
  helpContent: HelpContent
  children: ReactNode
  onOpenInputAsset: (panel: InputAssetPanel) => void
  onSetActivePage: (page: ActivePage) => void
  onSetWorkflowTab: (tab: WorkflowTab) => void
  onToggleHelp: () => void
}

export function WorkspaceShell({
  workspace,
  activePage,
  inputAssetPanel,
  showHelp,
  helpContent,
  children,
  onOpenInputAsset,
  onSetActivePage,
  onSetWorkflowTab,
  onToggleHelp,
}: WorkspaceShellProps) {
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
            className={
              activePage === 'source-materials' &&
              isCreatorInputAssetPanel(inputAssetPanel)
                ? 'active'
                : ''
            }
            onClick={() =>
              onOpenInputAsset(
                isCreatorInputAssetPanel(inputAssetPanel)
                  ? inputAssetPanel
                  : 'xhs_creator_profiles',
              )
            }
          >
            <span>👤</span> 创作者档案
          </button>
          {INPUT_ASSET_DEFINITIONS.filter(
            (definition) => !isCreatorInputAssetPanel(definition.panel),
          ).map((definition) => (
            <button
              key={definition.panel}
              className={
                activePage === 'source-materials' &&
                inputAssetPanel === definition.panel
                  ? 'active'
                  : ''
              }
              onClick={() => onOpenInputAsset(definition.panel)}
            >
              <span>{definition.icon}</span> {definition.label}
            </button>
          ))}
          <button
            className={activePage === 'image-assets' ? 'active' : ''}
            onClick={() => onSetActivePage('image-assets')}
          >
            <span>🖼</span> 图文素材
          </button>
          <button
            className={activePage === 'video-assets' ? 'active' : ''}
            onClick={() => onSetActivePage('video-assets')}
          >
            <span>🎞</span> 视频素材
          </button>
          <button
            className={activePage === 'history' ? 'active' : ''}
            onClick={() => onSetActivePage('history')}
          >
            <span>◷</span> 分析结果
          </button>
          <button
            className={activePage === 'topics' ? 'active' : ''}
            onClick={() => onSetActivePage('topics')}
          >
            <span>◇</span> 选题库
          </button>
          <button
            className={activePage === 'simulations' ? 'active' : ''}
            onClick={() => onSetActivePage('simulations')}
          >
            <span>👥</span> 受众模拟
          </button>
        </nav>
      </aside>

      <main className="workspace-main">
        <header className="topbar">
          <div>
            <h1>创作者内容诊断与选题共创助手</h1>
            <p>左侧管理内容资产；右侧发起 workflow 调用并查看能力资产。</p>
          </div>
          <button
            className={`help-button ${showHelp ? 'active' : ''}`}
            type="button"
            aria-expanded={showHelp}
            aria-controls="workspace-help-panel"
            onClick={onToggleHelp}
          >
            帮助
          </button>
        </header>

        {showHelp && (
          <section
            id="workspace-help-panel"
            className="help-panel"
            aria-label="当前页面帮助"
          >
            <div>
              <span>整体说明</span>
              <p>
                左侧管理内容资产；右侧发起 workflow 调用并查看
                Skills、Agents、Workflows。当前页面帮助集中写在这里。
              </p>
            </div>
            <div>
              <span>{helpContent.title}</span>
              <p>{helpContent.description}</p>
              <ul>
                {helpContent.bullets.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          </section>
        )}

        {children}
      </main>

      <aside className="capability-sidebar">
        <div className="capability-header">
          <strong>能力资产</strong>
          <span>调用 workflow · 查看能力组合</span>
        </div>
        <nav aria-label="能力资产导航">
          <div className="nav-section-title">workflow 调用</div>
          <button
            className={activePage === 'account-diagnosis' ? 'active' : ''}
            onClick={() => {
              onSetWorkflowTab('account')
              onSetActivePage('account-diagnosis')
            }}
          >
            <span>📊</span> 账号诊断
          </button>
          <button
            className={activePage === 'trend-analysis' ? 'active' : ''}
            onClick={() => {
              onSetWorkflowTab('trend')
              onSetActivePage('trend-analysis')
            }}
          >
            <span>🔥</span> 热点分析
          </button>
          <button
            className={activePage === 'video-quality' ? 'active' : ''}
            onClick={() => {
              onSetWorkflowTab('video')
              onSetActivePage('video-quality')
            }}
          >
            <span>🎬</span> 视频博主质量诊断
          </button>
          <div className="nav-section-title">能力资产</div>
          <button
            className={activePage === 'skills' ? 'active' : ''}
            onClick={() => onSetActivePage('skills')}
          >
            <span>✦</span> Skills
          </button>
          <button
            className={activePage === 'agents' ? 'active' : ''}
            onClick={() => onSetActivePage('agents')}
          >
            <span>◉</span> Agents
          </button>
          <button
            className={activePage === 'workflows' ? 'active' : ''}
            onClick={() => onSetActivePage('workflows')}
          >
            <span>⌘</span> Workflows
          </button>
        </nav>
      </aside>
    </div>
  )
}
