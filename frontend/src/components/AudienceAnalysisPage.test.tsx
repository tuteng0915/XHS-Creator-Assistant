import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { simulatedFanApi } from '../api'
import type { AudienceAnalysis } from '../types'
import { AudienceAnalysisPage } from './AudienceAnalysisPage'

afterEach(() => {cleanup(); vi.restoreAllMocks()})
it('makes history loading failures visible rather than appearing as empty history', () => {
  render(<AudienceAnalysisPage workspaceId="w" analyses={[]} selectedId="" onSelect={vi.fn()} onRefresh={vi.fn()} onSimulate={vi.fn()} loadError="网络中断" />)
  expect(screen.getByRole('alert')).toHaveTextContent('受众分析历史加载失败：网络中断')
})
it('shows valid partial results and specific rejected reference reasons', () => {
  const run: AudienceAnalysis = {id:'partial',workspaceId:'w',sourceMaterialId:'p',status:'partially_completed',error:'',createdAt:'2026-09-29',inputSnapshot:{scope:{scope:'recent_10',selectedNoteCount:10}},result:{summary:'保留有效分组',groups:[{id:'good',name:'有效视角',profile:'关注费用',coreConcern:'费用',evidence:['费用多少']}]},diagnostics:{acceptedGroups:1,rejectedGroups:[{groupIndex:1,groupId:'bad',groupName:'未核验视角',issues:[{code:'quote_not_exact',message:'引文不是来源中的连续原文',referenceIndex:0}]}]}}
  render(<AudienceAnalysisPage workspaceId="w" analyses={[run]} selectedId={run.id} onSelect={vi.fn()} onRefresh={vi.fn()} onSimulate={vi.fn()} />)
  expect(screen.getByRole('option')).toHaveTextContent('部分完成')
  expect(screen.getByText('有效视角')).toBeInTheDocument()
  expect(screen.getByText(/引用 1：引文不是来源中的连续原文/)).toBeInTheDocument()
  expect(screen.getAllByRole('button', {name:'收录为模拟读者'})).toHaveLength(1)
})

it('shows all audience groups as saveable fan candidates without population estimates', () => {
  const result: AudienceAnalysis = {id:'a',workspaceId:'w',sourceMaterialId:'p',status:'completed',error:'',createdAt:'2026-09-23',inputSnapshot:{scope:{scope:'recent_10',selectedNoteCount:10}},result:{summary:'四类受众',limitations:'评论样本有偏差',groups:[40,30,20,10].map((n,i) => ({id:String(i),name:`受众${i}`,profile:'具体画像',coreConcern:'关注费用',estimatedPercent:n,evidence:['原文证据']}))}}
  const simulate = vi.fn()
  render(<AudienceAnalysisPage workspaceId="w" analyses={[result]} selectedId="a" onSelect={vi.fn()} onRefresh={vi.fn()} onSimulate={simulate} />)
  expect(screen.getAllByRole('button', {name:'收录为模拟读者'})).toHaveLength(4)
  expect(screen.getByText('受众3')).toBeInTheDocument()
  expect(screen.queryByText('兴趣领域：')).not.toBeInTheDocument()
  expect(screen.getByText('这些角色用于模拟不同声音，并非真实粉丝的个人档案。')).toBeInTheDocument()
  expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  expect(screen.queryByText('约 40%')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'选择内容，邀请读者试读'}))
  expect(simulate).toHaveBeenCalledOnce()
})

it('separates broad interests from a concrete need and expression style', () => {
  const result: AudienceAnalysis = {id:'interest',workspaceId:'w',sourceMaterialId:'p',status:'completed',error:'',createdAt:'2026-10-01',inputSnapshot:{scope:{scope:'recent_10',selectedNoteCount:1}},result:{groups:[{id:'g',name:'先算账再行动',profile:'做决定前喜欢把账算清',interests:['留学','职业发展'],coreConcern:'想拿到能直接对照预算的费用清单',expressionStyle:'先追问遗漏项，再说自己会不会选',evidence:[]}]}}
  render(<AudienceAnalysisPage workspaceId="w" analyses={[result]} selectedId={result.id} onSelect={vi.fn()} onRefresh={vi.fn()} onSimulate={vi.fn()} />)
  expect(screen.getByText('留学 · 职业发展')).toBeVisible()
  expect(screen.getByText('具体需求：').parentElement).toHaveTextContent('想拿到能直接对照预算的费用清单')
  fireEvent.click(screen.getByText('阅读与表达习惯'))
  expect(screen.getByText('说话风格：').parentElement).toHaveTextContent('先追问遗漏项，再说自己会不会选')
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
  expect(screen.getAllByRole('heading', {level:2})).toHaveLength(8)
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
  expect(screen.getByText('已收录读者')).toBeVisible()
})
