import type { TextInputAsset } from './types'

export type CreatorNote = {
  noteId: string
  title: string
  desc: string
  publishedAt?: string | number | null
  metricsObservedAt?: string | number | null
  commentsObservedAt?: string | number | null
  coverMediaAssetId?: string
  metrics: { liked?: number; collected?: number; comments?: number; shares?: number }
  comments: Array<{ commentId?: string; content?: string; likeCount?: number }>
}

export function creatorNotes(profile?: TextInputAsset): CreatorNote[] {
  if (!profile) return []
  try {
    return creatorNotesFromPayload(JSON.parse(profile.content))
  } catch { return [] }
}

export function creatorNotesFromPayload(payload: unknown): CreatorNote[] {
  if (!payload || typeof payload !== 'object' || !Array.isArray((payload as {notes?: unknown}).notes)) return []
  return (payload as {notes: CreatorNote[]}).notes.filter((note: unknown) => note && typeof note === 'object' && !Array.isArray(note)).map((note: CreatorNote, index: number) => ({
    ...note,
    noteId: String(note.noteId || index),
    title: String(note.title || '未命名笔记'),
    desc: String(note.desc || ''),
    metrics: note.metrics || {},
    comments: Array.isArray(note.comments) ? note.comments.filter((comment) => comment && typeof comment === 'object') : [],
  }))
}

export function notePublishedAt(note: CreatorNote): number | null {
  return recordedTimestamp(note.publishedAt)
}

function recordedTimestamp(raw: unknown): number | null {
  if (raw === null || raw === undefined || raw === '') return null
  if (typeof raw !== 'string' && typeof raw !== 'number') return null
  const numeric = Number(raw)
  const text = String(raw)
  const iso = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/.test(text) ? `${text.replace(' ', 'T')}Z` : text
  const value = Number.isFinite(numeric)
    ? numeric * (numeric < 1e12 ? 1000 : 1)
    : Date.parse(iso)
  return Number.isFinite(value) && value > 0 ? value : null
}

export type AnalysisScope = 'recent_10' | 'most_liked_10' | 'most_engaged_10' | 'last_7_days' | 'last_30_days' | 'last_90_days' | 'all'
export type CreatorNoteRange = 'all' | 'last_7_days' | 'last_30_days' | 'last_90_days'
export type CreatorNoteSort = 'newest' | 'liked' | 'engagement'

export const ANALYSIS_SCOPE_LABELS: Record<AnalysisScope, string> = {
  recent_10: '最近 10 条', last_7_days: '最近 7 天', last_30_days: '最近 30 天', last_90_days: '最近 90 天', all: '全部已导入笔记',
  most_liked_10: '点赞最高 10 条', most_engaged_10: '互动最高 10 条',
}

export function validNoteMetric(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null
}

export function noteRankValue(note: CreatorNote, sort: CreatorNoteSort): number | null {
  if (sort === 'newest') return notePublishedAt(note)
  if (sort === 'liked') return validNoteMetric(note.metrics.liked)
  const values = Object.values({liked: note.metrics.liked, collected: note.metrics.collected, comments: note.metrics.comments, shares: note.metrics.shares})
    .map(validNoteMetric).filter((value): value is number => value !== null)
  return values.length ? values.reduce((sum, value) => sum + value, 0) : null
}

export function filterCreatorNotes(notes: CreatorNote[], range: CreatorNoteRange, sort: CreatorNoteSort, now = Date.now()): CreatorNote[] {
  const days = Number(range.split('_')[1])
  const filtered = range === 'all' ? notes : notes.filter(note => {
    const date = notePublishedAt(note)
    return date !== null && date >= now - days * 86400000 && date <= now
  })
  return [...filtered].sort((a, b) => {
    const first = noteRankValue(a, sort), second = noteRankValue(b, sort)
    if (first === null && second !== null) return 1
    if (second === null && first !== null) return -1
    return (second ?? 0) - (first ?? 0) || (notePublishedAt(b) || 0) - (notePublishedAt(a) || 0)
      || (a.noteId < b.noteId ? -1 : a.noteId > b.noteId ? 1 : 0)
  })
}

export function selectTopCreatorNotes(notes: CreatorNote[], range: CreatorNoteRange, sort: CreatorNoteSort, count: number, now = Date.now()): CreatorNote[] {
  if (!Number.isInteger(count) || count < 1) return []
  return filterCreatorNotes(notes, range, sort, now)
    .filter(note => sort === 'newest' || noteRankValue(note, sort) !== null).slice(0, count)
}

export function selectCreatorNotes(notes: CreatorNote[], scope: AnalysisScope, now = Date.now()): CreatorNote[] {
  if (scope === 'all') return notes
  if (scope === 'recent_10') return selectTopCreatorNotes(notes, 'all', 'newest', 10, now)
  if (scope === 'most_liked_10') return selectTopCreatorNotes(notes, 'all', 'liked', 10, now)
  if (scope === 'most_engaged_10') return selectTopCreatorNotes(notes, 'all', 'engagement', 10, now)
  return filterCreatorNotes(notes, scope, 'newest', now)
}

export function noteDataTimeLabel(note: CreatorNote): string | null {
  const value = recordedTimestamp(note.metricsObservedAt)
  return value === null ? null : `指标截至 ${new Date(value).toLocaleDateString('zh-CN')}`
}

export function noteCommentsTimeLabel(note: CreatorNote): string | null {
  const value = recordedTimestamp(note.commentsObservedAt)
  return value === null ? null : `评论更新于 ${new Date(value).toLocaleDateString('zh-CN')}`
}

// Only source observation/import metadata is meaningful here. Asset edit time is not capture time.
export function creatorDataTimeLabel(profile?: TextInputAsset): string {
  const notes = creatorNotes(profile)
  const dates = notes.map(note => recordedTimestamp(note.metricsObservedAt))
  const known = dates.filter((date): date is number => date !== null)
  if (known.length) {
    const newest = Math.max(...known)
    const day = new Date(newest).toLocaleDateString('zh-CN')
    const same = known.length === notes.length && known.every(value => new Date(value).toLocaleDateString('zh-CN') === day)
    return same ? `数据截至 ${day}` : `最近更新 ${day} · 各篇时间见详情`
  }
  try {
    const imported = recordedTimestamp(JSON.parse(profile?.content || '{}')?.source?.importedAt)
    if (imported !== null) return `导入于 ${new Date(imported).toLocaleDateString('zh-CN')}`
  } catch { /* Legacy malformed imports have no reliable observation time. */ }
  return '暂未记录更新时间'
}
