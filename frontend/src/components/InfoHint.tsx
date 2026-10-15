import {useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode} from 'react'
import {createPortal} from 'react-dom'
import './InfoHint.css'

/** Short, supplementary help only. Keep errors and action consequences visible. */
export function InfoHint({label, children, action}: {
  label: string
  children: ReactNode
  action?: {label: string; onClick: () => void; className?: string}
}) {
  const id = useId()
  const trigger = useRef<HTMLButtonElement>(null)
  const bubble = useRef<HTMLSpanElement>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pinned = useRef(false)
  const focused = useRef(false)
  const pointerFocus = useRef(false)
  const [host, setHost] = useState<HTMLElement | null>(null)
  const [open, setOpen] = useState(false)
  const [position, setPosition] = useState({left: 0, top: 0, ready: false})

  const clearTimer = useCallback(() => {if (timer.current !== null) clearTimeout(timer.current); timer.current = null}, [])
  const close = useCallback(() => {clearTimer(); pinned.current = false; focused.current = false; setOpen(false)}, [clearTimer])
  function show() {
    clearTimer()
    // A dialog's top layer makes body portals inert/hidden behind its backdrop.
    setHost(trigger.current?.closest('dialog') || document.body)
    setOpen(true)
  }
  function leave() {
    clearTimer()
    if (!pinned.current && !focused.current) timer.current = setTimeout(() => setOpen(false), 120)
  }
  useEffect(() => () => {if (timer.current !== null) clearTimeout(timer.current)}, [])

  useLayoutEffect(() => {
    if (!open || !host) return
    function place() {
      if (!trigger.current || !bubble.current) return
      const anchor = trigger.current.getBoundingClientRect()
      const tip = bubble.current.getBoundingClientRect()
      const margin = 12, gap = 6
      const width = tip.width || Math.min(300, window.innerWidth - margin * 2)
      const height = tip.height
      const left = Math.max(margin, Math.min(anchor.left, window.innerWidth - width - margin))
      const below = window.innerHeight - anchor.bottom - margin
      const top = below < height + gap && anchor.top > below
        ? Math.max(margin, anchor.top - height - gap)
        : Math.max(margin, Math.min(anchor.bottom + gap, window.innerHeight - height - margin))
      setPosition({left, top, ready: true})
    }
    place()
    window.addEventListener('resize', place)
    window.addEventListener('scroll', place, true)
    return () => {window.removeEventListener('resize', place); window.removeEventListener('scroll', place, true)}
  }, [open, host, children])

  useEffect(() => {
    if (!open) return
    function outside(event: PointerEvent) {
      const node = event.target as Node
      if (!trigger.current?.contains(node) && !bubble.current?.contains(node)) close()
    }
    function escape(event: KeyboardEvent) {
      if (event.key !== 'Escape') return
      event.preventDefault(); event.stopPropagation(); close()
    }
    document.addEventListener('pointerdown', outside, true)
    document.addEventListener('keydown', escape, true)
    return () => {document.removeEventListener('pointerdown', outside, true); document.removeEventListener('keydown', escape, true)}
  }, [open, close])

  return <span className={`info-hint${action ? ' info-hint-with-action' : ''}`}>
    {action && <button type="button" className={action.className}
      aria-describedby={open ? id : undefined}
      onMouseEnter={show} onMouseLeave={leave}
      onPointerDown={() => {pointerFocus.current = true}}
      onPointerUp={() => {pointerFocus.current = false}}
      onPointerCancel={() => {pointerFocus.current = false}}
      onFocus={() => {if (!pointerFocus.current) {focused.current = true; show()}}}
      onBlur={() => {pointerFocus.current = false; focused.current = false; leave()}}
      onClick={() => {close(); action.onClick()}}>{action.label}</button>}
    <button ref={trigger} type="button" className="info-hint-trigger" aria-label={label}
      aria-describedby={open ? id : undefined} aria-expanded={open}
      onMouseEnter={show} onMouseLeave={leave}
      onPointerDown={() => {pointerFocus.current = true}}
      onPointerUp={() => {pointerFocus.current = false}}
      onPointerCancel={() => {pointerFocus.current = false}}
      onFocus={() => {if (!pointerFocus.current) {focused.current = true; show()}}}
      onBlur={() => {pointerFocus.current = false; focused.current = false; pinned.current = false; leave()}}
      onClick={() => {pointerFocus.current = false; if (pinned.current) close(); else {pinned.current = true; show()}}}>
      <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
        <circle cx="10" cy="10" r="7.25" stroke="currentColor" strokeWidth="1.3" />
        <path d="M10 9V13.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="10" cy="6.5" r=".9" fill="currentColor" />
      </svg>
    </button>
    {open && host && createPortal(<span ref={bubble} id={id} role="tooltip" className="info-hint-tooltip"
      style={{left: position.left, top: position.top, visibility: position.ready ? 'visible' : 'hidden'}}
      onMouseEnter={clearTimer} onMouseLeave={leave}>{children}</span>, host)}
  </span>
}
