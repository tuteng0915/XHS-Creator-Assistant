import type { SimulationRun } from './types'

export type FeedbackRun = Pick<SimulationRun, 'id' | 'inputSnapshot' | 'personaDefinitions' | 'reactionResults' | 'debateResults'>
export type Row = Record<string, unknown>
export const object = (v: unknown): Row => v && typeof v === 'object' && !Array.isArray(v) ? v as Row : {}
export const text = (v: unknown) => typeof v === 'string' ? v : ''
export const rows = (v: unknown): Row[] => Array.isArray(v) ? v.map(object) : []
export const strings = (v: unknown): string[] => Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : []
export const feedbackKinds: Record<string, string> = {keep:'建议保留',clarify:'讲得更清楚',rewrite:'调整表达',add_material:'补充材料',explore:'可选探索'}
export function feedbackCards(data: Row) {
  return rows(data.editorFeedback).filter(c => text(c.id) && Object.hasOwn(feedbackKinds,text(c.kind))
    && ['reader','editor_optional'].includes(text(c.sourceType)) && ['first','optional'].includes(text(c.priority))
    && text(c.observation) && text(c.reason))
}

export function verifiedConcerns(card: Row, run?: FeedbackRun): Row[] | null {
  const ids = strings(card.readerConcernIds)
  const saved = rows(card.readerConcerns)
  if (!run || !ids.length || new Set(ids).size !== ids.length || saved.length !== ids.length) return null
  const sourceIds = strings(card.sourceMessageIds)
  const result: Row[] = []
  for (const id of ids) {
    const matches = saved.filter(c => c.id === id)
    if (matches.length !== 1) return null
    const c = matches[0]
    const field = c.field === 'concerns' ? 'concerns' : c.field === 'newConcerns' ? 'newConcerns' : null
    if (!field || !text(c.text).trim() || !sourceIds.includes(text(c.messageId))) return null
    const all = [...run.reactionResults, ...run.debateResults].filter(m => m.messageId === c.messageId)
    if (all.length !== 1 || all[0].personaId !== c.personaId) return null
    const source = all[0]
    if (field === 'concerns' ? !run.reactionResults.includes(source) : !run.debateResults.includes(source)) return null
    if (field === 'newConcerns' && !(text(source.response) || text(source.text)).trim()) return null
    if (!run.personaDefinitions.some(p => p.id === c.personaId) || !strings(source[field]).includes(text(c.text))) return null
    result.push(c)
  }
  if (new Set(sourceIds).size !== sourceIds.length || sourceIds.some(id => !result.some(c => c.messageId === id))) return null
  return result
}

export function frozenTargetMatches(target: Row, run?: FeedbackRun): boolean {
  if (!run || !text(target.contentHash) || target.contentHash !== run.inputSnapshot.targetContentHash) return false
  if (target.field === 'whole') return !text(target.quote) && target.occurrence === 1
  if (target.field !== 'title' && target.field !== 'body') return false
  const points = Array.from(text(object(run.inputSnapshot.topic)[target.field]))
  const quote = text(target.quote), needle = Array.from(quote)
  const {start, end, occurrence} = target
  if (target.coordinateSystem !== 'unicode_code_points' || !Number.isInteger(start) || !Number.isInteger(end)
    || Number(start) < 0 || Number(end) > points.length || Number(end) <= Number(start)
    || !Number.isInteger(occurrence) || Number(occurrence) < 1 || !needle.length) return false
  let seen = 0
  for (let i = 0; i <= points.length - needle.length; i++) {
    if (points.slice(i, i + needle.length).join('') === quote && ++seen === occurrence)
      return i === start && i + needle.length === end
  }
  return false
}

export function feedbackGroups(cards: Row[], run?: FeedbackRun): Row[][] {
  const groups: Row[][] = [], byKey = new Map<string, Row[]>()
  for (const card of cards) {
    const concerns = card.sourceType === 'reader' && card.kind !== 'keep' ? verifiedConcerns(card, run) : null
    const target = object(card.target)
    if (!concerns || !frozenTargetMatches(target, run)) {groups.push([card]); continue}
    const key = JSON.stringify([concerns.map(c => c.id).sort(), card.priority, target.contentHash,
      target.field, target.quote, target.occurrence, target.start, target.end])
    const existing = byKey.get(key)
    if (existing) existing.push(card)
    else {const group = [card]; byKey.set(key, group); groups.push(group)}
  }
  return groups
}
