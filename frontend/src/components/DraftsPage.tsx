import type { ReactNode } from 'react'

import { EmptyState, JsonPreview } from './CommonUi'
import { SaveIndicator, type SaveState } from './StageResultViews'
import type { Draft, DraftSummary } from '../types'

type Props = {
  drafts: DraftSummary[]
  selectedDraft: Draft | null
  draftEditor: string
  draftSaveState: SaveState
  onOpenDraft: (draftId: string) => void
  onDraftEditorChange: (value: string) => void
  onSaveDraftEdits: () => void
  onGenerateStructureFromBrief: (draft: Draft) => void
  onRunAudienceSimulation: (draft: Draft) => void
  renderDraftStructure: (value: Record<string, unknown>) => ReactNode
  draftDisplayTitle: (draft: Draft) => string
  draftKindLabel: (draft: Draft | DraftSummary) => string
}

export function DraftsPage({
  drafts,
  selectedDraft,
  draftEditor,
  draftSaveState,
  onOpenDraft,
  onDraftEditorChange,
  onSaveDraftEdits,
  onGenerateStructureFromBrief,
  onRunAudienceSimulation,
  renderDraftStructure,
  draftDisplayTitle,
  draftKindLabel,
}: Props) {
  return (
    <div className="workspace-page">
      <section className="history-list">
        <div className="panel-title">▱ 创作输出</div>
        {drafts.length === 0 ? (
          <EmptyState>
            暂无创作 Brief 或内容结构。请先从选题生成 Brief，再继续生成结构。
          </EmptyState>
        ) : (
          drafts.map((draft) => (
            <button
              key={draft.id}
              className={`run-row ${selectedDraft?.id === draft.id ? 'active' : ''}`}
              onClick={() => onOpenDraft(draft.id)}
            >
              <span>
                {draft.sourceWorkflow === 'trend_analysis' ? '热点' : '账号'} ·{' '}
                {draftKindLabel(draft)}
              </span>
              <b>{draft.status}</b>
              <small>{new Date(draft.createdAt).toLocaleString()}</small>
            </button>
          ))
        )}
      </section>
      <section className="history-detail">
        {selectedDraft ? (
          <>
            <div className="detail-head asset-detail-head">
              <div>
                <h2>{draftDisplayTitle(selectedDraft)}</h2>
                <p>
                  {draftKindLabel(selectedDraft)} · {selectedDraft.status} ·{' '}
                  {new Date(selectedDraft.createdAt).toLocaleString()}
                </p>
              </div>
              <div className="detail-actions">
                {selectedDraft.kind === 'content_brief' && (
                  <button onClick={() => onGenerateStructureFromBrief(selectedDraft)}>
                    继续生成内容结构
                  </button>
                )}
                <button onClick={() => onRunAudienceSimulation(selectedDraft)}>
                  发送到受众模拟
                </button>
              </div>
            </div>
            <div className="asset-detail-card">
              <div className="asset-section-head">
                <h3>可编辑内容</h3>
                <span>用户编辑区</span>
              </div>
              <label htmlFor="draft-editor">Editable Content JSON</label>
              <textarea
                id="draft-editor"
                rows={12}
                value={draftEditor}
                onChange={(event) => onDraftEditorChange(event.target.value)}
              />
              <div className="save-row">
                <button className="save-button" onClick={onSaveDraftEdits}>
                  保存创作输出资产
                </button>
                <SaveIndicator state={draftSaveState} />
              </div>
            </div>
            <div className="asset-detail-card readonly">
              <div className="asset-section-head">
                <h3>生成快照</h3>
                <span>只读</span>
              </div>
              {renderDraftStructure(selectedDraft.generatedSnapshot)}
            </div>
            <div className="asset-detail-card readonly">
              <div className="asset-section-head">
                <h3>来源与执行记录</h3>
                <span>只读</span>
              </div>
              <div className="asset-meta-grid">
                <div>
                  <b>类型</b>
                  <span>{draftKindLabel(selectedDraft)}</span>
                </div>
                <div>
                  <b>来源 workflow</b>
                  <span>{selectedDraft.sourceWorkflow}</span>
                </div>
                <div>
                  <b>Topic ID</b>
                  <span>{selectedDraft.topicId}</span>
                </div>
                <div>
                  <b>来源分析</b>
                  <span>{selectedDraft.sourceAnalysisRunId || '无'}</span>
                </div>
                <div>
                  <b>创建时间</b>
                  <span>{new Date(selectedDraft.createdAt).toLocaleString()}</span>
                </div>
                <div>
                  <b>更新时间</b>
                  <span>{new Date(selectedDraft.updatedAt).toLocaleString()}</span>
                </div>
              </div>
              <details className="asset-json-details" open>
                <summary>Input Snapshot</summary>
                <JsonPreview value={selectedDraft.inputSnapshot} />
              </details>
              <details className="asset-json-details">
                <summary>Stage Errors / Model Metadata</summary>
                <JsonPreview
                  value={{
                    stageErrors: selectedDraft.stageErrors,
                    modelMetadata: selectedDraft.modelMetadata,
                  }}
                />
              </details>
            </div>
          </>
        ) : (
          <EmptyState>
            选择一个创作 Brief 或内容结构，查看生成快照和当前编辑内容。
          </EmptyState>
        )}
      </section>
    </div>
  )
}
