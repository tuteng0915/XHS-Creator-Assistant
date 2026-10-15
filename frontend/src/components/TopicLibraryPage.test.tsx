import { useState } from 'react'
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
  it('closes the creation dialog on success and gives the library one primary creation action', async () => {
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
    expect(screen.getByRole('button', { name: '开始创作' })).toBeEnabled()
    expect(screen.getByRole('heading', { name: '选题库', level: 1 })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /如何判断一个选题值得做 待创作/ })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: '全部' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.queryByRole('button', { name: '受众模拟' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '＋ 新建选题' })).toHaveClass('primary')
    expect(screen.getByRole('button', { name: '开始创作' })).toHaveClass('primary')
    expect(screen.queryByLabelText('标题')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('正文')).not.toBeInTheDocument()
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
  for (const name of ['更多', '＋ 新建选题', '开始创作']) expect(screen.getByRole('button', {name})).toBeDisabled()
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
  expect(screen.getByRole('heading', {name: topic.title})).toBeVisible()
  expect(screen.getByText(topic.angle)).toBeVisible()
  expect(screen.queryByRole('button', {name:'开始创作'})).not.toBeInTheDocument()
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
  expect(screen.getByRole('button', {name:'编辑选题'})).toBeDisabled()
  expect(props.onArchiveTopic).toHaveBeenCalledOnce()
  resolve()
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
})

it('opens the existing draft in the assistant without rendering a second body editor or empty source cards', () => {
  const props = publicProps()
  const saved = {...topic, sourceWorkflow: 'manual' as const, associatedPainPoint: '', whyItFits: '', body: '已经保存的正文'}
  const onOpenCanvas = vi.fn()
  render(<TopicLibraryPage {...props} selectedTopic={saved} visibleTopics={[saved]}
    topicDraft={{title: saved.title, angle: saved.angle, body: saved.body}} onOpenCanvas={onOpenCanvas} />)
  expect(screen.getByText('已有稿件 · 7 字')).toBeVisible()
  expect(screen.queryByText(saved.body)).not.toBeInTheDocument()
  expect(screen.queryByText('来源与适配理由')).not.toBeInTheDocument()
  expect(screen.queryByText('无')).not.toBeInTheDocument()
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', {name: '继续创作'}))
  expect(onOpenCanvas).toHaveBeenCalledWith(saved)
  expect(props.onGenerateBrief).not.toHaveBeenCalled()
  expect(props.onGenerateDraft).not.toHaveBeenCalled()
})

it('keeps the optional simulation shortcut in More without starting it when the topic is selected', () => {
  const props = publicProps(), onSimulateTopic = vi.fn()
  render(<TopicLibraryPage {...props} onSimulateTopic={onSimulateTopic} />)
  expect(onSimulateTopic).not.toHaveBeenCalled()
  expect(screen.queryByRole('button', {name: '受众模拟'})).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', {name: '更多'}))
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', {name: '受众模拟'}))
  expect(onSimulateTopic).toHaveBeenCalledWith(topic)
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})

it('edits only title and angle, preserves the saved body, and allows explicit cancellation', () => {
  const props = publicProps()
  const saved = {...topic, body: '只能在创作助手修改的正文'}
  function EditableLibrary() {
    const [draft, setDraft] = useState({title: saved.title, angle: saved.angle, body: saved.body})
    return <TopicLibraryPage {...props} selectedTopic={saved} topicDraft={draft}
      onTopicDraftChange={next => {props.onTopicDraftChange(next); setDraft({...next, body: next.body || ''})}} />
  }
  render(<EditableLibrary />)
  fireEvent.click(screen.getByRole('button', {name: '编辑选题'}))
  expect(screen.getAllByRole('textbox')).toHaveLength(2)
  expect(screen.queryByLabelText('正文')).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('切入角度'), {target: {value: '重新考虑切入角度'}})
  expect(props.onTopicDraftChange).toHaveBeenLastCalledWith({title: saved.title, angle: '重新考虑切入角度', body: saved.body})
  expect(screen.getByRole('button', {name: '继续创作'})).toBeDisabled()
  fireEvent.click(screen.getByRole('button', {name: '取消'}))
  expect(props.onTopicDraftChange).toHaveBeenLastCalledWith({title: saved.title, angle: saved.angle, body: saved.body})
  expect(screen.queryByLabelText('标题')).not.toBeInTheDocument()
  expect(screen.getByText(saved.angle)).toBeVisible()
  expect(props.onSaveTopicEdits).not.toHaveBeenCalled()
})

it('returns to the readable topic after saving but keeps failed or newer edits available', () => {
  const props = publicProps()
  const {rerender} = render(<TopicLibraryPage {...props} />)
  fireEvent.click(screen.getByRole('button', {name: '编辑选题'}))
  rerender(<TopicLibraryPage {...props} topicDraft={{title: '新标题', angle: topic.angle}} />)
  fireEvent.click(screen.getByRole('button', {name: '保存修改'}))
  rerender(<TopicLibraryPage {...props} topicDraft={{title: '新标题', angle: topic.angle}} topicSaveState={{phase: 'error', message: '保存失败，请重试'}} />)
  expect(screen.getByLabelText('标题')).toHaveValue('新标题')
  expect(screen.getByRole('status')).toHaveTextContent('保存失败，请重试')
  fireEvent.click(screen.getByRole('button', {name: '保存修改'}))
  const updated = {...topic, title: '新标题'}
  rerender(<TopicLibraryPage {...props} selectedTopic={updated} topicDraft={{title: '保存时继续修改', angle: topic.angle}} topicSaveState={{phase: 'saved'}} />)
  expect(screen.getByLabelText('标题')).toHaveValue('保存时继续修改')
  rerender(<TopicLibraryPage {...props} selectedTopic={updated} topicDraft={{title: '新标题', angle: topic.angle}} topicSaveState={{phase: 'saved'}} />)
  expect(screen.queryByLabelText('标题')).not.toBeInTheDocument()
  expect(screen.getByRole('button', {name: '编辑选题'})).toBeEnabled()
})

it('shows meaningful provenance only and leaves the internal asset editor unchanged', () => {
  const props = publicProps()
  const {rerender} = render(<TopicLibraryPage {...props} />)
  expect(screen.getByText('来自账号诊断')).toBeVisible()
  expect(screen.getByText(topic.associatedPainPoint)).toBeVisible()
  expect(screen.getByText(topic.whyItFits)).toBeVisible()
  expect(screen.queryByText('run-1')).not.toBeInTheDocument()
  rerender(<TopicLibraryPage {...props} publicMode={false} />)
  expect(screen.getByLabelText('标题')).toHaveValue(topic.title)
  expect(screen.getByLabelText('切入角度')).toHaveValue(topic.angle)
  expect(screen.getByRole('button', {name: '生成创作 Brief'})).toBeEnabled()
  expect(screen.getByRole('button', {name: '生成内容结构'})).toBeEnabled()
  expect(screen.getByText('Generated Snapshot')).toBeInTheDocument()
  expect(screen.getByText('run-1')).toBeVisible()
})
