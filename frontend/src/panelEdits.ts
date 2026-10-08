import type { Row } from './editorFeedback'

export type PanelEditOperation = 'replace' | 'insert_before' | 'insert_after'
export type EditVersion = {title: string; body: string; updatedAt: string}
export type PanelEditProposal = {
  id: string; workspaceId: string; simulationId: string; topicId: string
  status: 'pending' | 'applied' | 'rejected' | 'undone'; freshness: 'current' | 'stale'
  snapshot: {
    version: string; feedback: Row; before: EditVersion
    authorMaterial?: string
    proposed: {title: string; body: string}
    edit: {field: 'title' | 'body'; start: number; end: number; operation: PanelEditOperation; text: string}
  }
  receipt: {before?: EditVersion; after?: EditVersion; appliedAt?: string}
  undoReceipt?: {before?: EditVersion; after?: EditVersion; undoneAt?: string}
  createdAt: string; updatedAt: string
}
export const editOperationLabels = {replace:'替换原句', insert_before:'插在原句前', insert_after:'插在原句后'}
