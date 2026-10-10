import { ApiError } from './api'

export type CollaborationRole = 'creator' | 'research' | 'writing' | 'review' | 'system'
export type SpecialistRole = 'research' | 'writing' | 'review'
export type CollaborationStatus = 'idle' | 'queued' | 'running' | 'waiting_creator' | 'completed' | 'failed'
export interface CollaborationMessage {
  id: string; sessionId: string; sequenceNo: number; sender: CollaborationRole
  recipient: CollaborationRole | null; content: string; replyToMessageId: string | null
  modelMetadata: Record<string, unknown>; createdAt: string
}
export interface CollaborationRun {
  id: string; status: CollaborationStatus; triggerMessageId: string | null
  graphState: Record<string, unknown>; errorCode: string; errorDetail: string
  createdAt: string; startedAt: string | null; completedAt: string | null
}
export interface CollaborationSummary {
  id: string; workspaceId: string; title: string; status: 'active' | 'archived'
  contextTarget: {assetType: 'topic'; assetId: string}
  executionStatus: CollaborationStatus; failureCode: string; failureDetail: string
  createdAt: string; updatedAt: string
  assistantMode?: 'single_writer' | 'legacy_team'
  creatorContextSelection?: CreatorContextSelection
  contextRevision?: number
}
export interface CollaborationSession extends CollaborationSummary {
  messages: CollaborationMessage[]; runs: CollaborationRun[]
}
export interface CollaborationCandidate {
  kind: 'evidence' | 'open_question' | 'outline' | 'copy_option' | 'review_note'
  title: string; body: string; confidence: 'supported' | 'inference' | 'needs_creator'
  writingFocus?: FrozenWritingFocus
  focusUnavailable?: boolean
}
export interface ReaderFeedbackIntent {
  id: string; workspaceId: string; topicId: string; simulationId: string
  stage: 'initial' | 'reply' | 'interview'; messageId: string; interviewId?: string
  senderName: string; quote: string; authorQuestion?: string
}
export interface WritingSelection {start: number; end: number; text: string}
export interface ReaderReference {
  simulationId: string; stage: 'initial' | 'reply' | 'interview'; messageId: string; interviewId?: string
}
export interface WritingFocusRequest {
  expectedUpdatedAt: string; selection?: WritingSelection; readerReference?: ReaderReference
}
export interface FrozenWritingFocus {
  baseTopicId: string; baseTitle: string; baseBody: string; baseUpdatedAt: string
  selection?: WritingSelection; readerReference?: ReaderReference
  readerMessage?: {personaId: string; senderName: string; content: string; authorQuestion?: string; sourceTarget?: unknown}
}
export interface CollaborationComposeIntent {id: string; text: string; recipient: SpecialistRole}

export type CreatorContextReference =
  | {kind: 'account_analysis' | 'audience_analysis'; id: string}
  | {kind: 'imported_note'; id: string; noteId: string}
export interface CreatorContextSelection {
  schemaVersion: 'creator-context-selection/v1'
  references: CreatorContextReference[]
}
export const emptyCreatorContext = (): CreatorContextSelection => ({schemaVersion: 'creator-context-selection/v1', references: []})
export const creatorReferenceKey = (reference: CreatorContextReference): string => reference.kind === 'imported_note'
  ? `imported_note:${JSON.stringify([reference.id, reference.noteId])}` : `${reference.kind}:${reference.id}`
export const creatorContextSignature = (selection: CreatorContextSelection): string => selection.references.map(creatorReferenceKey).sort().join('|')

export function selectionFromTextarea(body: string, start: number, end: number): WritingSelection | null {
  if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end <= start || end > body.length) return null
  const prefix = body.slice(0, start), selected = body.slice(start, end)
  // Browser offsets are UTF-16, while the API deliberately uses Unicode code points.
  const points = Array.from(body), pointStart = Array.from(prefix).length, pointEnd = pointStart + Array.from(selected).length
  if (points.slice(pointStart, pointEnd).join('') !== selected || !selected.trim()) return null
  return {start: pointStart, end: pointEnd, text: selected}
}
export function validWritingSelection(body: string, value: unknown): value is WritingSelection {
  if (!value || typeof value !== 'object') return false
  const selected = value as WritingSelection, points = Array.from(body)
  return Number.isInteger(selected.start) && Number.isInteger(selected.end) && selected.start >= 0
    && selected.end > selected.start && selected.end <= points.length && typeof selected.text === 'string'
    && !!selected.text.trim() && points.slice(selected.start, selected.end).join('') === selected.text
}
export function frozenWritingFocus(value: unknown): FrozenWritingFocus | undefined {
  if (!value || typeof value !== 'object') return undefined
  const focus = value as FrozenWritingFocus
  if (typeof focus.baseTopicId !== 'string' || typeof focus.baseTitle !== 'string'
    || typeof focus.baseBody !== 'string' || typeof focus.baseUpdatedAt !== 'string'
    || (focus.selection !== undefined && !validWritingSelection(focus.baseBody, focus.selection))) return undefined
  return focus
}
export function replaceSelectedText(body: string, focus: FrozenWritingFocus, replacement: string): string | null {
  if (body !== focus.baseBody || !validWritingSelection(body, focus.selection)) return null
  const points = Array.from(body), {start, end} = focus.selection
  return points.slice(0, start).join('') + replacement + points.slice(end).join('')
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init)
  if (!response.ok) {
    let message = `请求未完成（${response.status}）`
    try { const body = await response.json(); if (typeof body.detail === 'string') message = body.detail } catch { /* stable fallback */ }
    throw new ApiError(message, response.status)
  }
  return response.json() as Promise<T>
}
const base = (workspaceId: string) => `/api/workspaces/${encodeURIComponent(workspaceId)}/content-collaboration-sessions`
const json = (body: unknown): RequestInit => ({method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})
export const contentCollaborationApi = {
  list: (workspaceId: string) => request<CollaborationSummary[]>(base(workspaceId)),
  get: (workspaceId: string, id: string) => request<CollaborationSession>(`${base(workspaceId)}/${encodeURIComponent(id)}`),
  create: (workspaceId: string, topicId: string, title: string, requestKey: string) => request<CollaborationSession>(base(workspaceId), json({title: title.slice(0, 160), contextTarget: {assetType: 'topic', assetId: topicId}, requestKey, assistantMode: 'single_writer'})),
  send: (workspaceId: string, id: string, content: string, recipient: SpecialistRole, requestKey: string, writingFocus?: WritingFocusRequest, creatorContextSelection?: CreatorContextSelection) => request<CollaborationSession>(`${base(workspaceId)}/${encodeURIComponent(id)}/messages`, json({content, recipient, requestKey, mode: 'live', ...(writingFocus ? {writingFocus} : {}), ...(creatorContextSelection ? {creatorContextSelection} : {})})),
}

export function collaborationCandidates(message: CollaborationMessage): CollaborationCandidate[] {
  const value = message.modelMetadata.candidateSuggestions
  if (!Array.isArray(value)) return []
  const focus = frozenWritingFocus(message.modelMetadata.writingFocus)
  return value.filter((item): item is CollaborationCandidate => !!item && typeof item === 'object'
    && typeof item.title === 'string' && typeof item.body === 'string'
    && ['evidence', 'open_question', 'outline', 'copy_option', 'review_note'].includes(item.kind)
    && ['supported', 'inference', 'needs_creator'].includes(item.confidence))
    .map(item => ({kind: item.kind, title: item.title, body: item.body, confidence: item.confidence,
      ...(item.kind === 'copy_option' && focus ? {writingFocus: focus} : {}),
      ...(item.kind === 'copy_option' && message.modelMetadata.writingFocus && !focus ? {focusUnavailable: true} : {})}))
}

export function collaborationSummary(message: CollaborationMessage): string {
  // Old records include candidates in both content and metadata. Render each
  // candidate once, preserving the independent role summary above the cards.
  const candidates = collaborationCandidates(message)
  const index = candidates.length ? message.content.indexOf(`【${candidates[0].title}】`) : -1
  return index < 0 ? message.content : message.content.slice(0, index).trim()
}
