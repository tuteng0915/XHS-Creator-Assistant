import type { TextInputAsset, Workspace } from '../types'
import { xhsCreatorProfileSummaryFromAsset } from '../xhsCreatorProfile'

export function CreatorOverviewPage({ workspace, profile, onNotes, onAnalyze, onImport }: {
  workspace: Workspace
  profile?: TextInputAsset
  onNotes: () => void
  onAnalyze: () => void
  onImport: () => void
}) {
  const summary = xhsCreatorProfileSummaryFromAsset(profile)
  return <section className="creator-materials-page">
    <div className="creator-page-head"><h1>{summary?.displayName || workspace.name}</h1>
      <button className="primary" onClick={summary ? onAnalyze : onImport}>{summary ? '分析账号' : '导入账号'}</button>
    </div>
    {summary ? <>
      <div className="creator-overview-metrics">
        <span>粉丝 {summary.followers ?? '未获取'}</span><span>{summary.totalLikes == null && summary.likesAndCollections != null ? `获赞与收藏 ${summary.likesAndCollections}` : `总获赞 ${summary.totalLikes ?? '未获取'}`}</span>
        <span>已读取 {summary.noteCount} 条笔记</span><span>{summary.commentCount} 条评论</span>
      </div>
      <div className="creator-profile-overview" style={{ marginTop: 24 }}>
        <div className="creator-page-head"><h2>高互动笔记</h2><div><button onClick={onImport}>抓取更多笔记</button><button onClick={onNotes}>查看已抓取笔记</button></div></div>
        <ol className="creator-overview-notes">{summary.topNotes.map((note) => <li key={note.noteId}><strong>{note.title}</strong><p>赞 {note.liked ?? '—'} · 收藏 {note.collected ?? '—'} · 评论 {note.comments ?? '—'}</p></li>)}</ol>
      </div>
    </> : <p className="empty-card">粘贴主页链接，开始了解你的账号。</p>}
  </section>
}
