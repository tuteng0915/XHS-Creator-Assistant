import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { agentConversationApi, topicApi } from '../api'
import type { AgentConversation, Topic } from '../types'
import { CreatorCanvasPage } from './CreatorCanvasPage'

afterEach(() => {cleanup();vi.restoreAllMocks()})
const topic: Topic = {id:'t',workspaceId:'w',title:'原题',body:'原文',angle:'',associatedPainPoint:'',whyItFits:'',generatedSnapshot:{},sourceAnalysisRunId:null,sourceWorkflow:'manual',status:'candidate',createdAt:'v1',updatedAt:'v1'}
const conversation: AgentConversation = {id:'c',workspaceId:'w',agentAssetId:'a',title:'对话',status:'active',executionStatus:'completed',contextTarget:{assetType:'topic',assetId:'t'},createdAt:'',updatedAt:'',messages:[]}
function deferred<T>() {
  let resolve!:(value:T)=>void, reject!:(error:Error)=>void
  const promise=new Promise<T>((yes,no)=>{resolve=yes;reject=no})
  return {promise,resolve,reject}
}
function setup() {
  vi.spyOn(agentConversationApi,'list').mockResolvedValue([])
  return {
    save:vi.spyOn(topicApi,'update').mockResolvedValue({...topic,updatedAt:'v2'}),
    create:vi.spyOn(agentConversationApi,'create').mockResolvedValue(conversation),
    send:vi.spyOn(agentConversationApi,'sendMessage').mockResolvedValue(conversation),
    get:vi.spyOn(topicApi,'get').mockResolvedValue({...topic,body:'AI 改稿',updatedAt:'v3'}),
  }
}
const props={workspaceId:'w',topic,topics:[topic],agentId:'a',onSelect:vi.fn()}
async function submit() {
  fireEvent.change(screen.getByLabelText('给创作助手的消息'),{target:{value:'修改开头'}})
  await waitFor(()=>expect(screen.getByRole('button',{name:'发送'})).toBeEnabled())
  fireEvent.click(screen.getByRole('button',{name:'发送'}))
}

it.each(['save','create','reply','get'] as const)('stops the %s continuation after switching accounts/topics', async stage=>{
  const api=setup(), onUpdated=vi.fn()
  const pendingTopic=deferred<Topic>(),pendingConversation=deferred<AgentConversation>()
  if(stage==='save') api.save.mockReturnValue(pendingTopic.promise)
  if(stage==='create') api.create.mockReturnValue(pendingConversation.promise)
  if(stage==='reply') api.send.mockReturnValue(pendingConversation.promise)
  if(stage==='get') api.get.mockReturnValue(pendingTopic.promise)
  const {rerender}=render(<CreatorCanvasPage {...props} onUpdated={onUpdated} />)
  if(stage==='save') fireEvent.change(screen.getByLabelText('创作正文'),{target:{value:'发送前的修改'}})
  await submit()
  await waitFor(()=>expect(stage==='save'?api.save:stage==='create'?api.create:stage==='reply'?api.send:api.get).toHaveBeenCalledTimes(1))
  onUpdated.mockClear()
  const next={...topic,id:'next',workspaceId:'another',title:'另一个账号的题'}
  rerender(<CreatorCanvasPage {...props} workspaceId="another" topic={next} onUpdated={onUpdated} />)
  fireEvent.change(screen.getByLabelText('创作正文'),{target:{value:'新选题未保存稿'}})
  fireEvent.change(screen.getByLabelText('给创作助手的消息'),{target:{value:'新消息'}})
  await act(async()=>{
    if(stage==='save'||stage==='get') pendingTopic.resolve({...topic,body:'迟到的旧稿'})
    else pendingConversation.resolve(conversation)
  })
  expect(onUpdated).not.toHaveBeenCalled()
  expect(screen.getByLabelText('创作正文')).toHaveValue('新选题未保存稿')
  expect(screen.getByLabelText('给创作助手的消息')).toHaveValue('新消息')
  if(stage==='save') expect(api.create).not.toHaveBeenCalled()
  if(stage==='save'||stage==='create') expect(api.send).not.toHaveBeenCalled()
  if(stage!=='get') expect(api.get).not.toHaveBeenCalled()
})

it('does not fetch a stale conversation after the list returns to an unmounted canvas',async()=>{
  const pending=deferred<AgentConversation[]>()
  vi.spyOn(agentConversationApi,'list').mockReturnValueOnce(pending.promise).mockResolvedValue([])
  const get=vi.spyOn(agentConversationApi,'get').mockResolvedValue(conversation)
  const {rerender}=render(<CreatorCanvasPage {...props} onUpdated={vi.fn()} />)
  rerender(<CreatorCanvasPage {...props} topic={{...topic,id:'next'}} onUpdated={vi.fn()} />)
  await act(async()=>pending.resolve([conversation]))
  expect(get).not.toHaveBeenCalled()
})

it('retains the message after a failed send and does not clear a newly typed message on success',async()=>{
  const api=setup(), failed=deferred<AgentConversation>()
  api.send.mockReturnValueOnce(failed.promise)
  render(<CreatorCanvasPage {...props} onUpdated={vi.fn()} />)
  await submit()
  await waitFor(()=>expect(api.send).toHaveBeenCalledTimes(1))
  await act(async()=>failed.reject(new Error('连接中断')))
  expect(screen.getByRole('alert')).toHaveTextContent('连接中断')
  expect(screen.getByLabelText('给创作助手的消息')).toHaveValue('修改开头')
  const next=deferred<AgentConversation>()
  api.send.mockReturnValueOnce(next.promise)
  fireEvent.click(screen.getByRole('button',{name:'发送'}))
  fireEvent.change(screen.getByLabelText('给创作助手的消息'),{target:{value:'下一条想法'}})
  await act(async()=>next.resolve(conversation))
  expect(screen.getByLabelText('给创作助手的消息')).toHaveValue('下一条想法')
})

it('stops before model submission if the draft changed while saving',async()=>{
  const api=setup(),pending=deferred<Topic>()
  api.save.mockReturnValue(pending.promise)
  render(<CreatorCanvasPage {...props} onUpdated={vi.fn()} />)
  fireEvent.change(screen.getByLabelText('创作正文'),{target:{value:'要保存的版本'}})
  await submit()
  await waitFor(()=>expect(api.save).toHaveBeenCalledTimes(1))
  fireEvent.change(screen.getByLabelText('创作正文'),{target:{value:'保存中又改的新版本'}})
  await act(async()=>pending.resolve({...topic,body:'要保存的版本',updatedAt:'v2'}))
  expect(screen.getByLabelText('创作正文')).toHaveValue('保存中又改的新版本')
  expect(screen.getByText('有未保存修改')).toBeInTheDocument()
  expect(api.send).not.toHaveBeenCalled()
  expect(api.create).not.toHaveBeenCalled()
})

it('preserves local draft changes while the accepted request completes',async()=>{
  const api=setup(), pending=deferred<AgentConversation>(),onUpdated=vi.fn()
  api.send.mockReturnValue(pending.promise)
  render(<CreatorCanvasPage {...props} onUpdated={onUpdated} />)
  await submit()
  await waitFor(()=>expect(api.send).toHaveBeenCalledTimes(1))
  fireEvent.change(screen.getByLabelText('创作正文'),{target:{value:'等待期间的新想法'}})
  await act(async()=>pending.resolve(conversation))
  expect(screen.getByLabelText('创作正文')).toHaveValue('等待期间的新想法')
  expect(screen.getByRole('alert')).toHaveTextContent('有未保存的修改')
  expect(onUpdated).not.toHaveBeenCalled()
})

it('suppresses a late failure after navigating away',async()=>{
  const api=setup(),pending=deferred<AgentConversation>()
  api.send.mockReturnValue(pending.promise)
  const {rerender}=render(<CreatorCanvasPage {...props} onUpdated={vi.fn()} />)
  await submit()
  await waitFor(()=>expect(api.send).toHaveBeenCalledTimes(1))
  rerender(<CreatorCanvasPage {...props} topic={{...topic,id:'next'}} onUpdated={vi.fn()} />)
  await act(async()=>pending.reject(new Error('旧请求失败')))
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

it('ignores duplicate form submission in the same turn',async()=>{
  const api=setup(),pending=deferred<AgentConversation>()
  api.create.mockReturnValue(pending.promise)
  render(<CreatorCanvasPage {...props} onUpdated={vi.fn()} />)
  fireEvent.change(screen.getByLabelText('给创作助手的消息'),{target:{value:'修改开头'}})
  await waitFor(()=>expect(screen.getByRole('button',{name:'发送'})).toBeEnabled())
  const form=screen.getByLabelText('给创作助手的消息').closest('form')!
  act(()=>{fireEvent.submit(form);fireEvent.submit(form)})
  expect(api.create).toHaveBeenCalledTimes(1)
  await act(async()=>pending.resolve(conversation))
  expect(api.send).toHaveBeenCalledTimes(1)
})
