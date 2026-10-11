import { useId, useState, type ReactNode } from 'react'
import type { MediaAsset } from '../types'
import type { CreatorNote } from '../creatorNotes'
import { accountStatementKey } from '../accountReportText'
import { CreatorNoteBrowser } from './CreatorNoteBrowser'
import { AccountPerformanceView, type MetricSummary, type PerformanceNote } from './AccountPerformanceView'
import './AccountReport.css'

type Evidence = { noteId: string; quote?: string; scope?: 'note' }
type Claim = { statement: string; evidence: Evidence[]; counterexamples?: Evidence[] }
type Portrait = {
  summary?: Claim | null
  keywords?: Claim[]
  strengths?: Claim[]
  encouragement?: Claim | null
  recurringThemes?: Claim[]
  readerValue?: Claim[]
  expressionPatterns?: Claim[]
  nextSteps?: Claim[]
  recentChange?: Claim | null
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
  notes: PerformanceNote[]
  metricSummaries?: MetricSummary[]
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

function appendEvidence(existing: Evidence[], incoming: Evidence[]): Evidence[] {
  const seen = new Set(existing.map(ref => JSON.stringify([ref.noteId, ref.quote, ref.scope])))
  return [...existing, ...incoming.filter(ref => {
    const key = JSON.stringify([ref.noteId, ref.quote, ref.scope])
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })]
}

export function AccountPortraitView({ portrait, observations, notes, mediaAssets, contentDetails, expressionDetails, nextSteps }: {
  portrait?: Portrait | null
  observations: Observations
  notes: CreatorNote[]
  mediaAssets: MediaAsset[]
  contentDetails?: ReactNode
  expressionDetails?: ReactNode
  nextSteps?: ReactNode
}) {
  const [openClaim, setOpenClaim] = useState<string | null>(null)
  const keywordEvidenceId = useId()
  const coverage = observations.coverage
  const selectable = new Map(notes.map(note => [note.noteId, note]))
  // Merge only equivalent written statements, never guessed semantic overlap.
  // The display copies collect every supporting/exception quote across fields.
  const seenClaims = new Map<string, Claim>()
  function claimsOnce(values: Array<Claim | null | undefined>, registry = seenClaims): Claim[] {
    return values.filter(claimHasEvidence).flatMap(claim => {
      const key = accountStatementKey(claim.statement)
      const existing = registry.get(key)
      if (existing) {
        existing.evidence = appendEvidence(existing.evidence, claim.evidence)
        existing.counterexamples = appendEvidence(existing.counterexamples || [], claim.counterexamples || [])
        return []
      }
      const copy = {...claim, evidence: appendEvidence([], claim.evidence), counterexamples: appendEvidence([], claim.counterexamples || [])}
      registry.set(key, copy)
      return [copy]
    })
  }
  const summary = claimsOnce([portrait?.summary])[0]
  const strengths = claimsOnce([...(portrait?.strengths || []), portrait?.encouragement])
  const themes = claimsOnce((portrait?.recurringThemes || []).filter(claim => claimHasEvidence(claim) && new Set(claim.evidence.map(ref => ref.noteId)).size >= 2))
  const values = claimsOnce(portrait?.readerValue || [])
  const changes = claimsOnce(observations.chronology?.status === 'comparable' ? [portrait?.recentChange] : [])
  const expressions = claimsOnce(portrait?.expressionPatterns || [])
  const suggestedSteps = claimsOnce(portrait?.nextSteps || [])
  const keywords = claimsOnce(portrait?.keywords || [], new Map())
  const openKeyword = keywords.find((_, index) => openClaim === `keyword-${index}`)
  const hasIntro = !!summary || keywords.length > 0
  const hasContent = themes.length > 0 || values.length > 0 || changes.length > 0 || !!contentDetails
  const hasExpression = expressions.length > 0 || !!expressionDetails
  const hasPortrait = hasIntro || strengths.length > 0 || hasContent || hasExpression

  function renderQuotes(evidence: Evidence[]) {
    const quoted = evidence.filter(ref => typeof ref.quote === 'string' && ref.quote.trim())
    return quoted.length > 0 ? <div className="account-portrait-quotes">
      {quoted.map((ref, index) => <span key={`${ref.noteId}-${index}`}>“{ref.quote}”</span>)}
    </div> : null
  }

  function renderEvidence(claim: Claim) {
    const evidenceIds = [...new Set(claim.evidence.map(ref => ref.noteId))]
    const exceptionIds = [...new Set((claim.counterexamples || []).map(ref => ref.noteId))]
    const linkedNotes = evidenceIds.map(id => selectable.get(id)).filter((note): note is CreatorNote => Boolean(note))
    const exceptionNotes = exceptionIds.map(id => selectable.get(id)).filter((note): note is CreatorNote => Boolean(note))
    const missingCount = evidenceIds.length - linkedNotes.length
    const missingExceptions = exceptionIds.length - exceptionNotes.length
    return <div className="account-portrait-evidence">
        {renderQuotes(claim.evidence)}
        {missingCount > 0 && <p className="muted">{missingCount} 条依据笔记未保留在本次分析快照中，仅显示历史引用。</p>}
        <CreatorNoteBrowser notes={linkedNotes} mediaAssets={mediaAssets} />
        {exceptionIds.length > 0 && <div className="account-portrait-exceptions">
          <b>可能的例外</b>
          {renderQuotes(claim.counterexamples || [])}
          {missingExceptions > 0 && <p className="muted">{missingExceptions} 条例外笔记未保留在本次分析快照中，仅显示历史引用。</p>}
          <CreatorNoteBrowser notes={exceptionNotes} mediaAssets={mediaAssets} />
        </div>}
      </div>
  }

  function renderClaim(claim: Claim, key: string) {
    const evidenceCount = new Set(claim.evidence.map(ref => ref.noteId)).size
    return <div className="account-portrait-claim" key={key}>
      <p>{claim.statement}</p>
      <button type="button" className="text-button" onClick={() => setOpenClaim(openClaim === key ? null : key)}
        aria-expanded={openClaim === key}>查看依据 · {evidenceCount} 条笔记</button>
      {openClaim === key && renderEvidence(claim)}
    </div>
  }

  return <div className="account-portrait-view account-report">
    {hasPortrait ? <>
      {hasIntro && <div className="account-portrait-intro">
        <h4>这个账号给人的印象</h4>
        {summary && <div className="account-portrait-summary">{renderClaim(summary, 'summary')}</div>}
        {keywords.length > 0 && <div className="account-portrait-keyword-section">
          <div className="account-portrait-keywords" role="group" aria-label="账号关键词">
            {keywords.map((claim, index) => <button type="button" className="account-portrait-keyword" key={index}
              aria-label={`${claim.statement}：查看 ${new Set(claim.evidence.map(ref => ref.noteId)).size} 条笔记依据`}
              aria-expanded={openClaim === `keyword-${index}`} aria-controls={keywordEvidenceId}
              onClick={() => setOpenClaim(openClaim === `keyword-${index}` ? null : `keyword-${index}`)}>{claim.statement}</button>)}
          </div>
          <div id={keywordEvidenceId} hidden={!openKeyword}>
            {openKeyword && <div className="account-portrait-keyword-detail" role="region" aria-label={`${openKeyword.statement}的依据`} key={openClaim}>
              {renderEvidence(openKeyword)}
            </div>}
          </div>
        </div>}
      </div>}
      {strengths.length > 0 && <section className="account-portrait-strengths">
        <h4>值得继续放大的优势</h4>
        <div className="account-portrait-claims">{strengths.map((claim, index) => renderClaim(claim, `strength-${index}`))}</div>
      </section>}
    </> : null}
    {hasContent && <section className="account-report-content">
      <h4>内容方向与读者价值</h4>
      {contentDetails}
      {themes.length > 0 && <div className="account-report-subsection">
        {values.length > 0 && <h5>内容方向</h5>}
        <div className="account-portrait-claims">{themes.map((claim, index) => renderClaim(claim, `theme-${index}`))}</div>
      </div>}
      {values.length > 0 && <div className="account-report-subsection">
        {themes.length > 0 && <h5>读者从中获得什么</h5>}
        <div className="account-portrait-claims">{values.map((claim, index) => renderClaim(claim, `value-${index}`))}</div>
      </div>}
      {changes.length > 0 && <div className="account-report-subsection"><h5>内容方向的新变化</h5>{renderClaim(changes[0], 'recent-change')}</div>}
    </section>}
    {hasExpression && <section className="account-report-expression">
      <h4>你的表达方式</h4>
      <div className="account-portrait-claims">{expressions.map((claim, index) => renderClaim(claim, `expression-${index}`))}</div>
      {expressionDetails}
    </section>}
    {!hasPortrait && !nextSteps && suggestedSteps.length === 0 && <p className="muted">本次暂无可展示的账号画像，已保留的内容归纳与笔记数据不受影响。</p>}
    <AccountPerformanceView observations={observations.notes} summaries={observations.metricSummaries} notes={notes} mediaAssets={mediaAssets} />
    {suggestedSteps.length > 0 && <section className="account-report-next-steps">
      <h4>接下来值得试什么</h4>
      <div className="account-portrait-claims">{suggestedSteps.map((claim, index) => renderClaim(claim, `next-step-${index}`))}</div>
    </section>}
    {nextSteps}
    <details className="account-portrait-source">
      <summary>分析范围 <span>· {coverage.selectedCount} 条笔记</span></summary>
      <div className="account-portrait-coverage">
        <span>本次分析 {coverage.selectedCount}{coverage.availableCount ? ` / 已导入 ${coverage.availableCount}` : ''} 条笔记</span>
        <span>已抓取一级评论 {coverage.capturedCommentCount} 条</span>
        {coverage.dateRange && <span>笔记发布于 {new Date(coverage.dateRange.earliest).toLocaleDateString('zh-CN')}—{new Date(coverage.dateRange.latest).toLocaleDateString('zh-CN')}</span>}
        {coverage.sourceFetchedAt && <span>数据导入于 {new Date(coverage.sourceFetchedAt).toLocaleDateString('zh-CN')}</span>}
        {coverage.snapshotAt && <span>分析于 {new Date(coverage.snapshotAt).toLocaleDateString('zh-CN')}</span>}
        {coverage.missingDateCount > 0 && <span>{coverage.missingDateCount} 条缺少发布时间</span>}
      </div>
    </details>
  </div>
}

export type { Observations, Portrait }
