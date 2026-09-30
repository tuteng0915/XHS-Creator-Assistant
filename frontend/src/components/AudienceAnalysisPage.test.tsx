import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { AudienceAnalysis } from '../types'
import { AudienceAnalysisPage } from './AudienceAnalysisPage'

afterEach(cleanup)
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
  expect(screen.getAllByRole('button', {name:'保存为模拟粉丝'})).toHaveLength(1)
})

it('shows all audience groups as saveable fan candidates without population estimates', () => {
  const result: AudienceAnalysis = {id:'a',workspaceId:'w',sourceMaterialId:'p',status:'completed',error:'',createdAt:'2026-09-23',inputSnapshot:{scope:{scope:'recent_10',selectedNoteCount:10}},result:{summary:'四类受众',limitations:'评论样本有偏差',groups:[40,30,20,10].map((n,i) => ({id:String(i),name:`受众${i}`,profile:'具体画像',coreConcern:'关注费用',estimatedPercent:n,evidence:['原文证据']}))}}
  const simulate = vi.fn()
  render(<AudienceAnalysisPage workspaceId="w" analyses={[result]} selectedId="a" onSelect={vi.fn()} onRefresh={vi.fn()} onSimulate={simulate} />)
  expect(screen.getAllByRole('button', {name:'保存为模拟粉丝'})).toHaveLength(4)
  expect(screen.getByText('受众3')).toBeInTheDocument()
  expect(screen.getByText(/非平台真实粉丝统计/)).toBeInTheDocument()
  expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  expect(screen.queryByText('约 40%')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'选择选题进行模拟'}))
  expect(simulate).toHaveBeenCalledOnce()
})

it('shows verified source references without population percentages', () => {
  const result: AudienceAnalysis = {id:'a',workspaceId:'w',sourceMaterialId:'p',status:'completed',error:'',createdAt:'2026-09-23',inputSnapshot:{scope:{scope:'recent_10',selectedNoteCount:1}},result:{method:'evidence_grounded_v1',summary:'费用视角',limitations:'仅一条评论',sampling:{sentNotes:1,sentComments:1,availableComments:1},groups:[{id:'g',name:'申请者',profile:'关注费用',coreConcern:'费用',estimatedPercent:null,evidence:['费用多少'],evidenceRefs:[{noteId:'n',commentId:'c',sourceType:'comment',quote:'费用多少'}]}]}}
  render(<AudienceAnalysisPage workspaceId="w" analyses={[result]} selectedId="a" onSelect={vi.fn()} onRefresh={vi.fn()} onSimulate={vi.fn()} />)
  expect(screen.getByText(/评论直接表达 · 笔记 n/)).toBeInTheDocument()
  expect(screen.getByText(/1 条笔记、1 条已采集评论/)).toBeInTheDocument()
  expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
})
