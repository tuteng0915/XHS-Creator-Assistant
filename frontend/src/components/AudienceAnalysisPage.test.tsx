import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { AudienceAnalysis } from '../types'
import { AudienceAnalysisPage } from './AudienceAnalysisPage'

afterEach(cleanup)
it('shows all audience groups, marks only top three and labels estimates', () => {
  const result: AudienceAnalysis = {id:'a',workspaceId:'w',sourceMaterialId:'p',status:'completed',error:'',createdAt:'2026-09-23',inputSnapshot:{scope:{scope:'recent_10',selectedNoteCount:10}},result:{summary:'四类受众',limitations:'评论样本有偏差',groups:[40,30,20,10].map((n,i) => ({id:String(i),name:`受众${i}`,profile:'具体画像',coreConcern:'关注费用',estimatedPercent:n,evidence:['原文证据']}))}}
  const simulate = vi.fn()
  render(<AudienceAnalysisPage workspaceId="w" analyses={[result]} selectedId="a" onSelect={vi.fn()} onRefresh={vi.fn()} onSimulate={simulate} />)
  expect(screen.getAllByText(/· 模拟角色/)).toHaveLength(3)
  expect(screen.getByText('受众3')).toBeInTheDocument()
  expect(screen.getByText(/非平台真实粉丝统计/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'选择选题进行模拟'}))
  expect(simulate).toHaveBeenCalledOnce()
})
