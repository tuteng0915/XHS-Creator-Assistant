import type { TextInputAsset, Workspace } from '../types'
import { xhsCreatorProfileSummaryFromAsset } from '../xhsCreatorProfile'
import { InfoHint } from './InfoHint'

export function CreatorOverviewPage({ workspace, profile, onNotes, onAnalyze, onImport }: {
  workspace: Workspace
  profile?: TextInputAsset
  onNotes: () => void
  onAnalyze: () => void
  onImport: () => void
}) {
  const summary = xhsCreatorProfileSummaryFromAsset(profile)
  return <section className="creator-materials-page creator-overview-page">
    <div className="creator-page-head"><h1>{summary?.displayName || workspace.name}</h1>
      {summary ? <InfoHint label="分析账号说明" action={{label: '分析账号', className: 'primary', onClick: onAnalyze}}>
        先选想分析的笔记，了解账号的内容特点、读者反馈，以及下一篇可以写什么。
      </InfoHint> : <button className="primary" onClick={onImport}>导入账号</button>}
    </div>
    {summary ? <>
      <dl className="creator-overview-metrics" aria-label="账号数据">
        <div><dt>粉丝</dt><dd>{summary.followers ?? '未获取'}</dd></div>
        <div><dt>{summary.totalLikes == null && summary.likesAndCollections != null ? '获赞与收藏' : '总获赞'}</dt><dd>{summary.totalLikes ?? summary.likesAndCollections ?? '未获取'}</dd></div>
        <div><dt>已读取笔记</dt><dd>{summary.noteCount}<small>篇</small></dd></div>
        <div><dt>已读取评论</dt><dd>{summary.commentCount}<small>条</small></dd></div>
      </dl>
      <div className="creator-profile-overview creator-overview-section">
        <div className="creator-page-head"><h2>高互动笔记</h2><div><button onClick={onImport}>抓取更多笔记</button><button onClick={onNotes}>查看已抓取笔记</button></div></div>
        <ol className="creator-overview-notes">{summary.topNotes.map((note, index) => <li key={note.noteId}><span className="creator-note-rank" aria-hidden="true">{String(index + 1).padStart(2, '0')}</span><div><strong>{note.title}</strong><p>赞 {note.liked ?? '—'} · 收藏 {note.collected ?? '—'} · 评论 {note.comments ?? '—'}</p></div></li>)}</ol>
      </div>
    </> : <p className="empty-card">粘贴主页链接，开始了解你的账号。</p>}
  </section>
}
