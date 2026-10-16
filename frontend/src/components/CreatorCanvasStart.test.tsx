import { useState } from 'react'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { agentConversationApi, topicApi } from '../api'
import { contentCollaborationApi } from '../contentCollaboration'
import type { CollaborationSession } from '../contentCollaboration'
import { creatorDraftKey, writeCreatorCache } from '../creatorDraftCache'
import type { Topic } from '../types'
import { CreatorCanvasPage } from './CreatorCanvasPage'

const topic: Topic = {id:'topic',workspaceId:'w',title:'一次跨专业选择',body:'',angle:'',associatedPainPoint:'',whyItFits:'',generatedSnapshot:{},sourceAnalysisRunId:null,sourceWorkflow:'manual',status:'candidate',createdAt:'v1',updatedAt:'v1'}
const props = {workspaceId:'w',topic:null,topics:[],onSelect:vi.fn(),onUpdated:vi.fn()}
beforeEach(() => {
  vi.spyOn(agentConversationApi, 'list').mockResolvedValue([])
  vi.spyOn(contentCollaborationApi, 'list').mockResolvedValue([])
})
afterEach(() => {cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers()})

const emptySession: CollaborationSession = {id:'s',workspaceId:'w',title:'共创',assistantMode:'single_writer',status:'active',executionStatus:'waiting_creator',contextTarget:{assetType:'topic',assetId:topic.id},failureCode:'',failureDetail:'',createdAt:'',updatedAt:'',runs:[],messages:[]}
function generated(kind: 'copy_option' | 'outline' | 'open_question' = 'copy_option'): CollaborationSession {
  return {...emptySession, runs:[{id:'run',status:'completed',triggerMessageId:'c',graphState:{},errorCode:'',errorDetail:'',createdAt:'',startedAt:null,completedAt:null}], messages:[
    {id:'c',sessionId:'s',sequenceNo:1,sender:'creator',recipient:'writing',content:'帮我起草',replyToMessageId:null,createdAt:'',modelMetadata:{}},
    {id:'m',sessionId:'s',sequenceNo:2,sender:'writing',recipient:'creator',content:'这是第一版',replyToMessageId:'c',createdAt:'',modelMetadata:{runId:'run',candidateSuggestions:[{kind,title:'第一版正文',body:'那天我做了一个决定。',confidence:'inference',evidenceRefs:[]}]}}
  ]}
}
async function requestDraft() {
  fireEvent.change(screen.getByLabelText('给创作助手的消息'), {target:{value:'帮我起草'}})
  await waitFor(() => expect(screen.getByRole('button', {name:'发送'})).toBeEnabled())
  fireEvent.click(screen.getByRole('button', {name:'发送'}))
}

function Start() {
  const [selected, setSelected] = useState<Topic | null>(null)
  const [topics, setTopics] = useState<Topic[]>([])
  return <CreatorCanvasPage workspaceId="w" topic={selected} topics={topics} onSelect={setSelected} onUpdated={setSelected} onCreated={created => setTopics(previous => [...previous, created])} onNew={() => setSelected(null)} />
}

it('opens the real composer and references immediately, creating and sending only on the first explicit send', async () => {
  const create = vi.spyOn(topicApi, 'create').mockResolvedValue(topic)
  const send = vi.spyOn(contentCollaborationApi, 'send').mockResolvedValue(emptySession)
  const createSession = vi.spyOn(contentCollaborationApi, 'create').mockResolvedValue(emptySession)
  render(<Start />)
  expect(screen.getByRole('button', {name:'发送'})).toBeDisabled()
  expect(screen.getByRole('button', {name:/添加参考/})).toBeEnabled()
  expect(create).not.toHaveBeenCalled()
  expect(send).not.toHaveBeenCalled(); expect(createSession).not.toHaveBeenCalled()
  fireEvent.change(screen.getByLabelText('给创作助手的消息'), {target:{value:'想写一次跨专业选择\n重点讲犹豫和决定。'}})
  fireEvent.click(screen.getByRole('button', {name:'发送'}))
  await waitFor(() => expect(send).toHaveBeenCalledOnce())
  expect(send).toHaveBeenCalledWith('w','s','想写一次跨专业选择\n重点讲犹豫和决定。','writing',expect.any(String),undefined,{schemaVersion:'creator-context-selection/v1',references:[]})
  expect(screen.getByLabelText('给创作助手的消息')).toHaveValue('')
  expect(create).toHaveBeenCalledWith('w', {title:'想写一次跨专业选择', sourceWorkflow:'manual', generatedSnapshot:{creatorInitialTitle:'想写一次跨专业选择'}})
  await waitFor(() => expect(screen.getByRole('button', {name:/添加参考/})).toBeEnabled())
  expect(screen.getByLabelText('创作正文')).not.toBeVisible()
  expect(screen.queryByRole('separator')).not.toBeInTheDocument()
  expect(createSession).toHaveBeenCalledOnce()
  expect(screen.getAllByRole('option', {name:topic.title})).toHaveLength(1)
  fireEvent.click(screen.getByRole('button', {name:'新创作'}))
  expect(screen.getByLabelText('给创作助手的消息')).toHaveValue('')
})

it('opens a blank draft only when requested and keeps it open after its text is cleared', async () => {
  render(<CreatorCanvasPage {...props} topic={topic} topics={[topic]} />)
  expect(screen.getByLabelText('创作正文')).not.toBeVisible()
  fireEvent.click(screen.getByRole('button', {name:'自己写稿'}))
  const editor = screen.getByLabelText('创作正文')
  expect(editor).toBeVisible()
  expect(editor).toHaveFocus()
  fireEvent.change(editor, {target:{value:'第一句'}})
  fireEvent.change(editor, {target:{value:''}})
  expect(editor).toBeVisible()
})

it('uses the generated title instead of the initial request, preserves edits and saves only on adoption', async () => {
  const pending = {...topic, title:'请结合参考帮我写一篇完整正文和标题', generatedSnapshot:{creatorInitialTitle:'请结合参考帮我写一篇完整正文和标题'}}
  const record = generated()
  record.messages[1].modelMetadata.candidateSuggestions = [{kind:'copy_option',title:'标题：不急着给选择下结论',body:'先比较可以查证的事。',confidence:'inference',evidenceRefs:[]}]
  vi.mocked(contentCollaborationApi.list).mockResolvedValue([record])
  vi.spyOn(contentCollaborationApi,'get').mockResolvedValue(record)
  const update = vi.spyOn(topicApi,'update').mockResolvedValue({...pending,title:'我手改的标题',body:'手动调整后的正文。',updatedAt:'v2'})
  const first = render(<CreatorCanvasPage {...props} topic={pending} topics={[pending]} />)
  expect(await screen.findByLabelText('候选稿标题')).toHaveValue('不急着给选择下结论')
  expect(update).not.toHaveBeenCalled()
  fireEvent.change(screen.getByLabelText('候选稿标题'),{target:{value:'我手改的标题'}})
  fireEvent.change(screen.getByLabelText('编辑写作建议'),{target:{value:'手动调整后的正文。'}})
  fireEvent.click(screen.getByRole('button',{name:'在稿件区编辑'}))
  expect(screen.getByLabelText('候选稿标题')).toHaveValue('我手改的标题')
  first.unmount()
  render(<CreatorCanvasPage {...props} topic={pending} topics={[pending]} />)
  expect(screen.getByLabelText('候选稿标题')).toHaveValue('我手改的标题')
  fireEvent.click(screen.getByRole('button',{name:'采用并保存'}))
  expect(await screen.findByLabelText('创作正文')).toHaveValue('手动调整后的正文。')
  expect(update).toHaveBeenCalledWith(topic.id,{title:'我手改的标题',body:'手动调整后的正文。',expectedUpdatedAt:'v1'})
  const original = screen.getByText('查看当时的原始建议').closest('details')!
  expect(original).not.toHaveAttribute('open')
  expect(screen.getByText('先比较可以查证的事。')).not.toBeVisible()
  fireEvent.click(screen.getByText('查看当时的原始建议'))
  expect(screen.getByText('先比较可以查证的事。')).toBeVisible()
  expect(screen.getByLabelText('创作正文')).toHaveValue('手动调整后的正文。')
})

it('keeps an explicitly chosen title even when the first model draft suggests a different title', async () => {
  const edited = {...topic,title:'作者自己定的标题',generatedSnapshot:{creatorInitialTitle:'最初的起草要求'}}
  vi.mocked(contentCollaborationApi.list).mockResolvedValue([generated()])
  vi.spyOn(contentCollaborationApi,'get').mockResolvedValue(generated())
  render(<CreatorCanvasPage {...props} topic={edited} topics={[edited]} />)
  expect(await screen.findByLabelText('候选稿标题')).toHaveValue('作者自己定的标题')
})

it('keeps original suggestions collapsed after reopening a saved draft without claiming exact adoption', async () => {
  vi.mocked(contentCollaborationApi.list).mockResolvedValue([generated()])
  vi.spyOn(contentCollaborationApi,'get').mockResolvedValue(generated())
  render(<CreatorCanvasPage {...props} topic={{...topic,body:'保存后的手改正文',updatedAt:'v2'}} topics={[topic]} />)
  const disclosure = await screen.findByText('查看当时的原始建议')
  expect(disclosure.closest('details')).not.toHaveAttribute('open')
  expect(screen.getByText('那天我做了一个决定。')).not.toBeVisible()
  expect(screen.getByLabelText('创作正文')).toHaveValue('保存后的手改正文')
})

it('keeps the idea and allows explicit retry after creation fails', async () => {
  const create = vi.spyOn(topicApi, 'create').mockRejectedValueOnce(new Error('暂时无法连接')).mockResolvedValue(topic)
  vi.spyOn(contentCollaborationApi, 'create').mockResolvedValue(emptySession)
  vi.spyOn(contentCollaborationApi, 'send').mockResolvedValue(emptySession)
  render(<Start />)
  fireEvent.change(screen.getByLabelText('给创作助手的消息'), {target:{value:'我的想法'}})
  fireEvent.click(screen.getByRole('button', {name:'发送'}))
  expect(await screen.findByRole('alert')).toHaveTextContent('暂时无法连接')
  expect(screen.getByLabelText('给创作助手的消息')).toHaveValue('我的想法')
  expect(create).toHaveBeenCalledTimes(1)
  fireEvent.click(screen.getByRole('button', {name:'发送'}))
  await waitFor(() => expect(screen.getByLabelText('给创作助手的消息')).toHaveValue(''))
  expect(create).toHaveBeenCalledTimes(2)
})

it('locks duplicate submissions and ignores a late creation after changing accounts', async () => {
  let resolve!: (created: Topic) => void
  const create = vi.spyOn(topicApi, 'create').mockReturnValue(new Promise(done => {resolve = done}))
  const onCreated = vi.fn(), onSelect = vi.fn()
  const view = render(<CreatorCanvasPage {...props} onCreated={onCreated} onSelect={onSelect} />)
  fireEvent.change(screen.getByLabelText('给创作助手的消息'), {target:{value:'账号一的想法'}})
  fireEvent.submit(screen.getByRole('button', {name:'发送'}).closest('form')!)
  fireEvent.submit(screen.getByRole('button', {name:'正在提交…'}).closest('form')!)
  expect(create).toHaveBeenCalledTimes(1)
  view.rerender(<CreatorCanvasPage {...props} workspaceId="another" onCreated={onCreated} onSelect={onSelect} />)
  expect(screen.getByLabelText('给创作助手的消息')).toHaveValue('')
  await act(async () => {resolve(topic)})
  expect(onCreated).not.toHaveBeenCalled(); expect(onSelect).not.toHaveBeenCalled()
  expect(screen.getByLabelText('给创作助手的消息')).toHaveValue('')
  view.rerender(<CreatorCanvasPage {...props} onCreated={onCreated} onSelect={onSelect} />)
  expect(screen.getByLabelText('给创作助手的消息')).toHaveValue('账号一的想法')
})

it('restores a title-only local draft directly into the editor without writing backend data', () => {
  writeCreatorCache('draft', 'w', topic.id, {version:1, baseUpdatedAt:'v1', baseTitle:topic.title, baseBody:'', title:'我改过的标题', body:''})
  const update = vi.spyOn(topicApi, 'update').mockResolvedValue({...topic, body:'那天我做了一个决定。',updatedAt:'v2'})
  render(<CreatorCanvasPage {...props} topic={topic} topics={[topic]} />)
  expect(screen.getByLabelText('创作标题')).toBeVisible()
  expect(screen.getByLabelText('创作标题')).toHaveValue('我改过的标题')
  expect(update).not.toHaveBeenCalled()
})

it('opens a first candidate in preview without silently adopting it, including on narrow screens', async () => {
  vi.stubGlobal('matchMedia', vi.fn(() => ({matches:true, addEventListener:vi.fn(), removeEventListener:vi.fn()})))
  const record = {id:'s',workspaceId:'w',title:'共创',assistantMode:'single_writer',status:'active',executionStatus:'waiting_creator',contextTarget:{assetType:'topic',assetId:topic.id},failureCode:'',failureDetail:'',createdAt:'',updatedAt:'',runs:[],messages:[{id:'m',sessionId:'s',sequenceNo:1,sender:'writing',recipient:'creator',content:'试试这个开头',replyToMessageId:null,createdAt:'',modelMetadata:{candidateSuggestions:[{kind:'copy_option',title:'一个具体瞬间',body:'那天我做了一个决定。',confidence:'inference',evidenceRefs:[]}]}}]} as CollaborationSession
  vi.mocked(contentCollaborationApi.list).mockResolvedValue([record])
  vi.spyOn(contentCollaborationApi, 'get').mockResolvedValue(record)
  const update = vi.spyOn(topicApi, 'update').mockResolvedValue({...topic,body:'那天我做了一个决定。',updatedAt:'v2'})
  render(<CreatorCanvasPage {...props} topic={topic} topics={[topic]} />)
  expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
  fireEvent.click(await screen.findByRole('button', {name:'在稿件区编辑'}))
  expect(screen.getByLabelText('写作建议预览')).toBeVisible()
  expect(screen.getByLabelText('写作建议预览')).toHaveFocus()
  expect(screen.getByRole('tab', {name:'稿件'})).toHaveAttribute('aria-selected', 'true')
  expect(screen.queryByLabelText('创作正文')).not.toBeInTheDocument()
  expect(update).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', {name:'采用并保存'}))
  expect(await screen.findByLabelText('创作正文')).toHaveValue('那天我做了一个决定。')
  expect(update).toHaveBeenCalledOnce()
})

it('offers the library inside the creation page and preserves an unsent idea across reopening', async () => {
  const onOpenTopics = vi.fn()
  const first = render(<CreatorCanvasPage {...props} onOpenTopics={onOpenTopics} />)
  fireEvent.change(screen.getByLabelText('给创作助手的消息'), {target:{value:'先留着这个想法'}})
  fireEvent.click(screen.getByRole('button', {name:'选题库'}))
  expect(onOpenTopics).toHaveBeenCalledOnce()
  first.unmount()
  render(<CreatorCanvasPage {...props} onOpenTopics={onOpenTopics} />)
  expect(screen.getByLabelText('给创作助手的消息')).toHaveValue('先留着这个想法')
  await waitFor(() => expect(window.sessionStorage.getItem(creatorDraftKey('message', 'w', '__new_creation__'))).toContain('先留着这个想法'))
})

it('automatically reveals only the first new body as an unadopted preview after an active request', async () => {
  vi.spyOn(contentCollaborationApi, 'create').mockResolvedValue(emptySession)
  vi.spyOn(contentCollaborationApi, 'send').mockResolvedValue(generated())
  const update = vi.spyOn(topicApi, 'update').mockResolvedValue({...topic,body:'那天我做了一个决定。',updatedAt:'v2'})
  render(<CreatorCanvasPage {...props} topic={topic} topics={[topic]} />)
  const composer = screen.getByLabelText('给创作助手的消息')
  composer.focus()
  await requestDraft()
  expect(await screen.findByLabelText('写作建议预览')).toBeVisible()
  expect(composer).toHaveFocus()
  expect(screen.queryByLabelText('创作正文')).not.toBeInTheDocument()
  expect(screen.queryByLabelText('建议用于')).not.toBeInTheDocument()
  expect(screen.queryByLabelText('建议放入方式')).not.toBeInTheDocument()
  expect(screen.getByLabelText('编辑写作建议')).toHaveValue('那天我做了一个决定。')
  expect(update).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', {name:'采用并保存'}))
  expect(await screen.findByLabelText('创作正文')).toHaveValue('那天我做了一个决定。')
  expect(update).toHaveBeenCalledWith(topic.id,{title:topic.title,body:'那天我做了一个决定。',expectedUpdatedAt:'v1'})
})

it('reveals a polled first draft without switching the narrow-screen tab or stealing focus', async () => {
  vi.useFakeTimers()
  vi.stubGlobal('matchMedia', vi.fn(() => ({matches:true, addEventListener:vi.fn(), removeEventListener:vi.fn()})))
  const completed = generated()
  const queued: CollaborationSession = {...completed, executionStatus:'running', messages:[completed.messages[0]], runs:[{...completed.runs[0], status:'running'}]}
  vi.spyOn(contentCollaborationApi, 'create').mockResolvedValue(emptySession)
  vi.spyOn(contentCollaborationApi, 'send').mockResolvedValue(queued)
  vi.spyOn(contentCollaborationApi, 'get').mockResolvedValue(completed)
  render(<CreatorCanvasPage {...props} topic={topic} topics={[topic]} />)
  await act(async () => {})
  const composer = screen.getByLabelText('给创作助手的消息')
  composer.focus()
  fireEvent.change(composer, {target:{value:'帮我起草'}})
  fireEvent.click(screen.getByRole('button', {name:'发送'}))
  await act(async () => {})
  expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
  await act(async () => {await vi.advanceTimersByTimeAsync(500)})
  expect(screen.getByRole('tab', {name:'对话'})).toHaveAttribute('aria-selected','true')
  expect(composer).toHaveFocus()
  expect(screen.getByTitle('有待采用建议')).toBeVisible()
  fireEvent.click(screen.getByRole('tab', {name:'稿件'}))
  expect(screen.getByLabelText('写作建议预览')).toBeVisible()
  expect(screen.queryByLabelText('创作正文')).not.toBeInTheDocument()
})

it.each(['outline', 'open_question'] as const)('does not automatically open the editor for %s', async kind => {
  vi.spyOn(contentCollaborationApi, 'create').mockResolvedValue(emptySession)
  vi.spyOn(contentCollaborationApi, 'send').mockResolvedValue(generated(kind))
  render(<CreatorCanvasPage {...props} topic={topic} topics={[topic]} />)
  await requestDraft()
  await screen.findByText('这是第一版')
  expect(screen.queryByLabelText('写作建议预览')).not.toBeInTheDocument()
  expect(screen.getByLabelText('创作正文')).not.toBeVisible()
})

it('restores the latest eligible full candidate without adoption or focus changes', async () => {
  vi.mocked(contentCollaborationApi.list).mockResolvedValue([generated()])
  vi.spyOn(contentCollaborationApi, 'get').mockResolvedValue(generated())
  render(<CreatorCanvasPage {...props} topic={topic} topics={[topic]} />)
  const composer = screen.getByLabelText('给创作助手的消息')
  composer.focus()
  await screen.findByText('这是第一版')
  expect(await screen.findByLabelText('写作建议预览')).toBeVisible()
  expect(screen.queryByLabelText('创作正文')).not.toBeInTheDocument()
  expect(composer).toHaveFocus()
  expect(screen.getByRole('button', {name:'在稿件区编辑'})).toBeVisible()
})

it('does not interrupt a saved draft with a new automatic preview', async () => {
  vi.spyOn(contentCollaborationApi, 'create').mockResolvedValue(emptySession)
  vi.spyOn(contentCollaborationApi, 'send').mockResolvedValue(generated())
  render(<CreatorCanvasPage {...props} topic={{...topic,body:'已有正文'}} topics={[topic]} />)
  await requestDraft()
  await screen.findByText('这是第一版')
  expect(screen.queryByLabelText('写作建议预览')).not.toBeInTheDocument()
  expect(screen.getByLabelText('创作正文')).toHaveValue('已有正文')
})

it.each(['message', 'draft'] as const)('does not open a preview when the user is editing a new %s during the response', async target => {
  let resolve!: (session: CollaborationSession) => void
  vi.spyOn(contentCollaborationApi, 'create').mockResolvedValue(emptySession)
  const send = vi.spyOn(contentCollaborationApi, 'send').mockReturnValue(new Promise(done => {resolve = done}))
  render(<CreatorCanvasPage {...props} topic={topic} topics={[topic]} />)
  await requestDraft()
  await waitFor(() => expect(send).toHaveBeenCalledOnce())
  if (target === 'draft') {
    fireEvent.click(screen.getByRole('button', {name:'自己写稿'}))
    fireEvent.change(screen.getByLabelText('创作正文'), {target:{value:'我自己写的开头'}})
  } else fireEvent.change(screen.getByLabelText('给创作助手的消息'), {target:{value:'还有一个想法没发'}})
  await act(async () => {resolve(generated())})
  expect(screen.queryByLabelText('写作建议预览')).not.toBeInTheDocument()
  expect(screen.getByLabelText(target === 'draft' ? '创作正文' : '给创作助手的消息')).toHaveValue(target === 'draft' ? '我自己写的开头' : '还有一个想法没发')
})

it('reuses the created topic, session key and uncertain send after leaving and reopening', async () => {
  const create = vi.spyOn(topicApi, 'create').mockResolvedValue(topic)
  const get = vi.spyOn(topicApi, 'get').mockResolvedValue(topic)
  const createSession = vi.spyOn(contentCollaborationApi, 'create').mockResolvedValue(emptySession)
  const send = vi.spyOn(contentCollaborationApi, 'send').mockRejectedValueOnce(new Error('响应中断')).mockResolvedValue(emptySession)
  const first = render(<Start />)
  await requestDraft()
  await screen.findByText('响应中断')
  expect(screen.getByLabelText('给创作助手的消息')).toHaveValue('帮我起草')
  first.unmount()
  render(<Start />)
  expect(screen.getByLabelText('给创作助手的消息')).toHaveValue('帮我起草')
  fireEvent.click(screen.getByRole('button',{name:'发送'}))
  await waitFor(() => expect(screen.getByLabelText('给创作助手的消息')).toHaveValue(''))
  expect(create).toHaveBeenCalledOnce()
  expect(get).toHaveBeenCalledWith(topic.id)
  expect(createSession.mock.calls[0][3]).toBe(createSession.mock.calls[1][3])
  expect(send.mock.calls[0][4]).toBe(send.mock.calls[1][4])
})

it('sends the manually selected references on first send and retains new typing during that request', async () => {
  const references = {schemaVersion:'creator-context-selection/v1' as const,references:[{kind:'account_analysis' as const,id:'chosen-history'}]}
  writeCreatorCache('message','w','__new_creation__',{version:1,message:'我选好的问题',selection:references})
  vi.spyOn(topicApi,'create').mockResolvedValue(topic)
  vi.spyOn(contentCollaborationApi,'create').mockResolvedValue(emptySession)
  let resolve!: (value: CollaborationSession) => void
  const send = vi.spyOn(contentCollaborationApi,'send').mockReturnValue(new Promise(done => {resolve = done}))
  render(<Start />)
  fireEvent.click(screen.getByRole('button',{name:'发送'}))
  await waitFor(() => expect(send).toHaveBeenCalledOnce())
  fireEvent.change(screen.getByLabelText('给创作助手的消息'),{target:{value:'下一条还没发的想法'}})
  await act(async () => resolve(emptySession))
  expect(screen.getByLabelText('给创作助手的消息')).toHaveValue('下一条还没发的想法')
  expect(send).toHaveBeenCalledWith('w','s','我选好的问题','writing',expect.any(String),undefined,references)
  expect(send).toHaveBeenCalledOnce()
})

it('retains edited candidate text when navigating to it, blocks stale-context sending, and recovers it after a failed save', async () => {
  vi.mocked(contentCollaborationApi.list).mockResolvedValue([generated()])
  vi.spyOn(contentCollaborationApi,'get').mockResolvedValue(generated())
  const update = vi.spyOn(topicApi,'update').mockRejectedValue(new Error('保存暂时失败'))
  const first = render(<CreatorCanvasPage {...props} topic={topic} topics={[topic]} />)
  fireEvent.change(await screen.findByLabelText('编辑写作建议'),{target:{value:'我改过的第一版。'}})
  fireEvent.change(screen.getByLabelText('候选稿标题'),{target:{value:'我改过的标题'}})
  fireEvent.click(screen.getByRole('button',{name:'在稿件区编辑'}))
  expect(screen.getByLabelText('编辑写作建议')).toHaveValue('我改过的第一版。')
  expect(screen.getByLabelText('候选稿标题')).toHaveValue('我改过的标题')
  fireEvent.change(screen.getByLabelText('给创作助手的消息'),{target:{value:'再改一下'}})
  expect(screen.getByRole('button',{name:'发送'})).toBeDisabled()
  expect(screen.getByText('先采用并保存修改，或暂不采用后继续讨论。')).toBeVisible()
  fireEvent.click(screen.getByRole('button',{name:'采用并保存'}))
  await screen.findByText('保存暂时失败')
  expect(update).toHaveBeenCalledOnce()
  first.unmount()
  render(<CreatorCanvasPage {...props} topic={topic} topics={[topic]} />)
  expect(screen.getByLabelText('编辑写作建议')).toHaveValue('我改过的第一版。')
  expect(screen.getByLabelText('候选稿标题')).toHaveValue('我改过的标题')
  expect(screen.getByLabelText('给创作助手的消息')).toHaveValue('再改一下')
  expect(screen.queryByLabelText('创作正文')).not.toBeInTheDocument()
})

it.each(['wrong-topic', 'same-version'] as const)('does not accept an invalid candidate save receipt: %s', async kind => {
  vi.mocked(contentCollaborationApi.list).mockResolvedValue([generated()])
  vi.spyOn(contentCollaborationApi,'get').mockResolvedValue(generated())
  vi.spyOn(topicApi,'update').mockResolvedValue({...topic,body:'那天我做了一个决定。',id:kind === 'wrong-topic' ? 'other-topic' : topic.id,updatedAt:kind === 'same-version' ? 'v1' : 'v2'})
  const updated = vi.fn()
  render(<CreatorCanvasPage {...props} topic={topic} topics={[topic]} onUpdated={updated} />)
  fireEvent.click(await screen.findByRole('button',{name:'采用并保存'}))
  await screen.findByText('保存回执与当前稿件不一致，候选内容已保留，请重新核对。')
  expect(screen.getByLabelText('编辑写作建议')).toHaveValue('那天我做了一个决定。')
  expect(updated).not.toHaveBeenCalled()
})

it('preserves an edited candidate when a newer saved version is opened', async () => {
  vi.mocked(contentCollaborationApi.list).mockResolvedValue([generated()])
  vi.spyOn(contentCollaborationApi,'get').mockResolvedValue(generated())
  const first = render(<CreatorCanvasPage {...props} topic={topic} topics={[topic]} />)
  fireEvent.change(await screen.findByLabelText('编辑写作建议'),{target:{value:'仍未采用的个人修改。'}})
  first.unmount()
  render(<CreatorCanvasPage {...props} topic={{...topic,body:'别处保存的新正文',updatedAt:'v2'}} topics={[topic]} />)
  expect(screen.getByLabelText('待恢复的本地草稿')).toBeVisible()
  expect(screen.getByLabelText('创作正文')).toHaveValue('别处保存的新正文')
  fireEvent.click(screen.getByRole('button',{name:'恢复本地草稿'}))
  expect(screen.getByLabelText('创作正文')).toHaveValue('仍未采用的个人修改。')
  expect(screen.getByText('有未保存修改')).toBeVisible()
})

it('uses a topic receipt that arrived after reopening instead of creating another topic', async () => {
  let resolve!: (value: Topic) => void
  const create = vi.spyOn(topicApi,'create').mockReturnValue(new Promise(done => {resolve = done}))
  const get = vi.spyOn(topicApi,'get').mockResolvedValue(topic)
  vi.spyOn(contentCollaborationApi,'create').mockResolvedValue(emptySession)
  const send = vi.spyOn(contentCollaborationApi,'send').mockResolvedValue(emptySession)
  const first = render(<Start />)
  await requestDraft()
  await waitFor(() => expect(create).toHaveBeenCalledOnce())
  first.unmount()
  render(<Start />)
  await act(async () => resolve(topic))
  fireEvent.change(screen.getByLabelText('给创作助手的消息'),{target:{value:'还想补充一个角度'}})
  fireEvent.click(screen.getByRole('button',{name:'发送'}))
  await waitFor(() => expect(send).toHaveBeenCalledOnce())
  expect(create).toHaveBeenCalledOnce()
  expect(get).toHaveBeenCalledWith(topic.id)
})

it('keeps an outline on the explicit preview path instead of treating it as a first draft', async () => {
  vi.mocked(contentCollaborationApi.list).mockResolvedValue([generated('outline')])
  vi.spyOn(contentCollaborationApi,'get').mockResolvedValue(generated('outline'))
  render(<CreatorCanvasPage {...props} topic={topic} topics={[topic]} />)
  fireEvent.click(await screen.findByRole('button',{name:'预览并编辑这条建议'}))
  expect(screen.queryByRole('button',{name:'采用并保存'})).not.toBeInTheDocument()
  expect(screen.getByLabelText('建议用于')).toBeVisible()
  expect(screen.getByLabelText('创作正文')).toBeVisible()
  expect(screen.getByRole('button',{name:'确认放入画布'})).toBeVisible()
})

it.each([false, true])('reconciles a valid adoption receipt after leaving without clearing newer cached edits: %s', async changed => {
  vi.mocked(contentCollaborationApi.list).mockResolvedValue([generated()])
  vi.spyOn(contentCollaborationApi,'get').mockResolvedValue(generated())
  let resolve!: (value: Topic) => void
  const update = vi.spyOn(topicApi,'update').mockReturnValue(new Promise(done => {resolve = done}))
  const updated = vi.fn()
  const first = render(<CreatorCanvasPage {...props} topic={topic} topics={[topic]} onUpdated={updated} />)
  fireEvent.click(await screen.findByRole('button',{name:'采用并保存'}))
  await waitFor(() => expect(update).toHaveBeenCalledOnce())
  first.unmount()
  if (changed) {
    render(<CreatorCanvasPage {...props} topic={topic} topics={[topic]} onUpdated={updated} />)
    fireEvent.change(screen.getByLabelText('编辑写作建议'),{target:{value:'重新打开后继续编辑的内容'}})
  }
  const receipt = {...topic,body:'那天我做了一个决定。',updatedAt:'v2'}
  await act(async () => resolve(receipt))
  expect(updated).toHaveBeenCalledWith(receipt)
  const cache = window.sessionStorage.getItem(creatorDraftKey('candidate','w',topic.id))
  if (changed) {
    expect(cache).toContain('重新打开后继续编辑的内容')
    expect(screen.getByLabelText('编辑写作建议')).toHaveValue('重新打开后继续编辑的内容')
  } else expect(cache).toBeNull()
})

it('does not reconcile an invalid late adoption receipt or discard its cached candidate', async () => {
  vi.mocked(contentCollaborationApi.list).mockResolvedValue([generated()])
  vi.spyOn(contentCollaborationApi,'get').mockResolvedValue(generated())
  let resolve!: (value: Topic) => void
  vi.spyOn(topicApi,'update').mockReturnValue(new Promise(done => {resolve = done}))
  const updated = vi.fn()
  const first = render(<CreatorCanvasPage {...props} topic={topic} topics={[topic]} onUpdated={updated} />)
  fireEvent.click(await screen.findByRole('button',{name:'采用并保存'}))
  first.unmount()
  await act(async () => resolve({...topic,workspaceId:'other',body:'那天我做了一个决定。',updatedAt:'v2'}))
  expect(updated).not.toHaveBeenCalled()
  expect(window.sessionStorage.getItem(creatorDraftKey('candidate','w',topic.id))).toContain('那天我做了一个决定。')
})
