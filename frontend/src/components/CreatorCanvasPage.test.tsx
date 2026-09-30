import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { agentConversationApi, topicApi } from '../api'
import type { AgentConversation, Topic } from '../types'
import { CreatorCanvasPage } from './CreatorCanvasPage'

afterEach(() => {cleanup(); vi.restoreAllMocks(); vi.useRealTimers()})

const topic: Topic = {id:'topic',workspaceId:'w',title:'原题',body:'原文',angle:'角度',associatedPainPoint:'',whyItFits:'',generatedSnapshot:{},sourceAnalysisRunId:null,sourceWorkflow:'manual',status:'candidate',createdAt:'2026-01-01',updatedAt:'2026-01-01'}
const conversation: AgentConversation = {id:'chat', workspaceId:'w',agentAssetId:'a',title:'创作',status:'active',executionStatus:'completed',contextTarget:{assetType:'topic',assetId:'topic'},createdAt:'',updatedAt:'',messages:[]}

it('reopens saved conversation without creating another one and saves before sending', async () => {
  vi.spyOn(agentConversationApi,'list').mockResolvedValue([conversation])
  vi.spyOn(agentConversationApi,'get').mockResolvedValue(conversation)
  const create = vi.spyOn(agentConversationApi,'create')
  const save = vi.spyOn(topicApi,'update').mockResolvedValue({...topic,body:'我的修改',updatedAt:'2026-01-02'})
  vi.spyOn(topicApi,'get').mockResolvedValue({...topic,body:'我的修改',updatedAt:'2026-01-02'})
  const send = vi.spyOn(agentConversationApi,'sendMessage').mockResolvedValue(conversation)
  render(<CreatorCanvasPage workspaceId="w" topic={topic} topics={[topic]} agentId="a" onSelect={vi.fn()} onUpdated={vi.fn()} />)
  fireEvent.change(screen.getByLabelText('创作正文'),{target:{value:'我的修改'}})
  fireEvent.change(screen.getByLabelText('给创作助手的消息'),{target:{value:'改进开头'}})
  await waitFor(() => expect(screen.getByRole('button',{name:'发送'})).toBeEnabled())
  fireEvent.click(screen.getByRole('button',{name:'发送'}))
  await waitFor(() => expect(send).toHaveBeenCalled())
  expect(save).toHaveBeenCalledWith('topic',expect.objectContaining({body:'我的修改',expectedUpdatedAt:topic.updatedAt}))
  expect(create).not.toHaveBeenCalled()
  expect(save.mock.invocationCallOrder[0]).toBeLessThan(send.mock.invocationCallOrder[0])
})

it('waits for the updated topic before finishing polling and updating the canvas', async () => {
  vi.useFakeTimers()
  const running = {...conversation, executionStatus: 'running' as const}
  vi.spyOn(agentConversationApi, 'list').mockResolvedValue([running])
  vi.spyOn(agentConversationApi, 'get').mockResolvedValueOnce(running).mockResolvedValue(conversation)
  let resolveTopic!: (value: Topic) => void
  vi.spyOn(topicApi, 'get').mockReturnValue(new Promise(resolve => {resolveTopic = resolve}))
  const onUpdated = vi.fn()
  render(<CreatorCanvasPage workspaceId="w" topic={topic} topics={[topic]} agentId="a" onSelect={vi.fn()} onUpdated={onUpdated} />)
  await act(async () => {})
  await act(async () => {await vi.advanceTimersByTimeAsync(800)})
  const updated = {...topic, title: 'AI 新标题', body: 'AI 新正文', updatedAt: '2026-01-03'}
  await act(async () => {resolveTopic(updated)})
  expect(screen.getByLabelText('创作标题')).toHaveValue(updated.title)
  expect(screen.getByLabelText('创作正文')).toHaveValue(updated.body)
  expect(onUpdated).toHaveBeenCalledWith(updated)
})

it('reopens pending suggestions without putting the blocked proposal in the editor', async () => {
  const pending = '请确认是否有后台交流的经历？'
  const stored: AgentConversation = {...conversation, messages: [{
    id: 'reply', conversationId: conversation.id, role: 'assistant', content: '原稿未改动',
    contextPack: {}, assetRefs: [], proposedActions: [], createdAt: '',
    modelMetadata: {canvasApplyStatus: 'needs_confirmation', pendingSuggestions: [pending],
      suggestedCanvasUpdate: {title: '后台故事', body: '我去了后台'}},
  }]}
  vi.spyOn(agentConversationApi, 'list').mockResolvedValue([stored])
  vi.spyOn(agentConversationApi, 'get').mockResolvedValue(stored)
  const update = vi.spyOn(topicApi, 'update')
  render(<CreatorCanvasPage workspaceId="w" topic={topic} topics={[topic]} agentId="a" onSelect={vi.fn()} onUpdated={vi.fn()} />)
  await screen.findByText(pending)
  expect(screen.getByLabelText('创作正文')).toHaveValue('原文')
  expect(screen.queryByText('我去了后台')).not.toBeInTheDocument()
  expect(update).not.toHaveBeenCalled()
})
