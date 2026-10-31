import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from 'react'
import { createPortal } from 'react-dom'
import type { GuideStep } from './guideSteps'
import { findGuideTarget } from './guideTargets'
import './GuidedTour.css'

/** Read-only tour: the native modal makes the underlying controls inert. */
export function GuidedTour({ steps, onClose, returnFocusRef }: { steps: GuideStep[]; onClose: () => void; returnFocusRef?: RefObject<HTMLElement | null> }) {
  const [index, setIndex] = useState(0)
  const [layout, setLayout] = useState<{ x: number; y: number; w: number; h: number; left: number; top: number } | null>(null)
  const dialog = useRef<HTMLDialogElement>(null)
  const card = useRef<HTMLDivElement>(null)
  const current = steps[index]
  useEffect(() => {
    const previous = returnFocusRef?.current || document.activeElement as HTMLElement | null
    const node = dialog.current
    if (node?.showModal) node.showModal()
    else node?.setAttribute('open', '')
    return () => { node?.close?.(); previous?.focus({ preventScroll: true }) }
  }, [returnFocusRef])

  useLayoutEffect(() => {
    const target = findGuideTarget(current.target)
    target?.scrollIntoView?.({ block: 'center', inline: 'nearest', behavior: 'instant' })
    let frame = 0
    const measure = () => {
      const element = findGuideTarget(current.target)
      const rect = element?.getBoundingClientRect()
      const width = window.innerWidth
      const height = window.innerHeight
      const cardWidth = card.current?.offsetWidth || Math.min(340, width - 24)
      const cardHeight = card.current?.offsetHeight || 230
      const x = Math.max(6, (rect?.left ?? width / 2) - 5)
      const y = Math.max(6, (rect?.top ?? height / 2) - 5)
      const right = Math.min(width - 6, (rect?.right ?? x) + 5)
      const bottom = Math.min(height - 6, (rect?.bottom ?? y) + 5)
      const top = bottom + cardHeight + 24 < height ? bottom + 12 : y - cardHeight - 12 > 12 ? y - cardHeight - 12 : Math.max(12, height - cardHeight - 12)
      setLayout({ x, y, w: rect ? Math.max(0, right - x) : 0, h: rect ? Math.max(0, bottom - y) : 0,
        left: Math.max(12, Math.min(width - cardWidth - 12, width > 760 && right + cardWidth + 24 < width ? right + 12 : x)),
        top })
    }
    const update = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(measure) }
    measure()
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(update) : null
    if (target) observer?.observe(target)
    if (card.current) observer?.observe(card.current)
    const mutations = new MutationObserver(update)
    const main = document.querySelector('.workspace-main')
    if (main) mutations.observe(main, { childList: true, subtree: true, attributes: true, attributeFilter: ['hidden', 'class'] })
    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, true)
    return () => { cancelAnimationFrame(frame); observer?.disconnect(); mutations.disconnect(); window.removeEventListener('resize', update); window.removeEventListener('scroll', update, true) }
  }, [current])

  return createPortal(<dialog ref={dialog} className="guided-tour" aria-label="操作引导" aria-describedby="guide-description"
    onCancel={event => { event.preventDefault(); onClose() }}
    onKeyDown={event => {
      if (event.key === 'Escape') { event.preventDefault(); onClose() }
      if (event.key === 'ArrowRight' && index < steps.length - 1) { event.preventDefault(); setIndex(index + 1) }
      if (event.key === 'ArrowLeft' && index > 0) { event.preventDefault(); setIndex(index - 1) }
      if (event.key === 'Tab') {
        const buttons = Array.from(card.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') || [])
        const first = buttons[0], last = buttons[buttons.length - 1]
        if (event.shiftKey && document.activeElement === first) {event.preventDefault(); last?.focus()}
        else if (!event.shiftKey && document.activeElement === last) {event.preventDefault(); first?.focus()}
      }
    }}>
    <div className="guided-tour-spotlight" aria-hidden="true" style={layout ? {left: layout.x, top: layout.y, width: layout.w, height: layout.h} : undefined} />
    <div className="guided-tour-card" ref={card} style={layout ? {left: layout.left, top: layout.top} : undefined}>
      <div className="guided-tour-top"><span>{index + 1} / {steps.length}</span><button type="button" onClick={onClose}>结束引导</button></div>
      <div aria-live="polite" aria-atomic="true"><h2>{current.title}</h2><p id="guide-description">{current.description}</p>
        {layout?.w === 0 && <p className="guided-tour-unavailable">此入口当前未显示，可以继续下一步。</p>}</div>
      <div className="guided-tour-actions"><button type="button" disabled={index === 0} onClick={() => setIndex(index - 1)}>上一步</button><button type="button" className="primary" onClick={() => index === steps.length - 1 ? onClose() : setIndex(index + 1)}>{index === steps.length - 1 ? '完成' : '下一步'}</button></div>
    </div>
  </dialog>, document.body)
}
