import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { AccountPortraitView, type Observations } from './AccountPortraitView'
import { StageResultRenderer } from './ArtifactRenderers'
import type { AnalysisRun, MediaAsset } from '../types'

afterEach(cleanup)

const note = {noteId:'n1',title:'准备过程',desc:'先列成本，再分步骤。',metrics:{liked:12},comments:[]}
const observations:Observations = {
  schemaVersion:'xhs-account-observations/v1',
  coverage:{selectedCount:1,missingDateCount:1,capturedCommentCount:0,missingMetricCounts:{}},
  notes:[note],
}
const summary = {statement:'把过程讲得具体',evidence:[{noteId:'n1',quote:'先列成本'},{noteId:'n1',quote:'再分步骤'}]}

it('shows valid keywords and strengths without requiring a summary or missing sections', () => {
  render(<AccountPortraitView portrait={{summary:null,keywords:[{...summary,statement:'过程分享'}],strengths:[summary],recurringThemes:[],readerValue:[]}} observations={observations} notes={[note]} mediaAssets={[]} />)
  expect(screen.getByText('过程分享')).toBeInTheDocument()
  expect(screen.getByText(summary.statement)).toBeInTheDocument()
  expect(screen.queryByText('主要内容方向')).not.toBeInTheDocument()
  expect(screen.queryByText('给读者的价值')).not.toBeInTheDocument()
  expect(screen.queryByText(/本次暂无可展示/)).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'查看依据 · 1 条笔记'}))
  expect(screen.getByText('“先列成本”')).toBeInTheDocument()
})

it('does not render a blank intro card when only strengths are available', () => {
  const {container} = render(<AccountPortraitView portrait={{strengths:[summary]}} observations={observations} notes={[note]} mediaAssets={[]} />)
  expect(screen.getByText(summary.statement)).toBeInTheDocument()
  expect(container.querySelector('.account-portrait-intro')).toBeNull()
  expect(screen.queryByText(/本次暂无可展示/)).not.toBeInTheDocument()
})

it('switches keyword evidence below the tags and preserves missing historical quotes', () => {
  render(<AccountPortraitView portrait={{keywords:[
    {...summary,statement:'过程分享'},
    {statement:'真实表达',evidence:[{noteId:'missing',quote:'历史文字仍在'}]},
  ]}} observations={observations} notes={[note]} mediaAssets={[]} />)
  const first=screen.getByRole('button',{name:'过程分享：查看 1 条笔记依据'})
  const second=screen.getByRole('button',{name:'真实表达：查看 1 条笔记依据'})
  expect(first).toHaveAttribute('aria-expanded','false')
  expect(screen.queryByRole('region')).not.toBeInTheDocument()
  fireEvent.click(first)
  expect(first).toHaveAttribute('aria-expanded','true')
  const evidence=screen.getByRole('region',{name:'过程分享的依据'})
  expect(document.getElementById(first.getAttribute('aria-controls')!)).toContainElement(evidence)
  expect(screen.getByRole('group',{name:'账号关键词'})).not.toContainElement(evidence)
  expect(screen.getByText('“先列成本”')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:/准备过程 赞/}))
  expect(screen.getByRole('dialog')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'关闭'}))
  fireEvent.click(second)
  expect(first).toHaveAttribute('aria-expanded','false')
  expect(screen.queryByText('“先列成本”')).not.toBeInTheDocument()
  expect(screen.getByRole('region',{name:'真实表达的依据'})).toHaveTextContent('历史文字仍在')
  expect(screen.getByText('1 条依据笔记未保留在本次分析快照中，仅显示历史引用。')).toBeInTheDocument()
  fireEvent.click(second)
  expect(screen.queryByRole('region')).not.toBeInTheDocument()
})

it('opens note-level keyword sources without inventing a quote', () => {
  const {container} = render(<AccountPortraitView portrait={{keywords:[{
    statement:'过程分享', evidence:[{noteId:'n1',scope:'note'}],
  }]}} observations={observations} notes={[note]} mediaAssets={[]} />)
  fireEvent.click(screen.getByRole('button',{name:'过程分享：查看 1 条笔记依据'}))
  expect(screen.getByRole('region',{name:'过程分享的依据'})).toBeInTheDocument()
  expect(screen.getByRole('button',{name:/准备过程 赞/})).toBeInTheDocument()
  expect(container.querySelector('.account-portrait-quotes')).toBeNull()
  expect(screen.queryByText('“”')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:/准备过程 赞/}))
  expect(screen.getByRole('dialog')).toBeInTheDocument()
  expect(screen.getByText(note.desc)).toBeInTheDocument()
})

it('renders only nonempty original quotes among note-level sources and exceptions', () => {
  const {container} = render(<AccountPortraitView portrait={{summary:{
    statement:'笔记来源和摘句一起保留',
    evidence:[{noteId:'n1',scope:'note'},{noteId:'n1',quote:'先列成本'},{noteId:'n1',quote:''}],
    counterexamples:[{noteId:'n2',scope:'note'},{noteId:'n2',quote:'   '}],
  }}} observations={observations} notes={[note,{...note,noteId:'n2',title:'另一次准备'}]} mediaAssets={[]} />)
  fireEvent.click(screen.getByRole('button',{name:'查看依据 · 1 条笔记'}))
  expect(screen.getByText('“先列成本”')).toBeInTheDocument()
  expect(container.querySelectorAll('.account-portrait-quotes span')).toHaveLength(1)
  expect(screen.queryByText('“”')).not.toBeInTheDocument()
  expect(screen.getAllByRole('button',{name:/准备过程 赞/})).toHaveLength(1)
  expect(screen.getByRole('button',{name:/另一次准备 赞/})).toBeInTheDocument()
})

it('places note-linked next steps after performance and preserves legacy next steps', () => {
  const nextStep = {statement:'下一篇继续把选择过程写清楚',evidence:[{noteId:'n1',scope:'note' as const}]}
  const {rerender} = render(<AccountPortraitView portrait={{nextSteps:[nextStep]}} observations={observations} notes={[note]} mediaAssets={[]} />)
  expect(screen.queryByText(/本次暂无可展示/)).not.toBeInTheDocument()
  const step = screen.getByText(nextStep.statement)
  expect(step.closest('details')).toBeNull()
  expect(screen.getByText('笔记表现').compareDocumentPosition(step) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(step.compareDocumentPosition(screen.getByText('分析范围')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  fireEvent.click(screen.getByRole('button',{name:'查看依据 · 1 条笔记'}))
  expect(screen.getByRole('button',{name:/准备过程 赞/})).toBeInTheDocument()
  rerender(<AccountPortraitView portrait={{nextSteps:[nextStep]}} observations={observations} notes={[note]} mediaAssets={[]} nextSteps={<p>旧报告的下一篇建议</p>} />)
  expect(screen.getByText(nextStep.statement)).toBeInTheDocument()
  expect(screen.getByText('旧报告的下一篇建议')).toBeInTheDocument()
  rerender(<AccountPortraitView observations={observations} notes={[note]} mediaAssets={[]} nextSteps={<p>旧报告的下一篇建议</p>} />)
  expect(screen.getByText('旧报告的下一篇建议')).toBeInTheDocument()
  expect(screen.queryByText(/本次暂无可展示/)).not.toBeInTheDocument()
})

it('recognizes a valid recent change without an intro, but keeps the chronology requirement', () => {
  const {container,rerender} = render(<AccountPortraitView portrait={{recentChange:summary}} observations={{...observations,chronology:{status:'comparable'}}} notes={[note]} mediaAssets={[]} />)
  expect(screen.getByText('内容方向的新变化')).toBeInTheDocument()
  expect(container.querySelector('.account-portrait-intro')).toBeNull()
  expect(screen.queryByText(/本次暂无可展示/)).not.toBeInTheDocument()
  rerender(<AccountPortraitView portrait={{recentChange:summary}} observations={observations} notes={[note]} mediaAssets={[]} />)
  expect(screen.queryByText('内容方向的新变化')).not.toBeInTheDocument()
  expect(screen.getByText(/本次暂无可展示/)).toBeInTheDocument()
})

it('does not attribute an empty portrait to too few notes and preserves note performance', () => {
  render(<AccountPortraitView portrait={{summary:{statement:'无依据的概要',evidence:[]}}} observations={observations} notes={[note]} mediaAssets={[]} />)
  expect(screen.getByText(/本次暂无可展示的账号画像/)).toBeInTheDocument()
  expect(screen.queryByText(/选择更多笔记/)).not.toBeInTheDocument()
  expect(screen.queryByText('无依据的概要')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:note.title}))
  expect(screen.getByRole('button',{name:/准备过程 赞/})).toBeInTheDocument()
})

it('keeps long original statements and quotes intact when expanded', () => {
  const statement = '把长期准备写成可操作的过程。'.repeat(25)
  const quote = 'https://example.test/' + 'original-segment'.repeat(50)
  render(<AccountPortraitView portrait={{strengths:[{statement,evidence:[{noteId:'n1',quote}]}]}} observations={observations} notes={[note]} mediaAssets={[]} />)
  expect(screen.getByText(statement)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'查看依据 · 1 条笔记'}))
  expect(screen.getByText(`“${quote}”`)).toBeInTheDocument()
})

it('keeps every saved strength directly readable without an extra disclosure', () => {
  const strengths = Array.from({length:5}, (_,index) => ({...summary, statement:`优势 ${index + 1}：${'完整说明。'.repeat(5)}`}))
  const original = JSON.stringify(strengths)
  render(<AccountPortraitView portrait={{strengths}} observations={observations} notes={[note]} mediaAssets={[]} />)
  for (const claim of strengths) expect(screen.getByText(claim.statement).closest('details')).toBeNull()
  expect(screen.queryByText('更多优势')).not.toBeInTheDocument()
  fireEvent.click(screen.getAllByRole('button',{name:'查看依据 · 1 条笔记'})[4])
  expect(screen.getByText('“先列成本”')).toBeInTheDocument()
  expect(JSON.stringify(strengths)).toBe(original)
})

it('shows supporting findings directly and folds only source metadata after note performance', () => {
  const theme = {...summary, statement:'长期分享准备过程',evidence:[...summary.evidence,{noteId:'n2',quote:'第二次准备'}]}
  render(<AccountPortraitView portrait={{summary,recurringThemes:[theme],readerValue:[{...summary,statement:'让准备更省心'}],expressionPatterns:[],encouragement:{...summary,statement:'细致值得继续'}}} observations={observations} notes={[note]} mediaAssets={[]} />)
  expect(screen.getByRole('heading', {name:'内容方向与读者价值'})).toBeInTheDocument()
  for (const text of [theme.statement, '让准备更省心', '细致值得继续']) {
    expect(screen.getByText(text).closest('details')).toBeNull()
  }
  expect(screen.queryByText('表达特点')).not.toBeInTheDocument()
  const source = screen.getByText('分析范围').closest('details')!
  expect(source).not.toHaveAttribute('open')
  expect(screen.getByText('笔记表现').compareDocumentPosition(source) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  fireEvent.click(screen.getByText('分析范围'))
  expect(source).toHaveAttribute('open')
  expect(screen.getByText('1 条缺少发布时间')).toBeInTheDocument()
})

it('merges repeated findings without losing distinct supporting quotes or exceptions', () => {
  const portrait = {
    summary,
    strengths:[{statement:`${summary.statement}。`,evidence:[{noteId:'n2',quote:'第二份依据'}]}],
    expressionPatterns:[{...summary,counterexamples:[{noteId:'n3',quote:'另一种表达'}]}],
    encouragement:{...summary,evidence:[{noteId:'n1',quote:'第三句依据'}]},
  }
  const original = JSON.stringify(portrait)
  render(<AccountPortraitView portrait={portrait} observations={observations} notes={[note]} mediaAssets={[]} />)
  expect(screen.getAllByText(summary.statement)).toHaveLength(1)
  expect(screen.queryByRole('heading', {name:'值得继续放大的优势'})).not.toBeInTheDocument()
  expect(screen.queryByRole('heading', {name:'你的表达方式'})).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', {name:'查看依据 · 2 条笔记'}))
  for (const quote of ['先列成本','再分步骤','第二份依据','第三句依据','另一种表达']) expect(screen.getByText(`“${quote}”`)).toBeInTheDocument()
  expect(screen.getAllByText('“先列成本”')).toHaveLength(1)
  expect(JSON.stringify(portrait)).toBe(original)
})

it('merges equal keyword tags while retaining all their references and exceptions', () => {
  render(<AccountPortraitView portrait={{keywords:[
    {statement:'现场观察',evidence:[{noteId:'n1',quote:'第一处现场'}]},
    {statement:'现场观察',evidence:[{noteId:'n2',quote:'第二处现场'}],counterexamples:[{noteId:'n3',quote:'一次抽象讨论'}]},
  ]}} observations={observations} notes={[note]} mediaAssets={[]} />)
  expect(screen.getAllByRole('button',{name:'现场观察：查看 2 条笔记依据'})).toHaveLength(1)
  fireEvent.click(screen.getByRole('button',{name:'现场观察：查看 2 条笔记依据'}))
  for (const quote of ['第一处现场','第二处现场','一次抽象讨论']) expect(screen.getByText(`“${quote}”`)).toBeInTheDocument()
})

it('counts and browses unique notes while retaining every quoted passage', () => {
  render(<AccountPortraitView portrait={{summary}} observations={observations} notes={[note]} mediaAssets={[]} />)
  fireEvent.click(screen.getByRole('button',{name:'查看依据 · 1 条笔记'}))
  expect(screen.getByText('“先列成本”')).toBeInTheDocument()
  expect(screen.getByText('“再分步骤”')).toBeInTheDocument()
  expect(screen.getAllByRole('button',{name:/准备过程 赞/})).toHaveLength(1)
})

it('keeps historical claims and quotes visible when snapshot notes are missing', () => {
  render(<AccountPortraitView portrait={{summary:{...summary,counterexamples:[{noteId:'gone',quote:'历史例外'}]}}} observations={observations} notes={[]} mediaAssets={[]} />)
  expect(screen.getByText('把过程讲得具体')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'查看依据 · 1 条笔记'}))
  expect(screen.getByText('1 条依据笔记未保留在本次分析快照中，仅显示历史引用。')).toBeInTheDocument()
  expect(screen.getByText('1 条例外笔记未保留在本次分析快照中，仅显示历史引用。')).toBeInTheDocument()
  expect(screen.getByText('“历史例外”')).toBeInTheDocument()
  expect(screen.getByRole('button',{name:'准备过程'})).toBeDisabled()
  expect(screen.queryByRole('button',{name:/准备过程 赞/})).not.toBeInTheDocument()
})

it('deduplicates exception notes independently of supporting notes', () => {
  render(<AccountPortraitView portrait={{summary:{...summary,counterexamples:[{noteId:'n2',quote:'随笔'},{noteId:'n2',quote:'心情'}]}}} observations={observations} notes={[note,{...note,noteId:'n2',title:'偶尔的随笔'}]} mediaAssets={[]} />)
  fireEvent.click(screen.getByRole('button',{name:'查看依据 · 1 条笔记'}))
  expect(screen.getAllByRole('button',{name:/偶尔的随笔 赞/})).toHaveLength(1)
})

it('closes evidence dialogs on run changes and never borrows another workspace cover', () => {
  const run:AnalysisRun = {id:'run-1',workspaceId:'w1',workflowType:'account_diagnosis',status:'completed',inputSnapshot:{xhsCreatorProfile:{notes:[note]}},stageResults:{},stageErrors:{},modelMetadata:{},userNotes:'',reviewStatus:'unreviewed',createdAt:'2026-10-01',updatedAt:'2026-10-01',startedAt:null,completedAt:null}
  const media:MediaAsset = {id:'cover',workspaceId:'other',type:'image',name:'其他账号的封面',purpose:'',sourceType:'upload',originalFilename:'',mediaType:'image/png',byteSize:10,sha256:'',metadata:{noteId:'n1'},derived:{},userNotes:'',fileUrl:'/other-account.png',createdAt:'',updatedAt:''}
  const props = {stage:{key:'profile',n:'1',title:'画像',status:'completed' as const,result:{profile:{accountPortrait:{summary}},observations}},currentRun:run,mediaAssets:[media],onSaveGeneratedTopic:vi.fn(),onSelectTopic:vi.fn(),onGenerateBrief:vi.fn(),onGenerateDraft:vi.fn(),onFillSimulationTopic:vi.fn()}
  const {rerender} = render(<StageResultRenderer {...props} />)
  fireEvent.click(screen.getByRole('button',{name:'查看依据 · 1 条笔记'}))
  expect(screen.queryByRole('img')).not.toBeInTheDocument()
  rerender(<StageResultRenderer {...props} mediaAssets={[{...media,workspaceId:'w1'}]} />)
  expect(screen.getByRole('img')).toHaveAttribute('src','/other-account.png')
  fireEvent.click(screen.getByRole('button',{name:/准备过程 赞/}))
  expect(screen.getByRole('dialog')).toBeInTheDocument()
  // Same note ID in another snapshot must not retain an open detail dialog.
  rerender(<StageResultRenderer {...props} currentRun={{...run,id:'run-2',workspaceId:'w2',inputSnapshot:{xhsCreatorProfile:{notes:[{...note,desc:'另一份快照'}]}}}} />)
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.getByRole('button',{name:'查看依据 · 1 条笔记'})).toHaveAttribute('aria-expanded','false')
  fireEvent.click(screen.getByRole('button',{name:'查看依据 · 1 条笔记'}))
  fireEvent.click(screen.getByRole('button',{name:/准备过程 赞/}))
  expect(screen.getByText('另一份快照')).toBeInTheDocument()
  expect(screen.queryByText(note.desc)).not.toBeInTheDocument()
})
