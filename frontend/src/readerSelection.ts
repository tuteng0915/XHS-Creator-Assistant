export interface ReaderSelectionLink {
  readerSelectionId: string
  readerSelectionInputHash: string
}

export interface ReaderSelection {
  id: string
  workspaceId: string
  inputHash: string
  status: 'pending' | 'running' | 'completed' | 'partially_completed' | 'failed'
  inputSnapshot: {target: {title: string; body?: string}; candidates: Array<{id: string; name: string}>}
  result: null | {proposedReaders: Array<{fanId: string; fitReason: string; contribution: string}>; unmatchedReason: string}
  errorCode: string | null
  freshness?: {status: 'current' | 'stale' | 'unavailable'; reasons: string[]}
}
