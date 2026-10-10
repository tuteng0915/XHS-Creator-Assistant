import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { agentConversationApi, topicApi } from '../api'
import { contentCollaborationApi } from '../contentCollaboration'
import { creatorDraftKey } from '../creatorDraftCache'
import type { Topic } from '../types'
import { memoryStorage } from '../test/storage'
import { CreatorCanvasPage } from './CreatorCanvasPage'

const topic: Topic = {id:'topic',workspaceId:'w',title:'已保存标题',body:'已保存正文',angle:'',associatedPainPoint:'',whyItFits:'',generatedSnapshot:{},sourceAnalysisRunId:null,sourceWorkflow:'manual',status:'candidate',createdAt:'v1',updatedAt:'v1'}
const props = {workspaceId:'w',topic,topics:[topic],onSelect:vi.fn(),onUpdated:vi.fn()}
const draftKey = creatorDraftKey('draft', 'w', 'topic')
const messageKey = creatorDraftKey('message', 'w', 'topic')
beforeEach(() => {
  vi.spyOn(agentConversationApi,'list').mockResolvedValue([])
  vi.spyOn(contentCollaborationApi,'list').mockResolvedValue([])
})
afterEach(() => {cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals()})
function edit(body = '还没有保存的新正文') {
  fireEvent.change(screen.getByLabelText('创作标题'), {target:{value:'本地新标题'}})
  fireEvent.change(screen.getByLabelText('创作正文'), {target:{value:body}})
}

it('restores unsaved title, body and message after leaving and reopening without backend writes', async () => {
  const update = vi.spyOn(topicApi,'update')
  const first = render(<CreatorCanvasPage {...props} />)
  edit()
  fireEvent.change(screen.getByLabelText('给创作助手的消息'), {target:{value:'还没发出去的想法'}})
  first.unmount()
  render(<CreatorCanvasPage {...props} />)
  expect(screen.getByLabelText('创作标题')).toHaveValue('本地新标题')
  expect(screen.getByLabelText('创作正文')).toHaveValue('还没有保存的新正文')
  expect(screen.getByLabelText('给创作助手的消息')).toHaveValue('还没发出去的想法')
  expect(screen.getByText('已恢复本页未保存草稿。')).toBeInTheDocument()
  expect(update).not.toHaveBeenCalled()
})

it('keeps drafts isolated by account and topic while switching in the same page', async () => {
  const view = render(<CreatorCanvasPage {...props} />)
  edit('账号一选题一')
  fireEvent.change(screen.getByLabelText('给创作助手的消息'), {target:{value:'账号一的消息'}})
  const otherTopic = {...topic,id:'another',body:'另一题'}
  view.rerender(<CreatorCanvasPage {...props} topic={otherTopic} />)
  expect(screen.getByLabelText('创作正文')).toHaveValue('另一题')
  expect(screen.getByLabelText('给创作助手的消息')).toHaveValue('')
  edit('账号一选题二')
  view.rerender(<CreatorCanvasPage {...props} workspaceId="another" topic={{...topic,workspaceId:'another'}} />)
  expect(screen.getByLabelText('创作正文')).toHaveValue('已保存正文')
  edit('另一个账号')
  view.rerender(<CreatorCanvasPage {...props} />)
  expect(screen.getByLabelText('创作正文')).toHaveValue('账号一选题一')
  expect(screen.getByLabelText('给创作助手的消息')).toHaveValue('账号一的消息')
  view.rerender(<CreatorCanvasPage {...props} topic={otherTopic} />)
  expect(screen.getByLabelText('创作正文')).toHaveValue('账号一选题二')
})

it('requires an explicit recovery choice when the saved version changed and preserves the local copy until then', async () => {
  const update = vi.spyOn(topicApi,'update').mockResolvedValue({...topic,title:'本地新标题',body:'还没有保存的新正文',updatedAt:'v3'})
  const first = render(<CreatorCanvasPage {...props} />)
  edit(); first.unmount()
  const newer = {...topic,body:'在别处保存的新正文',updatedAt:'v2'}
  const reopened = render(<CreatorCanvasPage {...props} topic={newer} />)
  expect(screen.getByLabelText('待恢复的本地草稿')).toBeInTheDocument()
  expect(screen.getByLabelText('创作正文')).toHaveValue('在别处保存的新正文')
  expect(screen.getByLabelText('创作正文')).toBeDisabled()
  expect(JSON.parse(window.sessionStorage.getItem(draftKey)!)).toMatchObject({body:'还没有保存的新正文',baseUpdatedAt:'v1'})
  reopened.unmount()
  render(<CreatorCanvasPage {...props} topic={newer} />)
  fireEvent.click(screen.getByRole('button',{name:'恢复本地草稿'}))
  expect(screen.getByLabelText('创作正文')).toHaveValue('还没有保存的新正文')
  expect(screen.getByLabelText('创作正文')).toBeEnabled()
  expect(update).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button',{name:'保存'}))
  await waitFor(() => expect(update).toHaveBeenCalledWith('topic',expect.objectContaining({expectedUpdatedAt:'v2',body:'还没有保存的新正文'})))
})

it('lets the author explicitly keep the saved version and discards only the draft, not an unsent message', async () => {
  const first = render(<CreatorCanvasPage {...props} />)
  edit()
  fireEvent.change(screen.getByLabelText('给创作助手的消息'), {target:{value:'这条要求要留着'}})
  first.unmount()
  render(<CreatorCanvasPage {...props} topic={{...topic,updatedAt:'v2',body:'新保存稿'}} />)
  fireEvent.click(screen.getByRole('button',{name:'使用已保存稿'}))
  expect(screen.getByLabelText('创作正文')).toHaveValue('新保存稿')
  expect(screen.getByLabelText('创作正文')).toBeEnabled()
  expect(window.sessionStorage.getItem(draftKey)).toBeNull()
  expect(screen.getByLabelText('给创作助手的消息')).toHaveValue('这条要求要留着')
  expect(window.sessionStorage.getItem(messageKey)).not.toBeNull()
})

it('keeps failed saves recoverable and clears the draft only after a successful unchanged save', async () => {
  const updated = {...topic,title:'本地新标题',body:'还没有保存的新正文',updatedAt:'v2'}
  vi.spyOn(topicApi,'update').mockRejectedValueOnce(new Error('网络暂时断开')).mockResolvedValue(updated)
  const first = render(<CreatorCanvasPage {...props} />)
  edit(); fireEvent.click(screen.getByRole('button',{name:'保存'}))
  await screen.findByText('Error: 网络暂时断开')
  expect(window.sessionStorage.getItem(draftKey)).not.toBeNull()
  first.unmount()
  render(<CreatorCanvasPage {...props} />)
  expect(screen.getByLabelText('创作正文')).toHaveValue('还没有保存的新正文')
  fireEvent.click(screen.getByRole('button',{name:'保存'}))
  await waitFor(() => expect(window.sessionStorage.getItem(draftKey)).toBeNull())
  expect(screen.getByText('已保存')).toBeInTheDocument()
})

it('retains edits made while saving, with the new saved baseline for subsequent refresh recovery', async () => {
  let resolve!: (value: Topic) => void
  const update = vi.spyOn(topicApi,'update').mockReturnValue(new Promise<Topic>(yes => {resolve = yes}))
  const first = render(<CreatorCanvasPage {...props} />)
  edit('发出保存的正文')
  fireEvent.click(screen.getByRole('button',{name:'保存'}))
  await waitFor(() => expect(update).toHaveBeenCalledTimes(1))
  fireEvent.change(screen.getByLabelText('创作正文'), {target:{value:'等待时继续写的正文'}})
  const updated = {...topic,title:'本地新标题',body:'发出保存的正文',updatedAt:'v2'}
  await act(async () => resolve(updated))
  expect(JSON.parse(window.sessionStorage.getItem(draftKey)!)).toMatchObject({body:'等待时继续写的正文',baseBody:'发出保存的正文',baseUpdatedAt:'v2'})
  first.unmount()
  render(<CreatorCanvasPage {...props} topic={updated} />)
  expect(screen.queryByLabelText('待恢复的本地草稿')).not.toBeInTheDocument()
  expect(screen.getByLabelText('创作正文')).toHaveValue('等待时继续写的正文')
})

it('does not resurrect a draft already present in the saved version', async () => {
  const first = render(<CreatorCanvasPage {...props} />)
  edit(); first.unmount()
  render(<CreatorCanvasPage {...props} topic={{...topic,title:'本地新标题',body:'还没有保存的新正文',updatedAt:'v2'}} />)
  expect(screen.queryByLabelText('待恢复的本地草稿')).not.toBeInTheDocument()
  expect(screen.getByText('已保存')).toBeInTheDocument()
  expect(window.sessionStorage.getItem(draftKey)).toBeNull()
})

it('protects edits from an incoming updated topic while still mounted', async () => {
  const view = render(<CreatorCanvasPage {...props} />)
  edit('我还在编辑的内容')
  view.rerender(<CreatorCanvasPage {...props} topic={{...topic,body:'服务端新版本',updatedAt:'v2'}} />)
  expect(screen.getByLabelText('待恢复的本地草稿')).toBeInTheDocument()
  expect(JSON.parse(window.sessionStorage.getItem(draftKey)!)).toMatchObject({body:'我还在编辑的内容'})
  fireEvent.click(screen.getByRole('button',{name:'恢复本地草稿'}))
  expect(screen.getByLabelText('创作正文')).toHaveValue('我还在编辑的内容')
})

it('warns on unload and raises the app leave guard when storage is unavailable', async () => {
  vi.stubGlobal('sessionStorage',{...memoryStorage(),setItem:() => {throw new Error('禁止存储')}})
  const guard = vi.fn()
  const view = render(<CreatorCanvasPage {...props} onLeaveGuardChange={guard} />)
  edit()
  expect(screen.getByRole('alert')).toHaveTextContent('本页无法暂存')
  expect(guard).toHaveBeenLastCalledWith(expect.stringContaining('离开后未保存内容会丢失'))
  const event = new Event('beforeunload',{cancelable:true})
  window.dispatchEvent(event)
  expect(event.defaultPrevented).toBe(true)
  view.unmount()
  expect(guard).toHaveBeenLastCalledWith(null)
})

it('also guards a message-only draft when its storage fails', async () => {
  vi.stubGlobal('sessionStorage',{...memoryStorage(),setItem:() => {throw new Error('禁止存储')}})
  const guard = vi.fn()
  render(<CreatorCanvasPage {...props} onLeaveGuardChange={guard} />)
  fireEvent.change(screen.getByLabelText('给创作助手的消息'), {target:{value:'未发送消息'}})
  expect(guard).toHaveBeenLastCalledWith(expect.stringContaining('离开后未保存内容会丢失'))
  fireEvent.change(screen.getByLabelText('给创作助手的消息'), {target:{value:''}})
  expect(guard).toHaveBeenLastCalledWith(null)
})
