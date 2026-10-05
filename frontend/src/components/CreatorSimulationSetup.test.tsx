import {useState} from 'react'
import {act, cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react'
import {afterEach, beforeEach, expect, it, vi} from 'vitest'
import {memoryStorage} from '../test/storage'
import {readerSelectionApi, simulatedFanApi} from '../api'
import {useSimulatedFans} from '../hooks/useSimulatedFans'
import {readerSelectionStorageKey} from '../hooks/useReaderSelection'
import type {ReaderSelection} from '../readerSelection'
import type {PanelTask, SimulatedFan, Topic} from '../types'
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
function setup(saved:ReaderSelection=record) {
  vi.spyOn(simulatedFanApi,'list').mockResolvedValue(rows)
  const create=vi.spyOn(readerSelectionApi,'create').mockResolvedValue(saved)
  const get=vi.spyOn(readerSelectionApi,'get').mockResolvedValue(saved)
  const run=vi.fn()
  function Page(){
    const fans=useSimulatedFans('w','')
    const [selected,setSelected]=useState<Topic|null>(topic)
    return <CreatorSimulationSetup workspaceId="w" positioning="" topics={[topic,{...topic,id:'other',title:'其他选题'}]}
      topic={selected} fans={fans} running={false} onSelect={setSelected} onRun={run} onAddFans={()=>{}} />
  }
  render(<Page />)
  return {create,get,run}
}
async function recommend(){
  await waitFor(()=>expect(screen.getByLabelText('第 1 位模拟粉丝')).toHaveValue('a'))
  await waitFor(()=>expect(screen.getByRole('button',{name:'推荐读者'})).toBeEnabled())
  fireEvent.click(screen.getByRole('button',{name:'推荐读者'}))
  await screen.findByText('重视开始行动的门槛。')
}

it('previews the target first and does not replace manual choices until explicit adoption', async()=>{
  const {create,run}=setup()
  await recommend()
  expect(create).toHaveBeenCalledTimes(1)
  expect(screen.getByText(topic.body!)).toBeInTheDocument()
  expect(screen.getByLabelText('第 1 位模拟粉丝')).toHaveValue('a')
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
  const {get}=setup();await recommend()
  get.mockResolvedValue({...record,freshness:{status:'stale',reasons:['target_changed']}})
  fireEvent.click(screen.getByRole('button',{name:'使用这组'}))
  await screen.findByText('推荐已变化或暂时无法核验，名单未改变。')
  expect(screen.getByLabelText('第 1 位模拟粉丝')).toHaveValue('a')
  expect(screen.getByRole('button',{name:'使用这组'})).toBeDisabled()
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
  expect(screen.getByLabelText('第 1 位模拟粉丝')).toHaveValue('a')
  expect(create).not.toHaveBeenCalled()
  expect(screen.queryByText('已采用推荐，可继续调整名单。')).not.toBeInTheDocument()
})

it('does not require recommendation success to manually simulate', async()=>{
  setup({...record,status:'failed',result:null,errorCode:'model_error'})
  await waitFor(()=>expect(screen.getByLabelText('第 1 位模拟粉丝')).toHaveValue('a'))
  await waitFor(()=>expect(screen.getByRole('button',{name:'推荐读者'})).toBeEnabled())
  fireEvent.click(screen.getByRole('button',{name:'推荐读者'}))
  await screen.findByText('本次推荐未完成，可重新推荐或手动选择。')
  expect(screen.getByRole('button',{name:'开始模拟'})).toBeEnabled()
  expect(screen.queryByRole('button',{name:'使用这组'})).not.toBeInTheDocument()
})

it('retains fewer valid readers and renders no-match without fabricating slots', async()=>{
  const {get}=setup({...record,status:'partially_completed'})
  await recommend();expect(screen.getByText('部分完成，已保留有效读者。')).toBeInTheDocument()
  get.mockResolvedValue({...record,result:{proposedReaders:[],unmatchedReason:'现有读者不贴合这篇内容。'}})
  fireEvent.click(screen.getByRole('button',{name:'重新推荐读者'}))
  await screen.findByText('现有读者不贴合这篇内容。')
  expect(screen.getByLabelText('第 1 位模拟粉丝')).toHaveValue('a')
  expect(screen.queryByRole('button',{name:'使用这组'})).not.toBeInTheDocument()
})

it('does not carry adopted provenance to another topic', async()=>{
  const {run}=setup();await recommend()
  fireEvent.click(screen.getByRole('button',{name:'使用这组'}))
  await screen.findByText('已采用推荐，可继续调整名单。')
  fireEvent.change(screen.getByLabelText('模拟选题'),{target:{value:'other'}})
  fireEvent.click(screen.getByRole('button',{name:'开始模拟'}))
  expect(run).toHaveBeenLastCalledWith(expect.objectContaining({id:'other'}),undefined,task)
})

it('requires one or two nonempty guided questions and passes the task to manual simulation', async()=>{
  const {run}=setup()
  await waitFor(()=>expect(screen.getByLabelText('第 1 位模拟粉丝')).toHaveValue('a'))
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
  fireEvent.click(screen.getByRole('button',{name:'开始模拟'}))
  expect(run).toHaveBeenLastCalledWith(topic,undefined,{...task,discussionEnabled:false})
})
