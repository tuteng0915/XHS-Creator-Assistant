import type { ReactNode } from 'react'

export type CreatorNavIconName =
  | 'overview'
  | 'notes'
  | 'analysis'
  | 'history'
  | 'audience'
  | 'readers'
  | 'conversation'
  | 'topics'
  | 'writing'

const ICON_PATHS: Record<CreatorNavIconName, ReactNode> = {
  overview: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
  notes: <><rect x="5" y="3" width="14" height="18" rx="2" /><path d="M9 8h6M9 12h6M9 16h3" /></>,
  analysis: <><path d="M4 4v16h16M9 15v-4M14 15V7M19 15v-6" /></>,
  history: <><path d="M3 11a9 9 0 1 1 2.3 7M3 5v6h6M12 7v5l3 2" /></>,
  audience: <><circle cx="10" cy="8" r="3" /><path d="M4 20v-2a6 6 0 0 1 12 0v2M17 5a3 3 0 0 1 0 6M20 20v-2a6 6 0 0 0-2-4.5" /></>,
  readers: <><rect x="4" y="3" width="16" height="18" rx="2" /><circle cx="12" cy="9" r="2.5" /><path d="M7.5 17a4.5 4.5 0 0 1 9 0" /></>,
  conversation: <><path d="M19 13a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2H7a2 2 0 0 0-2 2v9l4-3h8M3 9v10a2 2 0 0 0 2 2h12l4 2v-6" /><path d="M9 7h8" /></>,
  topics: <><path d="M4 6a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v11a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1Z" /><path d="M8 11h8M8 15h5" /></>,
  writing: <><path d="m14 5 5 5M4 20l5-1L20 8a2.1 2.1 0 0 0-5-3L4 16Z" /><path d="M13 20h7" /></>,
}

export function CreatorNavIcon({ name }: { name: CreatorNavIconName }) {
  return (
    <svg className="creator-nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {ICON_PATHS[name]}
    </svg>
  )
}
