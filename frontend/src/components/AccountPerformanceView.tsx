import { useState } from 'react'
import type { CreatorNote } from '../creatorNotes'
import type { MediaAsset } from '../types'
import { CreatorNoteBrowser } from './CreatorNoteBrowser'

const metrics = { liked: '点赞', collected: '收藏', comments: '评论', shares: '分享' } as const
type Metric = keyof typeof metrics
export type PerformanceNote = {
  noteId: string
  title: string
  publishedAt?: string | null
  likesRankInSelection?: number | null
  metricRanksInSelection?: Partial<Record<Metric, number | null>>
  metrics: Partial<Record<Metric, number | null>>
}
export type MetricSummary = {
  metric: Metric
  validCount: number
  missingCount: number
  median: number | null
  rankMethod: string
}

function valid(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0
}

export function AccountPerformanceView({ observations, summaries, notes, mediaAssets }: {
  observations: PerformanceNote[]
  summaries?: MetricSummary[]
  notes: CreatorNote[]
  mediaAssets: MediaAsset[]
}) {
  const [metric, setMetric] = useState<Metric>('liked')
  const [openNote, setOpenNote] = useState<string | null>(null)
  const label = metrics[metric]
  const available = new Map(notes.map(note => [note.noteId, note]))
  const sorted = observations.filter(note => valid(note.metrics[metric]))
    .sort((a, b) => b.metrics[metric]! - a.metrics[metric]!)
  const values = sorted.map(note => note.metrics[metric]!)
  const ranks = new Map([...new Set(values)].map((value, index) => [value, index + 1]))
  const saved = summaries?.find(item => item.metric === metric)
  const middle = Math.floor(values.length / 2)
  // Old histories have frozen raw counts but no summary; derive a display-only fallback.
  const median = values.length ? (values.length % 2 ? values[middle] : (values[middle - 1] + values[middle]) / 2) : null
  const medianValue = saved && saved.validCount === values.length && saved.median === median ? saved.median : median
  const upper = sorted.slice(0, 2)
  const lower = sorted.length >= 4
    ? sorted.filter(note => note.metrics[metric]! < upper[upper.length - 1].metrics[metric]!).slice(-2).reverse()
    : []
  const equal = values.length > 1 && ranks.size === 1
  const missing = observations.length - sorted.length

  function renderGroup(title: string, entries: PerformanceNote[]) {
    if (!entries.length) return null
    return <div className="account-performance-group"><b>{title}</b>
      {entries.map(note => <div key={note.noteId} className="account-performance-row">
        <button type="button" className="text-button" disabled={!available.has(note.noteId)} aria-expanded={openNote === note.noteId}
          onClick={() => setOpenNote(openNote === note.noteId ? null : note.noteId)}>{note.title}</button>
        {!available.has(note.noteId) && <small>本次分析快照未保留正文</small>}
        <small>{note.publishedAt ? `${new Date(note.publishedAt).toLocaleDateString('zh-CN')} · ` : '发布时间未知 · '}
          {label} {note.metrics[metric]} · 本次{label}第 {ranks.get(note.metrics[metric]!)}
        </small>
        {openNote === note.noteId && available.has(note.noteId) && <div className="account-performance-note">
          <CreatorNoteBrowser notes={[available.get(note.noteId)!]} mediaAssets={mediaAssets} />
        </div>}
      </div>)}
    </div>
  }

  return <section className="account-performance">
    <div className="account-performance-heading">
      <h4>笔记表现</h4>
      <select aria-label="比较指标" value={metric} onChange={event => {
        setMetric(event.target.value as Metric)
        setOpenNote(null)
      }}>
        {Object.entries(metrics).map(([key, name]) => <option key={key} value={key}>{name}</option>)}
      </select>
    </div>
    <p className="muted" role="status">
      {sorted.length ? `${label}数据 ${sorted.length} / ${observations.length} 条 · 中位数 ${medianValue}` : `本次未获取${label}数据`}
      {missing > 0 && sorted.length > 0 ? ` · ${missing} 条未获取` : ''}
    </p>
    <div className="account-performance-grid">
      {renderGroup(equal ? `所选笔记${label}相同` : `按${label}排序`, upper)}
      {renderGroup(`所选笔记中${label}较低`, lower)}
    </div>
    <details className="account-performance-method"><summary>数据说明</summary>
      <p className="muted">来自本次所选笔记抓取时的累计互动，缺失不算零，同数值并列。列表每组最多展示 2 条；评论数不等于已抓取的评论条数。发布日期和累计时间可能不同，这不是点击率、内容质量分或增长趋势。</p>
    </details>
  </section>
}
