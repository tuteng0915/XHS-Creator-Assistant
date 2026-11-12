import { useState } from 'react'

export type TrendNote = {
  noteId: string
  title: string
  publishedAt: number
  total: number
  liked: number | null
  collected: number | null
  comments: number | null
  top: boolean
}

const dateLabel = (value: number) => {
  const date = new Date(value)
  return `${date.getFullYear()}.${date.getMonth() + 1}`
}

function niceCeiling(value: number): number {
  if (value <= 0) return 1
  const magnitude = 10 ** Math.floor(Math.log10(value))
  const step = [1, 2, 2.5, 5, 10].find(factor => factor * magnitude >= value) || 10
  return step * magnitude
}

export function OverviewTrendChart({ notes, total, activeId, onActive }: {
  notes: TrendNote[]
  total: number
  activeId: string | null
  onActive: (noteId: string | null) => void
}) {
  const [pinned, setPinned] = useState<string | null>(null)
  if (!notes.length) return <p className="overview-trend-empty">导入的笔记没有发布日期，暂时画不出趋势。</p>
  const max = niceCeiling(Math.max(...notes.map(note => note.total)))
  const activeIndex = notes.findIndex(note => note.noteId === (activeId ?? pinned))
  const active = activeIndex >= 0 ? notes[activeIndex] : null
  const ticks = [...new Set([0, Math.floor((notes.length - 1) / 2), notes.length - 1])]
  const first = notes[0], last = notes[notes.length - 1]
  const height = (note: TrendNote) => Math.max(note.total / max * 100, note.total > 0 ? 1.5 : 0)
  return <figure className="overview-trend">
    <figcaption>
      {notes.length < total ? `最近 ${notes.length} 篇` : `${notes.length} 篇`}笔记，每根柱是一篇，高度为赞、收藏、评论与分享之和；深色为高互动笔记。
    </figcaption>
    <div className="overview-trend-plot" role="img"
      aria-label={`${dateLabel(first.publishedAt)} 至 ${dateLabel(last.publishedAt)} 发布的 ${notes.length} 篇笔记互动量，最高 ${Math.max(...notes.map(note => note.total))}`}
      onPointerLeave={() => onActive(null)}>
      {[1, 0.5, 0].map(level => <div key={level} className={`overview-trend-grid${level === 0 ? ' is-base' : ''}`} style={{ bottom: `${level * 100}%` }}>
        <span>{Math.round(max * level).toLocaleString('zh-CN')}</span>
      </div>)}
      <div className="overview-trend-bars">
        {notes.map(note => <div key={note.noteId}
          className={`overview-trend-slot${note.top ? ' is-top' : ''}${active?.noteId === note.noteId ? ' is-active' : ''}`}
          onPointerEnter={event => { if (event.pointerType === 'mouse') onActive(note.noteId) }}
          onClick={() => setPinned(current => current === note.noteId ? null : note.noteId)}>
          <span style={{ height: `${height(note)}%` }} />
        </div>)}
      </div>
      {active && <div className={`overview-trend-tip${activeIndex > notes.length * 0.6 ? ' is-left' : ''}`}
        style={{ left: `${(activeIndex + 0.5) / notes.length * 100}%`, bottom: `calc(${height(active)}% + 10px)` }} aria-hidden="true">
        <strong>{active.title}</strong>
        <time>{new Date(active.publishedAt).toLocaleDateString('zh-CN')}</time>
        <span>互动 {active.total.toLocaleString('zh-CN')}：赞 {active.liked ?? '—'} · 收藏 {active.collected ?? '—'} · 评论 {active.comments ?? '—'}</span>
      </div>}
    </div>
    <div className="overview-trend-axis" aria-hidden="true">
      {ticks.map(index => <span key={index} style={{ left: `${(index + 0.5) / notes.length * 100}%` }}
        className={index === 0 ? 'is-first' : index === notes.length - 1 ? 'is-last' : undefined}>
        {dateLabel(notes[index].publishedAt)}
      </span>)}
    </div>
  </figure>
}
