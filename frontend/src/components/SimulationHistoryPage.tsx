import type { ReactNode } from 'react'

import { EmptyState, JsonPreview } from './CommonUi'
import { RunReviewEditor } from './AnalysisHistoryPage'
import type { SaveState } from './StageResultViews'
import type { ReviewStatus, SimulationRun, SimulationRunSummary, Topic } from '../types'
import type { StageView } from './WorkflowOutputPanel'
import { SimulationStageNotice } from './SimulationStageNotice'
import { stageDisplayStatus } from '../simulationStageStatus'
import { SimulationReaderSummary } from './SimulationReaderSummary'
import { SimulationTaskSummary } from './SimulationTaskSummary'
import { RetestProgress } from './RetestProgress'
import { PanelComparisonView } from './PanelComparisonView'
import {SimulationChat} from './SimulationChat'
import {simulationCategoryFor, simulationCategoryLabel, simulationStatusLabel} from '../simulationChat'

type ReviewDraft = {
  reviewStatus: ReviewStatus
  userNotes: string
}

type Props = {
  publicMode?: boolean
  simulationRuns: SimulationRunSummary[]
  selectedSimulationRun: SimulationRun | null
  simulationReviewDraft: ReviewDraft
  simulationReviewSaveState: SaveState
  loadState?: SaveState
  reviewStatusLabel: (status: ReviewStatus) => string
  onOpenSimulationRun: (runId: string, showInOutput?: boolean) => void
  onSimulationObserved?: (run: SimulationRun) => void
  onTopicAdded?: (topic: Topic) => void
  topics?: Topic[]
  onSimulationReviewDraftChange: (draft: ReviewDraft) => void
  onSaveSimulationRunReview: () => void
  stageSeedFromSimulation: (run: SimulationRun) => StageView[]
  renderStageResult: (stage: StageView) => ReactNode
}

export function SimulationHistoryPage({
  publicMode = false,
  simulationRuns,
  selectedSimulationRun,
  simulationReviewDraft,
  simulationReviewSaveState,
  loadState,
  reviewStatusLabel,
  onOpenSimulationRun,
  onSimulationObserved,
  onTopicAdded,
  topics,
  onSimulationReviewDraftChange,
  onSaveSimulationRunReview,
  stageSeedFromSimulation,
  renderStageResult,
}: Props) {
  return (
    <div className={`workspace-page${publicMode?' creator-simulation-history':''}`}>
      <section className="history-list">
        <div className="panel-title">{publicMode?'历史记录':'👥 受众模拟'}</div>
        {simulationRuns.length === 0 ? (
          <EmptyState>暂无受众模拟。</EmptyState>
        ) : (
          simulationRuns.map((run) => (
            <button
              key={run.id}
              className={`run-row ${selectedSimulationRun?.id === run.id ? 'active' : ''}`}
              onClick={() => onOpenSimulationRun(run.id)}
            >
              <span>{run.parentSimulationId ? '同组复测' : run.simulationCategory?`${simulationCategoryLabel(simulationCategoryFor(run))}模拟`:'受众模拟'}</span>
              {run.targetTitle&&<span className="simulation-history-target">{run.targetTitle}</span>}
              <b>{simulationStatusLabel(run.status)}</b>
              <small>{reviewStatusLabel(run.reviewStatus)}</small>
              <small>{new Date(run.createdAt).toLocaleString()}</small>
            </button>
          ))
        )}
      </section>
      <section className="history-detail">
        {loadState?.phase === 'saving' && <p role="status">正在读取模拟记录…</p>}
        {loadState?.phase === 'error' && <p role="alert">{loadState.message} 请重新点击记录重试。</p>}
        {selectedSimulationRun ? (
          <>
            <div className="detail-head">
              <div>
                <h2>{publicMode?`${simulationCategoryLabel(simulationCategoryFor(selectedSimulationRun))}模拟记录`:'受众模拟'}</h2>
                <p>
                  {simulationStatusLabel(selectedSimulationRun.status)} ·{' '}
                  {new Date(selectedSimulationRun.createdAt).toLocaleString()}
                </p>
              </div>
              {!publicMode && <button onClick={() => onOpenSimulationRun(selectedSimulationRun.id, true)}>
                在输出区打开
              </button>}
            </div>
            {selectedSimulationRun.parentSimulationId && <section aria-label="复测来源">
              <p>本次沿用上次人物与阅读任务，独立阅读新版稿件。模型与提示版本尚未配对核验。</p>
              {simulationRuns.some(r => r.id === selectedSimulationRun.parentSimulationId && r.workspaceId === selectedSimulationRun.workspaceId)
                ? <button onClick={() => onOpenSimulationRun(selectedSimulationRun.parentSimulationId!)}>查看上次试读</button>
                : <p className="muted">上次试读不在当前历史列表中。</p>}
              <PanelComparisonView key={`comparison:${selectedSimulationRun.id}`} run={selectedSimulationRun}/>
            </section>}
            {!publicMode && selectedSimulationRun.parentSimulationId && ['pending', 'running'].includes(selectedSimulationRun.status)
              && onSimulationObserved && <RetestProgress key={`retest-progress:${selectedSimulationRun.id}`} run={selectedSimulationRun} onObserved={onSimulationObserved}/>}
            <SimulationTaskSummary run={selectedSimulationRun} />
            <SimulationReaderSummary key={`readers:${selectedSimulationRun.id}`} run={selectedSimulationRun} />
            <details open={!publicMode}><summary>复盘备注</summary><RunReviewEditor
              idPrefix="simulation-run-review"
              draft={simulationReviewDraft}
              onDraftChange={onSimulationReviewDraftChange}
              onSave={onSaveSimulationRunReview}
              saveState={simulationReviewSaveState}
              hint="受众角色、反应、辩论和综合结论是不可变历史；这里仅保存人工复盘判断。"
            /></details>
            {!publicMode && <><label>原始输入快照</label><JsonPreview value={selectedSimulationRun.inputSnapshot} /></>}
            {!publicMode && <label>模拟结果</label>}
            {publicMode ? <SimulationChat key={`chat:${selectedSimulationRun.id}`} run={selectedSimulationRun} onObserved={onSimulationObserved} onTopicAdded={onTopicAdded} topics={topics}/> : stageSeedFromSimulation(selectedSimulationRun).map((stage) => (
              <div className="stage compact" key={stage.key}>
                <div className="stage-h">
                  <div className="stage-n">{stage.n}</div>
                  <h3>{stage.title}</h3>
                  <div className={`stage-status ${stageDisplayStatus(stage).className}`}>{stageDisplayStatus(stage).label}</div>
                </div>
                <SimulationStageNotice stage={stage} />
                {renderStageResult(stage)}
              </div>
            ))}
          </>
        ) : (
          loadState?.phase !== 'saving' && loadState?.phase !== 'error' && <EmptyState>选择一次受众模拟查看输入和结果。</EmptyState>
        )}
      </section>
    </div>
  )
}
