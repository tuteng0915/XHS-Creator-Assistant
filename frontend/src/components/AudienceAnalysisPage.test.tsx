import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { audienceAnalysisApi, simulatedFanApi } from '../api'
import type { AudienceAnalysis, TextInputAsset } from '../types'
import { AudienceAnalysisPage } from './AudienceAnalysisPage'

afterEach(() => {cleanup(); vi.restoreAllMocks()})

const importedProfile: TextInputAsset = {id:'profile',workspaceId:'w',name:'测试',type:'xhs_creator_profile',createdAt:'',updatedAt:'',content:JSON.stringify({notes:[
  {noteId:'n1',title:'笔记一',desc:'正文一',metrics:{liked:1},comments:[]},
  {noteId:'n2',title:'笔记二',desc:'正文二',metrics:{liked:9},comments:[]},
]})}

it('uses the shared preview selection and submits the exact confirmed note IDs', async () => {
  const create = vi.spyOn(audienceAnalysisApi,'create').mockResolvedValue({id:'created'} as AudienceAnalysis)
  const select = vi.fn()
  render(<AudienceAnalysisPage workspaceId="w" profile={importedProfile} analyses={[]} selectedId="" onSelect={select} onRefresh={vi.fn().mockResolvedValue(undefined)} onSimulate={vi.fn()} />)
  fireEvent.click(screen.getByRole('button',{name:'调整范围'}))
  fireEvent.click(screen.getByRole('button',{name:'取消选择'}))
  fireEvent.change(screen.getByLabelText('排序'),{target:{value:'liked'}})
  fireEvent.click(screen.getByRole('checkbox',{name:'选择笔记：笔记二'}))
  expect(create).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button',{name:'完成'}))
  expect(screen.getByText('已选 1 条笔记')).toBeVisible()
  fireEvent.click(screen.getByRole('button',{name:'分析受众'}))
  await waitFor(() => expect(create).toHaveBeenCalledExactlyOnceWith('w','profile','most_liked_10',['n2']))
  await waitFor(() => expect(select).toHaveBeenCalledWith('created'))
})

it('cancels selection changes and blocks stale confirmed selections', async () => {
  const create = vi.spyOn(audienceAnalysisApi,'create').mockResolvedValue({id:'created'} as AudienceAnalysis)
  const props = {workspaceId:'w',profile:importedProfile,analyses:[],selectedId:'',onSelect:vi.fn(),onRefresh:vi.fn().mockResolvedValue(undefined),onSimulate:vi.fn()}
  const view = render(<AudienceAnalysisPage {...props} />)
  fireEvent.click(screen.getByRole('button',{name:'调整范围'}))
  fireEvent.click(screen.getByRole('button',{name:'取消选择'}))
  fireEvent.click(screen.getByRole('button',{name:'取消'}))
  expect(screen.getByText('最近 10 条')).toBeVisible()
  expect(screen.getByRole('button',{name:'分析受众'})).toBeEnabled()
  fireEvent.click(screen.getByRole('button',{name:'调整范围'}))
  fireEvent.click(screen.getByRole('button',{name:'取消选择'}))
  fireEvent.click(screen.getByRole('checkbox',{name:'选择笔记：笔记二'}))
  fireEvent.click(screen.getByRole('button',{name:'完成'}))
  view.rerender(<AudienceAnalysisPage {...props} profile={{...importedProfile,content:JSON.stringify({notes:[{noteId:'n1',title:'笔记一',metrics:{},comments:[]}]})}} />)
  expect(screen.getByRole('alert')).toHaveTextContent('已选笔记有变动')
  expect(screen.getByRole('button',{name:'分析受众'})).toBeDisabled()
  expect(create).not.toHaveBeenCalled()
})

it('shows the page explanation on hover or focus while keeping the analysis range visible', async () => {
  render(<AudienceAnalysisPage workspaceId="w" analyses={[]} selectedId="" onSelect={vi.fn()} onRefresh={vi.fn()} onSimulate={vi.fn()} />)
  const hint = screen.getByRole('button', {name:'受众分析说明'})
  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  expect(screen.getByText('最近 10 条')).toBeVisible()
  fireEvent.mouseEnter(hint)
  expect(screen.getByRole('tooltip')).toHaveTextContent('从历史图文和评论梳理不同读者，由你选择收录。')
  fireEvent.mouseLeave(hint)
  await waitFor(() => expect(screen.queryByRole('tooltip')).not.toBeInTheDocument())
  fireEvent.focus(hint)
  expect(screen.getByRole('tooltip')).toBeVisible()
  expect(screen.getByRole('button', {name:'调整范围'})).toBeVisible()
})

it('keeps prewritten readers within the existing history and waits for manual adoption',async()=>{
  const create=vi.spyOn(simulatedFanApi,'create').mockResolvedValue({} as Awaited<ReturnType<typeof simulatedFanApi.create>>)
  const run:AudienceAnalysis={id:'oracle-a',workspaceId:'w',sourceMaterialId:'p',status:'completed',error:'',createdAt:'2026-10-09',
    inputSnapshot:{scope:{scope:'all',selectedNoteCount:2},notes:[]},result:{origin:'oracle_showcase',summary:'有人找入门路径，也有人判断经验如何迁移。',groups:[
      {id:'g',name:'先试一小步',profile:'先用一个小任务判断是否适合自己',coreConcern:'希望明确今天可以做什么',evidence:[]}]}}
  render(<AudienceAnalysisPage workspaceId="w" analyses={[run]} selectedId={run.id} onSelect={vi.fn()} onRefresh={vi.fn()} onSimulate={vi.fn()}/>)
  expect(screen.getByRole('option')).toHaveTextContent('预写示例')
  expect(screen.getByText('预写示例',{selector:'span'})).toBeVisible()
  expect(screen.getByText('基于本账号已保存笔记人工编排，未调用模型。')).toBeVisible()
  expect(create).not.toHaveBeenCalled()
  expect(screen.getByRole('status')).toHaveTextContent('已收录 0 位')
  fireEvent.click(screen.getByRole('button',{name:'收录为模拟读者'}))
  await waitFor(()=>expect(screen.getByRole('button',{name:'已收录'})).toBeDisabled())
  expect(create).toHaveBeenCalledExactlyOnceWith('w','oracle-a','g')
})
it('makes history loading failures visible rather than appearing as empty history', () => {
  render(<AudienceAnalysisPage workspaceId="w" analyses={[]} selectedId="" onSelect={vi.fn()} onRefresh={vi.fn()} onSimulate={vi.fn()} loadError="网络中断" />)
  expect(screen.getByRole('alert')).toHaveTextContent('受众分析历史加载失败：网络中断')
})
it('hides only repetitive prewritten counts and preserves meaningful audience summaries',()=>{
  const run:AudienceAnalysis={id:'oracle-count',workspaceId:'w',sourceMaterialId:'p',status:'completed',error:'',createdAt:'2026-10-09',
    inputSnapshot:{scope:{scope:'all',selectedNoteCount:2}},result:{origin:'oracle_showcase',summary:'6 位可供收录的示例读者。',groups:[]}}
  const props={workspaceId:'w',analyses:[run],selectedId:run.id,onSelect:vi.fn(),onRefresh:vi.fn(),onSimulate:vi.fn()}
  const page=render(<AudienceAnalysisPage {...props}/>)
  expect(screen.queryByText('6 位可供收录的示例读者。')).not.toBeInTheDocument()
  const summary='6 位候选读者中，有人关心入门成本，也有人更想看到你的判断。'
  page.rerender(<AudienceAnalysisPage {...props} analyses={[{...run,result:{...run.result,summary}}]}/>)
  expect(screen.getByText(summary)).toBeVisible()
})
it('shows usable readers without exposing internal rejection diagnostics', () => {
  const run: AudienceAnalysis = {id:'partial',workspaceId:'w',sourceMaterialId:'p',status:'partially_completed',error:'',createdAt:'2026-09-29',inputSnapshot:{scope:{scope:'recent_10',selectedNoteCount:10}},result:{summary:'保留有效分组',groups:[{id:'good',name:'有效视角',profile:'关注费用',coreConcern:'费用',evidence:['费用多少']}]},diagnostics:{acceptedGroups:1,rejectedGroups:[{groupIndex:1,groupId:'bad',groupName:'未核验视角',issues:[{code:'quote_not_exact',message:'引文不是来源中的连续原文',referenceIndex:0}]}]}}
  render(<AudienceAnalysisPage workspaceId="w" analyses={[run]} selectedId={run.id} onSelect={vi.fn()} onRefresh={vi.fn()} onSimulate={vi.fn()} />)
  expect(screen.getByRole('option')).toHaveTextContent('已生成')
  expect(screen.getByText('有效视角')).toBeInTheDocument()
  expect(screen.queryByText(/未通过核验|引文不是来源中的连续原文|下方已核验/)).not.toBeInTheDocument()
  expect(screen.getAllByRole('button', {name:'收录为模拟读者'})).toHaveLength(1)
})

it('cleans only fixed legacy diagnostic prose without changing saved results', () => {
  const run:AudienceAnalysis={id:'legacy',workspaceId:'w',sourceMaterialId:'p',status:'partially_completed',error:'',createdAt:'2026-09-29',inputSnapshot:{scope:{scope:'recent_10',selectedNoteCount:10}},result:{summary:'已保留 1 个通过原文核验的阅读视角。',limitations:'只参考最近十篇笔记。 另有 3 个分组未通过核验，未用于模拟粉丝或模拟。',groups:[{id:'g',name:'读者视角',profile:'关注成本',coreConcern:'成本',evidence:[]}]}}
  const original=JSON.stringify(run)
  render(<AudienceAnalysisPage workspaceId="w" analyses={[run]} selectedId={run.id} onSelect={vi.fn()} onRefresh={vi.fn()} onSimulate={vi.fn()}/>)
  fireEvent.click(screen.getByText('分析说明'))
  expect(screen.getByText('只参考最近十篇笔记。')).toBeVisible()
  expect(screen.getByRole('status')).toHaveTextContent('1 位 · 已收录 0 位')
  expect(screen.queryByText('为你整理了 1 位候选读者。')).not.toBeInTheDocument()
  expect(screen.queryByText(/未通过核验|通过原文核验/)).not.toBeInTheDocument()
  expect(JSON.stringify(run)).toBe(original)
})

it('keeps an actionable empty-result error for older failed analyses', () => {
  const run:AudienceAnalysis={id:'failed',workspaceId:'w',sourceMaterialId:'p',status:'failed',error:'所有分组的受众证据引用均未通过核验；具体原因已保存。',createdAt:'2026-09-29',inputSnapshot:{scope:{scope:'recent_10',selectedNoteCount:10}},result:{}}
  render(<AudienceAnalysisPage workspaceId="w" analyses={[run]} selectedId={run.id} onSelect={vi.fn()} onRefresh={vi.fn()} onSimulate={vi.fn()}/>)
  expect(screen.getByRole('alert')).toHaveTextContent('本次未生成可用读者，请重新分析。')
  expect(screen.queryByText(/未通过核验/)).not.toBeInTheDocument()
  expect(screen.queryByRole('button',{name:'收录为模拟读者'})).not.toBeInTheDocument()
})

it('shows all audience groups as saveable fan candidates without population estimates', () => {
  const result: AudienceAnalysis = {id:'a',workspaceId:'w',sourceMaterialId:'p',status:'completed',error:'',createdAt:'2026-09-23',inputSnapshot:{scope:{scope:'recent_10',selectedNoteCount:10}},result:{summary:'四类受众',limitations:'评论样本有偏差',groups:[40,30,20,10].map((n,i) => ({id:String(i),name:`受众${i}`,profile:'具体画像',coreConcern:'关注费用',estimatedPercent:n,evidence:['原文证据']}))}}
  const simulate = vi.fn()
  render(<AudienceAnalysisPage workspaceId="w" analyses={[result]} selectedId="a" onSelect={vi.fn()} onRefresh={vi.fn()} onSimulate={simulate} />)
  expect(screen.getAllByRole('button', {name:'收录为模拟读者'})).toHaveLength(4)
  expect(screen.getByText('受众3')).toBeInTheDocument()
  expect(screen.queryByText('兴趣领域：')).not.toBeInTheDocument()
  expect(screen.getByText(/这些角色用于模拟不同声音/)).not.toBeVisible()
  fireEvent.click(screen.getByText('分析说明'))
  expect(screen.getByText(/这些角色用于模拟不同声音/)).toBeVisible()
  expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  expect(screen.queryByText('约 40%')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'选择内容，邀请读者试读'}))
  expect(simulate).toHaveBeenCalledOnce()
})

it('separates broad interests from a concrete need and expression style', () => {
  const result: AudienceAnalysis = {id:'interest',workspaceId:'w',sourceMaterialId:'p',status:'completed',error:'',createdAt:'2026-10-01',inputSnapshot:{scope:{scope:'recent_10',selectedNoteCount:1}},result:{groups:[{id:'g',name:'先算账再行动',profile:'做决定前喜欢把账算清',interests:['留学','职业发展'],coreConcern:'想拿到能直接对照预算的费用清单',expressionStyle:'先追问遗漏项，再说自己会不会选',evidence:[]}]}}
  render(<AudienceAnalysisPage workspaceId="w" analyses={[result]} selectedId={result.id} onSelect={vi.fn()} onRefresh={vi.fn()} onSimulate={vi.fn()} />)
  expect(screen.getByText('留学 · 职业发展')).toBeVisible()
  expect(screen.getByText('想获得').parentElement).toHaveTextContent('想拿到能直接对照预算的费用清单')
  fireEvent.click(screen.getByText('阅读与表达习惯'))
  expect(screen.getByText('先追问遗漏项，再说自己会不会选')).toBeVisible()
})

it('shows verified source references without population percentages', () => {
  const result: AudienceAnalysis = {id:'a',workspaceId:'w',sourceMaterialId:'p',status:'completed',error:'',createdAt:'2026-09-23',inputSnapshot:{scope:{scope:'recent_10',selectedNoteCount:1}},result:{method:'evidence_grounded_v1',summary:'费用视角',limitations:'仅一条评论',sampling:{sentNotes:1,sentComments:1,availableComments:1},groups:[{id:'g',name:'申请者',profile:'关注费用',coreConcern:'费用',estimatedPercent:null,evidence:['费用多少'],evidenceRefs:[{noteId:'n',commentId:'c',sourceType:'comment',quote:'费用多少'}]}]}}
  render(<AudienceAnalysisPage workspaceId="w" analyses={[result]} selectedId="a" onSelect={vi.fn()} onRefresh={vi.fn()} onSimulate={vi.fn()} />)
  expect(screen.getByText('引用评论')).toBeInTheDocument()
  expect(screen.getByText(/1 条笔记、1 条已采集评论/)).toBeInTheDocument()
  expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
})

it('marks note-only views as content inference rather than observed commenters', () => {
  const result: AudienceAnalysis = {id:'note-only',workspaceId:'w',sourceMaterialId:'p',status:'completed',error:'',createdAt:'2026-10-01',inputSnapshot:{scope:{scope:'recent_10',selectedNoteCount:1}},result:{method:'evidence_grounded_v1',summary:'潜在阅读视角',groups:[{id:'g',name:'步骤阅读视角',profile:'可能需要步骤',coreConcern:'步骤',evidence:['申请步骤'],evidenceBasis:'content_inferred',evidenceRefs:[{noteId:'n',commentId:null,sourceType:'note',quote:'申请步骤'}]}]}}
  render(<AudienceAnalysisPage workspaceId="w" analyses={[result]} selectedId="note-only" onSelect={vi.fn()} onRefresh={vi.fn()} onSimulate={vi.fn()} />)
  expect(screen.getByText('从笔记内容推断')).toBeInTheDocument()
  expect(screen.queryByText('评论表达')).not.toBeInTheDocument()
})

it('shows eight concise voices and keeps supporting details collapsed', () => {
  const result: AudienceAnalysis = {id:'voices',workspaceId:'w',sourceMaterialId:'p',status:'completed',error:'',createdAt:'2026-10-01',inputSnapshot:{scope:{scope:'recent_10',selectedNoteCount:10}},result:{summary:'八种不同声音',limitations:'角色为模拟设定',sampling:{sentNotes:10,sentComments:20,availableComments:20},groups:Array.from({length:8},(_,i) => ({id:String(i),name:`声音${i+1}`,profile:`人物简介${i+1}`,coreConcern:`关注点${i+1}`,expressionStyle:`说话风格${i+1}`,evidence:['原文依据']}))}}
  render(<AudienceAnalysisPage workspaceId="w" analyses={[result]} selectedId="voices" onSelect={vi.fn()} onRefresh={vi.fn()} onSimulate={vi.fn()} />)
  expect(screen.getAllByRole('article')).toHaveLength(8)
  expect(screen.getAllByRole('button', {name:'收录为模拟读者'})).toHaveLength(8)
  expect(screen.getByText('人物简介8')).toBeVisible()
  expect(screen.getByText('说话风格8')).not.toBeVisible()
  for (const label of screen.getAllByText('依据', {selector:'summary'})) {
    expect(label.closest('details')).not.toHaveAttribute('open')
  }
  const notes = screen.getByText('分析说明', {selector:'summary'})
  expect(notes.closest('details')).not.toHaveAttribute('open')
  fireEvent.click(notes)
  expect(notes.closest('details')).toHaveAttribute('open')
})

it('keeps candidates separate until explicitly adopted and does not repeat a saved request after refresh failure', async () => {
  const create = vi.spyOn(simulatedFanApi,'create').mockResolvedValue({} as Awaited<ReturnType<typeof simulatedFanApi.create>>)
  const refresh = vi.fn().mockRejectedValueOnce(new Error('断网')).mockResolvedValue(undefined)
  const result: AudienceAnalysis = {id:'a',workspaceId:'w',sourceMaterialId:'p',status:'completed',error:'',createdAt:'2026-10-01',inputSnapshot:{scope:{scope:'all',selectedNoteCount:1}},result:{groups:[{id:'g',name:'读者视角',profile:'核对费用',coreConcern:'成本',evidence:[]}]}}
  render(<AudienceAnalysisPage workspaceId="w" analyses={[result]} selectedId="a" onSelect={vi.fn()} onRefresh={vi.fn()} onSimulate={vi.fn()} onFansChanged={refresh} />)
  expect(create).not.toHaveBeenCalled()
  expect(screen.getByText('候选读者')).toBeVisible()
  fireEvent.click(screen.getByRole('button',{name:'收录为模拟读者'}))
  await waitFor(() => expect(screen.getByRole('button',{name:'已收录'})).toBeDisabled())
  expect(create).toHaveBeenCalledExactlyOnceWith('w','a','g')
  expect(screen.getByRole('alert')).toHaveTextContent('读者已收录')
  expect(screen.getByRole('button',{name:'选择内容，邀请读者试读'})).toBeDisabled()
  fireEvent.click(screen.getByRole('button',{name:'重试刷新读者列表'}))
  await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
  expect(create).toHaveBeenCalledTimes(1)
  expect(refresh).toHaveBeenCalledTimes(2)
  expect(screen.getByRole('status')).toHaveTextContent('1 位 · 已收录 1 位')
})

it('keeps the full distinctive description and adoption action before supplementary details', () => {
  const profile = '看到成功经历时先比较自己的起点，再决定是否照做。'.repeat(6)
  const concern = '需要列出时间和成本，才能判断是否适合自己。'.repeat(6)
  const result:AudienceAnalysis={id:'readable',workspaceId:'w',sourceMaterialId:'p',status:'completed',error:'',createdAt:'2026-10-09',inputSnapshot:{scope:{scope:'recent_10',selectedNoteCount:1}},result:{summary:'同样的兴趣背后，有不同的决策方式。',groups:[{id:'g',name:'比较起点再行动',profile,coreConcern:concern,interests:['职业发展'],expressionStyle:'先问适用条件',evidence:['原文证据']}]}}
  const original=JSON.stringify(result)
  render(<AudienceAnalysisPage workspaceId="w" analyses={[result]} selectedId={result.id} onSelect={vi.fn()} onRefresh={vi.fn()} onSimulate={vi.fn()} />)
  expect(screen.getByText(profile)).toBeVisible()
  expect(screen.getByText(concern,{exact:false})).toBeVisible()
  expect(screen.getByText(result.result.summary!)).toBeVisible()
  const action=screen.getByRole('button',{name:'收录为模拟读者'})
  const evidence=screen.getByText('依据',{selector:'summary'})
  expect(action.compareDocumentPosition(evidence) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  fireEvent.click(evidence)
  expect(action).toBeVisible()
  expect(action).toBeEnabled()
  expect(screen.getByText('原文证据')).toBeVisible()
  expect(JSON.stringify(result)).toBe(original)
})

it('omits blank fields and empty disclosures without inventing replacement traits', () => {
  const result:AudienceAnalysis={id:'sparse',workspaceId:'w',sourceMaterialId:'p',status:'completed',error:'',createdAt:'2026-10-09',inputSnapshot:{scope:{scope:'recent_10',selectedNoteCount:1}},result:{groups:[{id:'g',name:'旧读者',profile:'',coreConcern:' ',interests:[' '],expressionStyle:' ',evidence:[]}]}}
  render(<AudienceAnalysisPage workspaceId="w" analyses={[result]} selectedId={result.id} onSelect={vi.fn()} onRefresh={vi.fn()} onSimulate={vi.fn()} />)
  expect(screen.getByText('旧读者')).toBeVisible()
  expect(screen.queryByText('想获得')).not.toBeInTheDocument()
  expect(screen.queryByLabelText('兴趣领域')).not.toBeInTheDocument()
  expect(screen.queryByText('阅读与表达习惯')).not.toBeInTheDocument()
  expect(screen.queryByText('依据',{selector:'summary'})).not.toBeInTheDocument()
  expect(screen.getByRole('button',{name:'收录为模拟读者'})).toBeEnabled()
})

it('offers a concise recovery hint for an empty completed result without showing empty reader cards', () => {
  const result:AudienceAnalysis={id:'empty',workspaceId:'w',sourceMaterialId:'p',status:'completed',error:'',createdAt:'2026-10-09',inputSnapshot:{scope:{scope:'recent_10',selectedNoteCount:1}},result:{groups:[]}}
  render(<AudienceAnalysisPage workspaceId="w" analyses={[result]} selectedId={result.id} onSelect={vi.fn()} onRefresh={vi.fn()} onSimulate={vi.fn()} />)
  expect(screen.getByText('这次没有可收录的读者，可以调整范围后重新分析。')).toBeVisible()
  expect(screen.queryByRole('article')).not.toBeInTheDocument()
  expect(screen.queryByRole('button',{name:'收录为模拟读者'})).not.toBeInTheDocument()
})
