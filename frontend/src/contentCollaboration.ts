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
}
export interface CollaborationSession extends CollaborationSummary {
  messages: CollaborationMessage[]; runs: CollaborationRun[]
}
export interface CollaborationCandidate {
  kind: 'evidence' | 'open_question' | 'outline' | 'copy_option' | 'review_note'
  title: string; body: string; confidence: 'supported' | 'inference' | 'needs_creator'
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
  create: (workspaceId: string, topicId: string, title: string, requestKey: string) => request<CollaborationSession>(base(workspaceId), json({title: title.slice(0, 160), contextTarget: {assetType: 'topic', assetId: topicId}, requestKey})),
  send: (workspaceId: string, id: string, content: string, recipient: SpecialistRole, requestKey: string) => request<CollaborationSession>(`${base(workspaceId)}/${encodeURIComponent(id)}/messages`, json({content, recipient, requestKey, mode: 'live'})),
}

export function collaborationCandidates(message: CollaborationMessage): CollaborationCandidate[] {
  const value = message.modelMetadata.candidateSuggestions
  if (!Array.isArray(value)) return []
  return value.filter((item): item is CollaborationCandidate => !!item && typeof item === 'object'
    && typeof item.title === 'string' && typeof item.body === 'string'
    && ['evidence', 'open_question', 'outline', 'copy_option', 'review_note'].includes(item.kind)
    && ['supported', 'inference', 'needs_creator'].includes(item.confidence))
}

export function collaborationSummary(message: CollaborationMessage): string {
  // Old records include candidates in both content and metadata. Render each
  // candidate once, preserving the independent role summary above the cards.
  const candidates = collaborationCandidates(message)
  const index = candidates.length ? message.content.indexOf(`【${candidates[0].title}】`) : -1
  return index < 0 ? message.content : message.content.slice(0, index).trim()
}
