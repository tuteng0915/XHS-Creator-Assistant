import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { audienceAnalysisApi } from '../api'
import type { AudienceAnalysis } from '../types'
import { AudienceAnalysisPage } from './AudienceAnalysisPage'

afterEach(() => {cleanup(); vi.restoreAllMocks()})
const run:AudienceAnalysis = {id:'a',workspaceId:'w',sourceMaterialId:'p',status:'completed',error:'',createdAt:'2026-10-03',inputSnapshot:{scope:{scope:'recent_10',selectedNoteCount:1}},result:{groups:[{id:'g',name:'先看条件的人',profile:'核对成本再行动',coreConcern:'找到第一步',evidence:[],evidenceRefs:[{noteId:'n',commentId:'c',sourceType:'comment',quote:'第一步'}]}]}}
const detail:AudienceAnalysis = {...run,inputSnapshot:{...run.inputSnapshot,notes:[{noteId:'n',title:'当时的笔记标题',desc:'当时的正文',metrics:{liked:1},comments:[{commentId:'c',content:'请问第一步怎么做？'}]}]}}
const props = {workspaceId:'w',analyses:[run],selectedId:'a',onSelect:vi.fn(),onRefresh:vi.fn(),onSimulate:vi.fn()}
async function openEvidence(index=0) {
  fireEvent.click(screen.getAllByText('依据',{selector:'summary'})[index])
  await act(async () => {await new Promise(resolve=>setTimeout(resolve,5))})
}

it('loads once on demand, shares detail across roles and opens the historical note', async () => {
  const get = vi.spyOn(audienceAnalysisApi,'get').mockResolvedValue(detail)
  const second = {...run.result.groups![0],id:'g2',name:'另一位'}
  render(<AudienceAnalysisPage {...props} analyses={[{...run,result:{groups:[...run.result.groups!,second]}}]} />)
  expect(get).not.toHaveBeenCalled()
  await openEvidence()
  expect(await screen.findAllByText('请问第一步怎么做？')).toHaveLength(2)
  await openEvidence(1)
  expect(get).toHaveBeenCalledTimes(1)
  fireEvent.click(screen.getAllByRole('button',{name:/当时的笔记标题 赞/})[0])
  expect(screen.getByRole('dialog')).toBeInTheDocument()
  expect(screen.getByText('当时的正文')).toBeInTheDocument()
})

it('keeps citations on failure and retries without replacing them with current material', async () => {
  const get = vi.spyOn(audienceAnalysisApi,'get').mockRejectedValueOnce(new Error('网络断开')).mockResolvedValue(detail)
  render(<AudienceAnalysisPage {...props} />)
  await openEvidence()
  expect(await screen.findByRole('alert')).toHaveTextContent('网络断开')
  expect(screen.getByText('引用评论').parentElement).toHaveTextContent('第一步')
  fireEvent.click(screen.getByRole('button',{name:'重试加载依据'}))
  await screen.findByText('请问第一步怎么做？')
  expect(get).toHaveBeenCalledTimes(2)
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

it('discards an old request after changing analysis and closes old detail state', async () => {
  let resolveOld!:(value:AudienceAnalysis)=>void
  const get=vi.spyOn(audienceAnalysisApi,'get').mockImplementationOnce(()=>new Promise(resolve=>{resolveOld=resolve})).mockResolvedValue({...detail,id:'b',inputSnapshot:{...detail.inputSnapshot,notes:[{noteId:'n',title:'新的快照',desc:'另一份正文',comments:[]}]}})
  const {rerender}=render(<AudienceAnalysisPage {...props} />)
  await openEvidence()
  const next={...run,id:'b'}
  rerender(<AudienceAnalysisPage {...props} analyses={[next]} selectedId="b" />)
  await act(async()=>resolveOld(detail))
  expect(screen.queryByText('当时的笔记标题')).not.toBeInTheDocument()
  expect(screen.getByText('依据').closest('details')).not.toHaveAttribute('open')
  await openEvidence()
  await screen.findByText('新的快照')
  expect(get).toHaveBeenCalledTimes(2)
})

it('rejects mismatched workspace detail and hides stale rows when workspace changes', async () => {
  vi.spyOn(audienceAnalysisApi,'get').mockResolvedValue({...detail,workspaceId:'other'})
  const {rerender}=render(<AudienceAnalysisPage {...props} />)
  await openEvidence()
  expect(await screen.findByRole('alert')).toHaveTextContent('分析来源不匹配')
  expect(screen.queryByText('当时的笔记标题')).not.toBeInTheDocument()
  rerender(<AudienceAnalysisPage {...props} workspaceId="other" />)
  expect(screen.queryByText('先看条件的人')).not.toBeInTheDocument()
  expect(screen.queryByLabelText('受众分析历史')).not.toBeInTheDocument()
})

it('uses existing snapshots directly and shows missing or ambiguous sources honestly', async () => {
  const get=vi.spyOn(audienceAnalysisApi,'get')
  const {rerender}=render(<AudienceAnalysisPage {...props} analyses={[detail]} />)
  await openEvidence()
  expect(get).not.toHaveBeenCalled()
  expect(screen.getByText('请问第一步怎么做？')).toBeInTheDocument()
  rerender(<AudienceAnalysisPage {...props} selectedId="missing" analyses={[{...run,id:'missing',inputSnapshot:{...run.inputSnapshot,notes:[]}}]} />)
  await openEvidence()
  expect(screen.getByText(/当次快照未保留这篇笔记/)).toBeInTheDocument()
  expect(screen.queryByRole('button',{name:/当时的笔记/})).not.toBeInTheDocument()
  await waitFor(()=>expect(get).not.toHaveBeenCalled())
})

it('does not choose one of two snapshot comments with the same ID', async () => {
  const duplicate:AudienceAnalysis = {...detail,inputSnapshot:{...detail.inputSnapshot,notes:[{noteId:'n',title:'重复评论来源',desc:'原始正文',comments:[{commentId:'c',content:'第一个候选'},{commentId:'c',content:'第二个候选'}]}]}}
  render(<AudienceAnalysisPage {...props} analyses={[duplicate]} />)
  await openEvidence()
  expect(screen.getByText('快照中无法唯一定位这条评论，保留历史引用。')).toBeInTheDocument()
  expect(screen.queryByText('第一个候选')).not.toBeInTheDocument()
  expect(screen.queryByText('第二个候选')).not.toBeInTheDocument()
})

it('resolves legacy fallback IDs with the same positions as the model input', async () => {
  const legacy:AudienceAnalysis = {...run,inputSnapshot:{...run.inputSnapshot,notes:[{title:'旧快照',desc:'旧正文',comments:[{content:'无ID评论'}]}]},result:{groups:[{...run.result.groups![0],evidenceRefs:[{noteId:'snapshot-note-0',commentId:'snapshot-comment-0',sourceType:'comment',quote:'无ID'}]}]}}
  render(<AudienceAnalysisPage {...props} analyses={[legacy]} />)
  await openEvidence()
  expect(screen.getByText('无ID评论')).toBeInTheDocument()
  expect(screen.getByRole('button',{name:/旧快照 赞/})).toBeInTheDocument()
})
