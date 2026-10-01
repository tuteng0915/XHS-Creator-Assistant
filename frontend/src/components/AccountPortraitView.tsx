import { useState } from 'react'
import type { MediaAsset } from '../types'
import type { CreatorNote } from '../creatorNotes'
import { CreatorNoteBrowser } from './CreatorNoteBrowser'

type Evidence = { noteId: string; quote: string }
type Claim = { statement: string; evidence: Evidence[]; counterexamples?: Evidence[] }
type Portrait = {
  summary?: Claim | null
  keywords?: Claim[]
  strengths?: Claim[]
  encouragement?: Claim | null
  recurringThemes?: Claim[]
  readerValue?: Claim[]
  expressionPatterns?: Claim[]
  recentChange?: Claim | null
}
type Observation = {
  noteId: string
  title: string
  publishedAt?: string | null
  likesRankInSelection?: number | null
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
  const validSections = sections.map(([title, claims]) => [title, claims.filter(claim =>
    claimHasEvidence(claim) && (title !== '主要内容方向' || new Set(claim.evidence.map(ref => ref.noteId)).size >= 2)
  )] as const)
  const keywords = (portrait?.keywords || []).filter(claimHasEvidence)
  const strengths = (portrait?.strengths || []).filter(claimHasEvidence)
  const hasPortrait = claimHasEvidence(portrait?.summary) || keywords.length > 0 || strengths.length > 0 ||
    claimHasEvidence(portrait?.encouragement) || validSections.some(([, claims]) => claims.length)
  const withLikes = observations.notes.filter(note => typeof note.metrics.liked === 'number')
    .sort((a, b) => (b.metrics.liked || 0) - (a.metrics.liked || 0))
  const upper = withLikes.slice(0, Math.min(2, withLikes.length))
  const lower = withLikes.length >= 4 ? withLikes.slice(-2).reverse() : []
  const missingLikes = coverage.missingMetricCounts?.liked || 0

  function renderClaim(claim: Claim, key: string) {
    const linkedNotes = claim.evidence.map(ref => selectable.get(ref.noteId)).filter((note): note is CreatorNote => Boolean(note))
    const exceptionNotes = (claim.counterexamples || []).map(ref => selectable.get(ref.noteId)).filter((note): note is CreatorNote => Boolean(note))
    if (!linkedNotes.length) return null
    return <div className={`account-portrait-claim${key.startsWith('keyword-') ? ' account-portrait-keyword' : ''}`} key={key}>
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
        <small>{note.publishedAt ? `${new Date(note.publishedAt).toLocaleDateString('zh-CN')} · ` : '发布时间未知 · '}
          赞 {note.metrics.liked ?? '—'} · 藏 {note.metrics.collected ?? '—'} · 评 {note.metrics.comments ?? '—'}
          {note.likesRankInSelection ? ` · 本次点赞第 ${note.likesRankInSelection}` : ''}</small>
        {openPerformanceNote === note.noteId && selectable.has(note.noteId) && <div className="account-performance-note">
          <CreatorNoteBrowser notes={[selectable.get(note.noteId)!]} mediaAssets={mediaAssets} />
        </div>}
      </div>)}
    </div>
  }

  return <div className="account-portrait-view">
    {hasPortrait ? <>
      <div className="account-portrait-intro">
        {claimHasEvidence(portrait?.summary) && <div className="account-portrait-summary">{renderClaim(portrait.summary, 'summary')}</div>}
        {keywords.length > 0 && <div className="account-portrait-keywords">{keywords.map((claim, index) => renderClaim(claim, `keyword-${index}`))}</div>}
        {claimHasEvidence(portrait?.encouragement) && <div className="account-portrait-encouragement">{renderClaim(portrait.encouragement, 'encouragement')}</div>}
      </div>
      {strengths.length > 0 && <section>
        <h4>这个账号已经做得好的地方</h4>
        <div className="account-portrait-claims">{strengths.map((claim, index) => renderClaim(claim, `strength-${index}`))}</div>
      </section>}
    </> : null}
    <div className="account-portrait-coverage">
      <span>本次分析 {coverage.selectedCount}{coverage.availableCount ? ` / 已导入 ${coverage.availableCount}` : ''} 条笔记</span>
      <span>已抓取一级评论 {coverage.capturedCommentCount} 条</span>
      {coverage.dateRange && <span>笔记发布于 {new Date(coverage.dateRange.earliest).toLocaleDateString('zh-CN')}—{new Date(coverage.dateRange.latest).toLocaleDateString('zh-CN')}</span>}
      {coverage.sourceFetchedAt && <span>数据导入于 {new Date(coverage.sourceFetchedAt).toLocaleDateString('zh-CN')}</span>}
      {coverage.snapshotAt && <span>分析于 {new Date(coverage.snapshotAt).toLocaleDateString('zh-CN')}</span>}
      {coverage.missingDateCount > 0 && <span>{coverage.missingDateCount} 条缺少发布时间</span>}
      {missingLikes > 0 && <span>{missingLikes} 条缺少点赞数据</span>}
    </div>
    {hasPortrait ? <>
      {validSections.map(([title, claims]) => claims.length > 0 && <section key={title}>
        <h4>{title}</h4>
        <div className="account-portrait-claims">{claims.map((claim, index) => renderClaim(claim, `${title}-${index}`))}</div>
      </section>)}
    </> : <p className="muted">先看看这次的内容归纳与笔记表现；选择更多笔记后，还可以得到更完整的账号关键词和特色。</p>}
    {observations.chronology?.status === 'comparable' && claimHasEvidence(portrait?.recentChange) && <section className="account-portrait-change">
      <h4>内容方向的新变化</h4>
      {renderClaim(portrait.recentChange, 'recent-change')}
    </section>}
    {withLikes.length > 0 && <section className="account-performance">
      <h4>笔记表现</h4>
      <div className="account-performance-grid">
        {renderPerformance('所选笔记中点赞较高', upper)}
        {renderPerformance('所选笔记中点赞较低', lower)}
      </div>
      <details className="account-performance-method"><summary>数据说明</summary>
        <p className="muted">这里展示所选笔记抓取时的累计点赞。发布日期和累计时间可能不同，不能据此判断点击率、内容质量或变化趋势。</p>
      </details>
    </section>}
  </div>
}

export type { Observations, Portrait }
