import type { CreatorContextSelection } from './contentCollaboration'
import type { Topic } from './types'

export interface CreatorDraft {
  version: 1
  baseUpdatedAt: string
  baseTitle: string
  baseBody: string
  title: string
  body: string
}

export interface CreatorMessageDraft {
  version: 1
  message: string
  selection: CreatorContextSelection
}

type CacheKind = 'draft' | 'message'
export function creatorDraftKey(kind: CacheKind, workspaceId: string, topicId: string) {
  return `sqs:creator:${kind}:v1:${encodeURIComponent(workspaceId)}:${encodeURIComponent(topicId)}`
}

function read<T>(kind: CacheKind, workspaceId: string, topicId: string, valid: (value: unknown) => value is T): {value: T | null; unavailable: boolean} {
  try {
    const raw = window.sessionStorage.getItem(creatorDraftKey(kind, workspaceId, topicId))
    if (!raw) return {value: null, unavailable: false}
    let value: unknown
    try {value = JSON.parse(raw)} catch {return {value: null, unavailable: false}}
    return {value: valid(value) ? value : null, unavailable: false}
  } catch {return {value: null, unavailable: true}}
}

const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value)

export function readCreatorDraft(workspaceId: string, topicId: string) {
  return read<CreatorDraft>('draft', workspaceId, topicId, (value): value is CreatorDraft => record(value) && value.version === 1
    && ['baseUpdatedAt', 'baseTitle', 'baseBody', 'title', 'body'].every(key => typeof value[key] === 'string'))
}

export function readCreatorMessage(workspaceId: string, topicId: string) {
  return read<CreatorMessageDraft>('message', workspaceId, topicId, (value): value is CreatorMessageDraft => record(value) && value.version === 1
    && typeof value.message === 'string' && record(value.selection) && value.selection.schemaVersion === 'creator-context-selection/v1'
    && Array.isArray(value.selection.references) && value.selection.references.length <= 8
    && value.selection.references.every(item => record(item) && ['account_analysis', 'audience_analysis'].includes(String(item.kind)) && typeof item.id === 'string'))
}

export function writeCreatorCache(kind: CacheKind, workspaceId: string, topicId: string, value: CreatorDraft | CreatorMessageDraft | null): boolean {
  try {
    const key = creatorDraftKey(kind, workspaceId, topicId)
    if (value) window.sessionStorage.setItem(key, JSON.stringify(value))
    else window.sessionStorage.removeItem(key)
    return true
  } catch {return false}
}

export function creatorDraftFrom(topic: Topic, title: string, body: string): CreatorDraft {
  return {version: 1, baseUpdatedAt: topic.updatedAt, baseTitle: topic.title, baseBody: topic.body || '', title, body}
}

export function draftMatchesSaved(draft: CreatorDraft, topic: Topic) {
  return draft.title === topic.title && draft.body === (topic.body || '')
}

export function draftHasSameBase(draft: CreatorDraft, topic: Topic) {
  return draft.baseUpdatedAt === topic.updatedAt && draft.baseTitle === topic.title && draft.baseBody === (topic.body || '')
}
