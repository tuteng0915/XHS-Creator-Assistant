import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
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
  it('closes the creation dialog on success and blocks generation with unsaved edits', async () => {
    const onSaveManualTopic = vi.fn().mockResolvedValue(true)
    render(<TopicLibraryPage
      publicMode visibleTopics={[topic]} selectedTopic={topic} topicFilter="all"
      manualTopicTitle="新选题" manualTopicAngle="" topicDraft={{ title: '尚未保存的标题', angle: topic.angle }}
      manualTopicSaveState={{ phase: 'idle' }} topicSaveState={{ phase: 'idle' }}
      onManualTopicTitleChange={vi.fn()} onManualTopicAngleChange={vi.fn()}
      onSaveManualTopic={onSaveManualTopic} onTopicFilterChange={vi.fn()}
      onSelectTopicRow={vi.fn()} onSelectCurrentTopic={vi.fn()} onGenerateBrief={vi.fn()}
      onGenerateDraft={vi.fn()} onArchiveTopic={vi.fn()} onTopicDraftChange={vi.fn()}
      onSaveTopicEdits={vi.fn()}
    />)
    expect(screen.getByRole('button', { name: 'AI 创作助手' })).toBeDisabled()
    expect(screen.getByRole('heading', { name: '选题库', level: 1 })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /如何判断一个选题值得做 待创作/ })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: '全部' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: '受众模拟' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '＋ 新建选题' })).toHaveClass('primary')
    expect(screen.getByRole('button', { name: 'AI 创作助手' })).toHaveClass('primary')
    fireEvent.click(screen.getByRole('button', { name: '＋ 新建选题' }))
    expect(screen.getByRole('button', { name: '保存选题' })).toHaveClass('primary')
    expect(screen.getByRole('button', { name: '关闭' })).toHaveClass('icon-button')
    expect(screen.getByRole('button', { name: '保存选题' })).not.toHaveClass('small-primary')
    fireEvent.click(screen.getByRole('button', { name: '保存选题' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(onSaveManualTopic).toHaveBeenCalledOnce()
  })

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
