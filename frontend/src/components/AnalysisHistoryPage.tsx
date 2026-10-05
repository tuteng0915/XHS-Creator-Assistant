import type { ReactNode } from 'react'

import { SaveIndicator, type SaveState } from './StageResultViews'
import type { StageView } from './WorkflowOutputPanel'
import type { AnalysisRun, AnalysisRunSummary, ReviewStatus } from '../types'
import { reviewStatusLabel, workflowLabel } from '../appUtils'
import { stageSeedFromRun } from '../workflowStageViews'

type ReviewDraft = { userNotes: string; reviewStatus: ReviewStatus }

type RunReviewEditorProps = {
  idPrefix: string
  draft: ReviewDraft
  onDraftChange: (draft: ReviewDraft) => void
  onSave: () => void
  saveState: SaveState
  hint: string
}

export function RunReviewEditor({
  idPrefix,
  draft,
  onDraftChange,
  onSave,
  saveState,
  hint,
}: RunReviewEditorProps) {
  return (
    <section className="review-card">
      <div className="detail-head">
        <div>
          <h3>人工复盘</h3>
          <p>{hint}</p>
        </div>
      </div>
      <label htmlFor={`${idPrefix}-status`}>复盘状态</label>
      <select
        id={`${idPrefix}-status`}
        value={draft.reviewStatus}
        onChange={(event) =>
          onDraftChange({
            ...draft,
            reviewStatus: event.target.value as ReviewStatus,
          })
        }
      >
        <option value="unreviewed">未复盘</option>
        <option value="useful">有用</option>
        <option value="rejected">弃用</option>
      </select>
      <label htmlFor={`${idPrefix}-notes`}>复盘备注</label>
      <textarea
        id={`${idPrefix}-notes`}
        rows={4}
        placeholder="记录这次结果是否可复用、哪里需要调整、后续如何改 prompt 或资产。"
        value={draft.userNotes}
        onChange={(event) =>
          onDraftChange({ ...draft, userNotes: event.target.value })
        }
      />
      <div className="save-row">
        <button type="button" onClick={onSave} disabled={saveState.phase === 'saving'}>
          保存复盘
        </button>
        <SaveIndicator state={saveState} />
      </div>
    </section>
  )
}

type AnalysisHistoryPageProps = {
  publicMode?: boolean
  analysisRuns: AnalysisRunSummary[]
  selectedRun: AnalysisRun | null
  analysisReviewDraft: ReviewDraft
  analysisReviewSaveState: SaveState
  loadState?: SaveState
  renderStageResult: (stage: StageView, run: AnalysisRun) => ReactNode
  onOpenRun: (runId: string, inOutput?: boolean) => void
  onAnalysisReviewDraftChange: (draft: ReviewDraft) => void
  onSaveAnalysisRunReview: () => void
}

export function AnalysisHistoryPage({
  publicMode = false,
  analysisRuns,
  selectedRun,
  analysisReviewDraft,
  analysisReviewSaveState,
  loadState,
  renderStageResult,
  onOpenRun,
  onAnalysisReviewDraftChange,
  onSaveAnalysisRunReview,
}: AnalysisHistoryPageProps) {
  return (
    <div className="workspace-page">
      <section className="history-list">
        <div className="panel-title">◷ 分析结果</div>
        {analysisRuns.length === 0 ? (
          <div className="empty-card">暂无分析运行。</div>
        ) : (
          analysisRuns.map((run) => (
            <button
              key={run.id}
              className={`run-row ${selectedRun?.id === run.id ? 'active' : ''}`}
              onClick={() => onOpenRun(run.id)}
            >
              <span>{workflowLabel(run.workflowType)}</span>
              <b>{run.status}</b>
              <small>{reviewStatusLabel(run.reviewStatus)}</small>
              <small>{new Date(run.createdAt).toLocaleString()}</small>
            </button>
          ))
        )}
      </section>
      <section className="history-detail">
        {loadState?.phase === 'saving' && <p role="status">正在读取分析记录…</p>}
        {loadState?.phase === 'error' && <p role="alert">{loadState.message} 请重新点击记录重试。</p>}
        {selectedRun ? (
          <>
            <div className="detail-head">
              <div>
                <h2>{workflowLabel(selectedRun.workflowType)}</h2>
                <p>
                  {selectedRun.status} ·{' '}
                  {new Date(selectedRun.createdAt).toLocaleString()}
                </p>
              </div>
              <button onClick={() => onOpenRun(selectedRun.id, true)}>
                在输出区打开
              </button>
            </div>
            <details open={!publicMode}><summary>复盘备注</summary><RunReviewEditor
              idPrefix="analysis-run-review"
              draft={analysisReviewDraft}
              onDraftChange={onAnalysisReviewDraftChange}
              onSave={onSaveAnalysisRunReview}
              saveState={analysisReviewSaveState}
              hint="执行输入、阶段结果和模型元数据是不可变历史；这里仅保存人工复盘判断。"
            /></details>
            <details open={!publicMode}><summary>{publicMode ? '本次分析的材料' : '原始输入快照'}</summary>
            <pre className="json-preview">
              {publicMode ? String((selectedRun.inputSnapshot.historicalPosts as {content?: string})?.content || '未保存笔记正文') : JSON.stringify(selectedRun.inputSnapshot, null, 2)}
            </pre>
            </details>
            {!publicMode && <label>生成结果</label>}
            {stageSeedFromRun(selectedRun).map((stage) => (
              <div className="stage compact" key={stage.key}>
                <div className="stage-h">
                  <div className="stage-n">{stage.n}</div>
                  <h3>{stage.title}</h3>
                </div>
                {stage.error && <div className="err">{stage.error}</div>}
                {renderStageResult(stage, selectedRun)}
              </div>
            ))}
          </>
        ) : (
          !['saving','error'].includes(loadState?.phase || '') && <div className="empty-card">选择一次运行查看输入和结果。</div>
        )}
      </section>
    </div>
  )
}
