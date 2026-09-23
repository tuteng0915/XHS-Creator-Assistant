import type { TextInputAsset } from './types'

export type CreatorNote = {
  noteId: string
  title: string
  desc: string
  publishedAt?: string | number | null
  coverMediaAssetId?: string
  metrics: { liked?: number; collected?: number; comments?: number; shares?: number }
  comments: Array<{ commentId?: string; content?: string; likeCount?: number }>
}

export function creatorNotes(profile?: TextInputAsset): CreatorNote[] {
  if (!profile) return []
  try {
    const payload = JSON.parse(profile.content)
    if (!Array.isArray(payload.notes)) return []
    return payload.notes.filter((note: unknown) => note && typeof note === 'object').map((note: CreatorNote, index: number) => ({
      ...note,
      noteId: String(note.noteId || index),
      title: String(note.title || '未命名笔记'),
      desc: String(note.desc || ''),
      metrics: note.metrics || {},
      comments: Array.isArray(note.comments) ? note.comments.filter((comment) => comment && typeof comment === 'object') : [],
    }))
  } catch { return [] }
}

export function notePublishedAt(note: CreatorNote): number | null {
  const raw = note.publishedAt
  if (raw === null || raw === undefined || raw === '') return null
  const numeric = Number(raw)
  const value = Number.isFinite(numeric)
    ? numeric * (numeric < 1e12 ? 1000 : 1)
    : Date.parse(String(raw))
  return Number.isFinite(value) && value > 0 ? value : null
}

export type AnalysisScope = 'recent_10' | 'last_7_days' | 'last_30_days' | 'last_90_days' | 'all'

export const ANALYSIS_SCOPE_LABELS: Record<AnalysisScope, string> = {
  recent_10: '最近 10 条', last_7_days: '最近 7 天', last_30_days: '最近 30 天', last_90_days: '最近 90 天', all: '全部已导入笔记',
}

export function selectCreatorNotes(notes: CreatorNote[], scope: AnalysisScope, now = Date.now()): CreatorNote[] {
  if (scope === 'all') return notes
  if (scope === 'recent_10') return [...notes].sort((a, b) => (notePublishedAt(b) || 0) - (notePublishedAt(a) || 0)).slice(0, 10)
  const days = Number(scope.split('_')[1])
  return notes.filter((note) => {
    const date = notePublishedAt(note)
    return date !== null && date >= now - days * 86400000 && date <= now
  })
}
