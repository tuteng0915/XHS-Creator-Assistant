import {act, cleanup, fireEvent, render, screen} from '@testing-library/react'
import {afterEach, expect, it, vi} from 'vitest'
import {InfoHint} from './InfoHint'

afterEach(() => {cleanup(); vi.useRealTimers(); vi.restoreAllMocks()})
const hint = <InfoHint label="参考说明">只读取选中的分析结果。</InfoHint>

it('keeps supplementary copy out of the page until hovered or focused', () => {
  render(hint)
  const trigger = screen.getByRole('button', {name: '参考说明'})
  expect(screen.queryByText('只读取选中的分析结果。')).not.toBeInTheDocument()
  expect(trigger).toHaveAttribute('type', 'button')
  fireEvent.mouseEnter(trigger)
  expect(screen.getByRole('tooltip')).toHaveTextContent('只读取选中的分析结果。')
  expect(trigger).toHaveAttribute('aria-describedby', screen.getByRole('tooltip').id)
})

it('allows hovering the explanation without it disappearing across the small gap', () => {
  vi.useFakeTimers()
  render(hint)
  const trigger = screen.getByRole('button')
  fireEvent.mouseEnter(trigger); fireEvent.mouseLeave(trigger)
  act(() => vi.advanceTimersByTime(60))
  fireEvent.mouseEnter(screen.getByRole('tooltip'))
  act(() => vi.advanceTimersByTime(500))
  expect(screen.getByRole('tooltip')).toBeVisible()
  fireEvent.mouseLeave(screen.getByRole('tooltip'))
  act(() => vi.advanceTimersByTime(121))
  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
})

it('opens for keyboard focus, lets Escape dismiss only the hint, and retains focus', () => {
  const parentEscape = vi.fn()
  render(<div onKeyDown={parentEscape}>{hint}</div>)
  const trigger = screen.getByRole('button')
  act(() => trigger.focus())
  expect(screen.getByRole('tooltip')).toBeVisible()
  fireEvent.keyDown(trigger, {key: 'Escape'})
  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  expect(trigger).toHaveFocus()
  expect(parentEscape).not.toHaveBeenCalled()
  expect(trigger).not.toHaveAttribute('aria-describedby')
})

it('supports touch/click pinning, second-click close and outside dismissal', () => {
  render(<>{hint}<button>其他操作</button></>)
  const trigger = screen.getByRole('button', {name: '参考说明'})
  fireEvent.pointerDown(trigger, {pointerType: 'touch'}); fireEvent.focus(trigger); fireEvent.click(trigger)
  expect(screen.getByRole('tooltip')).toBeVisible()
  fireEvent.click(trigger)
  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  fireEvent.click(trigger)
  fireEvent.pointerDown(screen.getByRole('button', {name: '其他操作'}))
  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
})

it('does not submit a surrounding form or close its dialog', () => {
  const submit = vi.fn(e => e.preventDefault())
  render(<dialog open aria-label="范围"><form onSubmit={submit}>{hint}</form></dialog>)
  fireEvent.click(screen.getByRole('button'))
  expect(screen.getByRole('tooltip').parentElement).toBe(screen.getByRole('dialog'))
  expect(submit).not.toHaveBeenCalled()
})

it('clamps near the viewport edge and updates after resizing', () => {
  render(hint)
  const trigger = screen.getByRole('button')
  vi.spyOn(trigger, 'getBoundingClientRect').mockReturnValue({left: window.innerWidth - 20, top: 80, bottom: 106} as DOMRect)
  fireEvent.mouseEnter(trigger)
  const tooltip = screen.getByRole('tooltip')
  expect(parseFloat(tooltip.style.left)).toBeLessThanOrEqual(window.innerWidth - 312)
  vi.spyOn(tooltip, 'getBoundingClientRect').mockReturnValue({width: 260, height: 100} as DOMRect)
  vi.spyOn(trigger, 'getBoundingClientRect').mockReturnValue({left: 1, top: window.innerHeight - 35, bottom: window.innerHeight - 9} as DOMRect)
  fireEvent.resize(window)
  expect(tooltip.style.left).toBe('12px')
  expect(parseFloat(tooltip.style.top)).toBe(window.innerHeight - 141)
})

it('uses unique descriptions and cleans up a pending hide on unmount', () => {
  vi.useFakeTimers()
  const {unmount} = render(<>{hint}<InfoHint label="保存说明">手动保存。</InfoHint></>)
  fireEvent.mouseEnter(screen.getByRole('button', {name: '参考说明'}))
  fireEvent.mouseEnter(screen.getByRole('button', {name: '保存说明'}))
  const ids = screen.getAllByRole('tooltip').map(tip => tip.id)
  expect(new Set(ids).size).toBe(2)
  fireEvent.mouseLeave(screen.getByRole('button', {name: '参考说明'}))
  unmount()
  act(() => vi.runAllTimers())
  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
})
