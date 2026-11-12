import type { CSSProperties, ReactNode } from 'react'
import './Skeleton.css'

/**
 * Grey placeholders shaped like the content that is about to appear.
 * They are decorative: the status text next to them carries the meaning for screen readers.
 */
export function SkeletonLines({ widths = ['100%', '92%', '64%'], still = false }: { widths?: string[]; still?: boolean }) {
  return <div className={`skeleton-lines${still ? ' is-still' : ''}`} aria-hidden="true">
    {widths.map((width, index) => <span className="skeleton skeleton-line" style={{ width }} key={index} />)}
  </div>
}

export function SkeletonBlock({ height, width, radius, still = false, className = '' }: {
  height: number | string; width?: number | string; radius?: number | string; still?: boolean; className?: string
}) {
  const style: CSSProperties = { height, width, borderRadius: radius }
  return <span className={`skeleton skeleton-block${still ? ' is-still' : ''} ${className}`.trim()} style={style} aria-hidden="true" />
}

/** Announces the wait once and hides the decorative shapes from assistive tech. */
export function SkeletonStatus({ label, children, className = '' }: { label: string; children: ReactNode; className?: string }) {
  return <div className={`skeleton-status ${className}`.trim()} role="status">
    <span className="visually-hidden">{label}</span>
    {children}
  </div>
}

/** A report section: heading, a paragraph, then a short evidence pill. */
export function ReportSkeleton({ sections = 3, still = false }: { sections?: number; still?: boolean }) {
  return <div className="skeleton-report" aria-hidden="true">
    {Array.from({ length: sections }, (_, index) => <div className="skeleton-report-section" key={index}>
      <div className="skeleton-report-heading"><SkeletonBlock height={28} width={28} radius={8} still={still} /><SkeletonBlock height={16} width={index % 2 ? 132 : 164} radius={6} still={still} /></div>
      <SkeletonLines widths={index % 2 ? ['96%', '88%', '42%'] : ['100%', '74%']} still={still} />
      <SkeletonBlock height={22} width={118} radius={999} still={still} />
    </div>)}
  </div>
}

/** One chat message: avatar, name and a bubble. `children` replaces the name placeholder when the speaker is known. */
export function MessageSkeleton({ children, lines = ['88%', '56%'], align = 'start' }: { children?: ReactNode; lines?: string[]; align?: 'start' | 'end' }) {
  return <div className={`skeleton-message${align === 'end' ? ' is-end' : ''}`}>
    {children ?? <SkeletonBlock height={36} width={36} radius={12} />}
    <div className="skeleton-message-main" aria-hidden="true">
      {!children && <SkeletonBlock height={12} width={72} radius={6} />}
      <div className="skeleton-bubble"><SkeletonLines widths={lines} /></div>
    </div>
  </div>
}

/** The overview while the workspace loads: step bar, four tiles, chart and list. */
export function WorkspaceSkeleton() {
  return <div className="skeleton-workspace" aria-hidden="true">
    <SkeletonBlock height={30} width={180} radius={8} />
    <div className="skeleton-workspace-steps">{Array.from({ length: 5 }, (_, index) => <SkeletonBlock height={62} radius={12} key={index} />)}</div>
    <div className="skeleton-workspace-tiles">{Array.from({ length: 4 }, (_, index) => <div className="skeleton-card" key={index}><SkeletonBlock height={12} width={64} radius={6} /><SkeletonBlock height={28} width={96} radius={8} /></div>)}</div>
    <div className="skeleton-workspace-panels">
      <div className="skeleton-card"><SkeletonBlock height={16} width={140} radius={6} /><SkeletonBlock height={260} radius={10} /></div>
      <div className="skeleton-card"><SkeletonBlock height={16} width={110} radius={6} />
        {Array.from({ length: 4 }, (_, index) => <div className="skeleton-row" key={index}><SkeletonBlock height={56} width={44} radius={8} /><SkeletonLines widths={['82%', '46%']} /></div>)}
      </div>
    </div>
  </div>
}

/** Reader cards while an audience analysis runs. */
export function ReaderCardsSkeleton({ count = 2 }: { count?: number }) {
  return <div className="skeleton-reader-cards" aria-hidden="true">
    {Array.from({ length: count }, (_, index) => <div className="skeleton-card" key={index}>
      <div className="skeleton-row"><SkeletonBlock height={36} width={36} radius={12} /><SkeletonBlock height={16} width={150} radius={6} /></div>
      <SkeletonLines widths={['100%', '94%', '58%']} />
      <SkeletonBlock height={64} radius={8} />
      <SkeletonBlock height={36} width={132} radius={8} />
    </div>)}
  </div>
}
