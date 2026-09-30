import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { CreatorNoteSelectionDialog } from './CreatorNoteSelectionDialog'
import type { CreatorNote } from '../creatorNotes'

afterEach(cleanup)
const notes: CreatorNote[] = Array.from({length:12}, (_, i) => ({
  noteId: `n${i}`, title: `笔记 ${i}`, desc: `正文 ${i}`, metrics: {liked: i}, comments: [{content: `评论 ${i}`}],
}))

it('reuses note cards and details and commits only an explicit selection', () => {
  const confirm = vi.fn()
  render(<CreatorNoteSelectionDialog notes={notes} mediaAssets={[]} scope="recent_10" onConfirm={confirm} onClose={vi.fn()} />)
  expect(screen.getAllByRole('checkbox').filter(el => (el as HTMLInputElement).checked)).toHaveLength(10)
  fireEvent.click(screen.getByRole('button', {name: '清空'}))
  expect(screen.getByRole('button', {name: '完成'})).toBeDisabled()
  fireEvent.click(screen.getByRole('checkbox', {name: '选择笔记：笔记 11'}))
  expect(screen.getByRole('status')).toHaveTextContent('已选 1 / 12')
  fireEvent.click(screen.getByRole('button', {name: /笔记 11 赞/}))
  const detail = screen.getByRole('dialog', {name:'笔记 11'})
  expect(within(detail).getByText('正文 11')).toBeInTheDocument()
  expect(within(detail).getByText('评论 11')).toBeInTheDocument()
  fireEvent.click(within(detail).getByRole('button', {name:'关闭'}))
  expect(confirm).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', {name:'完成'}))
  expect(confirm).toHaveBeenCalledWith('recent_10', ['n11'])
})

it('cancels without applying and can return to preset selection', () => {
  const confirm = vi.fn(), close = vi.fn()
  render(<CreatorNoteSelectionDialog notes={notes} mediaAssets={[]} scope="recent_10" selectedIds={['n11']} onConfirm={confirm} onClose={close} />)
  expect(screen.getByLabelText('从已导入笔记中选择')).toHaveValue('custom')
  fireEvent.click(screen.getByRole('button', {name:'全选'}))
  expect(screen.getByRole('status')).toHaveTextContent('已选 12 / 12')
  fireEvent.click(screen.getByRole('button', {name:'取消'}))
  expect(close).toHaveBeenCalledOnce()
  expect(confirm).not.toHaveBeenCalled()
  fireEvent.change(screen.getByLabelText('从已导入笔记中选择'), {target:{value:'recent_10'}})
  fireEvent.click(screen.getByRole('button', {name:'完成'}))
  expect(confirm).toHaveBeenCalledWith('recent_10', undefined)
})
