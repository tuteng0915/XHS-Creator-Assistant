import type { ReactNode } from 'react'

import { SaveIndicator, type SaveState } from './StageResultViews'
import type { StageView } from './WorkflowOutputPanel'
import type { AnalysisRun, AnalysisRunSummary, ReviewStatus } from '../types'
import { reviewStatusLabel, workflowLabel } from '../appUtils'
import { stageSeedFromRun } from '../workflowStageViews'
import { isOracleShowcase } from '../recordOrigin'
import { OracleNotice } from './OracleNotice'
import { creatorNotesFromPayload } from '../creatorNotes'
import type { RunStatus } from '../types'

const analysisStatusLabel = (status: RunStatus) => ({pending:'等待开始',running:'正在分析',completed:'已完成',partially_completed:'已有部分结果',failed:'未完成'}[status])

function AnalysisMaterials({ run }: {run: AnalysisRun}) {
  const notes = creatorNotesFromPayload(run.inputSnapshot.xhsCreatorProfile)
  const historical = run.inputSnapshot.historicalPosts as {content?: unknown} | undefined
  if (notes.length) return <div className="analysis-history-materials">
    {notes.map(note => <article key={note.noteId}>
      <h3>{note.title}</h3>
      <p>{note.desc || '这条笔记未保存正文。'}</p>
    </article>)}
  </div>
  return <p className="analysis-history-material-text">{typeof historical?.content === 'string' && historical.content ? historical.content : '未保存笔记正文'}</p>
}

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
        <option value="unreviewed">未标记</option>
        <option value="useful">有用</option>
        <option value="rejected">弃用</option>
      </select>
      <label htmlFor={`${idPrefix}-notes`}>复盘备注</label>
      <textarea
        id={`${idPrefix}-notes`}
        rows={4}
        placeholder="记录值得保留的发现，或下次想试的调整。"
        value={draft.userNotes}
        onChange={(event) =>
          onDraftChange({ ...draft, userNotes: event.target.value })
        }
      />
      <div className="save-row">
        <button type="button" className="primary" onClick={onSave} disabled={saveState.phase === 'saving'}>
          保存复盘
        </button>
        <SaveIndicator state={saveState} />
      </div>
    </section>
  )
}

type AnalysisHistoryPageProps = {
  embedded?: boolean
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
  embedded = false,
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
    <div className={`workspace-page${embedded ? ' diagnosis-history-embedded' : ''}`} role="region" aria-label={publicMode ? '诊断历史' : '分析结果'}>
      <section className="history-list">
        <div className="panel-title">◷ {publicMode ? '诊断历史' : '分析结果'}</div>
        {analysisRuns.length === 0 ? (
          <div className="empty-card">{publicMode ? '暂无诊断记录。完成分析后会保存在这里。' : '暂无分析运行。'}</div>
        ) : (
          analysisRuns.map((run) => (
            <button
              key={run.id}
              className={`run-row ${selectedRun?.id === run.id ? 'active' : ''}`}
              onClick={() => onOpenRun(run.id)}
            >
              <span>{workflowLabel(run.workflowType)}</span>
              <b>{publicMode ? analysisStatusLabel(run.status) : run.status}</b>
              {run.reviewStatus !== 'unreviewed' && <small>{reviewStatusLabel(run.reviewStatus)}</small>}
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
                <h2>{workflowLabel(selectedRun.workflowType)}{isOracleShowcase(selectedRun) && <OracleNotice />}</h2>
                <p>
                  {publicMode ? analysisStatusLabel(selectedRun.status) : selectedRun.status} ·{' '}
                  {new Date(selectedRun.createdAt).toLocaleString()}
                </p>
              </div>
              {!publicMode && <button onClick={() => onOpenRun(selectedRun.id, true)}>
                在输出区打开
              </button>}
            </div>
            <details open={!publicMode}><summary>复盘备注</summary><RunReviewEditor
              idPrefix="analysis-run-review"
              draft={analysisReviewDraft}
              onDraftChange={onAnalysisReviewDraftChange}
              onSave={onSaveAnalysisRunReview}
              saveState={analysisReviewSaveState}
              hint={publicMode ? '你的判断会单独保存，不改动这次分析。' : '执行输入、阶段结果和模型元数据是不可变历史；这里仅保存人工复盘判断。'}
            /></details>
            <details open={!publicMode}><summary>{publicMode ? '本次分析的材料' : '原始输入快照'}</summary>
              {publicMode ? <AnalysisMaterials run={selectedRun} /> : <pre className="json-preview">{JSON.stringify(selectedRun.inputSnapshot, null, 2)}</pre>}
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
          !['saving','error'].includes(loadState?.phase || '') && <div className="empty-card">{publicMode ? '选择一条诊断记录查看结果。' : '选择一次运行查看输入和结果。'}</div>
        )}
      </section>
    </div>
  )
}
