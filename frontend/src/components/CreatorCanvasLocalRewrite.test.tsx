import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react'
import {afterEach, beforeEach, expect, it, vi} from 'vitest'
import {agentConversationApi, topicApi} from '../api'
import {contentCollaborationApi, selectionFromTextarea, type CollaborationSession, type FrozenWritingFocus, type ReaderFeedbackIntent} from '../contentCollaboration'
import type {Topic} from '../types'
import {CreatorCanvasPage} from './CreatorCanvasPage'

const body = '开头🙂重复。\n中间。\n重复。结尾'
const topic: Topic = {id:'t',workspaceId:'w',title:'原题',body,angle:'',associatedPainPoint:'',whyItFits:'',generatedSnapshot:{},sourceAnalysisRunId:null,sourceWorkflow:'manual',status:'candidate',createdAt:'v1',updatedAt:'v1'}
const session: CollaborationSession = {id:'s',workspaceId:'w',title:'协作',assistantMode:'single_writer',status:'active',executionStatus:'waiting_creator',contextTarget:{assetType:'topic',assetId:'t'},failureCode:'',failureDetail:'',createdAt:'',updatedAt:'',messages:[],runs:[]}
const emptyReferences = {schemaVersion:'creator-context-selection/v1',references:[]}
const feedback: ReaderFeedbackIntent = {id:'intent',workspaceId:'w',topicId:'t',simulationId:'run',stage:'interview',messageId:'reply',interviewId:'i',senderName:'重细节的读者',quote:'我想看到这一步为什么这样做。',authorQuestion:'哪一处还不清楚？'}
const selection = selectionFromTextarea(body, body.lastIndexOf('重复。'), body.lastIndexOf('重复。') + 3)!
const focus: FrozenWritingFocus = {baseTopicId:'t',baseTitle:topic.title,baseBody:body,baseUpdatedAt:'v1',selection,
  readerReference:{simulationId:'run',stage:'interview',messageId:'reply',interviewId:'i'}}
const suggestion: CollaborationSession = {...session,messages:[{id:'answer',sessionId:'s',sequenceNo:2,sender:'writing',recipient:'creator',content:'保留节奏，改清楚这段。',replyToMessageId:null,createdAt:'',
  modelMetadata:{writingFocus:focus,candidateSuggestions:[{kind:'copy_option',title:'把理由说出来',body:'这是改清楚的段落。',confidence:'inference'}]}}]}
const props = {workspaceId:'w',topic,topics:[topic],onSelect:vi.fn(),onUpdated:vi.fn()}
beforeEach(() => {
  vi.spyOn(agentConversationApi,'list').mockResolvedValue([])
  vi.spyOn(contentCollaborationApi,'list').mockResolvedValue([])
})
afterEach(() => {cleanup();vi.restoreAllMocks();vi.unstubAllGlobals()})
function chooseLastParagraph() {
  const editor = screen.getByLabelText('创作正文') as HTMLTextAreaElement
  editor.focus(); editor.setSelectionRange(body.lastIndexOf('重复。'), body.lastIndexOf('重复。') + 3)
  fireEvent.select(editor)
}
function reopen() {vi.mocked(contentCollaborationApi.list).mockResolvedValue([suggestion]); vi.spyOn(contentCollaborationApi,'get').mockResolvedValue(suggestion)}

it('keeps duplicate selection text folded while retaining explicit save guidance', async () => {
  reopen()
  render(<CreatorCanvasPage {...props} />)
  chooseLastParagraph()
  const tools = within(screen.getByLabelText('选段改写'))
  expect(tools.getByText(selection.text)).not.toBeVisible()
  fireEvent.click(tools.getByText('查看选段'))
  expect(tools.getByText(selection.text)).toBeVisible()
  fireEvent.click(await screen.findByRole('button',{name:'对比并修改这一段'}))
  expect(screen.getByText('确认后仍需保存。')).toBeVisible()
  expect(screen.queryByText('只替换下面选中的这段文字，其余正文保持不变。')).not.toBeInTheDocument()
})

it('keeps identical candidate prose distinct when it targets another occurrence', async () => {
  const firstSelection = selectionFromTextarea(body,body.indexOf('重复。'),body.indexOf('重复。') + 3)!
  const firstMessage = {...suggestion.messages[0],id:'first',modelMetadata:{...suggestion.messages[0].modelMetadata,writingFocus:{...focus,selection:firstSelection}}}
  const record = {...suggestion,messages:[firstMessage,suggestion.messages[0]]}
  vi.mocked(contentCollaborationApi.list).mockResolvedValue([record])
  vi.spyOn(contentCollaborationApi,'get').mockResolvedValue(record)
  render(<CreatorCanvasPage {...props} />)
  fireEvent.click((await screen.findAllByRole('button',{name:'对比并修改这一段'}))[0])
  expect(screen.getAllByRole('button',{name:'在稿件区编辑'})).toHaveLength(1)
  fireEvent.click(screen.getByRole('button',{name:'对比并修改这一段'}))
  fireEvent.click(screen.getByRole('button',{name:'只替换这一段'}))
  expect(screen.getByLabelText('创作正文')).toHaveValue('开头🙂重复。\n中间。\n这是改清楚的段落。结尾')
})

it('imports feedback without changing the editor, overwriting typed instructions, or submitting automatically', async () => {
  const send = vi.spyOn(contentCollaborationApi,'send'), consumed = vi.fn()
  const {rerender} = render(<CreatorCanvasPage {...props} onReaderFeedbackConsumed={consumed} />)
  fireEvent.change(screen.getByLabelText('给创作助手的消息'),{target:{value:'我自己的要求'}})
  rerender(<CreatorCanvasPage {...props} readerFeedback={feedback} onReaderFeedbackConsumed={consumed} />)
  expect(await screen.findByText(feedback.quote)).toBeInTheDocument()
  expect(screen.getByLabelText('创作正文')).toHaveValue(body)
  expect(screen.getByLabelText('给创作助手的消息')).toHaveValue('我自己的要求')
  expect(consumed).toHaveBeenCalledTimes(1)
  fireEvent.click(screen.getByRole('button',{name:'和助手讨论'}))
  expect((screen.getByLabelText('给创作助手的消息') as HTMLTextAreaElement).value).toContain('我自己的要求\n\n请结合引用的读者意见')
  expect(screen.queryByLabelText('先交给哪位伙伴')).not.toBeInTheDocument()
  expect(screen.getByLabelText('给创作助手的消息')).toHaveFocus()
  expect(send).not.toHaveBeenCalled()
})

it('sends the exact Unicode selection and reference IDs only after explicit send', async () => {
  vi.spyOn(contentCollaborationApi,'create').mockResolvedValue(session)
  const send = vi.spyOn(contentCollaborationApi,'send').mockResolvedValue(session)
  render(<CreatorCanvasPage {...props} readerFeedback={feedback} />)
  const composer = screen.getByLabelText('给创作助手的消息') as HTMLTextAreaElement
  const scroll = vi.fn()
  composer.scrollIntoView = scroll
  chooseLastParagraph()
  fireEvent.click(screen.getByRole('button',{name:'更简洁'}))
  expect(composer).toHaveFocus()
  expect(composer.selectionStart).toBe(composer.value.length)
  expect(scroll).toHaveBeenCalledWith({block:'nearest',behavior:'auto'})
  expect(send).not.toHaveBeenCalled()
  await waitFor(() => expect(screen.getByRole('button',{name:'发送'})).toBeEnabled())
  fireEvent.click(screen.getByRole('button',{name:'发送'}))
  await waitFor(() => expect(send).toHaveBeenCalledWith('w','s',expect.stringContaining('更简洁'),'writing',expect.any(String),{
    expectedUpdatedAt:'v1',selection,readerReference:{simulationId:'run',stage:'interview',messageId:'reply',interviewId:'i'},
  },emptyReferences))
})

it('lets a feedback-only request discuss changes without inventing a selected range', async () => {
  vi.spyOn(contentCollaborationApi,'create').mockResolvedValue(session)
  const send = vi.spyOn(contentCollaborationApi,'send').mockResolvedValue(session)
  render(<CreatorCanvasPage {...props} readerFeedback={feedback} />)
  fireEvent.click(screen.getByRole('button',{name:'和助手讨论'}))
  await waitFor(() => expect(screen.getByRole('button',{name:'发送'})).toBeEnabled())
  fireEvent.click(screen.getByRole('button',{name:'发送'}))
  await waitFor(() => expect(send).toHaveBeenCalledTimes(1))
  expect(send.mock.calls[0][5]).toEqual({expectedUpdatedAt:'v1',readerReference:focus.readerReference})
})

it('does not keep sending the reference after the author removes it', async () => {
  vi.spyOn(contentCollaborationApi,'create').mockResolvedValue(session)
  const send = vi.spyOn(contentCollaborationApi,'send').mockResolvedValue(session)
  render(<CreatorCanvasPage {...props} readerFeedback={feedback} />)
  fireEvent.click(screen.getByRole('button',{name:'移除引用'}))
  fireEvent.change(screen.getByLabelText('给创作助手的消息'),{target:{value:'再聊一个方向'}})
  await waitFor(() => expect(screen.getByRole('button',{name:'发送'})).toBeEnabled())
  fireEvent.click(screen.getByRole('button',{name:'发送'}))
  await waitFor(() => expect(send).toHaveBeenCalledTimes(1))
  expect(send).toHaveBeenCalledWith('w','s','再聊一个方向','writing',expect.any(String),undefined,emptyReferences)
})

it('shows before/after, changes only the selected duplicate, and requires manual save', async () => {
  reopen()
  const save = vi.spyOn(topicApi,'update')
  render(<CreatorCanvasPage {...props} onRetestCreated={vi.fn()} />)
  fireEvent.click(await screen.findByRole('button',{name:'对比并修改这一段'}))
  expect(screen.getByLabelText('写作建议预览')).toHaveFocus()
  expect(screen.getByText('修改前')).toBeInTheDocument()
  expect(screen.queryByLabelText('建议放入方式')).not.toBeInTheDocument()
  screen.getByLabelText('编辑写作建议').focus()
  fireEvent.change(screen.getByLabelText('编辑写作建议'),{target:{value:'我认可的新写法。'}})
  expect(screen.getByLabelText('编辑写作建议')).toHaveFocus()
  fireEvent.click(screen.getByRole('button',{name:'只替换这一段'}))
  expect(screen.getByLabelText('创作正文')).toHaveValue('开头🙂重复。\n中间。\n我认可的新写法。结尾')
  expect(save).not.toHaveBeenCalled()
  expect(screen.getByRole('button',{name:'用同组读者复测'})).toBeDisabled()
})

it('rejects old candidates when the author edited while waiting for the model', async () => {
  let resolve!: (value: CollaborationSession) => void
  const pending = new Promise<CollaborationSession>(yes => {resolve = yes})
  vi.spyOn(contentCollaborationApi,'create').mockResolvedValue(session)
  const send = vi.spyOn(contentCollaborationApi,'send').mockReturnValue(pending)
  render(<CreatorCanvasPage {...props} />)
  chooseLastParagraph(); fireEvent.click(screen.getByRole('button',{name:'把观点讲清楚'}))
  await waitFor(() => expect(screen.getByRole('button',{name:'发送'})).toBeEnabled())
  fireEvent.click(screen.getByRole('button',{name:'发送'}))
  await waitFor(() => expect(send).toHaveBeenCalledTimes(1))
  screen.getByLabelText('创作正文').focus()
  fireEvent.change(screen.getByLabelText('创作正文'),{target:{value:body + '等待时的新结尾。'}})
  await act(async () => resolve(suggestion))
  expect(screen.getByLabelText('创作正文')).toHaveFocus()
  fireEvent.click(screen.getByRole('button',{name:'对比并修改这一段'}))
  expect(screen.getByRole('alert')).toHaveTextContent('依据的稿件已变化')
  expect(screen.getByLabelText('创作正文')).toHaveValue(body + '等待时的新结尾。')
  expect(screen.queryByRole('button',{name:'只替换这一段'})).not.toBeInTheDocument()
})

it('keeps later edits made during local preview and clears a removed reader reference', async () => {
  reopen()
  render(<CreatorCanvasPage {...props} readerFeedback={feedback} />)
  fireEvent.click(await screen.findByRole('button',{name:'对比并修改这一段'}))
  fireEvent.click(screen.getByRole('button',{name:'移除引用'}))
  expect(screen.queryByLabelText('带来的读者意见')).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('创作正文'),{target:{value:'我又自己改了'}})
  fireEvent.click(screen.getByRole('button',{name:'只替换这一段'}))
  expect(screen.getByRole('alert')).toHaveTextContent('预览期间画布有新修改')
  expect(screen.getByLabelText('创作正文')).toHaveValue('我又自己改了')
})

it('ignores feedback from a different workspace or topic', async () => {
  const consumed = vi.fn()
  render(<CreatorCanvasPage {...props} readerFeedback={{...feedback,workspaceId:'other'}} onReaderFeedbackConsumed={consumed} />)
  await waitFor(() => expect(contentCollaborationApi.list).toHaveBeenCalled())
  expect(screen.queryByText(feedback.quote)).not.toBeInTheDocument()
  expect(consumed).not.toHaveBeenCalled()
})

it('moves between the real narrow-screen composer and preview without focusing a hidden pane', async () => {
  vi.stubGlobal('matchMedia', vi.fn(() => ({matches:true,addEventListener:vi.fn(),removeEventListener:vi.fn()})))
  reopen()
  render(<CreatorCanvasPage {...props} />)
  await screen.findByRole('button',{name:'对比并修改这一段'})
  fireEvent.click(screen.getByRole('tab',{name:'稿件'}))
  chooseLastParagraph()
  fireEvent.click(screen.getByRole('button',{name:'更简洁'}))
  expect(screen.getByRole('tab',{name:'对话'})).toHaveAttribute('aria-selected','true')
  expect(screen.getByLabelText('给创作助手的消息')).toBeVisible()
  expect(screen.getByLabelText('给创作助手的消息')).toHaveFocus()
  fireEvent.click(screen.getByRole('button',{name:'对比并修改这一段'}))
  expect(screen.getByRole('tab',{name:'稿件'})).toHaveAttribute('aria-selected','true')
  expect(screen.getByLabelText('写作建议预览')).toHaveFocus()
  expect(screen.getByLabelText('给创作助手的消息')).not.toBeVisible()
  fireEvent.click(screen.getByRole('button',{name:'关闭预览'}))
  expect(screen.getByLabelText('创作正文')).toHaveFocus()
  expect(screen.getByLabelText('创作正文')).toHaveValue(body)
})
