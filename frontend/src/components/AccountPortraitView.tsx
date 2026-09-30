import { useState } from 'react'
import type { MediaAsset } from '../types'
import type { CreatorNote } from '../creatorNotes'
import { CreatorNoteBrowser } from './CreatorNoteBrowser'

type Evidence = { noteId: string; quote: string }
type Claim = { statement: string; evidence: Evidence[]; counterexamples?: Evidence[] }
type Portrait = {
  summary?: Claim | null
  recurringThemes?: Claim[]
  readerValue?: Claim[]
  expressionPatterns?: Claim[]
  recentChange?: Claim | null
}
type Observation = {
  noteId: string
  title: string
  metrics: { liked?: number | null; collected?: number | null; comments?: number | null; shares?: number | null }
}
type Observations = {
  schemaVersion: string
  coverage: {
    selectedCount: number
    availableCount?: number
    missingDateCount: number
    capturedCommentCount: number
    missingMetricCounts: Record<string, number>
    snapshotAt?: string
    sourceFetchedAt?: string | null
    dateRange?: { earliest: string; latest: string } | null
  }
  notes: Observation[]
  chronology?: {
    status: 'comparable' | 'insufficient_data'
    reason?: string
    earlier?: { noteIds: string[]; start: string; end: string }
    later?: { noteIds: string[]; start: string; end: string }
  }
}

function claimHasEvidence(value: Claim | null | undefined): value is Claim {
  return Boolean(value?.statement && Array.isArray(value.evidence) && value.evidence.length)
}

export function AccountPortraitView({ portrait, observations, notes, mediaAssets }: {
  portrait?: Portrait | null
  observations: Observations
  notes: CreatorNote[]
  mediaAssets: MediaAsset[]
}) {
  const [openClaim, setOpenClaim] = useState<string | null>(null)
  const [openPerformanceNote, setOpenPerformanceNote] = useState<string | null>(null)
  const coverage = observations.coverage
  const selectable = new Map(notes.map(note => [note.noteId, note]))
  const sections: Array<[string, Claim[]]> = [
    ['主要内容方向', portrait?.recurringThemes || []],
    ['给读者的价值', portrait?.readerValue || []],
    ['表达特点', portrait?.expressionPatterns || []],
  ]
  const validSections = sections.map(([title, claims]) => [title, claims.filter(claimHasEvidence)] as const)
  const hasPortrait = claimHasEvidence(portrait?.summary) || validSections.some(([, claims]) => claims.length)
  const withLikes = observations.notes.filter(note => typeof note.metrics.liked === 'number')
    .sort((a, b) => (b.metrics.liked || 0) - (a.metrics.liked || 0))
  const upper = withLikes.slice(0, Math.min(2, withLikes.length))
  const lower = withLikes.length >= 4 ? withLikes.slice(-2).reverse() : []
  const missingLikes = coverage.missingMetricCounts?.liked || 0

  function renderClaim(claim: Claim, key: string) {
    const linkedNotes = claim.evidence.map(ref => selectable.get(ref.noteId)).filter((note): note is CreatorNote => Boolean(note))
    const exceptionNotes = (claim.counterexamples || []).map(ref => selectable.get(ref.noteId)).filter((note): note is CreatorNote => Boolean(note))
    if (!linkedNotes.length) return null
    return <div className="account-portrait-claim" key={key}>
      <p>{claim.statement}</p>
      <button type="button" onClick={() => setOpenClaim(openClaim === key ? null : key)}
        aria-expanded={openClaim === key}>查看依据 · {linkedNotes.length} 条笔记</button>
      {openClaim === key && <div className="account-portrait-evidence">
        <div className="account-portrait-quotes">
          {claim.evidence.map((ref, index) => <span key={`${ref.noteId}-${index}`}>“{ref.quote}”</span>)}
        </div>
        <CreatorNoteBrowser notes={linkedNotes} mediaAssets={mediaAssets} />
        {exceptionNotes.length > 0 && <div className="account-portrait-exceptions">
          <b>可能的例外</b>
          <div className="account-portrait-quotes">{(claim.counterexamples || []).map((ref, index) => <span key={`${ref.noteId}-${index}`}>“{ref.quote}”</span>)}</div>
          <CreatorNoteBrowser notes={exceptionNotes} mediaAssets={mediaAssets} />
        </div>}
      </div>}
    </div>
  }

  function renderPerformance(title: string, entries: Observation[]) {
    if (!entries.length) return null
    return <div className="account-performance-group"><b>{title}</b>
      {entries.map(note => <div key={note.noteId} className="account-performance-row">
        <button type="button" onClick={() => setOpenPerformanceNote(openPerformanceNote === note.noteId ? null : note.noteId)}
          aria-expanded={openPerformanceNote === note.noteId}>{note.title}</button>
        <small>赞 {note.metrics.liked ?? '—'} · 藏 {note.metrics.collected ?? '—'} · 评 {note.metrics.comments ?? '—'}</small>
        {openPerformanceNote === note.noteId && selectable.has(note.noteId) && <div className="account-performance-note">
          <CreatorNoteBrowser notes={[selectable.get(note.noteId)!]} mediaAssets={mediaAssets} />
        </div>}
      </div>)}
    </div>
  }

  return <div className="account-portrait-view">
    <div className="account-portrait-coverage">
      <span>本次分析 {coverage.selectedCount}{coverage.availableCount ? ` / 已导入 ${coverage.availableCount}` : ''} 条笔记</span>
      <span>已抓取一级评论 {coverage.capturedCommentCount} 条</span>
      {coverage.dateRange && <span>笔记发布于 {new Date(coverage.dateRange.earliest).toLocaleDateString('zh-CN')}—{new Date(coverage.dateRange.latest).toLocaleDateString('zh-CN')}</span>}
      {coverage.sourceFetchedAt && <span>数据导入于 {new Date(coverage.sourceFetchedAt).toLocaleDateString('zh-CN')}</span>}
      {coverage.snapshotAt && <span>分析于 {new Date(coverage.snapshotAt).toLocaleDateString('zh-CN')}</span>}
      {coverage.missingDateCount > 0 && <span>{coverage.missingDateCount} 条缺少发布时间</span>}
      {missingLikes > 0 && <span>{missingLikes} 条缺少点赞数据</span>}
    </div>
    <p className="muted">以下画像是基于笔记的模型归纳。引用可以回看，解释是否成立仍需结合你的实际情况判断。</p>
    {hasPortrait ? <>
      {claimHasEvidence(portrait?.summary) && <div className="account-portrait-summary">{renderClaim(portrait.summary, 'summary')}</div>}
      {validSections.map(([title, claims]) => claims.length > 0 && <section key={title}>
        <h4>{title}</h4>
        <div className="account-portrait-claims">{claims.map((claim, index) => renderClaim(claim, `${title}-${index}`))}</div>
      </section>)}
    </> : <p className="muted">目前没有可回溯到所选笔记原文的账号画像结论；可以查看下方的旧版归纳。</p>}
    <section className="account-portrait-change">
      <h4>前后内容方向</h4>
      {observations.chronology?.status === 'comparable' ? <>
        <p className="muted">前期 {observations.chronology.earlier?.start}—{observations.chronology.earlier?.end} · 后期 {observations.chronology.later?.start}—{observations.chronology.later?.end}。仅比较内容，不比较累计互动。</p>
        {claimHasEvidence(portrait?.recentChange)
          ? renderClaim(portrait.recentChange, 'recent-change')
          : <p className="muted">目前没有足够依据说明内容方向发生了变化。</p>}
      </> : <p className="muted">{observations.chronology?.reason || '发布时间资料不足，暂时无法比较前后内容方向。'}</p>}
    </section>
    {withLikes.length > 0 && <section className="account-performance">
      <h4>笔记表现</h4>
      <p className="muted">仅按本次所选笔记的点赞数展示，不代表点击率或内容质量。</p>
      <div className="account-performance-grid">
        {renderPerformance('所选笔记中点赞较高', upper)}
        {renderPerformance('所选笔记中点赞较低', lower)}
      </div>
    </section>}
  </div>
}

export type { Observations, Portrait }
