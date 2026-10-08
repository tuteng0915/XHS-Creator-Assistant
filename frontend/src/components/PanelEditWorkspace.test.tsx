import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react'
import {afterEach, expect, it, vi} from 'vitest'
import {agentConversationApi, panelEditApi, simulationRunApi} from '../api'
import type {PanelEditProposal} from '../panelEdits'
import type {SimulationRun, Topic} from '../types'
import {PanelEditWorkspace} from './PanelEditWorkspace'
import {CreatorCanvasPage} from './CreatorCanvasPage'
import {contentCollaborationApi} from '../contentCollaboration'

afterEach(() => {cleanup(); vi.restoreAllMocks()})
const before = {title:'原标题', body:'🌱原句。\n原句。结尾。', updatedAt:'2026-10-05T00:00:00+00:00'}
const topic = {id:'t',workspaceId:'w',...before,status:'candidate',generatedSnapshot:{},angle:'',associatedPainPoint:'',whyItFits:'',sourceAnalysisRunId:null,sourceWorkflow:'manual',createdAt:before.updatedAt} as Topic
const card = {id:'f1',kind:'rewrite',sourceType:'editor_optional',sourceMessageIds:[],priority:'optional',observation:'第二句更具体',reason:'补充表达',suggestedText:'新句。',target:{field:'body',quote:'原句。',occurrence:2,start:5,end:8,coordinateSystem:'unicode_code_points',contentHash:'hash'}}
const run = {id:'r',workspaceId:'w',topicId:'t',draftId:null,status:'completed',createdAt:before.updatedAt,inputSnapshot:{panelTask:{protocolVersion:'panel/v1'},topic:{topicId:'t',...before},targetContentHash:'hash'},personaDefinitions:[],reactionResults:[],debateResults:[],synthesis:{editorFeedback:[card],editorFeedbackValidation:{status:'validated'}}} as unknown as SimulationRun
const proposal: PanelEditProposal = {id:'p',workspaceId:'w',simulationId:'r',topicId:'t',status:'pending',freshness:'current',snapshot:{version:'panel-edit/v1',feedback:card,before,proposed:{title:before.title,body:'🌱原句。\n新句。结尾。'},edit:{field:'body',start:5,end:8,operation:'replace',text:'新句。'}},receipt:{},createdAt:before.updatedAt,updatedAt:before.updatedAt}
const applied: PanelEditProposal = {...proposal,status:'applied',receipt:{before,after:{...proposal.snapshot.proposed,updatedAt:'2026-10-05T00:00:01+00:00'}}}
const undone: PanelEditProposal = {...applied,status:'undone',undoReceipt:{before:applied.receipt.after,after:{...before,updatedAt:'2026-10-05T00:00:02+00:00'},undoneAt:'2026-10-05T00:00:02+00:00'}}
function deferred<T>() {let resolve!:(value:T)=>void; const promise = new Promise<T>(yes => {resolve=yes}); return {promise,resolve}}
function setup() {
  vi.spyOn(contentCollaborationApi,'list').mockResolvedValue([])
  vi.spyOn(agentConversationApi,'list').mockResolvedValue([])
  return {
    get:vi.spyOn(simulationRunApi,'get').mockResolvedValue(run),
    list:vi.spyOn(panelEditApi,'list').mockResolvedValue([]),
    create:vi.spyOn(panelEditApi,'create').mockResolvedValue(proposal),
    apply:vi.spyOn(panelEditApi,'apply').mockResolvedValue(applied),
    undo:vi.spyOn(panelEditApi,'undo').mockResolvedValue(undone),
    reject:vi.spyOn(panelEditApi,'reject').mockResolvedValue({...proposal,status:'rejected'}),
  }
}
const props = {workspaceId:'w',topic,runs:[run],blocked:'',onApply:vi.fn(async () => applied)}

it('starts material input empty and records author text only after explicit preview', async () => {
  const api = setup(), onApply = vi.fn(async () => applied)
  const materialCard = {...card,kind:'add_material',materialRequests:['哪个练习让你开口？'],suggestedText:'模型猜测的课堂经历'}
  api.get.mockResolvedValue({...run,synthesis:{...run.synthesis,editorFeedback:[materialCard]}})
  render(<PanelEditWorkspace {...props} onApply={onApply}/>)
  await open()
  expect(screen.queryByText('可参考的表达')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'补充素材'}))
  expect(screen.getByRole('dialog')).toHaveAccessibleName('补充你的素材')
  expect(screen.getByLabelText('作者补充的正文')).toHaveValue('')
  fireEvent.change(screen.getByLabelText('修改方式'),{target:{value:'insert_after'}})
  expect(screen.getByRole('button',{name:'保存提案并预览'})).toBeDisabled()
  fireEvent.change(screen.getByLabelText('作者补充的正文'),{target:{value:'  '}})
  expect(screen.getByRole('button',{name:'保存提案并预览'})).toBeDisabled()
  fireEvent.change(screen.getByLabelText('作者补充的正文'),{target:{value:'我先向邻座问了一个问题。'}})
  fireEvent.click(screen.getByRole('button',{name:'保存提案并预览'}))
  await screen.findByRole('button',{name:'确认采用'})
  expect(api.create.mock.calls[0][2]).toMatchObject({operation:'insert_after',text:'我先向邻座问了一个问题。',authorMaterial:'我先向邻座问了一个问题。'})
  expect(onApply).not.toHaveBeenCalled()
})

it('keeps old material proposals readable without offering unconfirmed adoption', async () => {
  const api = setup()
  api.list.mockResolvedValue([{...proposal,snapshot:{...proposal.snapshot,feedback:{...card,kind:'add_material'}}}])
  render(<PanelEditWorkspace {...props}/>)
  await open()
  fireEvent.click(within(screen.getByRole('region',{name:'已保存的改稿提案'})).getByRole('button'))
  expect(screen.getByRole('button',{name:'确认采用'})).toBeDisabled()
  expect(screen.getByText(/这份旧提案未记录作者素材/)).toBeVisible()
  expect(screen.getByRole('button',{name:'不采用这份提案'})).toBeEnabled()
})

it('preserves supplied material after failed preview and reuses its request key', async () => {
  const api = setup()
  api.get.mockResolvedValue({...run,synthesis:{...run.synthesis,editorFeedback:[{...card,kind:'add_material',materialRequests:['请补一个例子']}]}})
  api.create.mockRejectedValueOnce(new Error('网络断开'))
  render(<PanelEditWorkspace {...props}/>)
  await open()
  fireEvent.click(screen.getByRole('button',{name:'补充素材'}))
  fireEvent.change(screen.getByLabelText('修改方式'),{target:{value:'replace'}})
  fireEvent.change(screen.getByLabelText('作者补充的正文'),{target:{value:'真实例子'}})
  fireEvent.click(screen.getByRole('button',{name:'保存提案并预览'}))
  await screen.findByRole('alert')
  expect(screen.getByLabelText('作者补充的正文')).toHaveValue('真实例子')
  fireEvent.click(screen.getByRole('button',{name:'保存提案并预览'}))
  await screen.findByRole('button',{name:'确认采用'})
  expect(api.create.mock.calls[0][2].requestKey).toBe(api.create.mock.calls[1][2].requestKey)
})
async function open() {
  fireEvent.click(screen.getByRole('button',{name:'试读反馈改稿'}))
  await screen.findByRole('heading',{name:'第二句更具体'})
  fireEvent.click(screen.getByText('其他可选建议（1）'))
}
async function preview() {
  await open()
  fireEvent.click(screen.getByRole('button',{name:'查看改写'}))
  fireEvent.change(screen.getByLabelText('修改方式'),{target:{value:'replace'}})
  fireEvent.click(screen.getByRole('button',{name:'保存提案并预览'}))
  await screen.findByRole('button',{name:'确认采用'})
}

it('requires explicit operation, previews full text, and only applies after confirmation',async () => {
  const api = setup(), onApply = vi.fn(async () => applied)
  render(<PanelEditWorkspace {...props} onApply={onApply}/>)
  await open()
  fireEvent.click(screen.getByRole('button',{name:'查看改写'}))
  expect(screen.getByRole('button',{name:'保存提案并预览'})).toBeDisabled()
  fireEvent.change(screen.getByLabelText('修改方式'),{target:{value:'insert_after'}})
  fireEvent.change(screen.getByLabelText('建议文字'),{target:{value:'补一句'}})
  fireEvent.click(screen.getByRole('button',{name:'保存提案并预览'}))
  await screen.findByRole('button',{name:'确认采用'})
  expect(api.create).toHaveBeenCalledWith('w','r',expect.objectContaining({operation:'insert_after',text:'补一句',feedbackId:'f1',expectedUpdatedAt:before.updatedAt}))
  expect(onApply).not.toHaveBeenCalled()
  expect(within(screen.getByRole('dialog')).getByText(before.body, {normalizer: value => value})).toBeVisible()
  fireEvent.click(screen.getByRole('button',{name:'确认采用'}))
  await waitFor(() => expect(onApply).toHaveBeenCalledOnce())
  expect(await screen.findByText(/已采用，回执已保存/)).toBeVisible()
})

it('keeps request identity across uncertain creation failures and permits editing after failure',async () => {
  const api = setup()
  api.create.mockRejectedValueOnce(new Error('连接中断'))
  render(<PanelEditWorkspace {...props}/>)
  await open()
  fireEvent.click(screen.getByRole('button',{name:'查看改写'}))
  fireEvent.change(screen.getByLabelText('修改方式'),{target:{value:'replace'}})
  fireEvent.click(screen.getByRole('button',{name:'保存提案并预览'}))
  await screen.findByRole('alert')
  expect(screen.getByLabelText('建议文字')).toHaveValue('新句。')
  fireEvent.click(screen.getByRole('button',{name:'保存提案并预览'}))
  await screen.findByRole('button',{name:'确认采用'})
  expect(api.create.mock.calls[0][2].requestKey).toBe(api.create.mock.calls[1][2].requestKey)
})

it('restores pending proposals on remount and rejects without applying',async () => {
  const api = setup(), onApply = vi.fn(async () => applied)
  api.list.mockResolvedValue([proposal])
  const page = render(<PanelEditWorkspace {...props} onApply={onApply}/>)
  await open()
  page.unmount()
  render(<PanelEditWorkspace {...props} onApply={onApply}/>)
  fireEvent.click(screen.getByRole('button',{name:'试读反馈改稿'}))
  const list = await screen.findByRole('region',{name:'已保存的改稿提案'})
  fireEvent.click(within(list).getByRole('button'))
  fireEvent.click(screen.getByRole('button',{name:'不采用这份提案'}))
  expect(await screen.findByText(/未采用，原稿未因这份提案改变/)).toBeVisible()
  expect(onApply).not.toHaveBeenCalled()
  expect(api.create).not.toHaveBeenCalled()
})

it.each(['dirty','stale'] as const)('blocks confirmation of a %s draft but preserves the proposal',async kind => {
  const api = setup(), onApply=vi.fn(async () => applied)
  const page=render(<PanelEditWorkspace {...props} onApply={onApply}/>)
  await preview()
  page.rerender(<PanelEditWorkspace {...props} onApply={onApply} blocked={kind==='dirty'?'有未保存的修改':''} topic={kind==='stale'?{...topic,body:'新稿'}:topic}/>)
  expect(screen.getByRole('button',{name:'确认采用'})).toBeDisabled()
  expect(onApply).not.toHaveBeenCalled()
  expect(api.reject).not.toHaveBeenCalled()
})

it('does not display a delayed response after changing the selected run',async () => {
  const api = setup(), late=deferred<SimulationRun>()
  api.get.mockReturnValueOnce(late.promise).mockResolvedValue({...run,id:'r2',synthesis:{}})
  render(<PanelEditWorkspace {...props} runs={[run,{...run,id:'r2'}]}/>)
  fireEvent.click(screen.getByRole('button',{name:'试读反馈改稿'}))
  fireEvent.change(screen.getByLabelText('改稿依据的试读记录'),{target:{value:'r2'}})
  await screen.findByText(/这次记录没有可直接改稿/)
  await act(async () => late.resolve(run))
  expect(screen.queryByText('第二句更具体')).not.toBeInTheDocument()
})

it('shows load failure and recovers by reading again without creating a proposal',async () => {
  const api=setup(); api.list.mockRejectedValueOnce(new Error('读取失败'))
  render(<PanelEditWorkspace {...props}/>)
  fireEvent.click(screen.getByRole('button',{name:'试读反馈改稿'}))
  await screen.findByRole('alert')
  fireEvent.click(screen.getByRole('button',{name:'刷新提案'}))
  await screen.findByText('第二句更具体')
  expect(api.create).not.toHaveBeenCalled()
})

function canvas(onUpdated = vi.fn(), selected = topic) {
  return <CreatorCanvasPage workspaceId={selected.workspaceId} topic={selected} topics={[selected]} simulationRuns={[run]} agentId="a" onSelect={vi.fn()} onUpdated={onUpdated}/>
}
it('applies through the canvas and preserves unrelated content without a model call',async () => {
  const api=setup(),onUpdated=vi.fn()
  render(canvas(onUpdated))
  await preview()
  fireEvent.click(screen.getByRole('button',{name:'确认采用'}))
  await waitFor(() => expect(screen.getByLabelText('创作正文')).toHaveValue(proposal.snapshot.proposed.body))
  expect(onUpdated).toHaveBeenCalledWith(expect.objectContaining({id:'t',title:before.title,updatedAt:applied.receipt.after!.updatedAt}))
  expect(api.apply).toHaveBeenCalledOnce()
})

it.each(['edit','switch'] as const)('protects the canvas on %s during confirmation and prevents duplicate apply',async change => {
  const api=setup(),onUpdated=vi.fn(),pending=deferred<PanelEditProposal>()
  api.apply.mockReturnValue(pending.promise)
  const page=render(canvas(onUpdated))
  await preview()
  const button=screen.getByRole('button',{name:'确认采用'})
  act(() => {fireEvent.click(button); fireEvent.click(button)})
  expect(api.apply).toHaveBeenCalledOnce()
  if(change==='switch') page.rerender(canvas(onUpdated,{...topic,id:'next',workspaceId:'another'}))
  fireEvent.change(screen.getByLabelText('创作正文'),{target:{value:'等待时新写的文字'}})
  await act(async () => pending.resolve(applied))
  expect(screen.getByLabelText('创作正文')).toHaveValue('等待时新写的文字')
  expect(onUpdated).not.toHaveBeenCalled()
  if(change==='edit') expect(screen.getByText(/等待期间你又编辑/)).toBeVisible()
})

it('keeps the preview and canvas after apply conflict',async () => {
  const api=setup(); api.apply.mockRejectedValue(new Error('稿件已有新编辑'))
  render(canvas())
  await preview()
  fireEvent.click(screen.getByRole('button',{name:'确认采用'}))
  await screen.findByText(/稿件已有新编辑/)
  expect(screen.getByLabelText('创作正文')).toHaveValue(before.body)
  expect(screen.getByRole('button',{name:'确认采用'})).toBeEnabled()
})

it('uses a new request identity when preparing the same wording after a known rejection',async () => {
  const api=setup()
  render(<PanelEditWorkspace {...props}/>)
  await preview()
  fireEvent.click(screen.getByRole('button',{name:'不采用这份提案'}))
  await screen.findByText(/未采用，原稿未因这份提案改变/)
  fireEvent.click(screen.getByRole('button',{name:'关闭'}))
  fireEvent.click(screen.getByRole('button',{name:'查看改写'}))
  fireEvent.change(screen.getByLabelText('修改方式'),{target:{value:'replace'}})
  fireEvent.click(screen.getByRole('button',{name:'保存提案并预览'}))
  await screen.findByRole('button',{name:'确认采用'})
  expect(api.create).toHaveBeenCalledTimes(2)
  expect(api.create.mock.calls[0][2].requestKey).not.toBe(api.create.mock.calls[1][2].requestKey)
})

async function adopt() {
  await preview()
  fireEvent.click(screen.getByRole('button',{name:'确认采用'}))
  await screen.findByRole('button',{name:'撤销这次采用'})
}

it('requires a second confirmation to undo, restores the canvas and keeps the original comparison',async () => {
  const api=setup(),onUpdated=vi.fn()
  render(canvas(onUpdated))
  await adopt()
  fireEvent.click(screen.getByRole('button',{name:'撤销这次采用'}))
  expect(api.undo).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button',{name:'保留当前版本'}))
  expect(api.undo).not.toHaveBeenCalled()
  expect(screen.getByLabelText('创作正文')).toHaveValue(proposal.snapshot.proposed.body)
  fireEvent.click(screen.getByRole('button',{name:'撤销这次采用'}))
  fireEvent.click(screen.getByRole('button',{name:'确认恢复修改前内容'}))
  await screen.findByText(/已撤销，撤销时恢复了/)
  expect(screen.getByLabelText('创作正文')).toHaveValue(before.body)
  expect(onUpdated).toHaveBeenLastCalledWith(expect.objectContaining({updatedAt:undone.undoReceipt!.after!.updatedAt}))
  expect(screen.getByText('当时采用后')).toBeVisible()
  expect(screen.queryByRole('button',{name:'撤销这次采用'})).not.toBeInTheDocument()
  expect(api.undo).toHaveBeenCalledOnce()
})

it.each(['dirty','stale'] as const)('blocks undo with %s content without losing the receipt',async kind => {
  const api=setup(); api.list.mockResolvedValue([applied])
  const appliedTopic={...topic,...applied.receipt.after!}
  render(<PanelEditWorkspace {...props} topic={kind==='stale'?{...appliedTopic,body:'后续编辑'}:appliedTopic}
    blocked={kind==='dirty'?'有未保存修改':''} onUndo={p => panelEditApi.undo('w',p.id)}/>)
  fireEvent.click(screen.getByRole('button',{name:'试读反馈改稿'}))
  const list=await screen.findByRole('region',{name:'已保存的改稿提案'})
  fireEvent.click(within(list).getByRole('button'))
  expect(screen.getByRole('button',{name:'撤销这次采用'})).toBeDisabled()
  expect(api.undo).not.toHaveBeenCalled()
})

it.each(['edit','switch'] as const)('protects new %s while undo is in flight and ignores duplicate confirmation',async change => {
  const api=setup(),onUpdated=vi.fn(),pending=deferred<PanelEditProposal>()
  api.undo.mockReturnValue(pending.promise)
  const page=render(canvas(onUpdated))
  await adopt()
  onUpdated.mockClear()
  fireEvent.click(screen.getByRole('button',{name:'撤销这次采用'}))
  const button=screen.getByRole('button',{name:'确认恢复修改前内容'})
  act(() => {fireEvent.click(button);fireEvent.click(button)})
  expect(api.undo).toHaveBeenCalledOnce()
  if(change==='switch') page.rerender(canvas(onUpdated,{...topic,id:'next',workspaceId:'another'}))
  fireEvent.change(screen.getByLabelText('创作正文'),{target:{value:'撤销等待期间新写'}})
  await act(async () => pending.resolve(undone))
  expect(screen.getByLabelText('创作正文')).toHaveValue('撤销等待期间新写')
  expect(onUpdated).not.toHaveBeenCalled()
  if(change==='edit') expect(screen.getByText(/提案已撤销，但等待期间/)).toBeVisible()
})

it('keeps undo confirmation on failure and retries the same proposal',async () => {
  const api=setup();api.undo.mockRejectedValueOnce(new Error('连接中断'))
  render(canvas())
  await adopt()
  fireEvent.click(screen.getByRole('button',{name:'撤销这次采用'}))
  fireEvent.click(screen.getByRole('button',{name:'确认恢复修改前内容'}))
  await screen.findByRole('alert')
  expect(screen.getByLabelText('创作正文')).toHaveValue(proposal.snapshot.proposed.body)
  fireEvent.click(screen.getByRole('button',{name:'确认恢复修改前内容'}))
  await screen.findByText(/已撤销，撤销时恢复了/)
  expect(api.undo.mock.calls).toEqual([['w','p'],['w','p']])
})

it('loads an undone receipt without offering apply or undo again',async () => {
  const api=setup();api.list.mockResolvedValue([undone])
  render(<PanelEditWorkspace {...props} onUndo={async () => undone}/>)
  fireEvent.click(screen.getByRole('button',{name:'试读反馈改稿'}))
  const list=await screen.findByRole('region',{name:'已保存的改稿提案'})
  expect(list).toHaveTextContent('已撤销')
  fireEvent.click(within(list).getByRole('button'))
  expect(screen.getByText(/已撤销，撤销时恢复了/)).toBeVisible()
  expect(screen.queryByRole('button',{name:'确认采用'})).not.toBeInTheDocument()
  expect(screen.queryByRole('button',{name:'撤销这次采用'})).not.toBeInTheDocument()
})
