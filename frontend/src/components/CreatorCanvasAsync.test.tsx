import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { agentConversationApi, topicApi } from '../api'
import { contentCollaborationApi } from '../contentCollaboration'
import type { CollaborationSession } from '../contentCollaboration'
import type { Topic } from '../types'
import { CreatorCanvasPage } from './CreatorCanvasPage'

afterEach(() => {cleanup();vi.restoreAllMocks()})
const topic: Topic = {id:'t',workspaceId:'w',title:'原题',body:'原文',angle:'',associatedPainPoint:'',whyItFits:'',generatedSnapshot:{},sourceAnalysisRunId:null,sourceWorkflow:'manual',status:'candidate',createdAt:'v1',updatedAt:'v1'}
const session: CollaborationSession = {id:'s',workspaceId:'w',title:'协作',status:'active',executionStatus:'waiting_creator',contextTarget:{assetType:'topic',assetId:'t'},failureCode:'',failureDetail:'',createdAt:'',updatedAt:'',messages:[],runs:[]}
function deferred<T>() {let resolve!:(value:T)=>void, reject!:(error:Error)=>void; const promise=new Promise<T>((yes,no)=>{resolve=yes;reject=no}); return {promise,resolve,reject}}
function setup() {
  vi.spyOn(agentConversationApi,'list').mockResolvedValue([])
  vi.spyOn(contentCollaborationApi,'list').mockResolvedValue([])
  return {save:vi.spyOn(topicApi,'update').mockResolvedValue({...topic,updatedAt:'v2'}),
    create:vi.spyOn(contentCollaborationApi,'create').mockResolvedValue(session),
    send:vi.spyOn(contentCollaborationApi,'send').mockResolvedValue(session)}
}
const props={workspaceId:'w',topic,topics:[topic],onSelect:vi.fn()}
async function submit() {
  fireEvent.change(screen.getByLabelText('给创作助手的消息'),{target:{value:'修改开头'}})
  await waitFor(()=>expect(screen.getByRole('button',{name:'发送'})).toBeEnabled())
  fireEvent.click(screen.getByRole('button',{name:'发送'}))
}

it.each(['save','create','reply'] as const)('stops the %s continuation after switching accounts/topics', async stage => {
  const api=setup(), onUpdated=vi.fn(), pendingTopic=deferred<Topic>(), pendingSession=deferred<CollaborationSession>()
  if(stage==='save') api.save.mockReturnValue(pendingTopic.promise)
  if(stage==='create') api.create.mockReturnValue(pendingSession.promise)
  if(stage==='reply') api.send.mockReturnValue(pendingSession.promise)
  const {rerender}=render(<CreatorCanvasPage {...props} onUpdated={onUpdated} />)
  if(stage==='save') fireEvent.change(screen.getByLabelText('创作正文'),{target:{value:'发送前的修改'}})
  await submit()
  await waitFor(()=>expect(stage==='save'?api.save:stage==='create'?api.create:api.send).toHaveBeenCalledTimes(1))
  onUpdated.mockClear()
  rerender(<CreatorCanvasPage {...props} workspaceId="another" topic={{...topic,id:'next',workspaceId:'another'}} onUpdated={onUpdated} />)
  fireEvent.change(screen.getByLabelText('创作正文'),{target:{value:'新选题未保存稿'}})
  fireEvent.change(screen.getByLabelText('给创作助手的消息'),{target:{value:'新消息'}})
  await act(async()=>{if(stage==='save') pendingTopic.resolve({...topic,body:'迟到的旧稿'}); else pendingSession.resolve(session)})
  expect(onUpdated).not.toHaveBeenCalled()
  expect(screen.getByLabelText('创作正文')).toHaveValue('新选题未保存稿')
  expect(screen.getByLabelText('给创作助手的消息')).toHaveValue('新消息')
  if(stage==='save') expect(api.create).not.toHaveBeenCalled()
  if(stage!=='reply') expect(api.send).not.toHaveBeenCalled()
})

it.each(['save','create'] as const)('preserves local edits made during %s and stops before model submission', async stage => {
  const api=setup(), saved=deferred<Topic>(), created=deferred<CollaborationSession>()
  if(stage==='save') api.save.mockReturnValue(saved.promise); else api.create.mockReturnValue(created.promise)
  render(<CreatorCanvasPage {...props} onUpdated={vi.fn()} />)
  if(stage==='save') fireEvent.change(screen.getByLabelText('创作正文'),{target:{value:'要保存的版本'}})
  await submit()
  await waitFor(()=>expect(stage==='save'?api.save:api.create).toHaveBeenCalledTimes(1))
  fireEvent.change(screen.getByLabelText('创作正文'),{target:{value:'准备中又改的新版本'}})
  await act(async()=>{if(stage==='save') saved.resolve({...topic,body:'要保存的版本',updatedAt:'v2'}); else created.resolve(session)})
  expect(screen.getByLabelText('创作正文')).toHaveValue('准备中又改的新版本')
  expect(screen.getByText('有未保存修改')).toBeInTheDocument()
  expect(api.send).not.toHaveBeenCalled()
})

it('reuses an uncertain request key and preserves newer typed messages on success', async () => {
  const api=setup(); api.send.mockRejectedValueOnce(new Error('连接中断'))
  render(<CreatorCanvasPage {...props} onUpdated={vi.fn()} />)
  await submit(); await screen.findByText('连接中断')
  expect(screen.getByLabelText('给创作助手的消息')).toHaveValue('修改开头')
  const pending=deferred<CollaborationSession>(); api.send.mockReturnValueOnce(pending.promise)
  fireEvent.click(screen.getByRole('button',{name:'发送'}))
  await waitFor(()=>expect(api.send).toHaveBeenCalledTimes(2))
  fireEvent.change(screen.getByLabelText('给创作助手的消息'),{target:{value:'下一条想法'}})
  fireEvent.change(screen.getByLabelText('创作正文'),{target:{value:'等待时的新正文'}})
  await act(async()=>pending.resolve(session))
  expect(api.send.mock.calls[0][4]).toBe(api.send.mock.calls[1][4])
  expect(screen.getByLabelText('给创作助手的消息')).toHaveValue('下一条想法')
  expect(screen.getByLabelText('创作正文')).toHaveValue('等待时的新正文')
})

it('ignores duplicate form submission in the same turn',async()=>{
  const api=setup(),pending=deferred<CollaborationSession>(); api.create.mockReturnValue(pending.promise)
  render(<CreatorCanvasPage {...props} onUpdated={vi.fn()} />)
  fireEvent.change(screen.getByLabelText('给创作助手的消息'),{target:{value:'修改开头'}})
  await waitFor(()=>expect(screen.getByRole('button',{name:'发送'})).toBeEnabled())
  const form=screen.getByLabelText('给创作助手的消息').closest('form')!
  act(()=>{fireEvent.submit(form);fireEvent.submit(form)})
  await waitFor(()=>expect(api.create).toHaveBeenCalledTimes(1))
  await act(async()=>pending.resolve(session))
  expect(api.send).toHaveBeenCalledTimes(1)
})
