import { expect, it } from 'vitest'
import type { TextInputAsset } from './types'
import { creatorDataTimeLabel, filterCreatorNotes, notePublishedAt, noteRankValue, selectCreatorNotes, selectTopCreatorNotes, type CreatorNote } from './creatorNotes'

const note = (id: string, metrics: CreatorNote['metrics'] = {}, publishedAt?: string): CreatorNote => ({noteId:id, title:id, desc:'', metrics, comments:[], publishedAt})
const profile = (notes: CreatorNote[], source = {}): TextInputAsset => ({id:'p', workspaceId:'w', type:'xhs_creator_profile', name:'账号', content:JSON.stringify({notes, source}), createdAt:'2026-10-10', updatedAt:'2099-01-01'})

it('ranks only recorded metrics, retains zero, resolves ties by date then stable ID', () => {
  const notes = [note('missing'), note('bad', {liked:-1}), note('zero', {liked:0}), note('b', {liked:8}, '2026-10-02'), note('a', {liked:8}, '2026-10-02'), note('newer', {liked:8}, '2026-10-03')]
  expect(selectCreatorNotes(notes, 'most_liked_10').map(n => n.noteId)).toEqual(['newer','a','b','zero'])
  expect(filterCreatorNotes(notes,'all','liked').map(n => n.noteId)).toEqual(['newer','a','b','zero','bad','missing'])
  expect(notes[0].noteId).toBe('missing')
})

it('sums known likes, collections, comments and shares without treating missing as zero', () => {
  const notes = [note('partial', {liked:10}), note('complete', {liked:2,collected:3,comments:4,shares:5}), note('zero', {comments:0}), note('unknown')]
  expect(selectTopCreatorNotes(notes,'all','engagement',3).map(n => n.noteId)).toEqual(['complete','partial','zero'])
  expect(noteRankValue(notes[3], 'engagement')).toBeNull()
  expect(noteRankValue(notes[2], 'engagement')).toBe(0)
  expect(selectTopCreatorNotes(notes,'all','engagement',0)).toEqual([])
  expect(selectTopCreatorNotes(notes,'all','engagement',1.2)).toEqual([])
})

it('time filters exclude unknown and future dates without hiding them from all', () => {
  const now = Date.parse('2026-10-10T00:00:00Z')
  const notes = [note('old',{},'2026-09-01'), note('now',{},'2026-10-10'), note('future',{},'2026-10-11'), note('unknown')]
  expect(filterCreatorNotes(notes,'last_7_days','newest',now).map(n => n.noteId)).toEqual(['now'])
  expect(filterCreatorNotes(notes,'all','newest',now)).toHaveLength(4)
  expect(notePublishedAt(note('naive',{},'2026-10-10T00:00:00'))).toBe(now)
})

it('labels legacy imported time honestly and never uses asset edit time as data freshness', () => {
  expect(creatorDataTimeLabel(profile([note('n')], {importedAt:'2026-10-08T12:00:00Z'}))).toBe('导入于 2026/10/8')
  expect(creatorDataTimeLabel(profile([note('n')]))).toBe('暂未记录更新时间')
  expect(creatorDataTimeLabel({...profile([]), content:'broken'})).toBe('暂未记录更新时间')
})

it('distinguishes same-date full observation from partially refreshed notes', () => {
  const fresh = {...note('fresh'), metricsObservedAt:'2026-10-09T12:00:00Z'}
  expect(creatorDataTimeLabel(profile([fresh,{...fresh,noteId:'also',metricsObservedAt:'2026-10-09T13:00:00Z'}]))).toBe('数据截至 2026/10/9')
  expect(creatorDataTimeLabel(profile([fresh,note('unknown')]))).toBe('最近更新 2026/10/9 · 各篇时间见详情')
  expect(creatorDataTimeLabel(profile([fresh,{...note('old'),metricsObservedAt:'2026-10-08T12:00:00Z'}]))).toBe('最近更新 2026/10/9 · 各篇时间见详情')
})
