import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { AnalysisRun } from '../types'
import { StageResultRenderer } from './ArtifactRenderers'
import { PainPointsView } from './StageResultViews'

afterEach(cleanup)

it('shows the frozen original comments when the model returned no themes', () => {
  render(<PainPointsView items={[]} profile={{notes:[
    {title:'申请分享',comments:[{content:'请问有面试嘛？'},{content:'感谢分享'}]},
    {title:'工作日常',comments:[{content:'诶 请问贵公司招人吗'}]},
  ]}} />)
  expect(screen.getByText('本次有 3 条文字评论，但未提炼出反馈主题。')).toBeVisible()
  expect(screen.getByRole('heading', {name:'评论原文'})).toBeVisible()
  expect(screen.getByText('请问有面试嘛？').tagName).toBe('BLOCKQUOTE')
  expect(screen.getByText('感谢分享')).toBeVisible()
  expect(screen.getByText('《工作日常》')).toBeVisible()
  expect(screen.queryByText(/没有可用/)).not.toBeInTheDocument()
})

it('excludes verified author replies while retaining unknown and non-author comments', () => {
  render(<PainPointsView items={[]} profile={{notes:[
    {authorHash:' ABCDEF0123456789 ',comments:[
      {content:'作者自己回答',authorHash:'abcdef0123456789'},
      {content:'另一位读者',authorHash:'0123456789abcdef'},
      {content:'身份未知的提问'},
    ]},
    {authorHash:'invalid',comments:[{content:'不能按无效标识排除',authorHash:'invalid'}]},
  ]}} />)
  expect(screen.queryByText('作者自己回答')).not.toBeInTheDocument()
  expect(screen.getByText('本次有 3 条文字评论，但未提炼出反馈主题。')).toBeVisible()
  expect(screen.getByText('身份未知的提问')).toBeVisible()
})

it.each([
  [{notes:[]}, '本次所选笔记没有可用的读者评论。'],
  [{notes:[{comments:[]}]}, '本次所选笔记没有可用的读者评论。'],
  [{notes:[{authorHash:'abcdef0123456789',comments:[{authorHash:'abcdef0123456789',content:'作者回答'}]}]}, '本次所选笔记没有可用的读者评论。'],
  [{notes:[{comments:[{content:''},{content:'  '},{image:'some-image'}]}]}, '本次评论没有可分析的文字。'],
  [undefined, '本次未提炼出读者反馈。'],
])('distinguishes empty text, unavailable sources and no eligible comments %#', (profile, message) => {
  render(<PainPointsView items={[]} profile={profile} />)
  expect(screen.getByText(message)).toBeVisible()
  expect(screen.queryByRole('heading', {name:'评论原文'})).not.toBeInTheDocument()
})

it('does not change nonempty saved feedback or append source noise', () => {
  render(<PainPointsView items={[{theme:'面试流程',intensity:'中',count:1,evidence:['请问有面试嘛？']}]} profile={{notes:[]}} />)
  expect(screen.getByText('面试流程')).toBeVisible()
  expect(screen.getByText('“请问有面试嘛？”')).toBeVisible()
  expect(screen.queryByText(/本次/)).not.toBeInTheDocument()
})

it('labels ranking fallback without hiding valid first-stage feedback', () => {
  render(<PainPointsView rankingFallback items={[{theme:'面试流程',intensity:'中',count:1,evidence:['请问有面试嘛？']}]} />)
  expect(screen.getByText('重要性排序暂未完成，先保留已提取的反馈。')).toBeVisible()
  expect(screen.getByText('面试流程')).toBeVisible()
  expect(screen.getByText('“请问有面试嘛？”')).toBeVisible()
})

it('keeps the initial source preview short and makes remaining comments accessible', () => {
  render(<PainPointsView items={[]} profile={{notes:[{comments:Array.from({length:7}, (_, i) => ({content:`评论 ${i+1}`}))}]}} />)
  expect(screen.getByText('评论 6')).toBeVisible()
  expect(screen.getByText('评论 7')).not.toBeVisible()
  fireEvent.click(screen.getByText('其余 1 条评论原文'))
  expect(screen.getByText('评论 7')).toBeVisible()
})

it('uses each displayed run snapshot rather than stale account comments', () => {
  const run: AnalysisRun = {id:'run-a',workspaceId:'w',workflowType:'account_diagnosis',status:'completed',
    createdAt:'2026-10-12',updatedAt:'2026-10-12',startedAt:null,completedAt:null,userNotes:'',reviewStatus:'unreviewed',
    inputSnapshot:{xhsCreatorProfile:{notes:[{comments:[{content:'第一份快照'}]}]}},stageResults:{},stageErrors:{},modelMetadata:{}}
  const props = {stage:{key:'pain_points',n:'2',title:'读者反馈',status:'completed' as const,result:{painPoints:[]}},
    currentRun:run,onSaveGeneratedTopic:vi.fn(),onSelectTopic:vi.fn(),onGenerateBrief:vi.fn(),onGenerateDraft:vi.fn(),onFillSimulationTopic:vi.fn()}
  const {rerender} = render(<StageResultRenderer {...props} />)
  expect(screen.getByText('第一份快照')).toBeVisible()
  rerender(<StageResultRenderer {...props} currentRun={{...run,id:'run-b',inputSnapshot:{xhsCreatorProfile:{notes:[{comments:[{content:'第二份快照'}]}]}}}} />)
  expect(screen.getByText('第二份快照')).toBeVisible()
  expect(screen.queryByText('第一份快照')).not.toBeInTheDocument()
})
