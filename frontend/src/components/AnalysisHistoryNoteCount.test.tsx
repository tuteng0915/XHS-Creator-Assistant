import {cleanup, render, screen, within} from '@testing-library/react'
import {afterEach, expect, it, vi} from 'vitest'
import type {AnalysisRun, AnalysisRunSummary} from '../types'
import {AnalysisHistoryPage} from './AnalysisHistoryPage'

afterEach(cleanup)
const timestamp = '2026-10-16T00:00:00Z'
const run: AnalysisRunSummary = {id: 'a', workspaceId: 'w', workflowType: 'account_diagnosis', status: 'completed',
  userNotes: '', reviewStatus: 'unreviewed', createdAt: timestamp, updatedAt: timestamp, startedAt: timestamp, completedAt: timestamp}
const props = {publicMode: true, selectedRun: null, analysisReviewDraft: {userNotes: '', reviewStatus: 'unreviewed' as const},
  analysisReviewSaveState: {phase: 'idle' as const}, renderStageResult: () => null, onOpenRun: vi.fn(),
  onAnalysisReviewDraftChange: vi.fn(), onSaveAnalysisRunReview: vi.fn()}

it('shows each frozen run count in the list without loading its detail', () => {
  render(<AnalysisHistoryPage {...props} analysisRuns={[{...run, noteCount: 2}, {...run, id: 'b', noteCount: 10}]} />)
  const rows = screen.getAllByRole('button', {name: /账号诊断 已完成/})
  expect(within(rows[0]).getByText(/共 2 条笔记/)).toBeVisible()
  expect(within(rows[1]).getByText(/共 10 条笔记/)).toBeVisible()
  expect(props.onOpenRun).not.toHaveBeenCalled()
})

it('does not invent counts for legacy summaries, while preserving a genuine zero', () => {
  render(<AnalysisHistoryPage {...props} analysisRuns={[run, {...run, id: 'b', noteCount: null}, {...run, id: 'c', noteCount: 0}]} />)
  const rows = screen.getAllByRole('button', {name: /账号诊断 已完成/})
  expect(within(rows[0]).queryByText(/条笔记/)).not.toBeInTheDocument()
  expect(within(rows[1]).queryByText(/条笔记/)).not.toBeInTheDocument()
  expect(within(rows[2]).getByText(/共 0 条笔记/)).toBeVisible()
})

it('shows the same saved count in the selected detail', () => {
  const detail: AnalysisRun = {...run, noteCount: 2, inputSnapshot: {}, stageResults: {}, stageErrors: {}, modelMetadata: {}}
  render(<AnalysisHistoryPage {...props} selectedRun={detail} analysisRuns={[detail]} />)
  expect(screen.getAllByText(/共 2 条笔记/)).toHaveLength(2)
})
