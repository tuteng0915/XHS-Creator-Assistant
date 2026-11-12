import { useMemo, useState } from 'react'
import { creatorNotes, noteCoverUrl, notePublishedAt, validNoteMetric } from '../creatorNotes'
import type { MediaAsset, TextInputAsset, Workspace } from '../types'
import { xhsCreatorProfileSummaryFromAsset } from '../xhsCreatorProfile'
import { CreatorNavIcon, type CreatorNavIconName } from './CreatorNavIcon'
import { InfoHint } from './InfoHint'
import { OverviewTrendChart, type TrendNote } from './OverviewTrendChart'

export type OverviewStep = {
  key: string
  label: string
  icon: CreatorNavIconName
  state: 'done' | 'running' | 'todo'
  detail: string
  onOpen: () => void
}

const TREND_LIMIT = 40

export function CreatorOverviewPage({ workspace, profile, mediaAssets = [], steps = [], onNotes, onAnalyze, onImport }: {
  workspace: Workspace
  profile?: TextInputAsset
  mediaAssets?: MediaAsset[]
  steps?: OverviewStep[]
  onNotes: () => void
  onAnalyze: () => void
  onImport: () => void
}) {
  const summary = xhsCreatorProfileSummaryFromAsset(profile)
  const notes = useMemo(() => creatorNotes(profile), [profile])
  const [activeId, setActiveId] = useState<string | null>(null)
  const topIds = new Set(summary?.topNotes.map(note => note.noteId))
  const dated: TrendNote[] = notes.flatMap(note => {
    const publishedAt = notePublishedAt(note)
    if (publishedAt === null) return []
    const values = [note.metrics.liked, note.metrics.collected, note.metrics.comments, note.metrics.shares].map(validNoteMetric)
    return [{
      noteId: note.noteId, title: note.title, publishedAt, top: topIds.has(note.noteId),
      total: values.reduce<number>((sum, value) => sum + (value ?? 0), 0),
      liked: validNoteMetric(note.metrics.liked), collected: validNoteMetric(note.metrics.collected), comments: validNoteMetric(note.metrics.comments),
    }]
  }).sort((a, b) => a.publishedAt - b.publishedAt)
  const nextIndex = steps.findIndex(step => step.state === 'todo')
  const cover = (noteId: string) => {
    const note = notes.find(item => item.noteId === noteId)
    return note ? noteCoverUrl(note, mediaAssets) : undefined
  }
  return <section className="creator-materials-page creator-overview-page">
    <div className="creator-page-head"><h1>{summary?.displayName || workspace.name}</h1>
      {summary ? <InfoHint label="分析账号说明" action={{label: '分析账号', className: 'primary', onClick: onAnalyze}}>
        先选想分析的笔记，了解账号的内容特点、读者反馈，以及下一篇可以写什么。
      </InfoHint> : <button className="primary" onClick={onImport}>导入账号</button>}
    </div>
    {summary && steps.length > 0 && <nav className="creator-overview-flow" aria-label="创作流程">
      <ol>{steps.map((step, index) => <li key={step.key} className={`is-${step.state}${index === nextIndex ? ' is-next' : ''}`}>
        <button type="button" onClick={step.onOpen} aria-current={index === nextIndex ? 'step' : undefined}>
          <span className="creator-overview-flow-icon"><CreatorNavIcon name={step.icon} /></span>
          <span className="creator-overview-flow-text"><strong>{step.label}</strong>
            <small>{index === nextIndex ? '下一步' : step.detail}</small></span>
        </button>
      </li>)}</ol>
    </nav>}
    {summary ? <>
      <dl className="creator-overview-metrics" aria-label="账号数据">
        <div><dt>粉丝</dt><dd>{summary.followers ?? '未获取'}</dd></div>
        <div><dt>{summary.totalLikes == null && summary.likesAndCollections != null ? '获赞与收藏' : '总获赞'}</dt><dd>{summary.totalLikes ?? summary.likesAndCollections ?? '未获取'}</dd></div>
        <div><dt>已读取笔记</dt><dd>{summary.noteCount}<small>篇</small></dd></div>
        <div><dt>已读取评论</dt><dd>{summary.commentCount}<small>条</small></dd></div>
      </dl>
      <div className="creator-overview-body">
        <div className="creator-profile-overview creator-overview-section creator-overview-trend">
          <div className="creator-page-head"><h2>互动随发布时间</h2></div>
          <OverviewTrendChart notes={dated.slice(-TREND_LIMIT)} total={dated.length} activeId={activeId} onActive={setActiveId} />
        </div>
        <div className="creator-profile-overview creator-overview-section">
          <div className="creator-page-head"><h2>高互动笔记</h2><div><button onClick={onImport}>抓取更多笔记</button><button onClick={onNotes}>查看已抓取笔记</button></div></div>
          <ol className="creator-overview-notes">{summary.topNotes.map((note, index) => {
            const url = cover(note.noteId)
            return <li key={note.noteId} className={activeId === note.noteId ? 'is-active' : undefined}
              onPointerEnter={event => { if (event.pointerType === 'mouse') setActiveId(note.noteId) }}
              onPointerLeave={() => setActiveId(null)}>
              <span className="creator-note-rank" aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>
              {url ? <img className="creator-overview-thumb" src={url} alt="" loading="lazy" /> : <span className="creator-overview-thumb" aria-hidden="true" />}
              <div><strong>{note.title}</strong><p>赞 {note.liked ?? '—'} · 收藏 {note.collected ?? '—'} · 评论 {note.comments ?? '—'}</p></div>
            </li>
          })}</ol>
        </div>
      </div>
    </> : <p className="empty-card">粘贴主页链接，开始了解你的账号。</p>}
  </section>
}
