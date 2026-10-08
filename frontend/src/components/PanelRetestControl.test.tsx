import {act, cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react'
import {afterEach, expect, it, vi} from 'vitest'
import {agentConversationApi, panelEditApi, simulationRunApi, topicApi} from '../api'
import type {PanelRetestPreview, SimulationRun, Topic} from '../types'
import {PanelRetestControl} from './PanelRetestControl'
import {CreatorCanvasPage} from './CreatorCanvasPage'
import {contentCollaborationApi} from '../contentCollaboration'

afterEach(() => {cleanup(); vi.restoreAllMocks(); sessionStorage.clear()})
const timestamp = '2026-10-05T00:00:01Z'
const topic = {id:'t',workspaceId:'w',title:'新版标题',body:'新版正文🌱',updatedAt:timestamp,status:'candidate',generatedSnapshot:{}} as Topic
const preview: PanelRetestPreview = {workspaceId:'w',parentSimulationId:'old',topicId:'t',title:topic.title,body:topic.body!,expectedUpdatedAt:timestamp,mode:'live',panelTask:{protocolVersion:'panel/v1',readingMode:'guided',focusQuestions:['第一步清楚吗？'],discussionEnabled:false},readers:[{id:'p',name:'行动派',profile:'条件清楚就愿意动手'}],limitations:['模型版本尚未配对核验']}
const old = {id:'old',workspaceId:'w',topicId:'t',draftId:null,status:'completed',createdAt:timestamp,inputSnapshot:{topic:{title:'旧标题',body:'旧正文',updatedAt:'2026-10-05T00:00:00Z'}},synthesis:{}} as unknown as SimulationRun
const child = {...old,id:'new',parentSimulationId:'old',status:'pending',inputSnapshot:{topic:{title:topic.title,body:topic.body,updatedAt:timestamp}}} as SimulationRun
const props = {workspaceId:'w',runId:'old',topic,blocked:''}
function deferred<T>() {let resolve!:(v:T)=>void; const promise = new Promise<T>(yes => {resolve=yes}); return {promise,resolve}}
function setup() {
  vi.spyOn(contentCollaborationApi,'list').mockResolvedValue([])
  vi.spyOn(agentConversationApi,'list').mockResolvedValue([])
  vi.spyOn(simulationRunApi,'get').mockResolvedValue(old)
  vi.spyOn(panelEditApi,'list').mockResolvedValue([])
  return {preview:vi.spyOn(simulationRunApi,'previewRetest').mockResolvedValue(preview),
    create:vi.spyOn(simulationRunApi,'createRetest').mockResolvedValue(child),
    save:vi.spyOn(topicApi,'update').mockResolvedValue(topic)}
}
async function open() {
  fireEvent.click(screen.getByRole('button',{name:'用同组读者复测'}))
  await screen.findByRole('button',{name:'确认开始复测'})
}

it('previews people, task and saved text without creating; supports cancel and explicit confirmation',async () => {
  const api=setup(),create=vi.fn().mockResolvedValue({run:child,canNavigate:true}),done=vi.fn()
  render(<PanelRetestControl {...props} onCreate={create} onCreated={done}/>)
  await open()
  expect(screen.getByText('1. 行动派')).toBeVisible()
  expect(screen.getByText('第一步清楚吗？')).toBeVisible()
  expect(screen.getByText(/本次已保存稿件：新版标题/)).toBeVisible()
  expect(create).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button',{name:'暂不复测'}))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  await open()
  fireEvent.click(screen.getByRole('button',{name:'确认开始复测'}))
  await waitFor(() => expect(done).toHaveBeenCalledWith(child,true))
  expect(create).toHaveBeenCalledWith('old',expect.objectContaining({confirmed:true,expectedUpdatedAt:timestamp}))
  expect(api.preview).toHaveBeenCalledTimes(2)
})

it('reuses request identity after an uncertain response, including remount',async () => {
  setup(); const create=vi.fn().mockRejectedValueOnce(new Error('连接断开')).mockResolvedValue({run:child,canNavigate:true})
  const page=render(<PanelRetestControl {...props} onCreate={create} onCreated={vi.fn()}/>)
  await open(); fireEvent.click(screen.getByRole('button',{name:'确认开始复测'}))
  await screen.findByRole('alert')
  const key=create.mock.calls[0][1].requestKey
  page.unmount()
  render(<PanelRetestControl {...props} onCreate={create} onCreated={vi.fn()}/>)
  await open(); fireEvent.click(screen.getByRole('button',{name:'确认开始复测'}))
  await waitFor(() => expect(create).toHaveBeenCalledTimes(2))
  expect(create.mock.calls[1][1].requestKey).toBe(key)
})

it.each(['dirty','changed'] as const)('blocks confirmation when the draft becomes %s',async kind => {
  setup(); const create=vi.fn(), done=vi.fn()
  const page=render(<PanelRetestControl {...props} onCreate={create} onCreated={done}/>)
  await open()
  page.rerender(<PanelRetestControl {...props} onCreate={create} onCreated={done}
    blocked={kind === 'dirty' ? '请先保存' : ''} topic={kind === 'changed' ? {...topic,body:'变化'} : topic}/>)
  expect(screen.getByRole('button',{name:'确认开始复测'})).toBeDisabled()
  expect(create).not.toHaveBeenCalled()
})

it('shows server ineligibility and retries a read without creating',async () => {
  const api=setup(); api.preview.mockRejectedValueOnce(new Error('标题和正文尚未改变'))
  const create=vi.fn()
  render(<PanelRetestControl {...props} onCreate={create} onCreated={vi.fn()}/>)
  fireEvent.click(screen.getByRole('button',{name:'用同组读者复测'}))
  expect(await screen.findByRole('alert')).toHaveTextContent('尚未改变')
  await open()
  expect(create).not.toHaveBeenCalled()
})

it('ignores preview after unmount and rejects a wrong-workspace preview',async () => {
  const api=setup(),pending=deferred<PanelRetestPreview>()
  api.preview.mockReturnValueOnce(pending.promise)
  const page=render(<PanelRetestControl {...props} onCreate={vi.fn()} onCreated={vi.fn()}/>)
  fireEvent.click(screen.getByRole('button',{name:'用同组读者复测'})); page.unmount()
  await act(async () => pending.resolve(preview))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  api.preview.mockResolvedValue({...preview,workspaceId:'other'})
  render(<PanelRetestControl {...props} onCreate={vi.fn()} onCreated={vi.fn()}/>)
  fireEvent.click(screen.getByRole('button',{name:'用同组读者复测'}))
  expect(await screen.findByRole('alert')).toHaveTextContent('不一致')
})

function canvas(done=vi.fn(), selected=topic) {
  return <CreatorCanvasPage workspaceId={selected.workspaceId} topic={selected} topics={[selected]}
    simulationRuns={[old]} onSelect={vi.fn()} onUpdated={vi.fn()} onRetestCreated={done}/>
}
async function openCanvas() {
  fireEvent.click(screen.getByRole('button',{name:'试读反馈改稿'}))
  await screen.findByRole('button',{name:'用同组读者复测'})
  await waitFor(() => expect(screen.getByRole('button',{name:'用同组读者复测'})).toBeEnabled())
  await open()
}

it.each(['success','edit','switch'] as const)('creates once and protects canvas on %s during submission',async change => {
  const api=setup(), pending=deferred<SimulationRun>(), done=vi.fn()
  api.create.mockReturnValue(pending.promise)
  const page=render(canvas(done))
  await openCanvas()
  const button=screen.getByRole('button',{name:'确认开始复测'})
  act(() => {fireEvent.click(button); fireEvent.click(button)})
  expect(api.create).toHaveBeenCalledOnce()
  if (change === 'switch') page.rerender(canvas(done,{...topic,id:'another',workspaceId:'different'}))
  if (change !== 'success') fireEvent.change(screen.getByLabelText('创作正文'),{target:{value:'等待时新写的文字'}})
  await act(async () => pending.resolve(child))
  if (change === 'success') expect(done).toHaveBeenCalledWith(child,true)
  else {
    expect(screen.getByLabelText('创作正文')).toHaveValue('等待时新写的文字')
    if (change === 'switch') expect(done).not.toHaveBeenCalled()
    else expect(done).toHaveBeenCalledWith(child,false)
  }
  expect(api.save).not.toHaveBeenCalled()
})

it('never opens preview from an unsaved canvas',async () => {
  const api=setup()
  render(canvas())
  fireEvent.change(screen.getByLabelText('创作正文'),{target:{value:'未保存'}})
  fireEvent.click(screen.getByRole('button',{name:'试读反馈改稿'}))
  expect(await screen.findByRole('button',{name:'用同组读者复测'})).toBeDisabled()
  expect(api.preview).not.toHaveBeenCalled()
})
