import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useRef, useState } from 'react'
import { GuidedTour } from './GuidedTour'
import { findGuideTarget } from './guideTargets'

const steps = [
  { target: '#target-a', title: '选择范围', description: '先选择笔记。' },
  { target: '#target-b', title: '开始分析', description: '确认之后再分析。' },
]
beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, 'getClientRects').mockReturnValue([{width: 100, height: 40}] as unknown as DOMRectList)
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({left: 20, top: 40, right: 120, bottom: 80, width: 100, height: 40} as DOMRect)
})
afterEach(() => { cleanup(); vi.restoreAllMocks() })

describe('GuidedTour', () => {
  it('steps forwards and backwards without clicking or changing target controls', () => {
    const action = vi.fn(), close = vi.fn()
    render(<><button id="target-a" onClick={action}>范围</button><button id="target-b" disabled>运行</button><GuidedTour steps={steps} onClose={close} /></>)
    expect(screen.getByRole('heading')).toHaveTextContent('选择范围')
    expect(screen.getByRole('button', {name: '上一步'})).toBeDisabled()
    fireEvent.click(screen.getByRole('button', {name: '下一步'}))
    expect(screen.getByRole('heading')).toHaveTextContent('开始分析')
    fireEvent.keyDown(screen.getByRole('dialog'), {key: 'ArrowLeft'})
    expect(screen.getByRole('heading')).toHaveTextContent('选择范围')
    fireEvent.keyDown(screen.getByRole('dialog'), {key: 'ArrowRight'})
    fireEvent.click(screen.getByRole('button', {name: '完成'}))
    expect(close).toHaveBeenCalledOnce()
    expect(action).not.toHaveBeenCalled()
    expect(screen.getByRole('button', {name: '运行'})).toBeDisabled()
  })
  it('supports escape and returns focus to the help button, preserving unsaved text', () => {
    function Harness() {
      const ref = useRef<HTMLButtonElement>(null)
      const [open, setOpen] = useState(false)
      return <><input defaultValue="未保存的文字" /><button ref={ref} onClick={() => setOpen(true)}>引导</button>{open && <GuidedTour steps={steps} returnFocusRef={ref} onClose={() => setOpen(false)} />}</>
    }
    render(<Harness />)
    fireEvent.click(screen.getByRole('button', {name: '引导'}))
    fireEvent.keyDown(screen.getByRole('dialog'), {key: 'Escape'})
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByRole('button', {name: '引导'})).toHaveFocus()
    expect(screen.getByRole('textbox')).toHaveValue('未保存的文字')
  })
  it('ignores hidden elements, selects the visible match, and explains missing targets', () => {
    render(<><div hidden><button className="candidate">隐藏</button></div><button className="candidate">可见</button><GuidedTour steps={steps} onClose={vi.fn()} /></>)
    expect(findGuideTarget('.candidate')).toHaveTextContent('可见')
    expect(screen.getByText('此入口当前未显示，可以继续下一步。')).toBeInTheDocument()
  })
  it('keeps keyboard focus in the guide', () => {
    render(<GuidedTour steps={steps} onClose={vi.fn()} />)
    const next = screen.getByRole('button', {name: '下一步'})
    next.focus()
    fireEvent.keyDown(next, {key: 'Tab'})
    expect(screen.getByRole('button', {name: '结束引导'})).toHaveFocus()
    fireEvent.keyDown(document.activeElement!, {key: 'Tab', shiftKey: true})
    expect(next).toHaveFocus()
  })
})
