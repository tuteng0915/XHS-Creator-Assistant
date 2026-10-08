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
function setup(saved:ReaderSelection=record, profile?:TextInputAsset, category?:SimulationCategory) {
  vi.spyOn(simulatedFanApi,'list').mockResolvedValue(rows)
  const create=vi.spyOn(readerSelectionApi,'create').mockResolvedValue(saved)
  const get=vi.spyOn(readerSelectionApi,'get').mockResolvedValue(saved)
  const run=vi.fn()
  const runNote=vi.fn()
  const runAccount=vi.fn()
  function Page(){
    const fans=useSimulatedFans('w','')
    const [selected,setSelected]=useState<Topic|null>(topic)
    return <CreatorSimulationSetup workspaceId="w" positioning="" topics={[topic,{...topic,id:'other',title:'其他选题'}]}
      topic={selected} fans={fans} running={false} onSelect={setSelected} onRun={run} onAddFans={()=>{}}
      category={category} profile={profile} onRunNote={runNote} onRunAccount={runAccount} />
  }
  render(<Page />)
  return {create,get,run,runNote,runAccount}
}
async function ready(){
  await waitFor(()=>expect(screen.getAllByRole('option',{name:'读者a'})).toHaveLength(3))
}
async function recommend(){
  await ready()
  await waitFor(()=>expect(screen.getByRole('button',{name:'推荐读者'})).toBeEnabled())
  fireEvent.click(screen.getByRole('button',{name:'推荐读者'}))
  await screen.findByText('重视开始行动的门槛。')
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
  fireEvent.click(screen.getByRole('button',{name:'使用这组'}))
  await screen.findByText('已采用推荐，可继续调整名单。')
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
  fireEvent.click(screen.getByRole('button',{name:'使用这组'}))
  await screen.findByText('推荐已变化或暂时无法核验，名单未改变。')
  expect(screen.getByLabelText('第 1 位模拟粉丝')).toHaveValue('a')
  expect(screen.getByRole('button',{name:'使用这组'})).toBeDisabled()
  expect(screen.getByRole('button',{name:'开始模拟'})).toBeDisabled()
  fireEvent.click(screen.getByRole('button',{name:'我来选择读者'}))
  expect(screen.getByRole('button',{name:'开始模拟'})).toBeEnabled()
})

it('locks topic and reader editing during explicit adoption verification', async()=>{
  const {get}=setup();await recommend()
  let finish!:(value:ReaderSelection)=>void
  get.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
  fireEvent.click(screen.getByRole('button',{name:'使用这组'}))
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
  expect(screen.queryByText('已采用推荐，可继续调整名单。')).not.toBeInTheDocument()
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
  expect(screen.queryByRole('button',{name:'使用这组'})).not.toBeInTheDocument()
})

it('retains fewer valid readers and renders no-match without fabricating slots', async()=>{
  const {get}=setup({...record,status:'partially_completed'})
  await recommend();expect(screen.getByText('部分完成，已保留有效读者。')).toBeInTheDocument()
  get.mockResolvedValue({...record,result:{proposedReaders:[],unmatchedReason:'现有读者不贴合这篇内容。'}})
  fireEvent.click(screen.getByRole('button',{name:'重新推荐读者'}))
  await screen.findByText('现有读者不贴合这篇内容。')
  expect(screen.getByLabelText('第 1 位模拟粉丝')).toHaveValue('')
  expect(screen.getByRole('button',{name:'开始模拟'})).toBeDisabled()
  expect(screen.queryByRole('button',{name:'使用这组'})).not.toBeInTheDocument()
})

it('does not carry adopted provenance to another topic', async()=>{
  const {run}=setup();await recommend()
  fireEvent.click(screen.getByRole('button',{name:'使用这组'}))
  await screen.findByText('已采用推荐，可继续调整名单。')
  fireEvent.change(screen.getByLabelText('模拟选题'),{target:{value:'other'}})
  expect(screen.getByRole('button',{name:'开始模拟'})).toBeDisabled()
  fireEvent.click(screen.getByRole('button',{name:'我来选择读者'}))
  fireEvent.click(screen.getByRole('button',{name:'开始模拟'}))
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
  fireEvent.click(screen.getByRole('button',{name:'使用这组'}))
  await screen.findByText('已采用推荐，可继续调整名单。')
  fireEvent.click(screen.getByLabelText('互相回应'))
  expect(screen.queryByText('已采用推荐，可继续调整名单。')).not.toBeInTheDocument()
  expect(screen.queryByRole('button',{name:'使用这组'})).not.toBeInTheDocument()
  expect(screen.getByLabelText('第 1 位模拟粉丝')).toHaveValue('d')
  expect(screen.getByRole('button',{name:'开始模拟'})).toBeDisabled()
  fireEvent.click(screen.getByRole('button',{name:'我来选择读者'}))
  fireEvent.click(screen.getByRole('button',{name:'开始模拟'}))
  expect(run).toHaveBeenLastCalledWith(topic,undefined,{...task,discussionEnabled:false})
})

it('uses one relevant recommendation without filling empty slots and keeps its avatar consistent', async()=>{
  const {create,run}=setup()
  await recommend()
  expect(create).toHaveBeenCalledWith('w',expect.objectContaining({desiredCount:3}))
  expect(screen.getByText('最多推荐 3 位；只有一位相关，也可以直接开始。')).toBeVisible()
  const recommendationAvatar=within(screen.getByLabelText('读者推荐')).getByRole('img',{name:'读者d的头像'}).innerHTML
  expect(screen.getByRole('button',{name:'开始模拟'})).toBeDisabled()
  fireEvent.click(screen.getByRole('button',{name:'使用这组'}))
  await screen.findByText('已采用推荐，可继续调整名单。')
  expect(screen.getByLabelText('第 1 位模拟粉丝')).toHaveValue('d')
  expect(screen.getByLabelText('第 2 位模拟粉丝')).toHaveValue('')
  expect(screen.getByLabelText('第 3 位模拟粉丝')).toHaveValue('')
  const finalReaders=screen.getByRole('region',{name:'确认实际参与者'})
  expect(within(finalReaders).getByRole('heading',{name:'本次实际参与 · 1 位'})).toBeVisible()
  expect(within(finalReaders).getAllByRole('listitem')).toHaveLength(1)
  expect(within(finalReaders).getByRole('img',{name:'读者d的头像'}).innerHTML).toBe(recommendationAvatar)
  fireEvent.click(screen.getByRole('button',{name:'开始模拟'}))
  expect(run).toHaveBeenCalledWith(topic,{readerSelectionId:record.id,readerSelectionInputHash:record.inputHash},task)
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
  fireEvent.change(screen.getByLabelText('试读历史笔记'),{target:{value:'low-performing'}})
  expect(screen.getByText('这是原来的完整正文。')).toBeInTheDocument()
  expect(screen.getByRole('option',{name:'阅读不佳的旧图文 · 2 赞 / 1 收藏'})).toBeInTheDocument()
  await recommend()
  const payload=create.mock.calls[0][1]
  expect(payload).toMatchObject({sourceMaterialId:'profile',noteId:'low-performing',panelTask:task})
  expect(payload).not.toHaveProperty('topicId')
  fireEvent.click(screen.getByRole('button',{name:'使用这组'}))
  await screen.findByText('已采用推荐，可继续调整名单。')
  fireEvent.click(screen.getByRole('button',{name:'开始模拟'}))
  expect(run).not.toHaveBeenCalled()
  expect(runNote).toHaveBeenCalledWith({sourceMaterialId:'profile',noteId:'low-performing'},
    {readerSelectionId:record.id,readerSelectionInputHash:record.inputHash},task)
})

it('clears adopted provenance when changing historical notes and explains title-only input', async()=>{
  const {runNote}=setup(record,historicalProfile)
  await ready()
  fireEvent.click(screen.getByRole('button',{name:'已发布的笔记'}))
  fireEvent.change(screen.getByLabelText('试读历史笔记'),{target:{value:'low-performing'}})
  await recommend()
  fireEvent.click(screen.getByRole('button',{name:'使用这组'}))
  await screen.findByText('已采用推荐，可继续调整名单。')
  fireEvent.change(screen.getByLabelText('试读历史笔记'),{target:{value:'title-only'}})
  expect(screen.queryByText('已采用推荐，可继续调整名单。')).not.toBeInTheDocument()
  expect(screen.getByText('只测标题吸引力与阅读期待，写出正文后可再做全文试读。')).toBeVisible()
  expect(screen.getByRole('button',{name:'开始模拟'})).toBeDisabled()
  fireEvent.click(screen.getByRole('button',{name:'我来选择读者'}))
  fireEvent.click(screen.getByRole('button',{name:'开始模拟'}))
  expect(runNote).toHaveBeenCalledWith({sourceMaterialId:'profile',noteId:'title-only'},undefined,task)
})

it('opens account simulation with real profile context and allows direct manual selection', async()=>{
  const {runAccount,run,runNote,create}=setup(record,historicalProfile,'account')
  await ready()
  expect(screen.getByRole('region',{name:'待模拟账号'})).toHaveTextContent('创作者')
  expect(screen.getByText('2 篇已导入笔记')).toBeVisible()
  expect(screen.queryByLabelText('模拟选题')).not.toBeInTheDocument()
  expect(screen.queryByRole('button',{name:'已发布的笔记'})).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('第 1 位模拟粉丝'),{target:{value:'a'}})
  fireEvent.click(screen.getByRole('button',{name:'开始模拟'}))
  expect(runAccount).toHaveBeenCalledWith('profile',undefined,task)
  expect(run).not.toHaveBeenCalled()
  expect(runNote).not.toHaveBeenCalled()
  expect(create).not.toHaveBeenCalled()
})

it('retrieves account readers without pretending that the account is a topic', async()=>{
  const {create,runAccount}=setup(record,historicalProfile,'account')
  await recommend()
  expect(create).toHaveBeenCalledWith('w',expect.objectContaining({accountProfileId:'profile',desiredCount:3}))
  expect(create.mock.calls[0][1]).not.toHaveProperty('topicId')
  expect(create.mock.calls[0][1]).not.toHaveProperty('sourceMaterialId')
  fireEvent.click(screen.getByRole('button',{name:'使用这组'}))
  await screen.findByText('已采用推荐，可继续调整名单。')
  fireEvent.click(screen.getByRole('button',{name:'开始模拟'}))
  expect(runAccount).toHaveBeenCalledWith('profile',{readerSelectionId:record.id,readerSelectionInputHash:record.inputHash},task)
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
  expect(screen.getByRole('button',{name:'开始模拟'})).toBeDisabled()
  fireEvent.click(screen.getByRole('button',{name:'我来选择读者'}))
  fireEvent.click(screen.getByRole('button',{name:'开始模拟'}))
  expect(run).toHaveBeenLastCalledWith(expect.objectContaining({id:'other'}),undefined,task)
})

it('does not revive one-off edits after removing and reselecting a reader', async()=>{
  const {runNote}=setup(record,historicalProfile,'published_note')
  await ready()
  expect(screen.queryByLabelText('模拟选题')).not.toBeInTheDocument()
  expect(screen.getByText('这次复盘用于下一篇同类内容，不会修改已发布的原文。')).toBeVisible()
  fireEvent.change(screen.getByLabelText('试读历史笔记'),{target:{value:'low-performing'}})
  fireEvent.change(screen.getByLabelText('第 1 位模拟粉丝'),{target:{value:'a'}})
  fireEvent.change(screen.getByLabelText('读者a的本次视角'),{target:{value:'只看本次修改。'}})
  fireEvent.change(screen.getByLabelText('第 1 位模拟粉丝'),{target:{value:''}})
  fireEvent.change(screen.getByLabelText('第 1 位模拟粉丝'),{target:{value:'a'}})
  expect(screen.getByLabelText('读者a的本次视角')).toHaveValue(rows[0].editable.profile)
  fireEvent.click(screen.getByRole('button',{name:'开始模拟'}))
  expect(runNote).toHaveBeenCalledWith({sourceMaterialId:'profile',noteId:'low-performing'},undefined,task)
})

it('marks adjusted recommended roles and prevents a blank local override before submitting', async()=>{
  const {run}=setup()
  await recommend()
  fireEvent.click(screen.getByRole('button',{name:'使用这组'}))
  await screen.findByText('已采用推荐，可继续调整名单。')
  fireEvent.change(screen.getByLabelText('读者d的本次关切'),{target:{value:'  '}})
  expect(screen.getByText('已采用推荐，并调整了名单或本次角色')).toBeVisible()
  expect(screen.getByRole('button',{name:'开始模拟'})).toBeDisabled()
  expect(screen.getByText(/请补全调整后的角色设定/)).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('读者d的本次关切'),{target:{value:'今天就能完成哪一步'}})
  expect(screen.getByRole('button',{name:'开始模拟'})).toBeEnabled()
  fireEvent.click(screen.getByRole('button',{name:'开始模拟'}))
  expect(run).toHaveBeenCalledWith(topic,{readerSelectionId:record.id,readerSelectionInputHash:record.inputHash},task,{d:{coreConcern:'今天就能完成哪一步'}})
  fireEvent.click(screen.getByRole('button',{name:'恢复已保存画像'}))
  expect(screen.getByText('使用推荐名单')).toBeVisible()
})
