import { useEffect, useRef, useState, type RefObject } from 'react'

type TocItem = { label: string; element: HTMLElement }

// Short names keep the bar on one line; unknown headings fall back to their own text.
const SHORT_LABELS: Record<string, string> = {
  '这个账号给人的印象': '印象', '历史笔记表现': '笔记表现', '值得继续放大的优势': '优势', '内容方向与读者价值': '内容方向',
  '你的表达方式': '表达方式', '接下来值得试什么': '可以尝试', '下一步 · 选题建议': '选题建议',
}

// Section headings of the open report: the portrait's sections, then each later stage.
function collectHeadings(container: HTMLElement): TocItem[] {
  return Array.from(container.querySelectorAll<HTMLElement>(':scope > .stage')).flatMap(stage => {
    const sections = Array.from(stage.querySelectorAll<HTMLElement>('.account-portrait-view h4'))
    const headings = sections.length ? sections : Array.from(stage.querySelectorAll<HTMLElement>(':scope > .stage-h h3'))
    return headings.map(element => {
      const text = element.textContent?.trim() || ''
      return { label: SHORT_LABELS[text] || text, element }
    }).filter(item => item.label)
  })
}

/** Sticky table of contents for a long report. It reads the rendered headings, so it follows whatever stages exist. */
export function ReportToc({ containerRef, watch }: { containerRef: RefObject<HTMLElement | null>; watch: unknown }) {
  const [items, setItems] = useState<TocItem[]>([])
  const [active, setActive] = useState(0)
  const itemsRef = useRef(items)
  const navRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    let frame = 0
    const refresh = () => {
      const next = collectHeadings(container)
      const same = next.length === itemsRef.current.length
        && next.every((item, index) => item.element === itemsRef.current[index].element && item.label === itemsRef.current[index].label)
      if (!same) { itemsRef.current = next; setItems(next) }
    }
    refresh()
    // Stage results arrive and expand after the first paint.
    const observer = new MutationObserver(() => { cancelAnimationFrame(frame); frame = requestAnimationFrame(refresh) })
    observer.observe(container, { childList: true, subtree: true })
    return () => { observer.disconnect(); cancelAnimationFrame(frame) }
  }, [containerRef, watch])

  useEffect(() => {
    if (items.length < 3) return
    let frame = 0
    const update = () => {
      const offset = (navRef.current?.getBoundingClientRect().height || 0) + 24
      let current = 0
      items.forEach((item, index) => { if (item.element.getBoundingClientRect().top <= offset) current = index })
      setActive(current)
    }
    const onScroll = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(update) }
    update()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => { window.removeEventListener('scroll', onScroll); window.removeEventListener('resize', onScroll); cancelAnimationFrame(frame) }
  }, [items])

  // Keep the current entry visible when the bar itself scrolls sideways on narrow screens.
  useEffect(() => {
    const nav = navRef.current
    const button = nav?.querySelectorAll('button')[active]
    if (!nav || !button || nav.scrollWidth <= nav.clientWidth) return
    nav.scrollTo?.({ left: button.offsetLeft - nav.clientWidth / 2 + button.offsetWidth / 2 })
  }, [active])

  if (items.length < 3) return null
  // A div with the navigation role: the app styles bare <nav> elements as the sidebar menu.
  return <div className="report-toc" role="navigation" aria-label="报告目录" ref={navRef}>
    {items.map((item, index) => <button type="button" key={`${index}:${item.label}`} aria-current={index === active ? 'true' : undefined}
      onClick={() => {
        const reduce = typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
        item.element.scrollIntoView?.({ block: 'start', behavior: reduce ? 'auto' : 'smooth' })
      }}>{item.label}</button>)}
  </div>
}
