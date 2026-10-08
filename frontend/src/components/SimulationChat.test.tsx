import {StrictMode} from 'react'
import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react'
import {afterEach, beforeEach, expect, it, vi} from 'vitest'
import {simulationRunApi} from '../api'
import {panelInterviewApi, type PanelInterview} from '../panelInterview'
import type {SimulationRun} from '../types'
import {visibleReply} from '../simulationChat'
import {SimulationChat} from './SimulationChat'

const run:SimulationRun={id:'run',workspaceId:'w',topicId:'topic',draftId:null,status:'completed',
  inputSnapshot:{topic:{title:'每天记一个词',body:'试着记一个词，漏一天也不用补。'},panelTask:{discussionEnabled:true}},
  personaDefinitions:[{id:'a',name:'轻松尝试型',sourceAnalysisId:'analysis',sourceGroupId:'group-a'},{id:'b',name:'细节求证型'}],
  reactionResults:[{personaId:'a',action:'comment',quote:'不用补，我愿意试一次。',understanding:'可以断续进行'},{personaId:'b',action:'no_comment',quote:'这句旧评论不该显示'}],
  debateResults:[{personaId:'b',targetedAt:'wrong',replyToId:'initial:a',response:'@initial:a 我也更喜欢这个节奏。'}],
  synthesis:{},stageErrors:{},modelMetadata:{},userNotes:'',reviewStatus:'unreviewed',
  createdAt:'2026-10-08T00:00:00Z',updatedAt:'2026-10-08T00:00:00Z',startedAt:'2026-10-08T00:00:00Z',completedAt:'2026-10-08T00:00:02Z'}
const round:PanelInterview={id:'interview',status:'completed',question:'哪一句让你更愿意试？',completedReplies:1,totalReplies:1,currentParticipantName:'',error:'',elapsedSeconds:2,
  messages:[{id:'q',role:'author',personaId:null,senderName:'作者',recipientName:'轻松尝试型',recipientPersonaId:'a',content:'哪一句让你更愿意试？',createdAt:''},
    {id:'r',role:'reader',personaId:'a',senderName:'轻松尝试型',recipientName:'作者',recipientPersonaId:null,content:'不用补这三个字，感觉负担很小。',createdAt:''}]}
beforeEach(()=>{vi.spyOn(panelInterviewApi,'list').mockResolvedValue([])})
afterEach(()=>{cleanup();vi.useRealTimers();vi.restoreAllMocks()})

it('shows public dialogue, named replies and hidden reading notes without inventing comments',async()=>{
  render(<SimulationChat run={run}/>)
  expect(screen.getByText('不用补，我愿意试一次。')).toBeVisible()
  expect(screen.getByText('回复 轻松尝试型')).toBeVisible()
  expect(screen.getByText('@轻松尝试型 我也更喜欢这个节奏。')).toBeVisible()
  expect(screen.getByText('读完了，暂时没有留言')).toBeVisible()
  expect(screen.queryByText('这句旧评论不该显示')).not.toBeInTheDocument()
  expect(screen.getByText('可以断续进行')).not.toBeVisible()
  fireEvent.click(screen.getByText('查看试读记录'))
  expect(screen.getByText('可以断续进行')).toBeVisible()
  await waitFor(()=>expect(panelInterviewApi.list).toHaveBeenCalledOnce())
})

it('keeps legacy draft scope distinct from title-only previews',async()=>{
  const page=render(<SimulationChat run={{...run,inputSnapshot:{topic:{title:'标题'},draft:{editableContent:{structure:{outline:[]}}}}}}/>)
  expect(screen.queryByText(/本次只看标题/)).not.toBeInTheDocument()
  page.rerender(<SimulationChat run={{...run,inputSnapshot:{topic:{title:'标题'}}}}/>)
  expect(screen.getByText(/本次只看标题/)).toBeVisible()
  await waitFor(()=>expect(panelInterviewApi.list).toHaveBeenCalledOnce())
})

it('reveals each persisted reader before the simulation finishes and stops after terminal',async()=>{
  vi.useFakeTimers()
  const observed=vi.fn(),get=vi.spyOn(simulationRunApi,'get').mockResolvedValue({...run,status:'running'})
  const page=render(<SimulationChat run={{...run,status:'running',reactionResults:[],debateResults:[]}} onObserved={observed}/>)
  expect(screen.getByText('读者独立试读 · 0/2 已返回')).toBeVisible()
  await act(async()=>{await vi.advanceTimersByTimeAsync(500)})
  expect(observed).toHaveBeenCalledWith(expect.objectContaining({reactionResults:run.reactionResults}))
  page.rerender(<SimulationChat run={{...run,status:'running'}} onObserved={observed}/>)
  expect(screen.getByText('不用补，我愿意试一次。')).toBeVisible()
  get.mockResolvedValue(run)
  await act(async()=>{await vi.advanceTimersByTimeAsync(1300)})
  await act(async()=>{await vi.advanceTimersByTimeAsync(8000)})
  expect(get).toHaveBeenCalledTimes(2)
})

it('retains received comments on polling failure without issuing another model request',async()=>{
  vi.useFakeTimers()
  const observed=vi.fn(),get=vi.spyOn(simulationRunApi,'get').mockRejectedValue(new Error('network'))
  render(<SimulationChat run={{...run,status:'running'}} onObserved={observed}/>)
  await act(async()=>{await vi.advanceTimersByTimeAsync(500)})
  expect(screen.getByRole('alert')).toHaveTextContent('已收到的发言保留')
  expect(screen.getByText('不用补，我愿意试一次。')).toBeVisible()
  await act(async()=>{await vi.advanceTimersByTimeAsync(8000)})
  expect(get).toHaveBeenCalledOnce()
  get.mockResolvedValue(run)
  fireEvent.click(screen.getByRole('button',{name:'恢复查看'}))
  await act(async()=>{await vi.advanceTimersByTimeAsync(500)})
  expect(observed).toHaveBeenCalledOnce()
})

it('rejects an unrelated run receipt',async()=>{
  vi.useFakeTimers()
  vi.spyOn(simulationRunApi,'get').mockResolvedValue({...run,workspaceId:'other'})
  const observed=vi.fn()
  render(<SimulationChat run={{...run,status:'running'}} onObserved={observed}/>)
  await act(async()=>{await vi.advanceTimersByTimeAsync(500)})
  expect(observed).not.toHaveBeenCalled()
  expect(screen.getByRole('alert')).toBeVisible()
})

it('moves past independent reading after a failed reader settles',()=>{
  render(<SimulationChat run={{...run,status:'running',reactionResults:[run.reactionResults[0]],
    stageErrors:{'initial_reactions.b':'连接失败'}}}/>)
  expect(screen.getByText('互相回应并整理修改建议')).toBeVisible()
  expect(screen.queryByText(/读者独立试读/)).not.toBeInTheDocument()
})

it('lets the author address one reader in StrictMode and displays the saved answer',async()=>{
  const create=vi.spyOn(panelInterviewApi,'create').mockImplementation(async()=>{vi.mocked(panelInterviewApi.list).mockResolvedValue([round]);return round})
  render(<StrictMode><SimulationChat run={run}/></StrictMode>)
  await waitFor(()=>expect(panelInterviewApi.list).toHaveBeenCalled())
  fireEvent.change(screen.getByLabelText('作者追问'),{target:{value:round.question}})
  fireEvent.click(screen.getByRole('button',{name:'加入讨论'}))
  await screen.findByText('不用补这三个字，感觉负担很小。')
  expect(create).toHaveBeenCalledWith('w','run',expect.objectContaining({question:round.question,recipientPersonaId:'a'}))
  expect(screen.getByLabelText('作者追问')).toHaveValue('')
  expect(within(screen.getByRole('log',{name:'访谈发言'})).getByText('作者 · 你')).toBeVisible()
})

it('reuses an uncertain request receipt only when the author explicitly retries',async()=>{
  const create=vi.spyOn(panelInterviewApi,'create').mockRejectedValueOnce(new Error('连接中断')).mockResolvedValue(round)
  render(<SimulationChat run={run}/>)
  await waitFor(()=>expect(panelInterviewApi.list).toHaveBeenCalledOnce())
  fireEvent.change(screen.getByLabelText('访谈对象'),{target:{value:''}})
  fireEvent.change(screen.getByLabelText('作者追问'),{target:{value:round.question}})
  fireEvent.click(screen.getByRole('button',{name:'加入讨论'}))
  await screen.findByText(/连接中断/)
  expect(screen.getByLabelText('作者追问')).toHaveValue(round.question)
  expect(create).toHaveBeenCalledOnce()
  fireEvent.click(screen.getByRole('button',{name:'加入讨论'}))
  await waitFor(()=>expect(create).toHaveBeenCalledTimes(2))
  expect(create.mock.calls[0][2]).toEqual(create.mock.calls[1][2])
  expect(create.mock.calls[1][2].recipientPersonaId).toBeNull()
})

it('removes unknown long mention IDs from public dialogue',()=>{
  expect(visibleReply('@initial:abcdefab-1234-5678-1234-123456789abc 请补充',[])).toBe('@读者 请补充')
})
