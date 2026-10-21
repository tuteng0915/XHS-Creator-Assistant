import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { CreatorDialog } from './CreatorDialog'

afterEach(cleanup)

it('separates long content from the header and footer without changing short dialogs', () => {
  const { rerender } = render(<CreatorDialog title="长内容" scrollBody onClose={vi.fn()} footer={<button>确认</button>}><p>正文</p></CreatorDialog>)
  const dialog = screen.getByRole('dialog')
  expect(dialog).toHaveClass('creator-dialog-scroll')
  const body = dialog.querySelector('.creator-dialog-body')!
  expect(body).toContainElement(screen.getByText('正文'))
  expect(body).not.toContainElement(screen.getByRole('button', {name:'关闭'}))
  expect(body).not.toContainElement(screen.getByRole('button', {name:'确认'}))
  expect(dialog.querySelector('.creator-dialog-footer')).toContainElement(screen.getByRole('button', {name:'确认'}))

  rerender(<CreatorDialog title="短确认" onClose={vi.fn()}><p>简短提示</p></CreatorDialog>)
  expect(dialog).not.toHaveClass('creator-dialog-scroll')
  expect(dialog.querySelector('.creator-dialog-body')).toBeNull()
  expect(dialog.querySelector('.creator-dialog-footer')).toBeNull()
})

it('explains blocked closing, protects Escape, and restores closing after the operation ends', () => {
  const close = vi.fn(), reason = '正在保存，请等待完成后再关闭。'
  const { rerender } = render(<CreatorDialog title="保存" onClose={close} closeDisabledReason={reason}><p>内容</p></CreatorDialog>)
  const dialog = screen.getByRole('dialog')
  expect(within(dialog).getByRole('button', {name:'关闭'})).toBeDisabled()
  expect(within(dialog).getByRole('status')).toHaveTextContent(reason)
  fireEvent.click(within(dialog).getByRole('button', {name:'关闭'}))
  fireEvent(dialog, new Event('cancel', {cancelable:true}))
  expect(close).not.toHaveBeenCalled()
  fireEvent.mouseEnter(within(dialog).getByRole('group', {name:'关闭暂不可用'}))
  expect(within(dialog).getByRole('tooltip')).toHaveTextContent(reason)

  rerender(<CreatorDialog title="保存" onClose={close}><p>内容</p></CreatorDialog>)
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  expect(within(dialog).getByRole('button', {name:'关闭'})).toBeEnabled()
  fireEvent(dialog, new Event('cancel', {cancelable:true}))
  expect(close).toHaveBeenCalledTimes(1)
  fireEvent.click(within(dialog).getByRole('button', {name:'关闭'}))
  expect(close).toHaveBeenCalledTimes(2)
})
