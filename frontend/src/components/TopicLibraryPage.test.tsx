import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { TopicLibraryPage } from './TopicLibraryPage'
import type { Topic } from '../types'

const topic: Topic = {
  id: 'topic-1',
  workspaceId: 'workspace-1',
  title: '如何判断一个选题值得做',
  angle: '用资产和受众反馈交叉验证',
  associatedPainPoint: '不知道下一篇写什么',
  whyItFits: '匹配账号方法论表达。',
  generatedSnapshot: { source: 'test' },
  sourceAnalysisRunId: 'run-1',
  sourceWorkflow: 'account_diagnosis',
  status: 'candidate',
  createdAt: '2026-08-26T00:00:00Z',
  updatedAt: '2026-08-26T00:00:00Z',
}

afterEach(() => cleanup())

describe('TopicLibraryPage', () => {
  it('renders topic detail and dispatches edit/save actions', () => {
    const onTopicDraftChange = vi.fn()
    const onSaveTopicEdits = vi.fn()
    render(
      <TopicLibraryPage
        visibleTopics={[topic]}
        selectedTopic={topic}
        topicFilter="all"
        manualTopicTitle=""
        manualTopicAngle=""
        topicDraft={{ title: topic.title, angle: topic.angle }}
        manualTopicSaveState={{ phase: 'idle' }}
        topicSaveState={{ phase: 'idle' }}
        onManualTopicTitleChange={vi.fn()}
        onManualTopicAngleChange={vi.fn()}
        onSaveManualTopic={vi.fn()}
        onTopicFilterChange={vi.fn()}
        onSelectTopicRow={vi.fn()}
        onSelectCurrentTopic={vi.fn()}
        onGenerateBrief={vi.fn()}
        onGenerateDraft={vi.fn()}
        onArchiveTopic={vi.fn()}
        onTopicDraftChange={onTopicDraftChange}
        onSaveTopicEdits={onSaveTopicEdits}
      />,
    )

    expect(screen.getByText('◇ 选题库')).toBeInTheDocument()
    expect(screen.getAllByText(topic.title).length).toBeGreaterThan(0)
    fireEvent.change(screen.getByLabelText('切入角度'), {
      target: { value: '新的角度' },
    })
    expect(onTopicDraftChange).toHaveBeenCalledWith({
      title: topic.title,
      angle: '新的角度',
    })
    fireEvent.click(screen.getByRole('button', { name: '保存选题资产' }))
    expect(onSaveTopicEdits).toHaveBeenCalledTimes(1)
  })
})

