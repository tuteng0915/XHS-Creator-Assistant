import {useState} from 'react'
import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react'
import {afterEach, beforeEach, expect, it, vi} from 'vitest'
import {memoryStorage} from '../test/storage'
import {readerSelectionApi, simulatedFanApi} from '../api'
import {useSimulatedFans} from '../hooks/useSimulatedFans'
import {readerSelectionStorageKey} from '../hooks/useReaderSelection'
import type {ReaderSelection} from '../readerSelection'
import type {PanelTask, SimulatedFan, TextInputAsset, Topic, SimulationCategory} from '../types'
import {CreatorSimulationSetup} from './CreatorSimulationSetup'

const topic:Topic={id:'t',workspaceId:'w',title:'下班后如何开始学语言',body:'每天只留十分钟，先开口。',angle:'',
  associatedPainPoint:'',whyItFits:'',generatedSnapshot:{},sourceAnalysisRunId:null,sourceWorkflow:'manual',
  status:'candidate',createdAt:'',updatedAt:''}
const rows:SimulatedFan[]=['a','b','c','d'].map(id=>({id,workspaceId:'w',sourceAnalysisId:'analysis',sourceGroupId:id,
  original:{},editable:{name:`读者${id}`,profile:'先确认时间投入，再试一次。',coreConcern:'',contentPreference:'',expressionStyle:''},
  status:'active',createdAt:'',updatedAt:'v1'}))
const task:PanelTask={protocolVersion:'panel/v1',readingMode:'natural',discussionEnabled:true,focusQuestions:[]}
const record:ReaderSelection={id:'r',workspaceId:'w',inputHash:'a'.repeat(64),status:'completed',errorCode:null,
  inputSnapshot:{panelTask:task,target:{title:topic.title},candidates:rows.map(f=>({id:f.id,name:f.editable.name}))},
  result:{proposedReaders:[{fanId:'d',fitReason:'重视开始行动的门槛。',contribution:'从时间投入角度试读。'}],unmatchedReason:''},
  freshness:{status:'current',reasons:[]}}
beforeEach(()=>vi.stubGlobal('localStorage',memoryStorage()))
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals()})
function setup(saved:ReaderSelection=record, profile?:TextInputAsset, category?:SimulationCategory, loadFans=()=>Promise.resolve(rows)) {
  const list=vi.spyOn(simulatedFanApi,'list').mockImplementation(loadFans)
  const create=vi.spyOn(readerSelectionApi,'create').mockResolvedValue(saved)
  const get=vi.spyOn(readerSelectionApi,'get').mockResolvedValue(saved)
  const run=vi.fn()
  const runNote=vi.fn()
  const runAccount=vi.fn()
  function Page({currentProfile=profile}:{currentProfile?:TextInputAsset}){
    const fans=useSimulatedFans('w','')
    const [selected,setSelected]=useState<Topic|null>(topic)
    return <CreatorSimulationSetup workspaceId="w" positioning="" topics={[topic,{...topic,id:'other',title:'其他选题'}]}
      topic={selected} fans={fans} running={false} onSelect={setSelected} onRun={run} onAddFans={()=>{}}
      category={category} profile={currentProfile} onRunNote={runNote} onRunAccount={runAccount} />
  }
  const view=render(<Page />)
  return {create,get,run,runNote,runAccount,list,rerenderProfile:(currentProfile:TextInputAsset)=>view.rerender(<Page currentProfile={currentProfile}/>)}
}
async function ready(){
  await waitFor(()=>expect(screen.getAllByRole('option',{name:'读者a'}).length).toBeGreaterThan(0))
}
async function recommend(){
  await ready()
  await waitFor(()=>expect(screen.getByRole('button',{name:'推荐读者'})).toBeEnabled())
  fireEvent.click(screen.getByRole('button',{name:'推荐读者'}))
  await screen.findByText('重视开始行动的门槛。')
}
function chooseNote(title:string){
  fireEvent.click(screen.queryByRole('button',{name:'更换笔记'})||screen.getByRole('button',{name:'选择笔记'}))
  const picker=screen.getByRole('dialog',{name:'选择试读笔记'})
  fireEvent.click(within(picker).getByRole('radio',{name:`选择笔记：${title}`}))
  fireEvent.click(within(picker).getByRole('button',{name:'完成'}))
}
function openAccountNotePicker(){
  fireEvent.click(screen.queryByRole('button',{name:'更改笔记'})||screen.getByRole('button',{name:'选择笔记'}))
  return screen.getByRole('dialog',{name:'选择账号模拟笔记'})
}
function chooseAccountNotes(titles?:string[]){
  const picker=openAccountNotePicker()
  if(titles){
    fireEvent.click(within(picker).getByRole('button',{name:'取消选择'}))
    titles.forEach(title=>fireEvent.click(within(picker).getByRole('checkbox',{name:`选择笔记：${title}`})))
  }
  fireEvent.click(within(picker).getByRole('button',{name:'完成'}))
}

it('previews the target first and does not replace manual choices until explicit adoption', async()=>{
  const {create,run}=setup()
  await recommend()
  expect(create).toHaveBeenCalledTimes(1)
  expect(screen.getByText(topic.body!)).toBeInTheDocument()
  expect(screen.getByLabelText('第 1 位模拟粉丝')).toHaveValue('')
  expect(screen.getByRole('button',{name:'开始模拟'})).toBeDisabled()
  fireEvent.change(screen.getByLabelText('第 1 位模拟粉丝'),{target:{value:'d'}})
  fireEvent.click(screen.getByRole('button',{name:'开始模拟'}))
  expect(run).toHaveBeenLastCalledWith(topic,undefined,task)
  fireEvent.click(screen.getByRole('button',{name:'采用这组读者'}))
  await screen.findByText('已采用推荐')
  expect(screen.getByLabelText('第 1 位模拟粉丝')).toHaveValue('d')
  expect(screen.getByLabelText('第 2 位模拟粉丝')).toHaveValue('')
  fireEvent.change(screen.getByLabelText('第 2 位模拟粉丝'),{target:{value:'b'}})
  fireEvent.click(screen.getByRole('button',{name:'开始模拟'}))
  expect(run).toHaveBeenLastCalledWith(topic,{readerSelectionId:'r',readerSelectionInputHash:record.inputHash},task)
})

it('checks freshness again at adoption and preserves the old selection on conflict', async()=>{
  const {get}=setup();await ready()
  fireEvent.change(screen.getByLabelText('第 1 位模拟粉丝'),{target:{value:'a'}})
  await recommend()
  get.mockResolvedValue({...record,freshness:{status:'stale',reasons:['target_changed']}})
  fireEvent.click(screen.getByRole('button',{name:'采用这组读者'}))
  await screen.findByText('推荐已变化或暂时无法核验，名单未改变。')
  expect(screen.getByLabelText('第 1 位模拟粉丝')).toHaveValue('a')
  expect(screen.getByRole('button',{name:'采用这组读者'})).toBeDisabled()
  expect(screen.getByText('手选')).toBeVisible()
  expect(screen.getByRole('button',{name:'开始模拟'})).toBeEnabled()
})

it('locks topic and reader editing during explicit adoption verification', async()=>{
  const {get}=setup();await recommend()
  let finish!:(value:ReaderSelection)=>void
  get.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
  fireEvent.click(screen.getByRole('button',{name:'采用这组读者'}))
  expect(screen.getByLabelText('模拟选题')).toBeDisabled()
  expect(screen.getByLabelText('第 1 位模拟粉丝')).toBeDisabled()
  await act(async()=>finish(record))
  expect(screen.getByLabelText('第 1 位模拟粉丝')).toBeEnabled()
})

it('restores recommendations without auto-adopting them or charging another request', async()=>{
  window.localStorage.setItem(readerSelectionStorageKey('w','t',task),JSON.stringify({id:'r',requestKey:'original',desiredCount:3}))
  const {create}=setup()
  await screen.findByText('重视开始行动的门槛。')
  expect(screen.getByLabelText('第 1 位模拟粉丝')).toHaveValue('')
  expect(screen.getByRole('button',{name:'开始模拟'})).toBeDisabled()
  expect(create).not.toHaveBeenCalled()
  expect(screen.queryByText('已采用推荐')).not.toBeInTheDocument()
})

it('does not require recommendation success to manually simulate', async()=>{
  const {run}=setup({...record,status:'failed',result:null,errorCode:'model_error'})
  await ready()
  await waitFor(()=>expect(screen.getByRole('button',{name:'推荐读者'})).toBeEnabled())
  fireEvent.click(screen.getByRole('button',{name:'推荐读者'}))
  await screen.findByText('本次推荐未完成，可重新推荐或手动选择。')
  expect(screen.getByRole('button',{name:'开始模拟'})).toBeDisabled()
  fireEvent.change(screen.getByLabelText('第 1 位模拟粉丝'),{target:{value:'a'}})
  expect(screen.getByRole('button',{name:'开始模拟'})).toBeEnabled()
  fireEvent.click(screen.getByRole('button',{name:'开始模拟'}))
  expect(run).toHaveBeenCalledWith(topic,undefined,task)
  expect(screen.queryByRole('button',{name:'采用这组读者'})).not.toBeInTheDocument()
})

it('retains fewer valid readers and renders no-match without fabricating slots', async()=>{
  const {get}=setup({...record,status:'partially_completed'})
  await recommend();expect(screen.getByText('部分完成，已保留有效读者。')).toBeInTheDocument()
  get.mockResolvedValue({...record,result:{proposedReaders:[],unmatchedReason:'现有读者不贴合这篇内容。'}})
  fireEvent.click(screen.getByRole('button',{name:'重新推荐读者'}))
  await screen.findByText('现有读者不贴合这篇内容。')
  expect(screen.getByLabelText('第 1 位模拟粉丝')).toHaveValue('')
  expect(screen.getByRole('button',{name:'开始模拟'})).toBeDisabled()
  expect(screen.queryByRole('button',{name:'采用这组读者'})).not.toBeInTheDocument()
})

it('does not carry adopted provenance to another topic', async()=>{
  const {run}=setup();await recommend()
  fireEvent.click(screen.getByRole('button',{name:'采用这组读者'}))
  await screen.findByText('已采用推荐')
  fireEvent.change(screen.getByLabelText('模拟选题'),{target:{value:'other'}})
  expect(screen.getByRole('button',{name:'确认名单并开始'})).toBeEnabled()
  fireEvent.click(screen.getByRole('button',{name:'确认名单并开始'}))
  expect(run).toHaveBeenLastCalledWith(expect.objectContaining({id:'other'}),undefined,task)
})

it('requires one or two nonempty guided questions and passes the task to manual simulation', async()=>{
  const {run}=setup()
  await ready()
  fireEvent.change(screen.getByLabelText('第 1 位模拟粉丝'),{target:{value:'a'}})
  fireEvent.click(screen.getByLabelText('定向试读'))
  expect(screen.getByRole('button',{name:'开始模拟'})).toBeDisabled()
  expect(screen.getByRole('button',{name:'推荐读者'})).toBeDisabled()
  fireEvent.change(screen.getByLabelText('重点问题 1'),{target:{value:'  第一步清楚吗？  '}})
  fireEvent.click(screen.getByRole('button',{name:'＋ 添加第二个问题'}))
  expect(screen.getByRole('button',{name:'开始模拟'})).toBeDisabled()
  fireEvent.change(screen.getByLabelText('重点问题 2'),{target:{value:'愿意尝试吗？'}})
  expect(screen.getByLabelText('重点问题 2')).toHaveAttribute('maxlength','300')
  fireEvent.click(screen.getByLabelText('互相回应'))
  fireEvent.click(screen.getByRole('button',{name:'开始模拟'}))
  expect(run).toHaveBeenLastCalledWith(topic,undefined,{...task,readingMode:'guided',discussionEnabled:false,
    focusQuestions:['第一步清楚吗？','愿意尝试吗？']})
  fireEvent.click(screen.getByRole('button',{name:'移除第二个问题'}))
  expect(screen.queryByLabelText('重点问题 2')).not.toBeInTheDocument()
  fireEvent.click(screen.getByLabelText('自然全文试读'))
  fireEvent.click(screen.getByRole('button',{name:'开始模拟'}))
  expect(run).toHaveBeenLastCalledWith(topic,undefined,{...task,discussionEnabled:false})
})

it('clears adoption on task changes without replacing the selected readers', async()=>{
  const {run,create}=setup();await recommend()
  expect(create).toHaveBeenCalledWith('w',expect.objectContaining({panelTask:task}))
  fireEvent.click(screen.getByRole('button',{name:'采用这组读者'}))
  await screen.findByText('已采用推荐')
  fireEvent.click(screen.getByLabelText('互相回应'))
  expect(screen.queryByText('已采用推荐')).not.toBeInTheDocument()
  expect(screen.queryByRole('button',{name:'采用这组读者'})).not.toBeInTheDocument()
  expect(screen.getByLabelText('第 1 位模拟粉丝')).toHaveValue('d')
  expect(screen.getByRole('button',{name:'确认名单并开始'})).toBeEnabled()
  fireEvent.click(screen.getByRole('button',{name:'确认名单并开始'}))
  expect(run).toHaveBeenLastCalledWith(topic,undefined,{...task,discussionEnabled:false})
})

it('uses one relevant recommendation without filling empty slots and keeps its avatar consistent', async()=>{
  const {create,run}=setup()
  await recommend()
  expect(create).toHaveBeenCalledWith('w',expect.objectContaining({desiredCount:3}))
  expect(screen.queryByRole('button',{name:'我来选择读者'})).not.toBeInTheDocument()
  const recommendationAvatar=within(screen.getByLabelText('读者推荐')).getByRole('img',{name:'读者d的头像'}).innerHTML
  expect(screen.getByRole('button',{name:'开始模拟'})).toBeDisabled()
  fireEvent.click(screen.getByRole('button',{name:'采用这组读者'}))
  await screen.findByText('已采用推荐')
  expect(screen.getByLabelText('第 1 位模拟粉丝')).toHaveValue('d')
  expect(screen.getByLabelText('第 2 位模拟粉丝')).toHaveValue('')
  expect(screen.queryByLabelText('第 3 位模拟粉丝')).not.toBeInTheDocument()
  const finalReaders=screen.getByRole('region',{name:'确认实际参与者'})
  expect(within(finalReaders).getByRole('heading',{name:'参与读者 · 1 位'})).toBeVisible()
  expect(within(finalReaders).getAllByRole('combobox')).toHaveLength(2)
  const currentList=within(finalReaders).getByRole('group',{name:'编辑参与读者'})
  expect(within(currentList).getAllByRole('img')).toHaveLength(1)
  expect(within(currentList).getByRole('img',{name:'读者d的头像'}).innerHTML).toBe(recommendationAvatar)
  fireEvent.click(screen.getByRole('button',{name:'开始模拟'}))
  expect(run).toHaveBeenCalledWith(topic,{readerSelectionId:record.id,readerSelectionInputHash:record.inputHash},task)
})

it('starts with a manual list while recommendation is waiting and keeps it when results arrive',async()=>{
  const {create,run}=setup()
  await ready()
  let resolve!:(result:ReaderSelection)=>void
  create.mockImplementationOnce(()=>new Promise(done=>{resolve=done}))
  fireEvent.change(screen.getByLabelText('第 1 位模拟粉丝'),{target:{value:'a'}})
  await waitFor(()=>expect(screen.getByRole('button',{name:'推荐读者'})).toBeEnabled())
  fireEvent.click(screen.getByRole('button',{name:'推荐读者'}))
  expect(create).toHaveBeenCalledOnce()
  expect(screen.getByRole('button',{name:'正在读取推荐…'})).toBeDisabled()
  expect(screen.getByRole('button',{name:'开始模拟'})).toBeEnabled()
  fireEvent.click(screen.getByRole('button',{name:'开始模拟'}))
  expect(run).toHaveBeenLastCalledWith(topic,undefined,task)
  await act(async()=>resolve(record))
  await screen.findByText('重视开始行动的门槛。')
  expect(screen.getByLabelText('第 1 位模拟粉丝')).toHaveValue('a')
  expect(screen.getByText('手选')).toBeVisible()
  fireEvent.click(screen.getByRole('button',{name:'开始模拟'}))
  expect(run).toHaveBeenLastCalledWith(topic,undefined,task)
})

it('can select readers for the first time after a recommendation request has begun',async()=>{
  const {create,run}=setup()
  await ready()
  let resolve!:(result:ReaderSelection)=>void
  create.mockImplementationOnce(()=>new Promise(done=>{resolve=done}))
  // Loading the reader list changes the recommendation revision; wait for its
  // separate effect to settle before starting the deliberately pending request.
  await waitFor(()=>expect(screen.getByRole('button',{name:'推荐读者'})).toBeEnabled())
  fireEvent.click(screen.getByRole('button',{name:'推荐读者'}))
  expect(create).toHaveBeenCalledOnce()
  expect(screen.getByRole('button',{name:'正在读取推荐…'})).toBeDisabled()
  expect(screen.getByRole('button',{name:'开始模拟'})).toBeDisabled()
  fireEvent.change(screen.getByLabelText('第 1 位模拟粉丝'),{target:{value:'b'}})
  expect(screen.getByRole('button',{name:'开始模拟'})).toBeEnabled()
  fireEvent.click(screen.getByRole('button',{name:'开始模拟'}))
  expect(run).toHaveBeenLastCalledWith(topic,undefined,task)
  await act(async()=>resolve(record))
  expect(screen.getByLabelText('第 1 位模拟粉丝')).toHaveValue('b')
})

it('keeps one editable participant list after adoption and puts start immediately below it',async()=>{
  setup()
  await recommend()
  fireEvent.click(screen.getByRole('button',{name:'采用这组读者'}))
  await screen.findByText('已采用推荐')
  const evidence=screen.getByText('查看推荐依据 · 1 位').closest('details')!
  expect(evidence).not.toHaveAttribute('open')
  expect(screen.getByText('重视开始行动的门槛。')).not.toBeVisible()
  expect(screen.queryByRole('button',{name:'采用这组读者'})).not.toBeInTheDocument()
  expect(screen.queryByRole('group',{name:/画像预览/})).not.toBeInTheDocument()
  const participants=screen.getByRole('region',{name:'确认实际参与者'})
  expect(within(participants).getAllByRole('combobox')).toHaveLength(2)
  expect(within(within(participants).getByRole('group',{name:'编辑参与读者'})).getAllByRole('img')).toHaveLength(1)
  expect(within(participants).getByRole('button',{name:'开始模拟'})).toBeEnabled()
  expect(screen.getByText('调整 读者d 的本次角色').closest('details')).not.toHaveAttribute('open')
  fireEvent.click(screen.getByText('查看推荐依据 · 1 位'))
  expect(screen.getByText('重视开始行动的门槛。')).toBeVisible()
})

it('distinguishes loading from failure and only offers adding readers after a successful empty read',async()=>{
  let reject!:(reason:Error)=>void
  const {list}=setup(record,undefined,undefined,()=>new Promise((_resolve,fail)=>{reject=fail}))
  expect(screen.getByText('正在读取已保存读者…')).toBeVisible()
  expect(screen.queryByRole('button',{name:'从受众分析添加模拟粉丝'})).not.toBeInTheDocument()
  await act(async()=>reject(new Error('断网')))
  expect(screen.getByRole('alert')).toHaveTextContent('读者列表暂时未能读取。')
  expect(screen.getByRole('button',{name:'重试读取读者'})).toBeEnabled()
  expect(screen.queryByRole('button',{name:'从受众分析添加模拟粉丝'})).not.toBeInTheDocument()
  list.mockResolvedValueOnce([])
  fireEvent.click(screen.getByRole('button',{name:'重试读取读者'}))
  await screen.findByText('还没有可用的模拟读者。')
  expect(screen.getByRole('button',{name:'从受众分析添加模拟粉丝'})).toBeEnabled()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  expect(screen.getByRole('button',{name:'开始模拟'})).toBeDisabled()
})

const historicalProfile:TextInputAsset={id:'profile',workspaceId:'w',type:'xhs_creator_profile',name:'历史图文',createdAt:'',updatedAt:'',content:JSON.stringify({
  schemaVersion:'xhs-creator-profile/v1',creator:{displayName:'创作者'},notes:[
    {noteId:'low-performing',title:'阅读不佳的旧图文',desc:'这是原来的完整正文。',metrics:{liked:2,collected:1},comments:[]},
    {noteId:'title-only',title:'仅保留标题的旧图文',desc:'',metrics:{liked:0},comments:[]},
  ],
})}

it('recommends and invites readers for the original historical note without copying it to a topic', async()=>{
  const saved={...record,inputSnapshot:{...record.inputSnapshot,target:{targetType:'note',title:'阅读不佳的旧图文',body:'这是原来的完整正文。'}}}
  const {create,run,runNote}=setup(saved,historicalProfile)
  await ready()
  fireEvent.click(screen.getByRole('button',{name:'已发布的笔记'}))
  expect(screen.getByRole('button',{name:'开始模拟'})).toBeDisabled()
  chooseNote('阅读不佳的旧图文')
  expect(screen.getByText('这是原来的完整正文。')).toBeInTheDocument()
  expect(screen.getByRole('region',{name:'待试读笔记'})).toHaveTextContent('2 赞 · 1 收藏')
  await recommend()
  const payload=create.mock.calls[0][1]
  expect(payload).toMatchObject({sourceMaterialId:'profile',noteId:'low-performing',panelTask:task})
  expect(payload).not.toHaveProperty('topicId')
  fireEvent.click(screen.getByRole('button',{name:'采用这组读者'}))
  await screen.findByText('已采用推荐')
  fireEvent.click(screen.getByRole('button',{name:'开始模拟'}))
  expect(run).not.toHaveBeenCalled()
  expect(runNote).toHaveBeenCalledWith({sourceMaterialId:'profile',noteId:'low-performing'},
    {readerSelectionId:record.id,readerSelectionInputHash:record.inputHash},task)
})

it('clears adopted provenance when changing historical notes and explains title-only input', async()=>{
  const {runNote}=setup(record,historicalProfile)
  await ready()
  fireEvent.click(screen.getByRole('button',{name:'已发布的笔记'}))
  chooseNote('阅读不佳的旧图文')
  await recommend()
  fireEvent.click(screen.getByRole('button',{name:'采用这组读者'}))
  await screen.findByText('已采用推荐')
  chooseNote('仅保留标题的旧图文')
  expect(screen.queryByText('已采用推荐')).not.toBeInTheDocument()
  expect(screen.getByText('只测标题吸引力与阅读期待，写出正文后可再做全文试读。')).toBeVisible()
  expect(screen.getByRole('button',{name:'确认名单并开始'})).toBeEnabled()
  fireEvent.click(screen.getByRole('button',{name:'确认名单并开始'}))
  expect(runNote).toHaveBeenCalledWith({sourceMaterialId:'profile',noteId:'title-only'},undefined,task)
})

it('cancels a new note choice without changing the adopted readers or their local roles',async()=>{
  const {runNote}=setup(record,historicalProfile,'published_note')
  await ready()
  chooseNote('阅读不佳的旧图文')
  await recommend()
  fireEvent.click(screen.getByRole('button',{name:'采用这组读者'}))
  await screen.findByText('已采用推荐')
  fireEvent.change(screen.getByLabelText('读者d的本次视角'),{target:{value:'只关心这篇表达是否清楚。'}})
  fireEvent.click(screen.getByRole('button',{name:'更换笔记'}))
  const picker=screen.getByRole('dialog',{name:'选择试读笔记'})
  expect(within(picker).getByRole('radio',{name:'选择笔记：阅读不佳的旧图文'})).toBeChecked()
  fireEvent.click(within(picker).getByRole('radio',{name:'选择笔记：仅保留标题的旧图文'}))
  fireEvent.click(within(picker).getByRole('button',{name:'取消'}))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.getByRole('region',{name:'待试读笔记'})).toHaveTextContent('阅读不佳的旧图文')
  expect(screen.getByLabelText('读者d的本次视角')).toHaveValue('只关心这篇表达是否清楚。')
  chooseNote('阅读不佳的旧图文')
  expect(screen.getByText('推荐后调整')).toBeVisible()
  fireEvent.click(screen.getByRole('button',{name:'开始模拟'}))
  expect(runNote).toHaveBeenCalledWith({sourceMaterialId:'profile',noteId:'low-performing'},
    {readerSelectionId:record.id,readerSelectionInputHash:record.inputHash},task,{d:{profile:'只关心这篇表达是否清楚。'}})
})

it('selects the exact note id when two imported notes have the same title',async()=>{
  const profile={...historicalProfile,content:JSON.stringify({schemaVersion:'xhs-creator-profile/v1',notes:[
    {noteId:'one',title:'同名笔记',desc:'第一篇原文',metrics:{},comments:[]},
    {noteId:'two',title:'同名笔记',desc:'第二篇原文',metrics:{},comments:[]},
  ]})}
  const {runNote}=setup(record,profile,'published_note')
  await ready()
  fireEvent.click(screen.getByRole('button',{name:'选择笔记'}))
  const picker=screen.getByRole('dialog',{name:'选择试读笔记'})
  fireEvent.click(within(picker).getAllByRole('radio',{name:'选择笔记：同名笔记'})[1])
  fireEvent.click(within(picker).getByRole('button',{name:'完成'}))
  expect(screen.getByText('第二篇原文')).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('第 1 位模拟粉丝'),{target:{value:'a'}})
  fireEvent.click(screen.getByRole('button',{name:'开始模拟'}))
  expect(runNote).toHaveBeenCalledWith({sourceMaterialId:'profile',noteId:'two'},undefined,task)
})

it('closes a pending selection and clears adopted context when the profile source changes',async()=>{
  vi.spyOn(simulatedFanApi,'list').mockResolvedValue(rows)
  vi.spyOn(readerSelectionApi,'create').mockResolvedValue(record)
  vi.spyOn(readerSelectionApi,'get').mockResolvedValue(record)
  const runNote=vi.fn()
  function Page({profile}:{profile:TextInputAsset}){
    const fans=useSimulatedFans('w','')
    return <CreatorSimulationSetup workspaceId="w" positioning="" topics={[]} topic={null} fans={fans}
      running={false} onSelect={()=>{}} onRun={()=>{}} onAddFans={()=>{}} category="published_note" profile={profile} onRunNote={runNote}/>
  }
  const {rerender}=render(<Page profile={historicalProfile}/>);
  await ready()
  chooseNote('阅读不佳的旧图文')
  await recommend()
  fireEvent.click(screen.getByRole('button',{name:'采用这组读者'}))
  await screen.findByText('已采用推荐')
  fireEvent.click(screen.getByRole('button',{name:'更换笔记'}))
  rerender(<Page profile={{...historicalProfile,id:'replacement-profile'}}/>);
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.getByRole('region',{name:'待试读笔记'})).toHaveTextContent('选择一篇已发布笔记')
  expect(screen.queryByText('已采用推荐')).not.toBeInTheDocument()
  expect(screen.getByRole('button',{name:'开始模拟'})).toBeDisabled()
  chooseNote('阅读不佳的旧图文')
  fireEvent.click(screen.getByRole('button',{name:'确认名单并开始'}))
  expect(runNote).toHaveBeenCalledWith({sourceMaterialId:'replacement-profile',noteId:'low-performing'},undefined,task)
})

it('requires explicit account note confirmation before recommending or starting with manual readers', async()=>{
  const {runAccount,run,runNote,create}=setup(record,historicalProfile,'account')
  await ready()
  expect(screen.getByRole('region',{name:'待模拟账号'})).toHaveTextContent('创作者')
  expect(screen.getByText('2 篇已导入笔记 · 尚未选择')).toBeVisible()
  expect(await screen.findByRole('button',{name:'推荐读者'})).toBeDisabled()
  fireEvent.change(screen.getByLabelText('第 1 位模拟粉丝'),{target:{value:'a'}})
  expect(screen.getByRole('button',{name:'开始模拟'})).toBeDisabled()
  expect(screen.queryByText(/12 篇/)).not.toBeInTheDocument()
  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  fireEvent.focus(screen.getByRole('button',{name:'模拟范围说明'}))
  expect(screen.getByRole('tooltip')).toHaveTextContent('从所选笔记出发，聊聊为什么关注、期待什么，以及哪些方向值得持续讲。')
  fireEvent.keyDown(document,{key:'Escape'})
  expect(screen.queryByLabelText('模拟选题')).not.toBeInTheDocument()
  expect(screen.queryByRole('button',{name:'已发布的笔记'})).not.toBeInTheDocument()
  chooseAccountNotes()
  expect(screen.getByText('已选 2 / 2 篇笔记')).toBeVisible()
  fireEvent.focus(screen.getByRole('button',{name:'账号笔记范围说明'}))
  expect(screen.getByRole('tooltip')).toHaveTextContent('只使用你确认的笔记，每篇都会参与；较长文字每篇最多节选 1200 字。')
  fireEvent.click(screen.getByRole('button',{name:'确认名单并开始'}))
  expect(runAccount).toHaveBeenCalledWith({sourceMaterialId:'profile',selectedNoteIds:['low-performing','title-only']},undefined,task)
  expect(run).not.toHaveBeenCalled()
  expect(runNote).not.toHaveBeenCalled()
  expect(create).not.toHaveBeenCalled()
})

it('retrieves account readers without pretending that the account is a topic', async()=>{
  const {create,runAccount}=setup(record,historicalProfile,'account')
  chooseAccountNotes(['阅读不佳的旧图文'])
  await recommend()
  const selection={sourceMaterialId:'profile',selectedNoteIds:['low-performing']}
  expect(create).toHaveBeenCalledWith('w',expect.objectContaining({accountNoteSelection:selection,desiredCount:3}))
  expect(create.mock.calls[0][1]).not.toHaveProperty('topicId')
  expect(create.mock.calls[0][1]).not.toHaveProperty('sourceMaterialId')
  expect(create.mock.calls[0][1]).not.toHaveProperty('accountProfileId')
  fireEvent.click(screen.getByRole('button',{name:'采用这组读者'}))
  await screen.findByText('已采用推荐')
  fireEvent.click(screen.getByRole('button',{name:'开始模拟'}))
  expect(runAccount).toHaveBeenCalledWith(selection,{readerSelectionId:record.id,readerSelectionInputHash:record.inputHash},task)
})

it('suggests only the newest ten notes inside the account picker without confirming them automatically',async()=>{
  const profile={...historicalProfile,content:JSON.stringify({notes:Array.from({length:12},(_,index)=>({
    noteId:`note-${index}`,title:`笔记 ${index}`,desc:'正文',publishedAt:`2026-10-${String(index+1).padStart(2,'0')}T08:00:00Z`,metrics:{liked:index},comments:[],
  }))})}
  const {create,runAccount}=setup(record,profile,'account')
  await ready()
  const picker=openAccountNotePicker()
  expect(within(picker).getByRole('status')).toHaveTextContent('已选 10 / 12 条笔记')
  expect(within(picker).getByRole('checkbox',{name:'选择笔记：笔记 0'})).not.toBeChecked()
  expect(within(picker).getByRole('checkbox',{name:'选择笔记：笔记 11'})).toBeChecked()
  expect(within(picker).getByRole('button',{name:'全选当前范围'})).toBeEnabled()
  expect(within(picker).getByRole('button',{name:'反选当前范围'})).toBeEnabled()
  fireEvent.click(within(picker).getByRole('button',{name:'取消'}))
  expect(screen.getByText('12 篇已导入笔记 · 尚未选择')).toBeVisible()
  expect(screen.getByRole('button',{name:'推荐读者'})).toBeDisabled()
  expect(screen.getByRole('button',{name:'开始模拟'})).toBeDisabled()
  expect(create).not.toHaveBeenCalled()
  expect(runAccount).not.toHaveBeenCalled()
})

it('cancels a changed account selection without discarding the adopted recommendation or local roles',async()=>{
  const {runAccount}=setup(record,historicalProfile,'account')
  chooseAccountNotes()
  await recommend()
  fireEvent.click(screen.getByRole('button',{name:'采用这组读者'}))
  await screen.findByText('已采用推荐')
  fireEvent.change(screen.getByLabelText('读者d的本次视角'),{target:{value:'关注账号的长期方向。'}})
  const picker=openAccountNotePicker()
  fireEvent.click(within(picker).getByRole('checkbox',{name:'选择笔记：仅保留标题的旧图文'}))
  expect(within(picker).getByRole('status')).toHaveTextContent('已选 1 / 2 条笔记')
  fireEvent.click(within(picker).getByRole('button',{name:'取消'}))
  expect(screen.getByText('已选 2 / 2 篇笔记')).toBeVisible()
  expect(screen.getByText('推荐后调整')).toBeVisible()
  expect(screen.getByLabelText('读者d的本次视角')).toHaveValue('关注账号的长期方向。')
  fireEvent.click(screen.getByRole('button',{name:'开始模拟'}))
  expect(runAccount).toHaveBeenCalledWith({sourceMaterialId:'profile',selectedNoteIds:['low-performing','title-only']},
    {readerSelectionId:record.id,readerSelectionInputHash:record.inputHash},task,{d:{profile:'关注账号的长期方向。'}})
})

it('keeps adoption and local roles when the same account note set is confirmed in a different order',async()=>{
  const {get,runAccount}=setup(record,historicalProfile,'account')
  chooseAccountNotes()
  await recommend()
  fireEvent.click(screen.getByRole('button',{name:'采用这组读者'}))
  await screen.findByText('已采用推荐')
  fireEvent.change(screen.getByLabelText('读者d的本次视角'),{target:{value:'关注账号的长期方向。'}})
  const lookups=get.mock.calls.length
  chooseAccountNotes(['仅保留标题的旧图文','阅读不佳的旧图文'])
  expect(screen.getByText('推荐后调整')).toBeVisible()
  expect(screen.getByLabelText('读者d的本次视角')).toHaveValue('关注账号的长期方向。')
  expect(get).toHaveBeenCalledTimes(lookups)
  fireEvent.click(screen.getByRole('button',{name:'开始模拟'}))
  expect(runAccount).toHaveBeenCalledWith({sourceMaterialId:'profile',selectedNoteIds:['low-performing','title-only']},
    {readerSelectionId:record.id,readerSelectionInputHash:record.inputHash},task,{d:{profile:'关注账号的长期方向。'}})
})

it('clears adopted account provenance and local roles when the confirmed note set changes',async()=>{
  const {runAccount}=setup(record,historicalProfile,'account')
  chooseAccountNotes()
  await recommend()
  fireEvent.click(screen.getByRole('button',{name:'采用这组读者'}))
  await screen.findByText('已采用推荐')
  fireEvent.change(screen.getByLabelText('读者d的本次视角'),{target:{value:'关注账号的长期方向。'}})
  chooseAccountNotes(['阅读不佳的旧图文'])
  expect(screen.getByText('已选 1 / 2 篇笔记')).toBeVisible()
  expect(screen.queryByText('已采用推荐')).not.toBeInTheDocument()
  expect(screen.getByLabelText('读者d的本次视角')).toHaveValue(rows[3].editable.profile)
  expect(screen.getByRole('button',{name:'确认名单并开始'})).toBeEnabled()
  fireEvent.click(screen.getByRole('button',{name:'确认名单并开始'}))
  expect(runAccount).toHaveBeenCalledWith({sourceMaterialId:'profile',selectedNoteIds:['low-performing']},undefined,task)
})

it('requires a new account range and clears adopted roles after replacing the source profile',async()=>{
  const {rerenderProfile,runAccount}=setup(record,historicalProfile,'account')
  chooseAccountNotes()
  await recommend()
  fireEvent.click(screen.getByRole('button',{name:'采用这组读者'}))
  await screen.findByText('已采用推荐')
  fireEvent.change(screen.getByLabelText('读者d的本次视角'),{target:{value:'关注账号的长期方向。'}})
  openAccountNotePicker()
  rerenderProfile({...historicalProfile,id:'replacement-profile'})
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.getByText('2 篇已导入笔记 · 尚未选择')).toBeVisible()
  expect(screen.queryByText('已采用推荐')).not.toBeInTheDocument()
  expect(screen.getByLabelText('读者d的本次视角')).toHaveValue(rows[3].editable.profile)
  expect(screen.getByRole('button',{name:'推荐读者'})).toBeDisabled()
  expect(screen.getByRole('button',{name:'开始模拟'})).toBeDisabled()
  chooseAccountNotes(['阅读不佳的旧图文'])
  fireEvent.click(screen.getByRole('button',{name:'确认名单并开始'}))
  expect(runAccount).toHaveBeenCalledWith({sourceMaterialId:'replacement-profile',selectedNoteIds:['low-performing']},undefined,task)
})

it('marks a deleted selected account note as stale and blocks use until the range is confirmed again',async()=>{
  const {rerenderProfile,runAccount}=setup(record,historicalProfile,'account')
  await ready()
  chooseAccountNotes()
  fireEvent.change(screen.getByLabelText('第 1 位模拟粉丝'),{target:{value:'a'}})
  expect(screen.getByRole('button',{name:'开始模拟'})).toBeEnabled()
  const payload=JSON.parse(historicalProfile.content)
  rerenderProfile({...historicalProfile,content:JSON.stringify({...payload,notes:payload.notes.slice(0,1)})})
  expect(screen.getByRole('alert')).toHaveTextContent('已选笔记有变动，范围已过期，请重新选择。')
  expect(screen.getByRole('button',{name:'推荐读者'})).toBeDisabled()
  expect(screen.getByRole('button',{name:'开始模拟'})).toBeDisabled()
  expect(runAccount).not.toHaveBeenCalled()
  chooseAccountNotes()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  expect(screen.getByText('已选 1 / 1 篇笔记')).toBeVisible()
  expect(screen.getByRole('button',{name:'确认名单并开始'})).toBeEnabled()
  fireEvent.click(screen.getByRole('button',{name:'确认名单并开始'}))
  expect(runAccount).toHaveBeenCalledWith({sourceMaterialId:'profile',selectedNoteIds:['low-performing']},undefined,task)
})

it('rechecks changed selected notes and drops stale provenance only through an explicit manual start',async()=>{
  const {get,rerenderProfile,runAccount}=setup(record,historicalProfile,'account')
  chooseAccountNotes(['阅读不佳的旧图文'])
  await recommend()
  fireEvent.click(screen.getByRole('button',{name:'采用这组读者'}))
  await screen.findByText('已采用推荐')
  const lookups=get.mock.calls.length
  const payload=JSON.parse(historicalProfile.content)
  payload.notes[1].title='未选笔记的新标题'
  payload.notes[1].desc='未选笔记的新正文'
  rerenderProfile({...historicalProfile,updatedAt:'v2',content:JSON.stringify(payload)})
  expect(get).toHaveBeenCalledTimes(lookups)
  expect(screen.getByText('已采用推荐')).toBeVisible()
  expect(screen.getByRole('button',{name:'开始模拟'})).toBeEnabled()
  get.mockResolvedValue({...record,freshness:{status:'stale',reasons:['target_changed']}})
  payload.notes[0].desc='已选笔记的新正文'
  rerenderProfile({...historicalProfile,updatedAt:'v3',content:JSON.stringify(payload)})
  await waitFor(()=>expect(get).toHaveBeenCalledTimes(lookups+1))
  await screen.findByText('内容或读者已变化，请重新推荐，或继续手动选择。')
  expect(screen.getByRole('button',{name:'按当前名单开始'})).toBeEnabled()
  expect(runAccount).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button',{name:'按当前名单开始'}))
  expect(runAccount).toHaveBeenCalledWith({sourceMaterialId:'profile',selectedNoteIds:['low-performing']},undefined,task)
  expect(screen.getByLabelText('第 1 位模拟粉丝')).toHaveValue('d')
})

it('keeps one-off reader edits in the simulation request and clears them on changing the target', async()=>{
  const {run}=setup(record,historicalProfile,'creation')
  await ready()
  fireEvent.change(screen.getByLabelText('第 1 位模拟粉丝'),{target:{value:'a'}})
  fireEvent.change(screen.getByLabelText('读者a的本次视角'),{target:{value:'希望十分钟内就有可见进展。'}})
  fireEvent.change(screen.getByLabelText('读者a的本次关切'),{target:{value:'今晚应该从哪个步骤开始。'}})
  fireEvent.change(screen.getByLabelText('读者a的本次表达'),{target:{value:'先问步骤，再给一句具体反馈。'}})
  fireEvent.click(screen.getByRole('button',{name:'开始模拟'}))
  expect(run).toHaveBeenCalledWith(topic,undefined,task,{a:{profile:'希望十分钟内就有可见进展。',coreConcern:'今晚应该从哪个步骤开始。',expressionStyle:'先问步骤，再给一句具体反馈。'}})
  expect(rows[0].editable.profile).toBe('先确认时间投入，再试一次。')
  fireEvent.change(screen.getByLabelText('模拟选题'),{target:{value:'other'}})
  expect(screen.getByLabelText('读者a的本次视角')).toHaveValue(rows[0].editable.profile)
  expect(screen.getByRole('button',{name:'确认名单并开始'})).toBeEnabled()
  fireEvent.click(screen.getByRole('button',{name:'确认名单并开始'}))
  expect(run).toHaveBeenLastCalledWith(expect.objectContaining({id:'other'}),undefined,task)
})

it('does not revive one-off edits after removing and reselecting a reader', async()=>{
  const {runNote}=setup(record,historicalProfile,'published_note')
  await ready()
  expect(screen.queryByLabelText('模拟选题')).not.toBeInTheDocument()
  fireEvent.mouseEnter(screen.getByRole('button',{name:'模拟范围说明'}))
  expect(screen.getByRole('tooltip')).toHaveTextContent('这次复盘用于下一篇同类内容，不会修改已发布的原文。')
  chooseNote('阅读不佳的旧图文')
  fireEvent.change(screen.getByLabelText('第 1 位模拟粉丝'),{target:{value:'a'}})
  fireEvent.change(screen.getByLabelText('读者a的本次视角'),{target:{value:'只看本次修改。'}})
  fireEvent.change(screen.getByLabelText('第 1 位模拟粉丝'),{target:{value:''}})
  fireEvent.change(screen.getByLabelText('第 1 位模拟粉丝'),{target:{value:'a'}})
  expect(screen.getByLabelText('读者a的本次视角')).toHaveValue(rows[0].editable.profile)
  fireEvent.click(screen.getByRole('button',{name:'开始模拟'}))
  expect(runNote).toHaveBeenCalledWith({sourceMaterialId:'profile',noteId:'low-performing'},undefined,task)
})

it('explains mutual replies without toggling the checkbox or nesting the hint inside its label',async()=>{
  setup()
  await ready()
  const checkbox=screen.getByRole('checkbox',{name:'互相回应'})
  const hint=screen.getByRole('button',{name:'互相回应说明'})
  expect(checkbox).toBeChecked()
  expect(hint.closest('label')).toBeNull()
  fireEvent.focus(hint)
  expect(screen.getByRole('tooltip')).toHaveTextContent('先各自表达，再回应其他人的公开留言。')
  expect(checkbox).toBeChecked()
  fireEvent.click(checkbox)
  expect(checkbox).not.toBeChecked()
  expect(screen.getByRole('tooltip')).toHaveTextContent('只做独立表达，省去互相回应。')
})

it('marks adjusted recommended roles and prevents a blank local override before submitting', async()=>{
  const {run}=setup()
  await recommend()
  fireEvent.click(screen.getByRole('button',{name:'采用这组读者'}))
  await screen.findByText('已采用推荐')
  fireEvent.change(screen.getByLabelText('读者d的本次关切'),{target:{value:'  '}})
  expect(screen.getByText('推荐后调整')).toBeVisible()
  expect(screen.getByRole('button',{name:'开始模拟'})).toBeDisabled()
  expect(screen.getByText(/请补全调整后的角色设定/)).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('读者d的本次关切'),{target:{value:'今天就能完成哪一步'}})
  expect(screen.getByRole('button',{name:'开始模拟'})).toBeEnabled()
  fireEvent.click(screen.getByRole('button',{name:'开始模拟'}))
  expect(run).toHaveBeenCalledWith(topic,{readerSelectionId:record.id,readerSelectionInputHash:record.inputHash},task,{d:{coreConcern:'今天就能完成哪一步'}})
  fireEvent.click(screen.getByRole('button',{name:'恢复已保存画像'}))
  expect(screen.getByText('已采用推荐')).toBeVisible()
})
