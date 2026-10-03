import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { AccountPerformanceView, type PerformanceNote } from './AccountPerformanceView'

afterEach(cleanup)
const notes: PerformanceNote[] = [
  {noteId:'a',title:'点赞突出',metrics:{liked:100,collected:0,comments:1,shares:0}},
  {noteId:'b',title:'收藏突出',metrics:{liked:20,collected:80,comments:2,shares:0}},
  {noteId:'c',title:'讨论突出',metrics:{liked:10,collected:10,comments:60}},
  {noteId:'d',title:'分享突出',metrics:{liked:0,collected:4,comments:0,shares:20}},
]
function setup(input = notes) {
  return render(<AccountPerformanceView observations={input} notes={input.map(note => ({...note,metrics:{liked:note.metrics.liked ?? undefined},desc:'历史正文',comments:[]}))} mediaAssets={[]} />)
}
function select(value:string) { fireEvent.change(screen.getByRole('combobox',{name:'比较指标'}),{target:{value}}) }

it('switches independent metrics and displays medians, missingness and frozen notes', () => {
  const {container} = setup()
  const original = JSON.stringify(notes)
  expect(screen.getByRole('status')).toHaveTextContent('点赞数据 4 / 4 条 · 中位数 15')
  for (const [metric, title, label] of [['collected','收藏突出','收藏'],['comments','讨论突出','评论'],['shares','分享突出','分享']]) {
    select(metric)
    const top = container.querySelector('.account-performance-group')!
    expect(within(top as HTMLElement).getAllByRole('button')[0]).toHaveTextContent(title)
    expect(within(top as HTMLElement).getByText(new RegExp(`本次${label}第 1`))).toBeInTheDocument()
  }
  expect(screen.getByRole('status')).toHaveTextContent('分享数据 3 / 4 条 · 中位数 0 · 1 条未获取')
  expect(JSON.stringify(notes)).toBe(original)
  fireEvent.click(screen.getByRole('button',{name:'分享突出'}))
  expect(screen.getByRole('button',{name:/分享突出 赞/})).toBeInTheDocument()
  select('liked')
  expect(screen.queryByRole('button',{name:/分享突出 赞/})).not.toBeInTheDocument()
})

it('does not put tied zero-value notes into opposing high and low groups', () => {
  setup(notes.map(note=>({...note,metrics:{liked:0}})))
  expect(screen.getByText('所选笔记点赞相同')).toBeInTheDocument()
  expect(screen.queryByText('所选笔记中点赞较低')).not.toBeInTheDocument()
  expect(screen.getAllByText(/本次点赞第 1/)).toHaveLength(2)
  expect(screen.getByRole('status')).toHaveTextContent('中位数 0')
})

it('keeps tied cutoff values out of the lower group', () => {
  const {container} = setup(notes.map((note,i)=>({...note,metrics:{liked:i === 3 ? 1 : 10}})))
  const lower = container.querySelectorAll('.account-performance-group')[1] as HTMLElement
  expect(within(lower).getAllByRole('button')).toHaveLength(1)
  expect(within(lower).getByRole('button')).toHaveTextContent('分享突出')
  expect(within(lower).getByText(/本次点赞第 2/)).toBeInTheDocument()
})

it('still offers other metrics when all likes are missing', () => {
  setup([{noteId:'a',title:'可收藏',metrics:{liked:null,collected:3}}])
  expect(screen.getByRole('status')).toHaveTextContent('本次未获取点赞数据')
  select('collected')
  expect(screen.getByRole('button',{name:'可收藏'})).toBeInTheDocument()
  expect(screen.getByRole('status')).toHaveTextContent('中位数 3')
  select('shares')
  expect(screen.getByRole('status')).toHaveTextContent('本次未获取分享数据')
})

it('rejects nonfinite, negative and fractional counts while keeping zero', () => {
  setup([NaN,Infinity,-1,0.5,0].map((liked,i)=>({noteId:String(i),title:String(i),metrics:{liked}})))
  expect(screen.getByRole('status')).toHaveTextContent('点赞数据 1 / 5 条 · 中位数 0 · 4 条未获取')
})

it('supports saved summaries and falls back to frozen counts when summaries disagree', () => {
  const props = {observations:notes,notes:[],mediaAssets:[]}
  const summary = {metric:'liked' as const,validCount:4,missingCount:0,median:15,rankMethod:'dense_descending'}
  const {rerender} = render(<AccountPerformanceView {...props} summaries={[summary]} />)
  expect(screen.getByRole('status')).toHaveTextContent('中位数 15')
  expect(screen.getByRole('button',{name:'点赞突出'})).toBeDisabled()
  rerender(<AccountPerformanceView {...props} summaries={[{...summary,median:999}]} />)
  expect(screen.getByRole('status')).toHaveTextContent('中位数 15')
})

it('keeps an empty snapshot readable without creating ranks or fetching data', () => {
  setup([])
  expect(screen.getByRole('status')).toHaveTextContent('本次未获取点赞数据')
  expect(screen.queryByText(/本次点赞第/)).not.toBeInTheDocument()
})
