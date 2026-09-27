import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { AnalysisRun, Topic } from '../types'
import { AnalysisHistoryPage } from './AnalysisHistoryPage'
import { StageResultRenderer } from './ArtifactRenderers'

afterEach(cleanup)

const candidate = { title: '原标题', angle: '角度', pain: '痛点', whyFit: '理由' }
const run: AnalysisRun = {
  id: 'history-run', workspaceId: 'workspace', workflowType: 'account_diagnosis',
  status: 'completed', userNotes: '', reviewStatus: 'unreviewed',
  createdAt: '2026-09-27', updatedAt: '2026-09-27', startedAt: null, completedAt: null,
  inputSnapshot: {}, stageResults: { topics: { topics: [candidate] } }, stageErrors: {}, modelMetadata: {},
}
const topic: Topic = {
  id: 'topic', workspaceId: 'workspace', title: candidate.title, angle: candidate.angle,
  associatedPainPoint: '', whyItFits: '', generatedSnapshot: candidate,
  sourceAnalysisRunId: run.id, sourceWorkflow: 'account_diagnosis', status: 'candidate',
  createdAt: '2026-09-27', updatedAt: '2026-09-27T01:00:00Z',
}

it.each(['AI 创作助手', '受众模拟'])('passes the selected topic version to %s', async button => {
  const selected: Topic = { ...topic, status: 'selected', updatedAt: '2026-09-27T02:00:00Z' }
  const save = vi.fn().mockResolvedValue(topic)
  const select = vi.fn().mockResolvedValue(selected)
  const navigate = vi.fn()
  render(<StageResultRenderer publicMode stage={{ key: 'topics', n: '3', title: '选题', status: 'completed', result: run.stageResults.topics }}
    currentRun={run} onSaveGeneratedTopic={save} onSelectTopic={select}
    onGenerateBrief={navigate} onSimulateSavedTopic={navigate} onGenerateDraft={vi.fn()} onFillSimulationTopic={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: button }))
  await waitFor(() => expect(navigate).toHaveBeenCalledWith(selected))
  expect(save).toHaveBeenCalledWith(candidate, run)
  expect(select).toHaveBeenCalledWith(topic)
})

it('renders reopened history with its source run instead of the active execution', () => {
  const renderer = vi.fn(() => null)
  render(<AnalysisHistoryPage publicMode analysisRuns={[run]} selectedRun={run}
    analysisReviewDraft={{ userNotes: '', reviewStatus: 'unreviewed' }} analysisReviewSaveState={{ phase: 'saved' }}
    renderStageResult={renderer} onOpenRun={vi.fn()} onAnalysisReviewDraftChange={vi.fn()} onSaveAnalysisRunReview={vi.fn()} />)
  expect(renderer).toHaveBeenCalledWith(expect.objectContaining({ key: 'topics', result: run.stageResults.topics }), run)
})
