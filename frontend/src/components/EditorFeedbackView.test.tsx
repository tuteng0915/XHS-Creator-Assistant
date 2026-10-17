import {cleanup, fireEvent, render, screen, within} from '@testing-library/react'
import {afterEach, expect, it, vi} from 'vitest'
import type {ActivityEvent, SimulationRun} from '../types'
import {applySimulationStageEvent, stageSeedFromSimulation} from '../workflowStageViews'
import {StageResultRenderer} from './ArtifactRenderers'
import {SynthesisView} from './StageResultViews'
import {SimulationHistoryPage} from './SimulationHistoryPage'
import type {StageView} from './WorkflowOutputPanel'
import {feedbackGroups, verifiedConcerns} from '../editorFeedback'
import {EditorFeedbackView} from './EditorFeedbackView'

afterEach(()=>{cleanup();vi.restoreAllMocks()})
const card={id:'f1',kind:'keep',sourceType:'reader',sourceMessageIds:['initial:a'],
  observation:'保留这一步',reason:'读者已知道如何开始。',priority:'first',beneficiaries:['a'],tradeoff:'',suggestedText:'',
  target:{field:'body',quote:'先试一次。',occurrence:2,start:7,end:12,coordinateSystem:'unicode_code_points',contentHash:'hash'}}
const data={verdict:'方向清楚',contentAdjustments:['旧版调整'],editorFeedback:[card],editorFeedbackValidation:{status:'validated',rejected:[]}}
const run={id:'r',workspaceId:'w',status:'completed',createdAt:'2026-10-05',inputSnapshot:{topic:{title:'先试一次',body:'🌱先试一次。\n先试一次。'},targetContentHash:'hash'},
  personaDefinitions:[{id:'a',name:'安静派'}],reactionResults:[{personaId:'a',messageId:'initial:a',action:'no_comment',understanding:'步骤清楚',quote:'不该展示的假公开评论'}],
  debateResults:[],synthesis:data,stageErrors:{}} as unknown as SimulationRun
const renderer=(stage:StageView)=><StageResultRenderer stage={stage} currentRun={null} onSaveGeneratedTopic={vi.fn()} onSelectTopic={vi.fn()} onGenerateBrief={vi.fn()} onGenerateDraft={vi.fn()} onFillSimulationTopic={vi.fn()}/>
const open=()=>fireEvent.click(screen.getByText('查看依据与原文'))

it('renders private reading evidence and highlights the second occurrence after an emoji',()=>{
  const before=JSON.stringify(run)
  const fetch=vi.spyOn(globalThis,'fetch')
  render(<SynthesisView data={data} feedbackRun={run}/>)
  expect(screen.getByText('值得保留')).toBeInTheDocument()
  expect(screen.queryByText('旧版调整')).not.toBeInTheDocument()
  expect(screen.getByText('当时理解：步骤清楚')).not.toBeVisible()
  open()
  expect(screen.getByText('安静派 · 试读感受（未公开留言）')).toBeVisible()
  expect(screen.queryByText('不该展示的假公开评论')).not.toBeInTheDocument()
  const mark=document.querySelector('mark')!
  expect(mark.textContent).toBe('先试一次。')
  expect(mark.previousSibling?.textContent).toBe('🌱先试一次。\n')
  expect(fetch).not.toHaveBeenCalled()
  expect(JSON.stringify(run)).toBe(before)
  expect(screen.queryByRole('button',{name:/采用|改稿/})).not.toBeInTheDocument()
})

it('orders strengths before changes and collapses optional editor suggestions',()=>{
  render(<SynthesisView data={{...data,editorFeedback:[
    {...card,id:'change',kind:'clarify',observation:'解释成本',suggestedText:'每天十分钟',tradeoff:'篇幅会增加'},
    {...card,id:'optional',sourceType:'editor_optional',sourceMessageIds:[],kind:'explore',priority:'optional',observation:'换个开头'},card,
  ]}} feedbackRun={run}/>)
  expect(screen.getAllByRole('heading',{level:5}).map(el=>el.textContent)).toEqual(['保留这一步','解释成本','换个开头'])
  expect(screen.getByText('换个开头')).not.toBeVisible()
  fireEvent.click(screen.getByText('其他可选建议（1）'))
  expect(screen.getByText('换个开头')).toBeVisible()
  expect(screen.getByText('这是编辑助手的额外建议，不是读者已经提出的问题。')).not.toBeVisible()
  fireEvent.click(screen.getAllByText('查看依据与原文')[2])
  expect(screen.getByText('这是编辑助手的额外建议，不是读者已经提出的问题。')).toBeVisible()
})

it.each(['invalid','not_returned','validated'])('keeps string fallback when feedback is %s',status=>{
  render(<SynthesisView data={{...data,editorFeedback:[],editorFeedbackValidation:{status,rejected:status==='invalid'?[{index:0}]:[]}}}/>)
  expect(screen.getByText('旧版调整')).toBeVisible()
  expect(screen.getByText(status==='validated'?'本次没有具体修改建议。':'这次未生成可用的修改建议，可查看读者发言或重新试读。')).toBeVisible()
})

it('retains legacy presentation without surfacing internal rejection counts',()=>{
  const {rerender}=render(<SynthesisView data={{verdict:'旧结论',contentAdjustments:['旧版调整']}}/>)
  expect(screen.queryByRole('region',{name:'创作修改反馈'})).not.toBeInTheDocument()
  rerender(<SynthesisView data={{...data,editorFeedbackValidation:{status:'partial',rejected:[{index:1}]}}} feedbackRun={run}/>)
  expect(screen.queryByText(/条反馈未通过/)).not.toBeInTheDocument()
  expect(screen.getByText('保留这一步')).toBeVisible()
})

it.each([{contentHash:'other'},{start:1,end:6},{occurrence:1},{coordinateSystem:'utf16'}])('does not highlight an invalid frozen anchor %j',change=>{
  render(<SynthesisView data={{...data,editorFeedback:[{...card,target:{...card.target,...change}}]}} feedbackRun={run}/>)
  open()
  expect(screen.getByText(/原文位置暂无法核对/)).toBeVisible()
  expect(document.querySelector('mark')).toBeNull()
})

it('shows missing sources rather than substituting another reader',()=>{
  render(<SynthesisView data={data} feedbackRun={{...run,reactionResults:[]}}/>)
  open();expect(screen.getByText('这条来源发言未保存或无法核对。')).toBeVisible()
})

it('falls back on malformed imported cards without rendering unknown enum values',()=>{
  render(<SynthesisView data={{...data,editorFeedback:[null,{...card,kind:'__proto__'},{...card,sourceType:'unknown'}]}} feedbackRun={run}/>)
  expect(screen.getByText('旧版调整')).toBeVisible()
  expect(screen.queryByText(/条反馈未通过/)).not.toBeInTheDocument()
  expect(screen.getByText('这次未生成可用的修改建议，可查看读者发言或重新试读。')).toBeVisible()
  expect(screen.queryByText('保留这一步')).not.toBeInTheDocument()
})

it('uses the history run and resets expanded evidence on switching runs',()=>{
  const props={publicMode:true,simulationRuns:[],selectedSimulationRun:run,simulationReviewDraft:{reviewStatus:'unreviewed' as const,userNotes:''},simulationReviewSaveState:{phase:'idle' as const},reviewStatusLabel:(s:string)=>s,onOpenSimulationRun:vi.fn(),onSimulationReviewDraftChange:vi.fn(),onSaveSimulationRunReview:vi.fn(),stageSeedFromSimulation,renderStageResult:renderer}
  const {rerender}=render(<SimulationHistoryPage {...props}/>);open()
  expect(screen.getByText('当时理解：步骤清楚')).toBeVisible()
  rerender(<SimulationHistoryPage {...props} selectedSimulationRun={{...run,id:'next',reactionResults:[{...run.reactionResults[0],understanding:'另一次理解'}]}}/> )
  expect(screen.getByText('当时理解：另一次理解')).not.toBeVisible()
  expect(screen.queryByText('当时理解：步骤清楚')).not.toBeInTheDocument()
})

it('carries the correct frozen context through SSE and rejects events for another run',()=>{
  let views=stageSeedFromSimulation({...run,personaDefinitions:[],reactionResults:[],debateResults:[],synthesis:{}})
  function event(stageKey:string,fields:Record<string,unknown>):ActivityEvent{return {runId:'r',stageKey,data:{eventType:'stage.succeeded',...fields}} as ActivityEvent}
  views=applySimulationStageEvent(views,event('personas',{personas:run.personaDefinitions}))
  views=applySimulationStageEvent(views,event('initial_reactions',{reactions:run.reactionResults}))
  views=applySimulationStageEvent(views,event('synthesis',{synthesis:data}))
  expect(applySimulationStageEvent(views,{...event('synthesis',{synthesis:{}}),runId:'other'})).toBe(views)
  render(renderer(views.find(s=>s.key==='synthesis')!));open()
  expect(screen.getByText('当时理解：步骤清楚')).toBeVisible()
  expect(document.querySelector('mark')?.textContent).toBe('先试一次。')
})

it('shows successive partial SSE results without declaring the stage complete',()=>{
  let views=stageSeedFromSimulation({...run,reactionResults:[],debateResults:[],synthesis:{}})
  const event=(reactions:Record<string,unknown>[],kind='stage.progress'):ActivityEvent=>({eventId:'partial',runId:run.id,runType:'audience_simulation',stageKey:'initial_reactions',status:'running',sequence:1,occurredAt:run.createdAt,data:{eventType:kind,reactions}})
  views=applySimulationStageEvent(views,event(run.reactionResults.slice(0,1)))
  expect(views.find(s=>s.key==='initial_reactions')?.status).toBe('running')
  expect(views.find(s=>s.key==='initial_reactions')?.result).toEqual({reactions:run.reactionResults.slice(0,1)})
  const more=[...run.reactionResults,{personaId:'other',understanding:'另一个具体判断'}]
  views=applySimulationStageEvent(views,event(more))
  expect(views.find(s=>s.key==='synthesis')?.feedbackRun?.reactionResults).toEqual(more)
  views=applySimulationStageEvent(views,event(more,'stage.succeeded'))
  expect(views.find(s=>s.key==='initial_reactions')?.status).toBe('completed')
})

const concern={id:'concern:1',messageId:'initial:a',personaId:'a',field:'concerns',text:'两个版本都正确时，该根据什么选择？'}
const concernedRun={...run,reactionResults:[{...run.reactionResults[0],concerns:[concern.text]}]}
const change={...card,kind:'clarify',observation:'补充选择标准',readerConcernIds:[concern.id],readerConcerns:[concern]}
const other={...change,id:'f2',kind:'add_material',observation:'用一个对照示例',suggestedText:'看看哪个版本更容易找到活动时间。'}

it('groups verified alternatives without losing cards or modifying the stored run',()=>{
  const before=JSON.stringify(concernedRun)
  render(<SynthesisView data={{...data,editorFeedback:[change,other]}} feedbackRun={concernedRun}/>)
  expect(screen.getByRole('region',{name:'同一问题的 2 种改法'})).toBeVisible()
  expect(screen.getAllByText(concern.text)).toHaveLength(1)
  expect(screen.getByText('安静派 · 试读顾虑记录（非公开原话）')).not.toBeVisible()
  fireEvent.click(screen.getByText('查看共同关注点'))
  expect(screen.getByText('安静派 · 试读顾虑记录（非公开原话）')).toBeVisible()
  expect(screen.getByText('改法 1')).toBeVisible()
  expect(screen.getByText('改法 2')).toBeVisible()
  expect(screen.getByText('用一个对照示例')).toBeVisible()
  expect(screen.getByText(/不必逐条都改/)).toBeVisible()
  expect(screen.queryByRole('button',{name:/采用|应用/})).not.toBeInTheDocument()
  fireEvent.click(screen.getAllByText('查看依据与原文')[1])
  expect(screen.getAllByText('安静派 · 试读感受（未公开留言）')[0]).not.toBeVisible()
  expect(screen.getAllByText('安静派 · 试读感受（未公开留言）')[1]).toBeVisible()
  expect(JSON.stringify(concernedRun)).toBe(before)
})

it.each(['different_concern','different_anchor','different_priority','missing_run','mismatched_text','duplicate_source','wrong_person','empty_reply'])('does not group unverified or different cases: %s',mode=>{
  let second:Record<string,unknown>=other
  let context:typeof concernedRun|undefined=concernedRun
  if(mode==='different_concern') {
    const next={...concern,id:'concern:2',text:'先核对什么？'}
    second={...other,readerConcernIds:[next.id],readerConcerns:[next]}
    context={...concernedRun,reactionResults:[{...concernedRun.reactionResults[0],concerns:[concern.text,next.text]}]}
  } else if(mode==='different_anchor') second={...other,target:{...other.target,start:1,end:6,occurrence:1}}
  else if(mode==='different_priority') second={...other,priority:'optional'}
  else if(mode==='missing_run') context=undefined
  else if(mode==='mismatched_text') second={...other,readerConcerns:[{...concern,text:'不是当时的顾虑'}]}
  else if(mode==='duplicate_source') context={...concernedRun,reactionResults:[...concernedRun.reactionResults,...concernedRun.reactionResults]}
  else if(mode==='wrong_person') second={...other,readerConcerns:[{...concern,personaId:'unknown'}]}
  else second={...other,readerConcerns:[{...concern,field:'newConcerns'}]}
  expect(feedbackGroups([change,second],context)).toHaveLength(2)
})

it('keeps legacy cards readable and shows unverifiable concerns without guessing',()=>{
  const {rerender}=render(<SynthesisView data={{...data,editorFeedback:[{...card,kind:'clarify'}]}} feedbackRun={run}/>)
  open()
  expect(screen.getByText('此记录未保存具体顾虑关联，仍可查看当时发言。')).toBeVisible()
  rerender(<SynthesisView data={{...data,editorFeedback:[change]}} feedbackRun={run}/>)
  expect(screen.getByText('具体顾虑暂无法核对，仍可查看当时发言。')).toBeVisible()
  expect(screen.queryByText(concern.text)).not.toBeInTheDocument()
})

it('verifies reply assessments separately from the public response',()=>{
  const c={...concern,id:'c:reply',messageId:'reply:a',field:'newConcerns'}
  const current={...run,debateResults:[{messageId:'reply:a',personaId:'a',response:'你提的对',newConcerns:[c.text]}]}
  const replyCard={...change,sourceMessageIds:['reply:a'],readerConcernIds:[c.id],readerConcerns:[c]}
  expect(verifiedConcerns(replyCard,current)).toEqual([c])
  render(<SynthesisView data={{...data,editorFeedback:[replyCard]}} feedbackRun={current}/>)
  expect(screen.getByText('安静派 · 回应后的顾虑记录（非公开原话）')).not.toBeVisible()
  open()
  expect(screen.getByText('安静派 · 回应后的顾虑记录（非公开原话）')).toBeVisible()
  expect(screen.getByText('你提的对')).toBeVisible()
  expect(verifiedConcerns(replyCard,{...current,debateResults:[{...current.debateResults[0],response:''}]})).toBeNull()
})

it('does not mix optional editor ideas into reader alternatives',()=>{
  const editor={...other,sourceType:'editor_optional',sourceMessageIds:[],readerConcernIds:[],readerConcerns:[],priority:'optional'}
  expect(feedbackGroups([change,editor],concernedRun)).toHaveLength(2)
  expect(verifiedConcerns({...change,readerConcernIds:[concern.id,concern.id]},concernedRun)).toBeNull()
})

it('puts the concrete suggestion and preview before folded explanation without mutating the result',()=>{
  const onPrepare=vi.fn(), suggested='先看哪一个版本能让你找到活动时间。\n再核对地点。'
  const current={...change,suggestedText:suggested,tradeoff:'多占用一行，但比较更直接。'}
  const before=JSON.stringify(current)
  render(<EditorFeedbackView data={{editorFeedback:[current]}} run={concernedRun} onPrepare={onPrepare}/>)
  expect(screen.getByText('正文')).toBeVisible()
  expect(screen.getByText(suggested,{normalizer:value=>value})).toBeVisible()
  expect(screen.getByText(current.reason)).not.toBeVisible()
  expect(screen.getByText(/多占用一行/)).not.toBeVisible()
  expect(screen.getByText(concern.text)).not.toBeVisible()
  const button=screen.getByRole('button',{name:'查看改写'})
  expect(button.compareDocumentPosition(screen.getByText('查看依据与原文')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(onPrepare).not.toHaveBeenCalled()
  fireEvent.click(button)
  expect(onPrepare).toHaveBeenCalledWith(current)
  open()
  expect(screen.getByText(current.reason)).toBeVisible()
  expect(screen.getByText(/更适合：安静派/)).toBeVisible()
  expect(screen.getByText(/多占用一行/)).toBeVisible()
  expect(JSON.stringify(current)).toBe(before)
})

it('preserves long expressions in full and does not stringify malformed optional fields',()=>{
  const suggested='逐条核对，不用一次全改。'.repeat(50)+'https://example.com/'+ 'a'.repeat(140)
  const {container}=render(<EditorFeedbackView data={{editorFeedback:[{...change,suggestedText:suggested,tradeoff:{text:'不可字符串化'},beneficiaries:null}]}} run={concernedRun}/>)
  expect(screen.getByText(suggested)).toBeVisible()
  expect(container.textContent).not.toContain('[object Object]')
  expect(screen.queryByText(/更适合：/)).not.toBeInTheDocument()
  expect(screen.queryByText(/尚未写入稿件/)).not.toBeInTheDocument()
  expect(screen.queryByRole('button')).not.toBeInTheDocument()
})

it('keeps material questions visible, leaves old unverified text folded, and offers only verified local actions',()=>{
  const material={...other,materialRequests:['你实际比较过的两个版本是什么？'],suggestedText:'未经确认的经历'}
  const whole={...material,id:'whole',target:{field:'whole',quote:'',occurrence:1,contentHash:'hash'}}
  render(<EditorFeedbackView data={{editorFeedback:[material,whole]}} run={concernedRun} onPrepare={vi.fn()}/>)
  expect(screen.getByText('整篇内容')).toBeVisible()
  for(const question of screen.getAllByText(material.materialRequests[0])) expect(question).toBeVisible()
  expect(screen.getAllByText('未经确认的经历')[0]).not.toBeVisible()
  expect(screen.getAllByRole('button',{name:'补充素材'})).toHaveLength(1)
  expect(screen.queryByText('可参考的表达')).not.toBeInTheDocument()
  fireEvent.click(screen.getAllByText('查看旧版参考文字（未核实）')[0])
  expect(screen.getAllByText('未经确认的经历')[0]).toBeVisible()
})

it('never exposes a local action for an invalid anchor and respects edit blocking',()=>{
  const onPrepare=vi.fn()
  const {rerender}=render(<EditorFeedbackView data={{editorFeedback:[change]}} run={concernedRun} onPrepare={onPrepare} editDisabled/>)
  const button=screen.getByRole('button',{name:'查看改写'})
  expect(button).toBeDisabled()
  fireEvent.click(button); expect(onPrepare).not.toHaveBeenCalled()
  rerender(<EditorFeedbackView data={{editorFeedback:[{...change,target:{...change.target,contentHash:'wrong'}}]}} run={concernedRun} onPrepare={onPrepare}/>)
  expect(screen.queryByText('正文')).not.toBeInTheDocument()
  expect(screen.queryByRole('button')).not.toBeInTheDocument()
})

it('retains separate cards with identical headings but different reader concerns',()=>{
  const second={...concern,id:'concern:2',text:'可以补一个实际例子吗？'}
  const secondCard={...change,id:'f2',readerConcernIds:[second.id],readerConcerns:[second]}
  render(<EditorFeedbackView data={{editorFeedback:[change,secondCard]}} run={{...concernedRun,reactionResults:[{...concernedRun.reactionResults[0],concerns:[concern.text,second.text]}]}}/>)
  expect(screen.getAllByRole('heading',{name:change.observation})).toHaveLength(2)
  expect(screen.queryByText('同一问题的 2 种改法')).not.toBeInTheDocument()
  for(const article of screen.getAllByRole('article')) expect(within(article).getByText('查看依据与原文')).toBeVisible()
})

it('shows the explanation when a change has no concrete replacement instead of leaving an empty card',()=>{
  render(<EditorFeedbackView data={{editorFeedback:[{...change,suggestedText:'',target:{field:'whole',quote:'',occurrence:1,contentHash:'hash'}}]}} run={concernedRun} onPrepare={vi.fn()}/>)
  expect(screen.getByText(change.reason)).toBeVisible()
  expect(screen.getAllByText(change.reason)).toHaveLength(1)
  expect(screen.queryByText('可参考的表达')).not.toBeInTheDocument()
  expect(screen.queryByRole('button')).not.toBeInTheDocument()
  expect(screen.queryByText(/先预览/)).not.toBeInTheDocument()
})
