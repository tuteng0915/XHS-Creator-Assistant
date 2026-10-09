import {act, cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react'
import {afterEach, beforeEach, expect, it, vi} from 'vitest'
import {simulationRunApi} from '../api'
import {panelInterviewApi} from '../panelInterview'
import type {SimulationRun, Topic} from '../types'
import {simulationCategoryFor} from '../simulationChat'
import {SimulationChat} from './SimulationChat'
import {SimulationReviewSummary} from './SimulationReviewSummary'

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
  expect(screen.getByText('用系列回答读者的新问题')).toBeVisible()
  expect(screen.getByText('想在碎片时间开始')).not.toBeVisible()
  expect(screen.getByText('保持具体示例')).not.toBeVisible()
  fireEvent.click(screen.getByText('读者在意什么'))
  expect(screen.getByText('想在碎片时间开始')).toBeVisible()
  fireEvent.click(screen.getByText('值得继续保持'))
  expect(screen.getByText('保持具体示例')).toBeVisible()
  expect(screen.queryByText(/本次只看标题/)).not.toBeInTheDocument()
  expect(screen.queryByRole('heading',{name:'修改方向'})).not.toBeInTheDocument()
  expect(screen.queryByText('不应该出现的改稿方案')).not.toBeInTheDocument()
  expect(adopt).not.toHaveBeenCalled()
})

it('keeps topic actions and angles visible while unfolding the complete rationale on demand',()=>{
  const rationale='这条选题回应读者希望从身边的小事起步的需求，同时延续账号用完整实例解释写作步骤的方式。无需更改原有内容，也不假定每位读者都有相同起点。'
  render(<SimulationReviewSummary run={{...run,synthesis:{review:{summary:'先从读者熟悉的小事开始。',topicIdeas:[{id:'idea-1',title:'写下第一句话',angle:'从一件小事开始',whyItFits:rationale}]}}}}/>)
  expect(screen.getByText('写下第一句话')).toBeVisible()
  expect(screen.getByText('从一件小事开始')).toBeVisible()
  expect(screen.getByRole('button',{name:'加入选题库'})).toBeEnabled()
  expect(screen.getByText(rationale)).not.toBeVisible()
  expect(screen.queryByText('选择你想继续的方向，点选后加入选题库。')).not.toBeInTheDocument()
  fireEvent.click(screen.getByText('为什么适合'))
  expect(screen.getByText(rationale)).toBeVisible()
})

it('preserves read-only review details while removing adoption actions',()=>{
  const adopt=vi.spyOn(simulationRunApi,'adoptTopicIdea').mockResolvedValue(topic)
  const onTopicAdded=vi.fn()
  render(<SimulationReviewSummary readOnly run={run} onTopicAdded={onTopicAdded}/>)
  expect(screen.getByText('读者喜欢轻量而具体的读写练习。')).toBeVisible()
  expect(screen.getByText('用系列回答读者的新问题')).toBeVisible()
  expect(screen.getByText('写下第一句话')).toBeVisible()
  expect(screen.getByText('从一件小事开始')).toBeVisible()
  fireEvent.click(screen.getByText('读者在意什么'))
  fireEvent.click(screen.getByText('值得继续保持'))
  fireEvent.click(screen.getByText('为什么适合'))
  expect(screen.getByText('想在碎片时间开始')).toBeVisible()
  expect(screen.getByText('保持具体示例')).toBeVisible()
  expect(screen.getByText('回应读者的起步需求')).toBeVisible()
  expect(screen.queryByRole('button')).not.toBeInTheDocument()
  expect(adopt).not.toHaveBeenCalled()
  expect(onTopicAdded).not.toHaveBeenCalled()
})

it.each(['account','published_note'] as const)('forwards read-only mode from %s chat to its review summary',(simulationCategory)=>{
  const adopt=vi.spyOn(simulationRunApi,'adoptTopicIdea').mockResolvedValue(topic)
  const create=vi.spyOn(panelInterviewApi,'create')
  render(<SimulationChat readOnly run={{...run,simulationCategory,personaDefinitions:[{id:'a',name:'读者甲'}]}}/>)
  expect(screen.getByText('读者喜欢轻量而具体的读写练习。')).toBeVisible()
  expect(screen.getByText('写下第一句话')).toBeVisible()
  fireEvent.click(screen.getByText('为什么适合'))
  expect(screen.getByText('回应读者的起步需求')).toBeVisible()
  expect(screen.queryByRole('button',{name:'加入选题库'})).not.toBeInTheDocument()
  expect(screen.queryByLabelText('作者追问')).not.toBeInTheDocument()
  expect(adopt).not.toHaveBeenCalled()
  expect(panelInterviewApi.list).not.toHaveBeenCalled()
  expect(create).not.toHaveBeenCalled()
})

it.each([
  {review:{nextTimeSuggestions:['用系列回答读者的新问题']},visible:'用系列回答读者的新问题'},
  {review:{readerNeeds:['想在碎片时间开始']},visible:'读者在意什么'},
  {review:{keepDoing:['保持具体示例']},visible:'值得继续保持'},
  {review:{topicIdeas:[{id:'idea-1',title:'写下第一句话'}]},visible:'写下第一句话'},
])('does not hide a valid review without a summary: $visible',({review,visible})=>{
  render(<SimulationReviewSummary run={{...run,synthesis:{verdict:'旧版本结论',review}}}/>)
  expect(screen.getByText(visible)).toBeVisible()
  expect(screen.queryByText(/这是旧版记录/)).not.toBeInTheDocument()
  expect(screen.queryByText('旧版本结论')).not.toBeInTheDocument()
})

it('does not create blank sections or pretend an empty review is a legacy conclusion',()=>{
  render(<SimulationReviewSummary run={{...run,synthesis:{review:{summary:'  ',readerNeeds:[' ',null,17],keepDoing:[],nextTimeSuggestions:false,topicIdeas:[{id:' ',title:'无效'},{id:'idea',title:'  '}]}}}}/>)
  expect(screen.getByText('暂未生成复盘结论。')).toBeVisible()
  expect(screen.queryByText(/这是旧版记录/)).not.toBeInTheDocument()
  expect(screen.queryByText('读者在意什么')).not.toBeInTheDocument()
  expect(screen.queryByText('值得继续保持')).not.toBeInTheDocument()
  expect(screen.queryByRole('region',{name:'待选选题'})).not.toBeInTheDocument()
})

it('keeps published post review focused on next time and adopts only the clicked idea',async()=>{
  let resolve!:(topic:Topic)=>void
  const adopt=vi.spyOn(simulationRunApi,'adoptTopicIdea').mockReturnValue(new Promise(done=>{resolve=done}))
  const onTopicAdded=vi.fn()
  render(<SimulationChat run={{...run,simulationCategory:'published_note',inputSnapshot:{targetType:'note',topic:{title:'旧笔记',body:'正文'}}}} onTopicAdded={onTopicAdded}/>)
  expect(screen.getByText('下一篇同类型内容，可以这样做')).toBeVisible()
  expect(screen.getByText('讨论下一篇同类内容；已发布笔记不作修改。')).toBeVisible()
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

it('preserves legacy records containing only editor feedback cards',()=>{
  const legacy={...run,synthesis:{editorFeedback:[{id:'feedback-1',kind:'keep',sourceType:'reader',priority:'first',observation:'保留完整示例',reason:'读者能从示例中看到如何开始。'}]}}
  render(<SimulationReviewSummary run={legacy}/>)
  expect(screen.getByText(/这是旧版记录/)).toBeVisible()
  expect(screen.queryByText('暂未生成复盘结论。')).not.toBeInTheDocument()
  expect(screen.getByText('保留完整示例')).not.toBeVisible()
  fireEvent.click(screen.getByText('查看旧版结论'))
  expect(screen.getByText('保留完整示例')).toBeVisible()
  expect(screen.getByText('读者能从示例中看到如何开始。')).toBeVisible()
})

it('retains the legacy disclosure for an object-shaped feedback record, but not an empty array',()=>{
  const page=render(<SimulationReviewSummary run={{...run,synthesis:{editorFeedback:{summary:'旧版反馈对象'}}}}/>)
  expect(screen.getByText('查看旧版结论')).toBeVisible()
  page.rerender(<SimulationReviewSummary run={{...run,synthesis:{editorFeedback:[]}}}/>)
  expect(screen.queryByText('查看旧版结论')).not.toBeInTheDocument()
  expect(screen.getByText('暂未生成复盘结论。')).toBeVisible()
})
