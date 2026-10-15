import type { CollaborationCandidate } from './contentCollaboration'

function ordered(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(ordered)
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([key, item]) => [key, ordered(item)]))
  return value
}

// Equal prose can target different passages or cite different readers.
export function sameCreatorCandidate(left: CollaborationCandidate | null | undefined, right: CollaborationCandidate): boolean {
  return !!left && left.kind === right.kind && left.title === right.title && left.body === right.body
    && !!left.focusUnavailable === !!right.focusUnavailable
    && JSON.stringify(ordered(left.writingFocus)) === JSON.stringify(ordered(right.writingFocus))
}
