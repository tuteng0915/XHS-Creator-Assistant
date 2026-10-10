import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import {memoryStorage} from './test/storage'

beforeEach(()=>vi.stubGlobal('localStorage',memoryStorage()))
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); window.history.replaceState({}, '', '/') })

function setup(withSimulation = false, withSavedUrl = false, withTopics = false) {
  window.history.replaceState({}, '', '/')
  const workspaces = ['甲', '乙'].map((name, index) => ({ id: `account-${index}`, name,
    profileUrl: withSavedUrl && index === 0 ? 'https://xhslink.cn/m/saved-profile' : null,
    accountPositioning: '', positioningVersion: 1, currentTopicId: null, createdAt: '', updatedAt: '' }))
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    const simulation = { id: 'simulation', workspaceId: 'account-0', status: 'running',
      userNotes: '', reviewStatus: 'unreviewed', createdAt: '2026-09-27', updatedAt: '2026-09-27',
      topicId: null, draftId: null, startedAt: null, completedAt: null,
      inputSnapshot: {}, personaDefinitions: [], reactionResults: [], debateResults: [], synthesis: {}, stageErrors: {}, modelMetadata: {} }
    if (withSimulation && url === '/api/simulation-runs/simulation') return Response.json({...simulation, status: 'completed'})
    const topicRows=['第一个测试选题','第二个测试选题'].map((title,index)=>({id:`topic-${index}`,workspaceId:'account-0',title,
      body:`${title}的正文`,angle:'',associatedPainPoint:'',whyItFits:'',generatedSnapshot:{},sourceAnalysisRunId:null,
      sourceWorkflow:'manual',status:'candidate',createdAt:'',updatedAt:'v1'}))
    if(withTopics && url==='/api/topics/topic-0' && init?.method==='PATCH') return Response.json({...topicRows[0],...JSON.parse(String(init.body)),updatedAt:'v2'})
    if(withTopics && init?.method==='POST' && url.endsWith('/simulation-runs')) return Response.json({detail:'测试停止于执行前'},{status:422})
    if (init?.method === 'POST' && url.endsWith('/analysis-runs')) {
      return new Response(JSON.stringify({ detail: '测试停止于执行前' }), { status: 422 })
    }
    if (init?.method === 'POST' && url.endsWith('/xhs-capture-jobs')) {
      return Response.json({ id: 'capture-job', workspaceId: 'account-0', status: 'completed',
        profileUrl: 'https://xhslink.cn/m/saved-profile', resolvedUrl: '',
        noteLimit: 20, includeComments: true, statusMessage: '读取完成', error: '' })
    }
    if (url === '/api/workspaces') return Response.json(workspaces)
    const workspace = workspaces.find((item) => url.startsWith(`/api/workspaces/${item.id}`))
    if (!workspace) throw new Error(`Unexpected ${url}`)
    if (url === `/api/workspaces/${workspace.id}`) return Response.json(workspace)
    if(withTopics && workspace.id==='account-0' && url.endsWith('/topics')) return Response.json(topicRows)
    if(withTopics && workspace.id==='account-0' && url.endsWith('/simulated-fans')) return Response.json(['a','b','c','d'].map(id=>({
      id,workspaceId:'account-0',sourceAnalysisId:'analysis',sourceGroupId:id,original:{},
      editable:{name:`读者${id}`,profile:'具体的阅读特点',coreConcern:'',contentPreference:'',expressionStyle:''},status:'active',createdAt:'',updatedAt:'v1'})))
    if (withSimulation && workspace.id === 'account-0' && url.endsWith('/simulation-runs')) return Response.json([simulation])
    if (url.endsWith('/input-assets')) return Response.json([{
      id: `profile-${workspace.id}`, workspaceId: workspace.id, type: 'xhs_creator_profile',
      name: workspace.name, createdAt: '', updatedAt: '', content: JSON.stringify({
        schemaVersion: 'xhs-creator-profile/v1', creator: { displayName: workspace.name },
        notes: [{ noteId: `note-${workspace.id}`, title: `${workspace.name}的笔记`, desc: `${workspace.name}的正文`, comments: [] },
          {noteId:`second-${workspace.id}`,title:`${workspace.name}的第二条笔记`,desc:'第二条正文',comments:[]}],
      }),
    }])
    return Response.json([])
  })
  render(<App />)
  return fetchMock
}

describe('public creator journey', () => {
  it('sends guided questions and discussion settings from the public setup to simulation creation', async()=>{
    const fetch=setup(false,false,true)
    await screen.findByText('甲的笔记')
    fireEvent.click(within(screen.getByRole('navigation', {name: '创作者功能导航'})).getByRole('button',{name:'受众模拟'}))
    fireEvent.click(screen.getByRole('tab',{name:/创作级/}))
    await waitFor(()=>expect(screen.getAllByRole('option',{name:'读者a'})).toHaveLength(3))
    expect(screen.getByLabelText('第 1 位模拟粉丝')).toHaveValue('')
    fireEvent.change(screen.getByLabelText('第 1 位模拟粉丝'),{target:{value:'a'}})
    fireEvent.change(screen.getByLabelText('第 2 位模拟粉丝'),{target:{value:'b'}})
    fireEvent.change(screen.getByLabelText('第 3 位模拟粉丝'),{target:{value:'c'}})
    fireEvent.change(screen.getByLabelText('模拟选题'),{target:{value:'topic-0'}})
    fireEvent.click(screen.getByRole('button',{name:'我来选择读者'}))
    fireEvent.click(screen.getByLabelText('定向试读'))
    fireEvent.change(screen.getByLabelText('重点问题 1'),{target:{value:'第一步清楚吗？'}})
    fireEvent.click(screen.getByLabelText('互相回应'))
    fireEvent.click(screen.getByRole('button',{name:'开始模拟'}))
    await waitFor(()=>expect(fetch.mock.calls.some(([url,init])=>String(url).endsWith('/simulation-runs')&&init?.method==='POST')).toBe(true))
    const sent=fetch.mock.calls.find(([url,init])=>String(url).endsWith('/simulation-runs')&&init?.method==='POST')!
    expect(JSON.parse(String(sent[1]?.body))).toMatchObject({topicId:'topic-0',simulatedFanIds:['a','b','c'],
      panelTask:{protocolVersion:'panel/v1',readingMode:'guided',discussionEnabled:false,focusQuestions:['第一步清楚吗？']}})
    await screen.findByText('测试停止于执行前')
    expect(screen.getByLabelText('重点问题 1')).toHaveValue('第一步清楚吗？')
    fireEvent.change(screen.getByLabelText('模拟选题'),{target:{value:'topic-1'}})
    expect(screen.getByLabelText('自然全文试读')).toBeChecked()
    expect(screen.getByLabelText('互相回应')).toBeChecked()
    expect(screen.queryByLabelText('重点问题 1')).not.toBeInTheDocument()
  })

  it('opens topic simulation confirmation without running and keeps manually chosen readers across shortcuts', async()=>{
    const fetch=setup(false,false,true)
    const simulations=()=>fetch.mock.calls.filter(([url,init])=>String(url).endsWith('/simulation-runs')&&init?.method==='POST')
    await screen.findByText('甲的笔记')
    fireEvent.click(within(screen.getByRole('navigation', {name: '创作者功能导航'})).getByRole('button',{name:'受众模拟'}))
    fireEvent.click(screen.getByRole('tab',{name:/创作级/}))
    await waitFor(()=>expect(screen.getAllByRole('option',{name:'读者d'})).toHaveLength(3))
    expect(screen.getByLabelText('第 1 位模拟粉丝')).toHaveValue('')
    fireEvent.change(screen.getByLabelText('第 1 位模拟粉丝'),{target:{value:'d'}})
    fireEvent.click(screen.getByRole('button',{name:/选题库/}))
    fireEvent.click(await screen.findByRole('button',{name:/第一个测试选题/}))
    fireEvent.click(within(screen.getByRole('main')).getByRole('button',{name:'受众模拟'}))
    await screen.findByRole('region',{name:'模拟准备'})
    expect(screen.getByLabelText('模拟选题')).toHaveValue('topic-0')
    expect(screen.getByLabelText('第 1 位模拟粉丝')).toHaveValue('d')
    expect(simulations()).toHaveLength(0)
    expect(fetch.mock.calls.filter(([url])=>String(url).includes('/reader-selections'))).toHaveLength(0)
    fireEvent.click(screen.getByRole('button',{name:/选题库/}))
    fireEvent.click(await screen.findByRole('button',{name:/第二个测试选题/}))
    fireEvent.click(within(screen.getByRole('main')).getByRole('button',{name:'受众模拟'}))
    expect(screen.getByLabelText('模拟选题')).toHaveValue('topic-1')
    expect(screen.getByLabelText('第 1 位模拟粉丝')).toHaveValue('d')
    expect(screen.getByRole('button',{name:'开始模拟'})).toBeDisabled()
    fireEvent.click(screen.getByRole('button',{name:'我来选择读者'}))
    fireEvent.click(screen.getByRole('button',{name:'开始模拟'}))
    await screen.findByText('测试停止于执行前')
    expect(JSON.parse(String(simulations()[0][1]?.body))).toMatchObject({topicId:'topic-1',simulatedFanIds:['d'],mode:'live'})
    expect(simulations()).toHaveLength(1)
  })

  it('takes the saved canvas text to confirmation rather than creating a simulation immediately', async()=>{
    const fetch=setup(false,false,true)
    await screen.findByText('甲的笔记')
    fireEvent.click(screen.getByRole('button',{name:/AI 创作助手/}))
    fireEvent.change(screen.getByLabelText('创作选题'),{target:{value:'topic-0'}})
    await waitFor(()=>expect(screen.getByRole('button',{name:'选择模拟读者'})).toBeEnabled())
    fireEvent.change(screen.getByLabelText('创作正文'),{target:{value:'刚刚润色的完整正文'}})
    fireEvent.click(screen.getByRole('button',{name:'选择模拟读者'}))
    await screen.findByRole('region',{name:'模拟准备'})
    expect(screen.getByText('刚刚润色的完整正文')).toBeInTheDocument()
    expect(fetch.mock.calls.filter(([url,init])=>String(url).endsWith('/simulation-runs')&&init?.method==='POST')).toHaveLength(0)
    expect(fetch.mock.calls.filter(([,init])=>init?.method==='PATCH')).toHaveLength(1)
    fireEvent.change(screen.getByLabelText('当前账号档案'),{target:{value:'account-1'}})
    await screen.findByText('乙的笔记')
    fireEvent.click(within(screen.getByRole('navigation', {name: '创作者功能导航'})).getByRole('button',{name:'受众模拟'}))
    fireEvent.click(screen.getByRole('tab',{name:/创作级/}))
    expect(screen.getByLabelText('模拟选题')).toHaveValue('')
    expect(screen.queryByText('刚刚润色的完整正文')).not.toBeInTheDocument()
    expect(screen.getByRole('button',{name:'开始模拟'})).toBeDisabled()
  })
  it('uses the recorded account URL when reading more notes', async () => {
    const fetchMock = setup(false, true)
    await screen.findByText('甲的笔记')
    fireEvent.click(screen.getByRole('button', { name: '抓取更多笔记' }))
    expect(screen.queryByRole('textbox', { name: /小红书用户主页 URL/ })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '继续读取' }))
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([url, init]) =>
        String(url).endsWith('/xhs-capture-jobs') && init?.method === 'POST')
      expect(JSON.parse(String(call?.[1]?.body)).profileUrl).toBe('https://xhslink.cn/m/saved-profile')
    })
  })
  it('sends manual note IDs and clears the selection when switching accounts', async () => {
    const fetchMock = setup()
    await screen.findByText('甲的笔记')
    fireEvent.click(screen.getByRole('button', {name:/账号诊断/}))
    fireEvent.click(screen.getByRole('button', {name:'调整范围'}))
    fireEvent.click(screen.getByRole('button', {name:'取消选择'}))
    fireEvent.click(screen.getByRole('checkbox', {name:'选择笔记：甲的第二条笔记'}))
    fireEvent.click(screen.getByRole('button', {name:'完成'}))
    expect(screen.getByText('手动选择 · 1 条笔记')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', {name:'开始分析'}))
    await screen.findByText(/测试停止于执行前/)
    const requests = () => fetchMock.mock.calls.filter(([url, init]) => String(url).endsWith('/analysis-runs') && init?.method === 'POST')
    expect(JSON.parse(String(requests()[0][1]?.body)).selectedNoteIds).toEqual(['second-account-0'])
    fireEvent.change(screen.getByLabelText('当前账号档案'), {target:{value:'account-1'}})
    await screen.findByText('乙的笔记')
    fireEvent.click(screen.getByRole('button', {name:/账号诊断/}))
    expect(screen.getByText('最近 10 条 · 2 条笔记')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', {name:'开始分析'}))
    await waitFor(() => expect(requests()).toHaveLength(2))
    expect(JSON.parse(String(requests()[1][1]?.body)).selectedNoteIds).toBeUndefined()
  })
  it('updates the history list status when reopening a simulation completed after refresh', async () => {
    setup(true)
    await screen.findByText('甲的笔记')
    fireEvent.click(within(screen.getByRole('navigation', {name: '创作者功能导航'})).getByRole('button', {name: '受众模拟'}))
    fireEvent.click(screen.getByRole('tab', {name: /创作级/}))
    fireEvent.click(screen.getByRole('button', {name: /受众模拟 正在试读/}))
    await screen.findByRole('button', {name: /受众模拟 已完成/})
    expect(screen.queryByRole('button', {name: /受众模拟 正在试读/})).not.toBeInTheDocument()
  })
  it('opens add-account without creating any database record', async () => {
    const fetchMock = setup()
    await screen.findByText('甲的笔记')
    fireEvent.click(screen.getByRole('button', {name: /添加账号/}))
    await screen.findByText('导入你的账号')
    expect(fetchMock.mock.calls.filter(([,init]) => init?.method === 'POST')).toHaveLength(0)
    expect(screen.queryByText('导入小红书账号')).not.toBeInTheDocument()
  })
  it('switches accounts without displaying the previous accounts notes', async () => {
    setup()
    await screen.findByText('甲的笔记')
    fireEvent.click(screen.getByRole('button', { name: /我的笔记/ }))
    fireEvent.change(screen.getByLabelText('当前账号档案'), { target: { value: 'account-1' } })
    await screen.findByText('乙的笔记')
    expect(screen.queryByText('甲的笔记')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Skills' })).not.toBeInTheDocument()
    expect(screen.queryByText('热点分析')).not.toBeInTheDocument()
  })

  it('uses the current profile, live model and ten-note default for diagnosis', async () => {
    const fetchMock = setup()
    await screen.findByText('甲的笔记')
    fireEvent.click(screen.getByRole('button', { name: /账号诊断/ }))
    fireEvent.click(screen.getByRole('button', { name: '开始分析' }))
    await screen.findByText(/测试停止于执行前/)
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([url, init]) => String(url).endsWith('/analysis-runs') && init?.method === 'POST')
      expect(call).toBeDefined()
      expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({
        xhsCreatorProfileInputAssetId: 'profile-account-0', analysisScope: 'recent_10', mode: 'live',
      })
    })
  })
})
