import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { agentConversationApi, topicApi } from '../api'
import type { AgentConversation, Topic } from '../types'
import { CreatorCanvasPage } from './CreatorCanvasPage'

afterEach(() => {cleanup(); vi.restoreAllMocks(); vi.useRealTimers()})

const topic: Topic = {id:'topic',workspaceId:'w',title:'原题',body:'原文',angle:'角度',associatedPainPoint:'',whyItFits:'',generatedSnapshot:{},sourceAnalysisRunId:null,sourceWorkflow:'manual',status:'candidate',createdAt:'2026-01-01',updatedAt:'2026-01-01'}
const conversation: AgentConversation = {id:'chat', workspaceId:'w',agentAssetId:'a',title:'创作',status:'active',executionStatus:'completed',contextTarget:{assetType:'topic',assetId:'topic'},createdAt:'',updatedAt:'',messages:[]}

it('saves the edited body before entering reader confirmation, with no conversation creation', async()=>{
  vi.spyOn(agentConversationApi,'list').mockResolvedValue([])
  const create=vi.spyOn(agentConversationApi,'create')
  let finish!:(value:Topic)=>void
  const save=vi.spyOn(topicApi,'update').mockImplementation(()=>new Promise(resolve=>{finish=resolve}))
  const onSimulate=vi.fn()
  render(<CreatorCanvasPage workspaceId="w" topic={topic} topics={[topic]} onSelect={vi.fn()} onUpdated={vi.fn()} onSimulate={onSimulate} />)
  await waitFor(()=>expect(screen.getByRole('button',{name:'选择模拟读者'})).toBeEnabled())
  fireEvent.change(screen.getByLabelText('创作正文'),{target:{value:'想测试的新正文'}})
  fireEvent.click(screen.getByRole('button',{name:'选择模拟读者'}))
  expect(onSimulate).not.toHaveBeenCalled()
  expect(screen.getByLabelText('创作正文')).toBeDisabled()
  fireEvent.click(screen.getByRole('button',{name:'正在保存…'}))
  expect(save).toHaveBeenCalledTimes(1)
  const updated={...topic,body:'想测试的新正文',updatedAt:'v2'}
  await act(async()=>finish(updated))
  expect(onSimulate).toHaveBeenCalledExactlyOnceWith(updated)
  expect(create).not.toHaveBeenCalled()
})

it('keeps edits and stays in the canvas if saving before simulation fails', async()=>{
  vi.spyOn(agentConversationApi,'list').mockResolvedValue([])
  vi.spyOn(topicApi,'update').mockRejectedValue(new Error('内容已被修改，请刷新后重试'))
  const onSimulate=vi.fn()
  render(<CreatorCanvasPage workspaceId="w" topic={topic} topics={[topic]} onSelect={vi.fn()} onUpdated={vi.fn()} onSimulate={onSimulate} />)
  await waitFor(()=>expect(screen.getByRole('button',{name:'选择模拟读者'})).toBeEnabled())
  fireEvent.change(screen.getByLabelText('创作正文'),{target:{value:'未保存内容'}})
  fireEvent.click(screen.getByRole('button',{name:'选择模拟读者'}))
  await screen.findByRole('alert')
  expect(screen.getByLabelText('创作正文')).toHaveValue('未保存内容')
  expect(onSimulate).not.toHaveBeenCalled()
})

it('uses already saved content without another save and waits while AI is replying', async()=>{
  vi.spyOn(agentConversationApi,'list').mockResolvedValue([])
  const save=vi.spyOn(topicApi,'update')
  const onSimulate=vi.fn()
  const page=render(<CreatorCanvasPage workspaceId="w" topic={topic} topics={[topic]} onSelect={vi.fn()} onUpdated={vi.fn()} onSimulate={onSimulate} />)
  await waitFor(()=>expect(screen.getByRole('button',{name:'选择模拟读者'})).toBeEnabled())
  fireEvent.click(screen.getByRole('button',{name:'选择模拟读者'}))
  expect(onSimulate).toHaveBeenCalledExactlyOnceWith(topic);expect(save).not.toHaveBeenCalled()
  page.unmount()
  vi.spyOn(agentConversationApi,'list').mockResolvedValue([conversation])
  vi.spyOn(agentConversationApi,'get').mockResolvedValue({...conversation,executionStatus:'running'})
  render(<CreatorCanvasPage workspaceId="w" topic={topic} topics={[topic]} onSelect={vi.fn()} onUpdated={vi.fn()} onSimulate={onSimulate} />)
  await screen.findByRole('button',{name:'正在回复…'})
  expect(screen.getByRole('button',{name:'选择模拟读者'})).toBeDisabled()
})

it('ignores a late save callback after switching topics', async()=>{
  vi.spyOn(agentConversationApi,'list').mockResolvedValue([])
  let finish!:(value:Topic)=>void
  vi.spyOn(topicApi,'update').mockImplementation(()=>new Promise(resolve=>{finish=resolve}))
  const onUpdated=vi.fn(),onSimulate=vi.fn()
  const props={workspaceId:'w',topics:[topic],onSelect:vi.fn(),onUpdated,onSimulate}
  const {rerender}=render(<CreatorCanvasPage {...props} topic={topic} />)
  await waitFor(()=>expect(screen.getByRole('button',{name:'选择模拟读者'})).toBeEnabled())
  fireEvent.change(screen.getByLabelText('创作正文'),{target:{value:'旧选题编辑'}})
  fireEvent.click(screen.getByRole('button',{name:'选择模拟读者'}))
  rerender(<CreatorCanvasPage {...props} topic={{...topic,id:'other',title:'另一个选题'}} />)
  await act(async()=>finish({...topic,body:'旧选题编辑'}))
  expect(onSimulate).not.toHaveBeenCalled();expect(onUpdated).not.toHaveBeenCalled()
  expect(screen.getByLabelText('创作标题')).toHaveValue('另一个选题')
})

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
