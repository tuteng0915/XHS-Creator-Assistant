import { useState } from 'react'
import { StageResultRenderer } from '../components/ArtifactRenderers'
import { CreatorCanvasPage } from '../components/CreatorCanvasPage'
import { CreatorDiagnosisPage } from '../components/CreatorDiagnosisPage'
import { SimulationChat } from '../components/SimulationChat'
import { WorkflowOutputPanel, type StageView } from '../components/WorkflowOutputPanel'
import { WorkspaceShell, type ActivePage } from '../components/WorkspaceShell'
import { accountResult, accountRun, profile, simulation, topic, workspace } from './fixtures'
import type { AnalysisScope } from '../creatorNotes'
import './ReadmePreview.css'

const noAction = () => undefined
const stage: StageView = { key: 'profile', n: '1', title: '账号画像', status: 'completed', result: accountResult }

export function ReadmePreview() {
  const initial = new URLSearchParams(window.location.search).get('view')
  const [view, setView] = useState(initial === 'account' || initial === 'panel' ? initial : 'writing')
  const [showHelp, setShowHelp] = useState(false)
  const [scope, setScope] = useState<AnalysisScope>('all')
  const [currentTopic, setCurrentTopic] = useState(topic)
  const activePage = view === 'account' ? 'account-diagnosis' : view === 'panel' ? 'simulations' : 'drafts'
  function navigate(page: ActivePage) {
    if (page === 'account-diagnosis') setView('account')
    if (page === 'simulations') setView('panel')
    if (page === 'drafts') setView('writing')
  }
  return <div className="readme-preview-frame">
    <div className="readme-preview-label">界面演示 · 虚构材料 · 不连接后端</div>
    <WorkspaceShell workspace={workspace} workspaces={[workspace]} selectedWorkspaceId={workspace.id}
      activePage={activePage} inputAssetPanel="xhs_creator_profiles" showHelp={showHelp}
      helpContent={{ title: 'README 界面演示', description: '复用当前产品组件；笔记、对话与读者发言均为手写虚构材料。', bullets: ['此页不连接正式数据，不调用模型。'] }}
      onOpenInputAsset={noAction} onSetActivePage={navigate} onSelectWorkspace={noAction} onCreateCreatorProfile={noAction}
      onToggleHelp={() => setShowHelp(value => !value)}>
      {view === 'account' && <CreatorDiagnosisPage profile={profile} scope={scope} onScopeChange={setScope} running={false} onRun={noAction} onImport={noAction}>
        <WorkflowOutputPanel targetTab="account" views={[stage]} outputKind="analysis" runError="" renderStageResult={value => <StageResultRenderer
          stage={value} currentRun={accountRun} onSaveGeneratedTopic={async () => topic} onSelectTopic={async value => value}
          onGenerateBrief={async () => undefined} onGenerateDraft={async () => undefined} onFillSimulationTopic={noAction} />} />
      </CreatorDiagnosisPage>}
      {view === 'writing' && <CreatorCanvasPage workspaceId={workspace.id} topic={currentTopic} topics={[currentTopic]} profile={profile}
        onSelect={setCurrentTopic} onUpdated={setCurrentTopic} onSimulate={() => setView('panel')} />}
      {view === 'panel' && <><div className="creator-page-head"><h1>受众模拟</h1></div><SimulationChat run={simulation} topics={[currentTopic]} onUseReaderFeedback={() => setView('writing')} /></>}
    </WorkspaceShell>
  </div>
}
