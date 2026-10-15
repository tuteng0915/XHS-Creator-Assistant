import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react'
import {afterEach, beforeEach, expect, it, vi} from 'vitest'
import App from './App'
import {memoryStorage} from './test/storage'

beforeEach(() => {window.history.replaceState({}, '', '/'); vi.stubGlobal('localStorage', memoryStorage())})
afterEach(() => {cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals()})

function setup() {
  const workspaces = ['w', 'other'].map(id => ({id, name:id === 'w' ? '甲账号' : '乙账号', accountPositioning:'', positioningVersion:1, currentTopicId:null, createdAt:'', updatedAt:''}))
  let rows = ['one', 'two'].map(id => ({id, workspaceId:'w', title:`选题${id}`, body:'已保存正文', angle:'原角度', associatedPainPoint:'', whyItFits:'', generatedSnapshot:{}, sourceAnalysisRunId:null, sourceWorkflow:'manual', status:'candidate', createdAt:'2026-10-10T00:00:00Z', updatedAt:'2026-10-10T00:00:00Z'}))
  let releaseSave: (() => void) | undefined
  let releaseCreate: (() => void) | undefined
  const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(async(input, init) => {
    const url = String(input)
    if (url === '/api/workspaces') return Response.json(workspaces)
    const workspace = workspaces.find(item => url === `/api/workspaces/${item.id}`)
    if (workspace) return Response.json(workspace)
    if (url.endsWith('/input-assets')) return Response.json([{id:'profile', workspaceId:'w', type:'xhs_creator_profile', name:'材料', createdAt:'', updatedAt:'', content:JSON.stringify({schemaVersion:'xhs-creator-profile/v1', creator:{displayName:'甲账号'}, notes:[{noteId:'note', title:'测试笔记', desc:'笔记原文', metrics:{}, comments:[]}]})}])
    if (url === '/api/workspaces/w/topics' && init?.method === 'POST') {
      const payload = JSON.parse(String(init.body))
      return new Promise(resolve => {releaseCreate = () => {
        const created = {...rows[0], ...payload, id:'created'}
        rows = [created, ...rows]
        resolve(Response.json(created))
      }})
    }
    if (url === '/api/workspaces/w/topics') return Response.json(rows)
    if (url.startsWith('/api/topics/') && init?.method === 'PATCH') {
      const id = url.split('/').at(-1), payload = JSON.parse(String(init.body))
      return new Promise(resolve => {releaseSave = () => {
        rows = rows.map(row => row.id === id ? {...row, ...payload, updatedAt:'2026-10-10T00:01:00Z'} : row)
        resolve(Response.json(rows.find(row => row.id === id)))
      }})
    }
    return Response.json([])
  })
  render(<App />)
  return {fetch, finishSave:() => {if (!releaseSave) throw new Error('No pending save'); releaseSave()},
    finishCreate:() => {if (!releaseCreate) throw new Error('No pending creation'); releaseCreate()}}
}

async function navigate(name: string) {
  fireEvent.click(within(screen.getByRole('navigation', {name:'创作者功能导航'})).getByRole('button', {name: name === '选题库' ? 'AI 创作助手' : name}))
  if (name === '选题库') fireEvent.click(screen.getByRole('button', {name: '选题库'}))
  await screen.findByRole('heading', {name, level:1})
}

it('restores canvas text and unsent input after leaving the page without writing to the server', async () => {
  const control = setup()
  await screen.findByText('测试笔记')
  await navigate('AI 创作助手')
  fireEvent.change(screen.getByLabelText('创作正文'), {target:{value:'尚未保存的正文'}})
  fireEvent.change(screen.getByLabelText('给创作助手的消息'), {target:{value:'还没发出的要求'}})
  await navigate('我的笔记')
  await navigate('AI 创作助手')
  expect(screen.getByLabelText('创作正文')).toHaveValue('尚未保存的正文')
  expect(screen.getByLabelText('给创作助手的消息')).toHaveValue('还没发出的要求')
  expect(control.fetch.mock.calls.filter(([,init]) => ['POST','PATCH'].includes(init?.method || ''))).toHaveLength(0)
})

it('guards library page, topic and account changes without losing unsaved input on cancel', async () => {
  setup(); await screen.findByText('测试笔记'); await navigate('选题库')
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
  fireEvent.click(screen.getByRole('button', {name:'编辑选题'}))
  fireEvent.change(screen.getByLabelText('标题'), {target:{value:'未保存的选题标题'}})
  fireEvent.click(within(screen.getByRole('navigation')).getByRole('button', {name:'我的笔记'}))
  expect(screen.getByRole('heading', {name:'选题库', level:1})).toBeVisible()
  fireEvent.click(screen.getByRole('button', {name:/选题two 已有稿件/}))
  expect(screen.getByLabelText('标题')).toHaveValue('未保存的选题标题')
  fireEvent.change(screen.getByLabelText('当前账号档案'), {target:{value:'other'}})
  expect(screen.getByLabelText('当前账号档案')).toHaveValue('w')
  expect(screen.getByLabelText('标题')).toHaveValue('未保存的选题标题')
  expect(confirm).toHaveBeenCalledTimes(3)
})

it.each(['one', 'two'])('does not replace newer library edits when an earlier save of %s completes', async id => {
  const control = setup(); await screen.findByText('测试笔记'); await navigate('选题库')
  fireEvent.click(screen.getByRole('button', {name:new RegExp(`选题${id} 已有稿件`)}))
  fireEvent.click(screen.getByRole('button', {name:'编辑选题'}))
  fireEvent.change(screen.getByLabelText('标题'), {target:{value:'第一次修改'}})
  fireEvent.click(screen.getByRole('button', {name:'保存修改'}))
  fireEvent.change(screen.getByLabelText('标题'), {target:{value:'保存期间继续输入'}})
  await act(async () => control.finishSave())
  await waitFor(() => expect(screen.getByRole('heading', {name:'第一次修改', level:2})).toBeVisible())
  expect(screen.getByLabelText('标题')).toHaveValue('保存期间继续输入')
  expect(screen.getByRole('button', {name:'保存修改'})).toBeEnabled()
  expect(screen.getByRole('button', {name:'更多'})).toBeDisabled()
})

it('does not show a late-created topic in another account', async () => {
  const control = setup(); await screen.findByText('测试笔记'); await navigate('选题库')
  fireEvent.click(screen.getByRole('button', {name:'＋ 新建选题'}))
  fireEvent.change(screen.getByLabelText('手动选题标题'), {target:{value:'甲账号新选题'}})
  fireEvent.click(screen.getByRole('button', {name:'保存选题'}))
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', {name:'关闭'}))
  fireEvent.change(screen.getByLabelText('当前账号档案'), {target:{value:'other'}})
  await waitFor(() => expect(screen.queryByLabelText('标题')).not.toBeInTheDocument())
  await act(async () => control.finishCreate())
  expect(screen.getByLabelText('当前账号档案')).toHaveValue('other')
  expect(screen.queryByRole('heading', {name:'甲账号新选题'})).not.toBeInTheDocument()
  expect(screen.queryByLabelText('标题')).not.toBeInTheDocument()
  await navigate('AI 创作助手')
  expect(screen.queryByLabelText('创作正文')).not.toBeInTheDocument()
})

it.each([false, true])('keeps the appropriate viewed topic after creation (changed selection: %s)', async changedSelection => {
  const control = setup(); await screen.findByText('测试笔记'); await navigate('选题库')
  fireEvent.click(screen.getByRole('button', {name:'＋ 新建选题'}))
  fireEvent.change(screen.getByLabelText('手动选题标题'), {target:{value:'新选题'}})
  fireEvent.click(screen.getByRole('button', {name:'保存选题'}))
  if (changedSelection) {
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', {name:'关闭'}))
    fireEvent.click(screen.getByRole('button', {name:/选题two 已有稿件/}))
    fireEvent.click(screen.getByRole('button', {name:'编辑选题'}))
    fireEvent.change(screen.getByLabelText('标题'), {target:{value:'继续编辑另一篇'}})
  }
  await act(async () => control.finishCreate())
  if (changedSelection) expect(screen.getByLabelText('标题')).toHaveValue('继续编辑另一篇')
  else {
    expect(screen.getByRole('heading', {name:'新选题', level:2})).toBeVisible()
    expect(screen.queryByLabelText('标题')).not.toBeInTheDocument()
  }
  expect(screen.getByRole('button', {name:/新选题 已有稿件/})).toBeVisible()
})
