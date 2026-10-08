import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react'
import {afterEach, beforeEach, expect, it, vi} from 'vitest'
import App from './App'
import {memoryStorage} from './test/storage'
import type {SimulationCategory, SimulationRun} from './types'

beforeEach(()=>{window.history.replaceState({},'','/');vi.stubGlobal('localStorage',memoryStorage())})
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals()})

function setup() {
  const workspace={id:'w',name:'测试账号',accountPositioning:'',positioningVersion:1,currentTopicId:null,createdAt:'',updatedAt:''}
  const runs:SimulationRun[]=([
    ['account','账号整体期待'],['published_note','旧笔记复盘'],['creation','正在写的选题'],
  ] as Array<[SimulationCategory,string]>).map(([simulationCategory,targetTitle])=>({
    id:simulationCategory,simulationCategory,targetTitle,workspaceId:'w',status:'completed',topicId:null,draftId:null,
    reviewStatus:'unreviewed',userNotes:'',createdAt:'2026-10-08T01:00:00Z',startedAt:null,completedAt:null,updatedAt:'',
    inputSnapshot:{simulationCategory,targetType:simulationCategory==='account'?'account':simulationCategory==='published_note'?'note':'topic',
      topic:{title:targetTitle,body:'这次讨论的正文。'}},
    personaDefinitions:[],reactionResults:[],debateResults:[],synthesis:{},stageErrors:{},modelMetadata:{},
  }))
  const fetch=vi.spyOn(globalThis,'fetch').mockImplementation(async(input,init)=>{
    const url=String(input)
    if(url==='/api/workspaces')return Response.json([workspace])
    if(url==='/api/workspaces/w')return Response.json(workspace)
    if(url==='/api/workspaces/w/input-assets')return Response.json([{id:'profile',workspaceId:'w',type:'xhs_creator_profile',name:'账号材料',createdAt:'',updatedAt:'v1',content:JSON.stringify({
      schemaVersion:'xhs-creator-profile/v1',creator:{displayName:'测试账号'},notes:[{noteId:'note',title:'我的历史笔记',desc:'历史正文',metrics:{liked:3},comments:[]}],
    })}])
    if(url==='/api/workspaces/w/topics')return Response.json([{id:'topic',workspaceId:'w',title:'下一篇创作',body:'创作正文',angle:'',associatedPainPoint:'',whyItFits:'',generatedSnapshot:{},sourceAnalysisRunId:null,sourceWorkflow:'manual',status:'candidate',createdAt:'',updatedAt:''}])
    if(url==='/api/workspaces/w/simulated-fans')return Response.json([{id:'reader',workspaceId:'w',sourceAnalysisId:'analysis',sourceGroupId:'group',original:{},editable:{name:'认真读者',profile:'读到具体步骤再判断',coreConcern:'时间投入',contentPreference:'生活成长',expressionStyle:'直接提问'},status:'active',createdAt:'',updatedAt:''}])
    if(url==='/api/workspaces/w/simulation-runs')return init?.method==='POST'?Response.json({detail:'检查请求后停止，不调用模型'},{status:422}):Response.json(runs)
    const run=runs.find(row=>url===`/api/simulation-runs/${row.id}`)
    if(run)return Response.json(run)
    return Response.json([])
  })
  render(<App />)
  return fetch
}

async function openHub() {
  await screen.findByText('我的历史笔记')
  fireEvent.click(screen.getByRole('button',{name:/👥 受众模拟/}))
  await waitFor(()=>expect(screen.getAllByRole('option',{name:'认真读者'})).toHaveLength(3))
}

it('keeps one first-level simulation hub with three independently browsable histories',async()=>{
  setup();await openHub()
  expect(screen.getByRole('heading',{level:1,name:'受众模拟'})).toBeVisible()
  expect(screen.getByRole('tab',{name:'账号级 1 次讨论'})).toHaveAttribute('aria-selected','true')
  expect(screen.getByRole('button',{name:/账号整体期待/})).toBeVisible()
  expect(screen.queryByRole('button',{name:/旧笔记复盘/})).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:/账号整体期待/}))
  await screen.findByRole('region',{name:'读者试读群聊'})
  fireEvent.click(screen.getByRole('tab',{name:/已发布笔记级/}))
  expect(screen.queryByRole('region',{name:'读者试读群聊'})).not.toBeInTheDocument()
  expect(screen.getByLabelText('试读历史笔记')).toBeVisible()
  expect(screen.getByRole('button',{name:/旧笔记复盘/})).toBeVisible()
  expect(screen.queryByRole('button',{name:/账号整体期待/})).not.toBeInTheDocument()
  fireEvent.keyDown(screen.getByRole('tab',{name:/已发布笔记级/}),{key:'ArrowRight'})
  expect(screen.getByRole('tab',{name:/创作级/})).toHaveAttribute('aria-selected','true')
  expect(screen.getByRole('tab',{name:/创作级/})).toHaveFocus()
  expect(screen.getByRole('button',{name:/正在写的选题/})).toBeVisible()
  expect(screen.getByLabelText('模拟选题')).toBeVisible()
})

it('submits each target without retrieval and keeps one-off role changes out of the next category',async()=>{
  const fetch=setup();await openHub()
  fireEvent.change(screen.getByLabelText('第 1 位模拟粉丝'),{target:{value:'reader'}})
  fireEvent.change(screen.getByLabelText('认真读者的本次关切'),{target:{value:'希望账号持续讲可执行的小步骤'}})
  fireEvent.click(screen.getByRole('button',{name:'开始模拟'}))
  await screen.findByText('检查请求后停止，不调用模型')
  const requests=()=>fetch.mock.calls.filter(([url,init])=>String(url).endsWith('/simulation-runs')&&init?.method==='POST').map(([,init])=>JSON.parse(String(init?.body)))
  expect(requests()[0]).toMatchObject({accountProfileId:'profile',simulatedFanIds:['reader'],personaOverrides:{reader:{coreConcern:'希望账号持续讲可执行的小步骤'}},mode:'live'})
  expect(requests()[0]).not.toHaveProperty('topicId')
  expect(requests()[0]).not.toHaveProperty('manualTopic')
  fireEvent.click(screen.getByRole('tab',{name:/已发布笔记级/}))
  fireEvent.change(screen.getByLabelText('试读历史笔记'),{target:{value:'note'}})
  expect(screen.getByLabelText('认真读者的本次关切')).toHaveValue('时间投入')
  expect(screen.getByRole('button',{name:'开始模拟'})).toBeDisabled()
  fireEvent.click(screen.getByRole('button',{name:'我来选择读者'}))
  fireEvent.click(screen.getByRole('button',{name:'开始模拟'}))
  await waitFor(()=>expect(requests()).toHaveLength(2))
  await screen.findByText('检查请求后停止，不调用模型')
  expect(requests()[1]).toMatchObject({sourceMaterialId:'profile',noteId:'note',simulatedFanIds:['reader']})
  expect(requests()[1]).not.toHaveProperty('accountProfileId')
  expect(requests()[1]).not.toHaveProperty('personaOverrides')
  fireEvent.click(screen.getByRole('tab',{name:/创作级/}))
  fireEvent.change(screen.getByLabelText('模拟选题'),{target:{value:'topic'}})
  fireEvent.click(screen.getByRole('button',{name:'我来选择读者'}))
  fireEvent.click(screen.getByRole('button',{name:'开始模拟'}))
  await waitFor(()=>expect(requests()).toHaveLength(3))
  expect(requests()[2]).toMatchObject({topicId:'topic',simulatedFanIds:['reader']})
  expect(requests()[2]).not.toHaveProperty('noteId')
  expect(requests()[2]).not.toHaveProperty('personaOverrides')
  expect(fetch.mock.calls.filter(([url,init])=>String(url).includes('/reader-selections')&&init?.method==='POST')).toHaveLength(0)
  expect(fetch.mock.calls.filter(([url,init])=>String(url).includes('/simulated-fans')&&init?.method==='PATCH')).toHaveLength(0)
})
