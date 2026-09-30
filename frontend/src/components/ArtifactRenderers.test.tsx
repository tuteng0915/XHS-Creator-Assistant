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

it('shows material requests separately on a generated topic card', () => {
  render(<StageResultRenderer publicMode stage={{key:'topics', n:'3', title:'选题', status:'completed', result:{topics:[{...candidate,pendingSuggestions:['请确认是否有亲身申请经历？']}]}}}
    currentRun={run} onSaveGeneratedTopic={vi.fn()} onSelectTopic={vi.fn()} onGenerateBrief={vi.fn()} onGenerateDraft={vi.fn()} onFillSimulationTopic={vi.fn()} />)
  expect(screen.getByText('待确认建议')).toBeInTheDocument()
  expect(screen.getByText('请确认是否有亲身申请经历？')).toBeInTheDocument()
  expect(screen.getByRole('heading')).toHaveTextContent(candidate.title)
})

it('shows snapshot-backed account evidence and opens the cited note', () => {
  const snapshotRun: AnalysisRun = { ...run, inputSnapshot: { xhsCreatorProfile: { notes: [
    { noteId: 'n1', title: '真实笔记', desc: '来自本次快照的正文', metrics: { liked: 12, collected: 3 }, comments: [] },
  ] } } }
  render(<StageResultRenderer stage={{key:'profile', n:'1', title:'账号画像', status:'completed', result:{
    profile:{accountPortrait:{summary:{statement:'持续分享真实经验', evidence:[{noteId:'n1',quote:'来自本次快照'}]}}, pillars:[]},
    observations:{schemaVersion:'xhs-account-observations/v1',coverage:{selectedCount:1,availableCount:2,missingDateCount:0,capturedCommentCount:0,missingMetricCounts:{},dateRange:{earliest:'2026-09-01T00:00:00Z',latest:'2026-09-01T00:00:00Z'}},notes:[{noteId:'n1',title:'真实笔记',metrics:{liked:12,collected:3}}]},
  }}} currentRun={snapshotRun} onSaveGeneratedTopic={vi.fn()} onSelectTopic={vi.fn()}
    onGenerateBrief={vi.fn()} onGenerateDraft={vi.fn()} onFillSimulationTopic={vi.fn()} />)
  expect(screen.getByText('本次分析 1 / 已导入 2 条笔记')).toBeInTheDocument()
  expect(screen.getByText(/笔记发布于/)).toBeInTheDocument()
  expect(screen.getByText('持续分享真实经验')).toBeInTheDocument()
  expect(screen.queryByText('来自本次快照的正文')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', {name:'查看依据 · 1 条笔记'}))
  fireEvent.click(screen.getByRole('button', {name:/真实笔记 赞/}))
  expect(screen.getByText('来自本次快照的正文')).toBeInTheDocument()
})

it('separates possible exceptions and dated content changes from performance claims', () => {
  const snapshotRun: AnalysisRun = { ...run, inputSnapshot: { xhsCreatorProfile: { notes: [
    { noteId: 'early', title: '前期笔记', desc: '分享申请经历', metrics: { liked: 12 }, comments: [] },
    { noteId: 'late', title: '后期笔记', desc: '分享申请方法', metrics: { liked: 7 }, comments: [] },
  ] } } }
  render(<StageResultRenderer stage={{key:'profile', n:'1', title:'账号画像', status:'completed', result:{
    profile:{accountPortrait:{
      summary:{statement:'常分享经历',evidence:[{noteId:'early',quote:'分享申请经历'}],counterexamples:[{noteId:'late',quote:'分享申请方法'}]},
      recentChange:{statement:'后期更多方法内容',evidence:[{noteId:'early',quote:'分享申请经历'},{noteId:'late',quote:'分享申请方法'}]},
    }},
    observations:{schemaVersion:'xhs-account-observations/v1',coverage:{selectedCount:2,missingDateCount:0,capturedCommentCount:0,missingMetricCounts:{}},
      notes:[{noteId:'early',title:'前期笔记',metrics:{liked:12}},{noteId:'late',title:'后期笔记',metrics:{liked:7}}],
      chronology:{status:'comparable',earlier:{noteIds:['early'],start:'2026-01-01',end:'2026-01-01'},later:{noteIds:['late'],start:'2026-03-01',end:'2026-03-01'}}},
  }}} currentRun={snapshotRun} onSaveGeneratedTopic={vi.fn()} onSelectTopic={vi.fn()}
    onGenerateBrief={vi.fn()} onGenerateDraft={vi.fn()} onFillSimulationTopic={vi.fn()} />)
  expect(screen.getByText('后期更多方法内容')).toBeInTheDocument()
  fireEvent.click(screen.getAllByRole('button', {name:'查看依据 · 1 条笔记'})[0])
  expect(screen.getByText('可能的例外')).toBeInTheDocument()
  expect(screen.getByText('“分享申请方法”')).toBeInTheDocument()
})
