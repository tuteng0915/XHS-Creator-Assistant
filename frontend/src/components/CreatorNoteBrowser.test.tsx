import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { CreatorNote } from '../creatorNotes'
import type { MediaAsset } from '../types'
import { CreatorNoteBrowser } from './CreatorNoteBrowser'

afterEach(cleanup)
const note: CreatorNote = {noteId:'n',title:'已保存笔记',desc:'正文',metrics:{liked:1,shares:2},comments:[],coverMediaAssetId:'cover',publishedAt:'2026-10-01',metricsObservedAt:'2026-10-08T12:00:00Z',commentsObservedAt:'2026-10-09T12:00:00Z'}
const media = (id:string, url:string): MediaAsset => ({id,workspaceId:'w',type:'image',name:id,purpose:'reference',sourceType:'upload',originalFilename:`${id}.jpg`,mediaType:'image/jpeg',byteSize:1,sha256:'',metadata:{noteId:'n'},derived:{},userNotes:'',fileUrl:url,createdAt:'',updatedAt:''})

it('groups likes and collections above comments and shares in two metric rows', () => {
  render(<CreatorNoteBrowser notes={[{...note,metrics:{liked:11,collected:22,comments:33,shares:44}}]} mediaAssets={[]} />)
  const card = screen.getByRole('button', {name:/已保存笔记 赞/})
  const metrics = card.querySelector('.creator-note-metrics')
  expect(metrics).toBeInTheDocument()
  const rows = metrics!.querySelectorAll('.creator-note-metric-row')
  expect(rows).toHaveLength(2)
  expect(Array.from(rows[0].children, item => item.textContent)).toEqual(['赞 11', '收藏 22'])
  expect(Array.from(rows[1].children, item => item.textContent)).toEqual(['评论 33', '分享 44'])
})

it.each<{
  label: string
  metrics: CreatorNote['metrics']
  expected: string[][]
}>([
  {label:'valid zero counts',metrics:{liked:0,collected:0,comments:0,shares:0},expected:[['赞 0','收藏 0'],['评论 0','分享 0']]},
  {label:'missing counts',metrics:{},expected:[['赞 —','收藏 —'],['评论 —','分享 —']]},
  {label:'invalid counts',metrics:{liked:-1,collected:NaN,comments:Infinity,shares:-2},expected:[['赞 —','收藏 —'],['评论 —','分享 —']]},
])('preserves $label in both metric rows', ({metrics, expected}) => {
  render(<CreatorNoteBrowser notes={[{...note,metrics}]} mediaAssets={[]} />)
  const rows = screen.getByRole('button', {name:/已保存笔记 赞/}).querySelectorAll('.creator-note-metric-row')
  expect(rows).toHaveLength(2)
  expect(Array.from(rows, row => Array.from(row.children, item => item.textContent))).toEqual(expected)
})

it('previews saved images and observation timestamps without toggling selection', () => {
  const toggle = vi.fn()
  render(<CreatorNoteBrowser notes={[note]} mediaAssets={[media('cover','/one.jpg'),media('second','/two.jpg')]} selectedIds={[]} onToggle={toggle} />)
  expect(screen.getByRole('img',{name:'已保存笔记'})).toHaveAttribute('src','/one.jpg')
  fireEvent.click(screen.getByRole('button',{name:/已保存笔记 赞/}))
  const detail = screen.getByRole('dialog',{name:'已保存笔记'})
  expect(within(detail).getAllByRole('img')).toHaveLength(2)
  expect(within(detail).getByText('指标截至 2026/10/8')).toBeVisible()
  expect(within(detail).getByText('评论更新于 2026/10/9')).toBeVisible()
  expect(toggle).not.toHaveBeenCalled()
  fireEvent.click(within(detail).getByRole('button',{name:'关闭'}))
  fireEvent.click(screen.getByRole('checkbox'))
  expect(toggle).toHaveBeenCalledWith('n')
})

it('keeps the close control outside the note scroll area and restores focus after closing', () => {
  render(<CreatorNoteBrowser notes={[{...note, desc:'长正文\n'.repeat(100)}]} mediaAssets={[]} />)
  const trigger = screen.getByRole('button', {name:/已保存笔记 赞/})
  trigger.focus()
  fireEvent.click(trigger)
  const dialog = screen.getByRole('dialog', {name:'已保存笔记'})
  expect(dialog).toHaveClass('creator-note-preview-dialog')
  const body = dialog.querySelector('.creator-dialog-body')!
  expect(body.querySelector('.creator-note-detail')).toBeInTheDocument()
  const close = within(dialog).getByRole('button', {name:'关闭'})
  expect(body).not.toContainElement(close)
  expect(dialog.querySelector('.creator-dialog-head')).toContainElement(close)
  fireEvent.scroll(body, {target:{scrollTop:500}})
  fireEvent.click(close)
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(trigger).toHaveFocus()

  fireEvent.click(trigger)
  fireEvent(screen.getByRole('dialog', {name:'已保存笔记'}), new Event('cancel', {cancelable:true}))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(trigger).toHaveFocus()
})

it('keeps negative or unknown metrics absent in the card and supports top N browsing', () => {
  const notes = Array.from({length:12},(_,i) => ({...note,noteId:`n${i}`,title:`笔记 ${i}`,metrics:{liked:i}}))
  render(<CreatorNoteBrowser notes={[...notes,{...note,noteId:'bad',title:'缺失指标',metrics:{liked:-3}}]} mediaAssets={[]} showFilters />)
  fireEvent.change(screen.getByLabelText('排序'),{target:{value:'liked'}})
  fireEvent.change(screen.getByLabelText('显示'),{target:{value:'10'}})
  expect(screen.getAllByRole('article')).toHaveLength(10)
  expect(screen.getAllByRole('article')[0]).toHaveTextContent('笔记 11')
  expect(screen.queryByText('缺失指标')).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('显示'),{target:{value:'0'}})
  expect(screen.getByRole('button',{name:/缺失指标 赞/})).toHaveTextContent('赞 —')
})

it('can preview saved text and images without displaying comment or observation-time sections', () => {
  render(<CreatorNoteBrowser notes={[{...note, comments: [{content: '不在本次参考范围的评论'}]}]} mediaAssets={[media('cover', '/one.jpg')]} showComments={false} showObservationTimes={false} />)
  fireEvent.click(screen.getByRole('button', {name: /已保存笔记 赞/}))
  const detail = screen.getByRole('dialog', {name: '已保存笔记'})
  expect(within(detail).getByText('正文')).toBeVisible()
  expect(within(detail).getByRole('img')).toHaveAttribute('src', '/one.jpg')
  expect(within(detail).queryByRole('region', {name: '笔记评论'})).not.toBeInTheDocument()
  expect(within(detail).queryByText(/指标截至|指标时间未记录|评论更新于|暂未读取到评论/)).not.toBeInTheDocument()
  expect(within(detail).queryByText('不在本次参考范围的评论')).not.toBeInTheDocument()
})
