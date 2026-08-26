import type { ReactNode } from 'react'

import { EmptyState, JsonPreview } from './CommonUi'
import { RunReviewEditor } from './AnalysisHistoryPage'
import type { SaveState } from './StageResultViews'
import type { ReviewStatus, SimulationRun, SimulationRunSummary } from '../types'
import type { StageView } from './WorkflowOutputPanel'

type ReviewDraft = {
  reviewStatus: ReviewStatus
  userNotes: string
}

type Props = {
  simulationRuns: SimulationRunSummary[]
  selectedSimulationRun: SimulationRun | null
  simulationReviewDraft: ReviewDraft
  simulationReviewSaveState: SaveState
  reviewStatusLabel: (status: ReviewStatus) => string
  onOpenSimulationRun: (runId: string, showInOutput?: boolean) => void
  onSimulationReviewDraftChange: (draft: ReviewDraft) => void
  onSaveSimulationRunReview: () => void
  stageSeedFromSimulation: (run: SimulationRun) => StageView[]
  renderStageResult: (stage: StageView) => ReactNode
}

export function SimulationHistoryPage({
  simulationRuns,
  selectedSimulationRun,
  simulationReviewDraft,
  simulationReviewSaveState,
  reviewStatusLabel,
  onOpenSimulationRun,
  onSimulationReviewDraftChange,
  onSaveSimulationRunReview,
  stageSeedFromSimulation,
  renderStageResult,
}: Props) {
  return (
    <div className="workspace-page">
      <section className="history-list">
        <div className="panel-title">👥 受众模拟</div>
        {simulationRuns.length === 0 ? (
          <EmptyState>暂无受众模拟。</EmptyState>
        ) : (
          simulationRuns.map((run) => (
            <button
              key={run.id}
              className={`run-row ${selectedSimulationRun?.id === run.id ? 'active' : ''}`}
              onClick={() => onOpenSimulationRun(run.id)}
            >
              <span>受众模拟</span>
              <b>{run.status}</b>
              <small>{reviewStatusLabel(run.reviewStatus)}</small>
              <small>{new Date(run.createdAt).toLocaleString()}</small>
            </button>
          ))
        )}
      </section>
      <section className="history-detail">
        {selectedSimulationRun ? (
          <>
            <div className="detail-head">
              <div>
                <h2>受众模拟</h2>
                <p>
                  {selectedSimulationRun.status} ·{' '}
                  {new Date(selectedSimulationRun.createdAt).toLocaleString()}
                </p>
              </div>
              <button onClick={() => onOpenSimulationRun(selectedSimulationRun.id, true)}>
                在输出区打开
              </button>
            </div>
            <RunReviewEditor
              idPrefix="simulation-run-review"
              draft={simulationReviewDraft}
              onDraftChange={onSimulationReviewDraftChange}
              onSave={onSaveSimulationRunReview}
              saveState={simulationReviewSaveState}
              hint="受众角色、反应、辩论和综合结论是不可变历史；这里仅保存人工复盘判断。"
            />
            <label>原始输入快照</label>
            <JsonPreview value={selectedSimulationRun.inputSnapshot} />
            <label>模拟结果</label>
            {stageSeedFromSimulation(selectedSimulationRun).map((stage) => (
              <div className="stage compact" key={stage.key}>
                <div className="stage-h">
                  <div className="stage-n">{stage.n}</div>
                  <h3>{stage.title}</h3>
                </div>
                {stage.error && <div className="err">{stage.error}</div>}
                {renderStageResult(stage)}
              </div>
            ))}
          </>
        ) : (
          <EmptyState>选择一次受众模拟查看输入和结果。</EmptyState>
        )}
      </section>
    </div>
  )
}
