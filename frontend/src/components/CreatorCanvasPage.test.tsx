import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { agentConversationApi, topicApi } from '../api'
import { contentCollaborationApi } from '../contentCollaboration'
import type { CollaborationSession } from '../contentCollaboration'
import type { AgentConversation, Topic } from '../types'
import { CreatorCanvasPage } from './CreatorCanvasPage'

const topic: Topic = {id:'topic',workspaceId:'w',title:'原题',body:'原文',angle:'',associatedPainPoint:'',whyItFits:'',generatedSnapshot:{},sourceAnalysisRunId:null,sourceWorkflow:'manual',status:'candidate',createdAt:'v1',updatedAt:'v1'}
const session: CollaborationSession = {id:'s',workspaceId:'w',title:'协作',status:'active',executionStatus:'waiting_creator',contextTarget:{assetType:'topic',assetId:'topic'},failureCode:'',failureDetail:'',createdAt:'',updatedAt:'',messages:[],runs:[]}
const candidate = {kind:'copy_option',title:'从选择那刻开场',body:'我在两个选项之间犹豫。',confidence:'inference',evidenceRefs:[]}
const withSuggestion: CollaborationSession = {...session,messages:[{id:'m',sessionId:'s',sequenceNo:1,sender:'writing',recipient:'review',content:`先把决定的现场写出来。\n\n【${candidate.title}】${candidate.body}`,replyToMessageId:null,modelMetadata:{candidateSuggestions:[candidate]},createdAt:''}]}
beforeEach(() => {vi.spyOn(agentConversationApi,'list').mockResolvedValue([]); vi.spyOn(contentCollaborationApi,'list').mockResolvedValue([])})
afterEach(() => {cleanup();vi.restoreAllMocks();vi.useRealTimers()})
const props = {workspaceId:'w',topic,topics:[topic],onSelect:vi.fn(),onUpdated:vi.fn()}
function reopen(value: CollaborationSession) {vi.mocked(contentCollaborationApi.list).mockResolvedValue([value]); vi.spyOn(contentCollaborationApi,'get').mockResolvedValue(value)}

it('uses the collaboration session instead of creating or sending to the legacy assistant', async () => {
  const oldCreate = vi.spyOn(agentConversationApi,'create'), oldSend = vi.spyOn(agentConversationApi,'sendMessage')
  const create = vi.spyOn(contentCollaborationApi,'create').mockResolvedValue(session)
  const send = vi.spyOn(contentCollaborationApi,'send').mockResolvedValue(session)
  const save = vi.spyOn(topicApi,'update').mockResolvedValue({...topic,body:'我的修改',updatedAt:'v2'})
  render(<CreatorCanvasPage {...props} />)
  fireEvent.change(screen.getByLabelText('创作正文'),{target:{value:'我的修改'}})
  fireEvent.change(screen.getByLabelText('给创作助手的消息'),{target:{value:'修改开头'}})
  await waitFor(() => expect(screen.getByRole('button',{name:'发送'})).toBeEnabled())
  fireEvent.click(screen.getByRole('button',{name:'发送'}))
  await waitFor(() => expect(send).toHaveBeenCalledWith('w','s','修改开头','research',expect.any(String)))
  expect(save.mock.invocationCallOrder[0]).toBeLessThan(create.mock.invocationCallOrder[0])
  expect(oldCreate).not.toHaveBeenCalled(); expect(oldSend).not.toHaveBeenCalled()
})

it('shows short role headings and previews a candidate before local adoption and explicit save', async () => {
  reopen(withSuggestion)
  const save = vi.spyOn(topicApi,'update').mockResolvedValue({...topic,body:'原文\n\n我的版本',updatedAt:'v2'})
  render(<CreatorCanvasPage {...props} />)
  expect(await screen.findByRole('heading',{name:candidate.title})).toBeInTheDocument()
  expect(screen.getByText('回复 审稿伙伴')).toBeInTheDocument()
  expect(screen.getAllByText(candidate.body)).toHaveLength(1)
  fireEvent.click(screen.getByRole('button',{name:'预览并编辑这条建议'}))
  expect(screen.getByLabelText('创作正文')).toHaveValue('原文')
  fireEvent.change(screen.getByLabelText('编辑写作建议'),{target:{value:'我的版本'}})
  fireEvent.click(screen.getByRole('button',{name:'确认放入画布'}))
  expect(screen.getByLabelText('创作正文')).toHaveValue('原文\n\n我的版本')
  expect(save).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button',{name:'保存'}))
  await waitFor(() => expect(save).toHaveBeenCalledWith('topic',expect.objectContaining({body:'原文\n\n我的版本',expectedUpdatedAt:'v1'})))
})

it('refuses to overwrite edits made after candidate preview opened', async () => {
  reopen(withSuggestion); render(<CreatorCanvasPage {...props} />)
  fireEvent.click(await screen.findByRole('button',{name:'预览并编辑这条建议'}))
  fireEvent.change(screen.getByLabelText('建议放入方式'),{target:{value:'replace'}})
  fireEvent.change(screen.getByLabelText('创作正文'),{target:{value:'后来写的句子'}})
  fireEvent.click(screen.getByRole('button',{name:'确认放入画布'}))
  expect(screen.getByLabelText('创作正文')).toHaveValue('后来写的句子')
  expect(screen.getByRole('alert')).toHaveTextContent('预览期间画布有新修改')
})

it('lets the author apply a title suggestion locally without changing the body', async () => {
  reopen(withSuggestion)
  const save = vi.spyOn(topicApi,'update')
  render(<CreatorCanvasPage {...props} />)
  fireEvent.click(await screen.findByRole('button',{name:'预览并编辑这条建议'}))
  fireEvent.change(screen.getByLabelText('建议用于'),{target:{value:'title'}})
  fireEvent.change(screen.getByLabelText('编辑写作建议'),{target:{value:'我的新标题'}})
  fireEvent.click(screen.getByRole('button',{name:'确认放入画布'}))
  expect(screen.getByLabelText('创作标题')).toHaveValue('我的新标题')
  expect(screen.getByLabelText('创作正文')).toHaveValue('原文')
  expect(save).not.toHaveBeenCalled()
})

it('polls active work, reveals each persisted turn, and stops after completion without replacing the editor', async () => {
  vi.useFakeTimers()
  const run = {id:'r',status:'running' as const,triggerMessageId:'creator',graphState:{pendingMessageId:'creator'},errorCode:'',errorDetail:'',createdAt:new Date().toISOString(),startedAt:null,completedAt:null}
  const active: CollaborationSession = {...session,executionStatus:'running',runs:[run],messages:[{id:'creator',sessionId:'s',sequenceNo:1,sender:'creator',recipient:'research',content:'聊聊',replyToMessageId:null,modelMetadata:{},createdAt:''}]}
  const research = {...withSuggestion.messages[0],id:'research',sender:'research' as const,recipient:'writing' as const,content:'材料已梳理',modelMetadata:{runId:'r'}}
  const partial = {...active,messages:[...active.messages,research],runs:[{...run,graphState:{pendingMessageId:'research'}}]}
  const completed = {...partial,executionStatus:'waiting_creator' as const}
  vi.mocked(contentCollaborationApi.list).mockResolvedValue([active])
  const get = vi.spyOn(contentCollaborationApi,'get').mockResolvedValueOnce(active).mockResolvedValueOnce(partial).mockResolvedValue(completed)
  const topicGet = vi.spyOn(topicApi,'get')
  render(<CreatorCanvasPage {...props} />)
  await act(async () => {})
  fireEvent.change(screen.getByLabelText('创作正文'),{target:{value:'等待中写的新稿'}})
  await act(async () => {await vi.advanceTimersByTimeAsync(500)})
  expect(screen.getByText('材料已梳理')).toBeInTheDocument()
  expect(screen.getByRole('status')).toHaveTextContent('写作伙伴正在整理下一部分')
  await act(async () => {await vi.advanceTimersByTimeAsync(1000)})
  const count = get.mock.calls.length
  await act(async () => {await vi.advanceTimersByTimeAsync(5000)})
  expect(get).toHaveBeenCalledTimes(count)
  expect(screen.getByLabelText('创作正文')).toHaveValue('等待中写的新稿')
  expect(topicGet).not.toHaveBeenCalled()
})

it('keeps legacy messages in a collapsed read-only history without old adoption buttons', async () => {
  const old = {id:'old',contextTarget:{assetType:'topic',assetId:'topic'},messages:[{id:'m',role:'assistant',content:'过去的建议',modelMetadata:{canvasApplyStatus:'pending_confirmation'}}]} as unknown as AgentConversation
  vi.mocked(agentConversationApi.list).mockResolvedValue([old]); vi.spyOn(agentConversationApi,'get').mockResolvedValue(old)
  render(<CreatorCanvasPage {...props} />)
  const summary = await screen.findByText('旧版创作对话（只读）')
  expect(summary.closest('details')).not.toHaveAttribute('open')
  fireEvent.click(summary)
  expect(screen.getByText('过去的建议')).toBeVisible()
  expect(screen.queryByRole('button',{name:'采用建议'})).not.toBeInTheDocument()
})

it('saves edited content before selecting readers and retains content after a failed save', async () => {
  const onSimulate = vi.fn()
  const save = vi.spyOn(topicApi,'update').mockRejectedValueOnce(new Error('版本冲突')).mockResolvedValue({...topic,body:'新正文',updatedAt:'v2'})
  render(<CreatorCanvasPage {...props} onSimulate={onSimulate} />)
  fireEvent.change(screen.getByLabelText('创作正文'),{target:{value:'新正文'}})
  fireEvent.click(screen.getByRole('button',{name:'选择模拟读者'}))
  await screen.findByText('版本冲突')
  expect(onSimulate).not.toHaveBeenCalled(); expect(screen.getByLabelText('创作正文')).toHaveValue('新正文')
  fireEvent.click(screen.getByRole('button',{name:'选择模拟读者'}))
  await waitFor(() => expect(onSimulate).toHaveBeenCalledWith(expect.objectContaining({body:'新正文'})))
  expect(save).toHaveBeenCalledTimes(2)
})

it('never retries a failed model run automatically and keeps the previous request editable', async () => {
  reopen({...session,executionStatus:'failed',failureDetail:'写作伙伴暂时未能完成',messages:[{id:'c',sessionId:'s',sequenceNo:1,sender:'creator',recipient:'writing',content:'先给我一个开头',replyToMessageId:null,modelMetadata:{},createdAt:''}]})
  const send = vi.spyOn(contentCollaborationApi,'send')
  render(<CreatorCanvasPage {...props} />)
  fireEvent.click(await screen.findByRole('button',{name:'把上次要求放回输入框'}))
  expect(screen.getByLabelText('给创作助手的消息')).toHaveValue('先给我一个开头')
  expect(screen.getByLabelText('先交给哪位伙伴')).toHaveValue('writing')
  expect(send).not.toHaveBeenCalled()
})
