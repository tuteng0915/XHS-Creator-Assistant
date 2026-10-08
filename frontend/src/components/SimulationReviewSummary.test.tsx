import {act, cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react'
import {afterEach, beforeEach, expect, it, vi} from 'vitest'
import {simulationRunApi} from '../api'
import {panelInterviewApi} from '../panelInterview'
import type {SimulationRun, Topic} from '../types'
import {simulationCategoryFor} from '../simulationChat'
import {SimulationChat} from './SimulationChat'

const run:SimulationRun={id:'review',workspaceId:'w',topicId:null,draftId:null,status:'completed',simulationCategory:'account',
  inputSnapshot:{targetType:'account',topic:{title:'读写账号'},sourceAccount:{scope:{omissionNotice:'从 20 篇中选取 12 篇。'}}},
  personaDefinitions:[],reactionResults:[],debateResults:[],
  synthesis:{verdict:'旧结论不重复显示',editorFeedback:{summary:'不应该出现的改稿方案'},review:{summary:'读者喜欢轻量而具体的读写练习。',readerNeeds:['想在碎片时间开始'],keepDoing:['保持具体示例'],nextTimeSuggestions:['用系列回答读者的新问题'],topicIdeas:[{id:'idea-1',title:'写下第一句话',angle:'从一件小事开始',whyItFits:'回应读者的起步需求'}]}},
  stageErrors:{},modelMetadata:{},userNotes:'',reviewStatus:'unreviewed',createdAt:'2026-10-08T00:00:00Z',updatedAt:'2026-10-08T00:00:00Z',startedAt:null,completedAt:null}
const topic:Topic={id:'new-topic',workspaceId:'w',title:'写下第一句话',angle:'从一件小事开始',associatedPainPoint:'',whyItFits:'回应读者的起步需求',generatedSnapshot:{sourceSimulationId:'review',sourceTopicIdeaId:'idea-1'},sourceAnalysisRunId:null,sourceWorkflow:'manual',status:'candidate',createdAt:'',updatedAt:''}
beforeEach(()=>{vi.spyOn(panelInterviewApi,'list').mockResolvedValue([])})
afterEach(()=>{cleanup();vi.restoreAllMocks()})

it('shows account directions and sampling, never treats the account as a title-only draft',()=>{
  const adopt=vi.spyOn(simulationRunApi,'adoptTopicIdea').mockResolvedValue(topic)
  render(<SimulationChat run={run}/>)
  expect(screen.getByRole('heading',{name:'账号读者群聊'})).toBeVisible()
  expect(screen.getByRole('heading',{name:'读者期待这个账号持续做什么'})).toBeVisible()
  expect(screen.getByText(/从 20 篇中选取 12 篇/)).toBeVisible()
  expect(screen.getByText('想在碎片时间开始')).toBeVisible()
  expect(screen.queryByText(/本次只看标题/)).not.toBeInTheDocument()
  expect(screen.queryByText('这次试读带来的修改方向')).not.toBeInTheDocument()
  expect(screen.queryByText('不应该出现的改稿方案')).not.toBeInTheDocument()
  expect(adopt).not.toHaveBeenCalled()
})

it('keeps published post review focused on next time and adopts only the clicked idea',async()=>{
  let resolve!:(topic:Topic)=>void
  const adopt=vi.spyOn(simulationRunApi,'adoptTopicIdea').mockReturnValue(new Promise(done=>{resolve=done}))
  const onTopicAdded=vi.fn()
  render(<SimulationChat run={{...run,simulationCategory:'published_note',inputSnapshot:{targetType:'note',topic:{title:'旧笔记',body:'正文'}}}} onTopicAdded={onTopicAdded}/>)
  expect(screen.getByText('下一篇同类型内容，可以这样做')).toBeVisible()
  expect(screen.getByText('已发布笔记保持原样，讨论下一篇同类型内容可以怎么做。')).toBeVisible()
  fireEvent.click(screen.getByRole('button',{name:'加入选题库'}))
  expect(screen.getByRole('button',{name:'正在加入…'})).toBeDisabled()
  expect(adopt).toHaveBeenCalledExactlyOnceWith('w','review','idea-1')
  await act(async()=>{resolve(topic)})
  expect(screen.getByRole('button',{name:'已加入选题库'})).toBeDisabled()
  expect(onTopicAdded).toHaveBeenCalledExactlyOnceWith(topic)
})

it('preserves a failed idea and allows a manual retry',async()=>{
  const adopt=vi.spyOn(simulationRunApi,'adoptTopicIdea').mockRejectedValueOnce(new Error('连接中断')).mockResolvedValue(topic)
  render(<SimulationChat run={run}/>)
  fireEvent.click(screen.getByRole('button',{name:'加入选题库'}))
  expect(await screen.findByRole('alert')).toHaveTextContent('连接中断')
  expect(adopt).toHaveBeenCalledOnce()
  fireEvent.click(screen.getByRole('button',{name:'加入选题库'}))
  await screen.findByRole('button',{name:'已加入选题库'})
  expect(adopt).toHaveBeenCalledTimes(2)
})

it('retains adopted state when reopening a record, including later edited topics',()=>{
  const adopt=vi.spyOn(simulationRunApi,'adoptTopicIdea')
  render(<SimulationChat run={run} topics={[{...topic,title:'作者后来改过的标题'}]}/>)
  expect(screen.getByRole('button',{name:'已加入选题库'})).toBeDisabled()
  expect(screen.getByText('写下第一句话')).toBeVisible()
  expect(adopt).not.toHaveBeenCalled()
})

it('waits for final review persistence before enabling manual adoption',()=>{
  render(<SimulationChat run={{...run,status:'running'}}/>)
  expect(screen.getByRole('button',{name:'等待复盘完成'})).toBeDisabled()
})

it('does not apply a late adoption response to another record',async()=>{
  let resolve!:(topic:Topic)=>void
  vi.spyOn(simulationRunApi,'adoptTopicIdea').mockReturnValue(new Promise(done=>{resolve=done}))
  const onTopicAdded=vi.fn()
  const page=render(<SimulationChat run={run} onTopicAdded={onTopicAdded}/>)
  fireEvent.click(screen.getByRole('button',{name:'加入选题库'}))
  page.rerender(<SimulationChat run={{...run,id:'another',workspaceId:'other'}} onTopicAdded={onTopicAdded}/>)
  await act(async()=>{resolve(topic)})
  expect(onTopicAdded).not.toHaveBeenCalled()
  expect(screen.getByRole('button',{name:'加入选题库'})).toBeEnabled()
})

it('rejects a mismatched account receipt',async()=>{
  vi.spyOn(simulationRunApi,'adoptTopicIdea').mockResolvedValue({...topic,workspaceId:'other'})
  const onTopicAdded=vi.fn()
  render(<SimulationChat run={run} onTopicAdded={onTopicAdded}/>)
  fireEvent.click(screen.getByRole('button',{name:'加入选题库'}))
  await waitFor(()=>expect(screen.getByRole('alert')).toHaveTextContent('账号不匹配'))
  expect(onTopicAdded).not.toHaveBeenCalled()
})

it('reads legacy note records without relabeling old edits as a new review',()=>{
  const legacy={...run,simulationCategory:undefined,inputSnapshot:{targetType:'note'},synthesis:{verdict:'旧版本结论',contentAdjustments:['旧版本修改建议']}}
  expect(simulationCategoryFor(legacy)).toBe('published_note')
  expect(simulationCategoryFor({...legacy,inputSnapshot:{}})).toBe('creation')
  render(<SimulationChat run={legacy}/>)
  expect(screen.getByText(/这是旧版记录/)).toBeVisible()
  expect(screen.getByText('旧版本修改建议')).not.toBeVisible()
  fireEvent.click(screen.getByText('查看旧版结论'))
  expect(screen.getByText('旧版本修改建议')).toBeVisible()
  expect(screen.queryByRole('button',{name:'加入选题库'})).not.toBeInTheDocument()
})
