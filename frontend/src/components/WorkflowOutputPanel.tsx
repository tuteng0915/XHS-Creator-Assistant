import type { ReactNode } from 'react'

import type { WorkflowTab } from '../workflows'
import { withSimulationPersonaLabels } from '../simulationPersonaLabels'
import { SimulationStageNotice } from './SimulationStageNotice'
import { stageDisplayStatus } from '../simulationStageStatus'
import type { FeedbackRun } from '../editorFeedback'
import { isOracleShowcase } from '../recordOrigin'
import { OracleBadge, OracleNotice } from './OracleNotice'

export type StageView = {
  key: string
  origin?: string
  n: string
  title: string
  status: 'waiting' | 'running' | 'completed' | 'failed'
  result?: unknown
  error?: string
  personaLabels?: ReadonlyMap<string, string>
  personaIds?: string[]
  executionErrors?: Record<string, string>
  executionEnded?: boolean
  feedbackRun?: FeedbackRun
}

export type WorkflowOutputKind = 'analysis' | 'simulation'

type WorkflowOutputPanelProps = {
  targetTab: WorkflowTab
  views: StageView[]
  outputKind: WorkflowOutputKind
  runError: string
  renderStageResult: (stage: StageView) => ReactNode
}

export function WorkflowOutputPanel({
  targetTab,
  views,
  outputKind,
  runError,
  renderStageResult,
}: WorkflowOutputPanelProps) {
  const isSimulation = outputKind === 'simulation'
  const renderedViews = isSimulation ? withSimulationPersonaLabels(views) : views
  return (
    <section className="output-panel">
      {views.some(isOracleShowcase) && <><OracleBadge /><OracleNotice /></>}
      {runError && <div className="error-banner">⚠ {runError}</div>}
      {!views.length ? (
        <div className="output-empty">
          <span>✓</span>
          <h2>
            {isSimulation
              ? '受众模拟待运行'
              : targetTab === 'account'
                ? '账号诊断待运行'
                : targetTab === 'video'
                  ? '视频创作者诊断待运行'
                  : '热点分析待运行'}
          </h2>
          <p>运行后结果会渐进渲染，并保存到分析结果。</p>
        </div>
      ) : (
        renderedViews.map((stage) => (
          <div className="stage" key={stage.key}>
            <div className="stage-h">
              <div className="stage-n">{stage.n}</div>
              <h3>{stage.title}</h3>
              <div className={`stage-status ${isSimulation ? stageDisplayStatus(stage).className : stage.status}`}>
                {isSimulation ? stageDisplayStatus(stage).label : stage.status === 'running'
                  ? '分析中…'
                  : stage.status === 'completed'
                    ? '已完成'
                    : stage.status === 'failed'
                      ? '失败'
                      : '等待中'}
              </div>
            </div>
            {stage.status === 'running' && (
              <div className="stage-loading">
                <span className="spinner" />
                分析中…
              </div>
            )}
            {isSimulation ? <SimulationStageNotice stage={stage} /> : stage.error && <div className="err">{stage.error}</div>}
            {renderStageResult(stage)}
          </div>
        ))
      )}
    </section>
  )
}
