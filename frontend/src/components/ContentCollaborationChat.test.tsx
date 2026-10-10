import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react'
import {afterEach, beforeEach, expect, it, vi} from 'vitest'
import {agentConversationApi} from '../api'
import {contentCollaborationApi, emptyCreatorContext, type CollaborationSession, type CreatorContextSelection} from '../contentCollaboration'
import type {Topic} from '../types'
import {ContentCollaborationChat} from './ContentCollaborationChat'

vi.mock('./CreatorReferencePicker', () => ({CreatorReferencePicker: ({selection, onChange, disabled}: {
  selection: CreatorContextSelection; onChange: (selection: CreatorContextSelection) => void; disabled: boolean
}) => <div>
  <output aria-label="已选参考">{selection.references.map(item => `${item.kind}:${item.id}`).join(',') || '无'}</output>
  <button disabled={disabled} onClick={() => onChange({schemaVersion:'creator-context-selection/v1',references:[{kind:'account_analysis',id:'account-a'}]})}>选账号分析</button>
  <button disabled={disabled} onClick={() => onChange({schemaVersion:'creator-context-selection/v1',references:[{kind:'audience_analysis',id:'audience-b'}]})}>选受众分析</button>
  <button disabled={disabled} onClick={() => onChange({schemaVersion:'creator-context-selection/v1',references:[]})}>清空参考</button>
</div>}))

const topic: Topic = {id:'t',workspaceId:'w',title:'当前稿件',body:'当前正文',angle:'',associatedPainPoint:'',whyItFits:'',generatedSnapshot:{},sourceAnalysisRunId:null,sourceWorkflow:'manual',status:'candidate',createdAt:'v1',updatedAt:'v1'}
const refsA: CreatorContextSelection = {schemaVersion:'creator-context-selection/v1',references:[{kind:'account_analysis',id:'account-a'}]}
const refsB: CreatorContextSelection = {schemaVersion:'creator-context-selection/v1',references:[{kind:'audience_analysis',id:'audience-b'}]}
const session: CollaborationSession = {id:'s',workspaceId:'w',title:'单助手对话',assistantMode:'single_writer',status:'active',executionStatus:'waiting_creator',contextTarget:{assetType:'topic',assetId:'t'},creatorContextSelection:emptyCreatorContext(),contextRevision:1,failureCode:'',failureDetail:'',createdAt:'',updatedAt:'',messages:[],runs:[]}
const creatorMessage = {id:'c',sessionId:'s',sequenceNo:1,sender:'creator' as const,recipient:'writing' as const,content:'之前的要求',replyToMessageId:null,modelMetadata:{contextRevision:1},createdAt:''}
const writerMessage = {id:'m',sessionId:'s',sequenceNo:2,sender:'writing' as const,recipient:'creator' as const,content:'之前的一条建议',replyToMessageId:null,modelMetadata:{contextRevision:1},createdAt:''}
const props = {workspaceId:'w',topic,blocked:false,beforeSend:vi.fn(async () => ({topic,assertCurrent:vi.fn()})),onActivityChange:vi.fn(),onPreview:vi.fn()}
const createSessionRequest = contentCollaborationApi.create
function deferred<T>() {let resolve!: (value:T) => void; const promise = new Promise<T>(yes => {resolve = yes}); return {promise,resolve}}
beforeEach(() => {
  vi.spyOn(agentConversationApi,'list').mockResolvedValue([])
  vi.spyOn(contentCollaborationApi,'list').mockResolvedValue([])
  vi.spyOn(contentCollaborationApi,'create').mockResolvedValue(session)
  vi.spyOn(contentCollaborationApi,'send').mockResolvedValue(session)
})
afterEach(() => {cleanup(); vi.restoreAllMocks(); vi.clearAllMocks(); vi.useRealTimers()})
async function submit(content = '帮我改善开头') {
  fireEvent.change(screen.getByLabelText('给创作助手的消息'),{target:{value:content}})
  await waitFor(() => expect(screen.getByRole('button',{name:'发送'})).toBeEnabled())
  fireEvent.click(screen.getByRole('button',{name:'发送'}))
}
function reopen(value: CollaborationSession) {
  vi.mocked(contentCollaborationApi.list).mockResolvedValue([value])
  return vi.spyOn(contentCollaborationApi,'get').mockResolvedValue(value)
}

it('creates a fresh session, always addresses writing, and explicitly sends no extra references by default', async () => {
  const oldCreate = vi.spyOn(agentConversationApi,'create'), oldSend = vi.spyOn(agentConversationApi,'sendMessage')
  vi.mocked(contentCollaborationApi.create).mockImplementation(createSessionRequest)
  const fetch = vi.spyOn(globalThis,'fetch').mockResolvedValue(new Response(JSON.stringify(session),{status:200}))
  render(<ContentCollaborationChat {...props} />)
  expect(screen.queryByLabelText('先交给哪位伙伴')).not.toBeInTheDocument()
  expect(screen.getByLabelText('已选参考')).toHaveTextContent('无')
  await submit()
  await waitFor(() => expect(contentCollaborationApi.send).toHaveBeenCalledWith('w','s','帮我改善开头','writing',expect.any(String),undefined,emptyCreatorContext()))
  expect(contentCollaborationApi.create).toHaveBeenCalledWith('w','t','当前稿件',expect.any(String))
  expect(JSON.parse(fetch.mock.calls[0][1]?.body as string)).toMatchObject({assistantMode:'single_writer',contextTarget:{assetType:'topic',assetId:'t'}})
  expect(oldCreate).not.toHaveBeenCalled()
  expect(oldSend).not.toHaveBeenCalled()
})

it('keeps an old team session read-only and starts a new single-writer session after viewing it', async () => {
  const old: CollaborationSession = {...session,id:'team',title:'旧版讨论',assistantMode:'legacy_team',executionStatus:'running',messages:[{...writerMessage,id:'old-message',sessionId:'team',sender:'review',recipient:'research',content:'旧团队的审稿意见'}]}
  vi.mocked(contentCollaborationApi.list).mockResolvedValue([old])
  const get = vi.spyOn(contentCollaborationApi,'get').mockResolvedValue(old)
  render(<ContentCollaborationChat {...props} />)
  const summary = await screen.findByText('旧版多人协作（只读）')
  expect(summary.closest('details')).not.toHaveAttribute('open')
  expect(get).not.toHaveBeenCalled()
  fireEvent.click(summary)
  const details = summary.closest('details')!
  fireEvent(details,new Event('toggle'))
  expect(await within(details).findByText('旧团队的审稿意见')).toBeVisible()
  expect(within(details).queryByRole('button')).not.toBeInTheDocument()
  await submit('现在用一个助手继续写')
  await waitFor(() => expect(contentCollaborationApi.create).toHaveBeenCalledTimes(1))
  expect(contentCollaborationApi.send).toHaveBeenCalledWith('w','s','现在用一个助手继续写','writing',expect.any(String),undefined,emptyCreatorContext())
  expect(get).toHaveBeenCalledTimes(1)
})

it('restores the sent reference set when reopening and submits the latest explicit selection', async () => {
  reopen({...session,creatorContextSelection:refsA,messages:[creatorMessage,writerMessage]})
  render(<ContentCollaborationChat {...props} />)
  await screen.findByText('之前的一条建议')
  expect(screen.getByLabelText('已选参考')).toHaveTextContent('account_analysis:account-a')
  fireEvent.click(screen.getByRole('button',{name:'选受众分析'}))
  expect(screen.getByText('参考已调整，下次发送会开启一段新对话。')).toBeInTheDocument()
  await submit()
  await waitFor(() => expect(contentCollaborationApi.send).toHaveBeenCalledWith('w','s','帮我改善开头','writing',expect.any(String),undefined,refsB))
  expect(contentCollaborationApi.create).not.toHaveBeenCalled()
})

it('does not restore an older reference snapshot over a selection changed while polling', async () => {
  vi.useFakeTimers()
  const run = {id:'run',status:'running' as const,triggerMessageId:'c',graphState:{},errorCode:'',errorDetail:'',createdAt:new Date().toISOString(),startedAt:null,completedAt:null}
  const running: CollaborationSession = {...session,creatorContextSelection:refsA,executionStatus:'running',messages:[creatorMessage],runs:[run]}
  vi.mocked(contentCollaborationApi.list).mockResolvedValue([running])
  vi.spyOn(contentCollaborationApi,'get').mockResolvedValueOnce(running).mockResolvedValueOnce(running).mockResolvedValue({...running,executionStatus:'waiting_creator',messages:[creatorMessage,writerMessage]})
  render(<ContentCollaborationChat {...props} />)
  await act(async () => {})
  expect(within(screen.getByLabelText('创作对话')).getByRole('status')).toHaveTextContent('创作助手正在整理')
  fireEvent.click(screen.getByRole('button',{name:'选受众分析'}))
  await act(async () => {await vi.advanceTimersByTimeAsync(500)})
  expect(screen.getByLabelText('已选参考')).toHaveTextContent('audience_analysis:audience-b')
  await act(async () => {await vi.advanceTimersByTimeAsync(1000)})
  expect(screen.getByLabelText('已选参考')).toHaveTextContent('audience_analysis:audience-b')
  fireEvent.change(screen.getByLabelText('给创作助手的消息'),{target:{value:'现在参考受众意见'}})
  fireEvent.click(screen.getByRole('button',{name:'发送'}))
  await act(async () => {})
  expect(contentCollaborationApi.send).toHaveBeenCalledWith('w','s','现在参考受众意见','writing',expect.any(String),undefined,refsB)
})

it('reuses the uncertain request key but creates a new key when its reference set changes', async () => {
  const send = vi.mocked(contentCollaborationApi.send).mockRejectedValueOnce(new Error('响应中断')).mockRejectedValueOnce(new Error('再次中断')).mockResolvedValue(session)
  render(<ContentCollaborationChat {...props} />)
  await submit('同一个要求')
  await screen.findByText('响应中断')
  expect(send).toHaveBeenCalledTimes(1)
  fireEvent.click(screen.getByRole('button',{name:'发送'}))
  await screen.findByText('再次中断')
  expect(send.mock.calls[0][4]).toBe(send.mock.calls[1][4])
  expect(send.mock.calls[0][6]).toEqual(emptyCreatorContext())
  fireEvent.click(screen.getByRole('button',{name:'选受众分析'}))
  fireEvent.click(screen.getByRole('button',{name:'发送'}))
  await waitFor(() => expect(send).toHaveBeenCalledTimes(3))
  expect(send.mock.calls[2][4]).not.toBe(send.mock.calls[1][4])
  expect(send.mock.calls[2][6]).toEqual(refsB)
  expect(contentCollaborationApi.create).toHaveBeenCalledTimes(1)
})

it.each(['load','reply'] as const)('ignores a late %s after switching account and topic with a remount', async stage => {
  const pending = deferred<CollaborationSession>()
  if (stage === 'load') {
    vi.mocked(contentCollaborationApi.list).mockResolvedValueOnce([session]).mockResolvedValue([])
    vi.spyOn(contentCollaborationApi,'get').mockReturnValue(pending.promise)
  } else vi.mocked(contentCollaborationApi.send).mockReturnValue(pending.promise)
  const {rerender} = render(<ContentCollaborationChat key="w:t" {...props} />)
  if (stage === 'load') await waitFor(() => expect(contentCollaborationApi.get).toHaveBeenCalledTimes(1))
  else {await submit(); await waitFor(() => expect(contentCollaborationApi.send).toHaveBeenCalledTimes(1))}
  const another = {...topic,id:'next',workspaceId:'other'}
  rerender(<ContentCollaborationChat key="other:next" {...props} workspaceId="other" topic={another} />)
  await waitFor(() => expect(screen.getByRole('button',{name:'选受众分析'})).toBeEnabled())
  fireEvent.change(screen.getByLabelText('给创作助手的消息'),{target:{value:'另一个账号的新要求'}})
  fireEvent.click(screen.getByRole('button',{name:'选受众分析'}))
  await act(async () => pending.resolve({...session,creatorContextSelection:refsA,messages:[writerMessage]}))
  expect(screen.getByLabelText('给创作助手的消息')).toHaveValue('另一个账号的新要求')
  expect(screen.getByLabelText('已选参考')).toHaveTextContent('audience_analysis:audience-b')
  expect(screen.queryByText('之前的一条建议')).not.toBeInTheDocument()
})

it('allows an explicit reload after a failed history request without losing typed instructions', async () => {
  vi.mocked(contentCollaborationApi.list).mockRejectedValueOnce(new Error('网络中断')).mockResolvedValue([session])
  vi.spyOn(contentCollaborationApi,'get').mockResolvedValue({...session,creatorContextSelection:refsA})
  render(<ContentCollaborationChat {...props} />)
  await screen.findByText('创作记录未能载入：网络中断')
  fireEvent.change(screen.getByLabelText('给创作助手的消息'),{target:{value:'重读后再发'}})
  expect(screen.getByRole('button',{name:'发送'})).toBeDisabled()
  expect(contentCollaborationApi.list).toHaveBeenCalledTimes(1)
  fireEvent.click(screen.getByRole('button',{name:'重新载入进度'}))
  await waitFor(() => expect(screen.getByRole('button',{name:'发送'})).toBeEnabled())
  expect(screen.getByLabelText('给创作助手的消息')).toHaveValue('重读后再发')
  expect(screen.getByLabelText('已选参考')).toHaveTextContent('account_analysis:account-a')
  expect(contentCollaborationApi.send).not.toHaveBeenCalled()
})

it.each(['先聊角度', '帮我起草'])('appends the %s shortcut without replacing a typed instruction or sending it', async name => {
  render(<ContentCollaborationChat {...props} />)
  fireEvent.change(screen.getByLabelText('给创作助手的消息'),{target:{value:'保留我开头讲的真实经历。'}})
  fireEvent.click(screen.getByRole('button',{name}))
  const composer = screen.getByLabelText('给创作助手的消息') as HTMLTextAreaElement
  expect(composer.value).toMatch(/^保留我开头讲的真实经历。\n\n/)
  expect(composer).toHaveFocus()
  expect(composer.selectionStart).toBe(composer.value.length)
  expect(contentCollaborationApi.send).not.toHaveBeenCalled()
})

it('appends a follow-up question and a failed instruction without erasing a new message', async () => {
  const candidate = {kind:'open_question',title:'你当时怎么决定？',body:'补充一个真实细节',confidence:'inference',evidenceRefs:[]}
  reopen({...session,executionStatus:'failed',messages:[creatorMessage,{...writerMessage,modelMetadata:{candidateSuggestions:[candidate]}}]})
  render(<ContentCollaborationChat {...props} />)
  await screen.findByRole('button',{name:'补充说明'})
  fireEvent.change(screen.getByLabelText('给创作助手的消息'),{target:{value:'我已经写了一半。'}})
  fireEvent.click(screen.getByRole('button',{name:'补充说明'}))
  expect(screen.getByLabelText('给创作助手的消息')).toHaveValue('我已经写了一半。\n\n关于“你当时怎么决定？”：')
  fireEvent.click(screen.getByRole('button',{name:'把上次要求放回输入框'}))
  expect(screen.getByLabelText('给创作助手的消息')).toHaveValue('我已经写了一半。\n\n关于“你当时怎么决定？”：\n\n之前的要求')
  expect(contentCollaborationApi.send).not.toHaveBeenCalled()
})

it('recovers an unsent message together with its selected references, not the last sent references', async () => {
  reopen({...session,creatorContextSelection:refsA,messages:[creatorMessage,writerMessage]})
  const first = render(<ContentCollaborationChat {...props} />)
  await screen.findByText('之前的一条建议')
  fireEvent.click(screen.getByRole('button',{name:'选受众分析'}))
  fireEvent.change(screen.getByLabelText('给创作助手的消息'),{target:{value:'用这组参考继续讨论'}})
  first.unmount()
  render(<ContentCollaborationChat {...props} />)
  await screen.findByText('之前的一条建议')
  expect(screen.getByLabelText('给创作助手的消息')).toHaveValue('用这组参考继续讨论')
  expect(screen.getByLabelText('已选参考')).toHaveTextContent('audience_analysis:audience-b')
  fireEvent.click(screen.getByRole('button',{name:'发送'}))
  await waitFor(() => expect(contentCollaborationApi.send).toHaveBeenCalledWith('w','s','用这组参考继续讨论','writing',expect.any(String),undefined,refsB))
})

it('retains over-limit shortcut text and asks for trimming instead of discarding input', async () => {
  render(<ContentCollaborationChat {...props} />)
  const original = '字'.repeat(7995)
  fireEvent.change(screen.getByLabelText('给创作助手的消息'),{target:{value:original}})
  fireEvent.click(screen.getByRole('button',{name:'先聊角度'}))
  expect((screen.getByLabelText('给创作助手的消息') as HTMLTextAreaElement).value).toMatch(new RegExp(`^${original}\\n\\n`))
  expect(screen.getByRole('alert')).toHaveTextContent('已保留完整输入')
  expect(screen.getByRole('button',{name:'发送'})).toBeDisabled()
  expect(contentCollaborationApi.send).not.toHaveBeenCalled()
})
