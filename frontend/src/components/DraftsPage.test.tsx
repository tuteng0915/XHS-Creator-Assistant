import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { DraftsPage } from './DraftsPage'
import type { Draft } from '../types'

const draft: Draft = {
  id: 'draft-1',
  workspaceId: 'workspace-1',
  topicId: 'topic-1',
  kind: 'content_brief',
  sourceAnalysisRunId: 'run-1',
  sourceWorkflow: 'account_diagnosis',
  status: 'completed',
  generatedSnapshot: { brief: { topicTitle: '生成快照' } },
  editableContent: { brief: { topicTitle: '可编辑内容' } },
  inputSnapshot: { topic: { title: '原始选题' } },
  stageErrors: {},
  modelMetadata: { provider: 'fake' },
  createdAt: '2026-08-26T00:00:00Z',
  completedAt: '2026-08-26T00:00:01Z',
  updatedAt: '2026-08-26T00:00:00Z',
}

afterEach(() => cleanup())

describe('DraftsPage', () => {
  it('renders selected draft and saves editable JSON', () => {
    const onDraftEditorChange = vi.fn()
    const onSaveDraftEdits = vi.fn()
    render(
      <DraftsPage
        drafts={[draft]}
        selectedDraft={draft}
        draftEditor={JSON.stringify(draft.editableContent, null, 2)}
        draftSaveState={{ phase: 'idle' }}
        onOpenDraft={vi.fn()}
        onDraftEditorChange={onDraftEditorChange}
        onSaveDraftEdits={onSaveDraftEdits}
        onGenerateStructureFromBrief={vi.fn()}
        onRunAudienceSimulation={vi.fn()}
        renderDraftStructure={() => <div>结构预览</div>}
        draftDisplayTitle={() => '可编辑内容'}
        draftKindLabel={() => '创作 Brief'}
      />,
    )

    expect(screen.getByText('▱ 创作输出')).toBeInTheDocument()
    expect(screen.getByText('结构预览')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Editable Content JSON'), {
      target: { value: '{"brief":{"topicTitle":"更新"}}' },
    })
    expect(onDraftEditorChange).toHaveBeenCalledWith(
      '{"brief":{"topicTitle":"更新"}}',
    )
    fireEvent.click(screen.getByRole('button', { name: '保存创作输出资产' }))
    expect(onSaveDraftEdits).toHaveBeenCalledTimes(1)
  })
})

