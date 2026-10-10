import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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
      manualTopicTitle="新选题" manualTopicAngle="" topicDraft={{ title: topic.title, angle: topic.angle }}
      manualTopicSaveState={{ phase: 'idle' }} topicSaveState={{ phase: 'idle' }}
      onManualTopicTitleChange={vi.fn()} onManualTopicAngleChange={vi.fn()}
      onSaveManualTopic={onSaveManualTopic} onTopicFilterChange={vi.fn()}
      onSelectTopicRow={vi.fn()} onSelectCurrentTopic={vi.fn()} onGenerateBrief={vi.fn()}
      onGenerateDraft={vi.fn()} onArchiveTopic={vi.fn()} onTopicDraftChange={vi.fn()}
      onSaveTopicEdits={vi.fn()}
    />)
    expect(screen.getByRole('button', { name: 'AI 创作助手' })).toBeEnabled()
    expect(screen.getByRole('heading', { name: '选题库', level: 1 })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /如何判断一个选题值得做 待创作/ })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: '全部' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: '受众模拟' })).toBeEnabled()
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

function publicProps() {
  return {publicMode:true, visibleTopics:[topic], selectedTopic:topic, topicFilter:'all' as const,
    manualTopicTitle:'', manualTopicAngle:'', topicDraft:{title:topic.title, angle:topic.angle},
    manualTopicSaveState:{phase:'idle' as const}, topicSaveState:{phase:'idle' as const},
    onManualTopicTitleChange:vi.fn(), onManualTopicAngleChange:vi.fn(), onSaveManualTopic:vi.fn(),
    onTopicFilterChange:vi.fn(), onSelectTopicRow:vi.fn(), onSelectCurrentTopic:vi.fn(),
    onGenerateBrief:vi.fn(), onGenerateDraft:vi.fn(), onArchiveTopic:vi.fn(),
    onTopicDraftChange:vi.fn(), onSaveTopicEdits:vi.fn(), onTogglePinned:vi.fn(), onLeaveGuardChange:vi.fn()}
}

it('keeps secondary actions in More and confirms archive with recoverable failure feedback', async () => {
  const props = publicProps()
  props.onArchiveTopic.mockRejectedValueOnce(new Error('暂时无法连接')).mockResolvedValueOnce(undefined)
  render(<TopicLibraryPage {...props} />)
  expect(screen.queryByRole('button', {name:'归档'})).not.toBeInTheDocument()
  expect(screen.queryByRole('button', {name:'置顶'})).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', {name:'更多'}))
  fireEvent.click(screen.getByRole('button', {name:'归档'}))
  expect(props.onArchiveTopic).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', {name:'确认归档'}))
  expect(await screen.findByRole('alert')).toHaveTextContent('暂时无法连接')
  expect(screen.getByRole('dialog')).toBeVisible()
  fireEvent.click(screen.getByRole('button', {name:'确认归档'}))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(props.onArchiveTopic).toHaveBeenCalledTimes(2)
})

it('blocks archive, new selection and generation while unsaved and warns before browser unload', () => {
  const props = publicProps()
  const {unmount} = render(<TopicLibraryPage {...props} topicDraft={{title:'还没保存', angle:topic.angle}} />)
  for (const name of ['更多', '＋ 新建选题', 'AI 创作助手', '受众模拟']) expect(screen.getByRole('button', {name})).toBeDisabled()
  expect(props.onLeaveGuardChange).toHaveBeenLastCalledWith(expect.stringContaining('未保存修改'))
  const event = new Event('beforeunload', {cancelable:true})
  window.dispatchEvent(event)
  expect(event.defaultPrevented).toBe(true)
  unmount()
  expect(props.onLeaveGuardChange).toHaveBeenLastCalledWith(null)
})

it('keeps archived content readable and provides an explicit restore action', async () => {
  const props = publicProps()
  const archived = {...topic, status:'archived' as const}
  render(<TopicLibraryPage {...props} selectedTopic={archived} visibleTopics={[archived]} />)
  expect(screen.getByLabelText('标题')).toHaveValue(topic.title)
  expect(screen.queryByRole('button', {name:'AI 创作助手'})).not.toBeInTheDocument()
  expect(screen.queryByRole('button', {name:'受众模拟'})).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', {name:'恢复并设为当前'}))
  await waitFor(() => expect(props.onSelectCurrentTopic).toHaveBeenCalledWith(archived))
})

it('prevents double archive submission and field changes while the operation is pending', async () => {
  const props = publicProps()
  let resolve!: () => void
  props.onArchiveTopic.mockImplementation(() => new Promise<void>(done => {resolve=done}))
  render(<TopicLibraryPage {...props} />)
  fireEvent.click(screen.getByRole('button', {name:'更多'}))
  fireEvent.click(screen.getByRole('button', {name:'归档'}))
  fireEvent.click(screen.getByRole('button', {name:'确认归档'}))
  expect(within(screen.getByRole('dialog')).getByRole('button', {name:'正在归档…'})).toBeDisabled()
  expect(screen.getByLabelText('标题')).toBeDisabled()
  expect(props.onArchiveTopic).toHaveBeenCalledOnce()
  resolve()
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
})
