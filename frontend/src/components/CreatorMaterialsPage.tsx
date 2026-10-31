import type { MediaAsset, TextInputAsset } from '../types'
import { creatorDataTimeLabel, creatorNotes } from '../creatorNotes'
import { CreatorNoteBrowser } from './CreatorNoteBrowser'
import { InfoHint } from './InfoHint'

export function CreatorMaterialsPage({ profile, mediaAssets, onImport, onAnalyze }: {
  profile?: TextInputAsset
  mediaAssets: MediaAsset[]
  onImport: () => void
  onAnalyze: () => void
}) {
  const notes = creatorNotes(profile)
  return (
    <section className="creator-materials-page">
      <div className="creator-page-head">
        <div className="creator-materials-heading"><h1>我的笔记</h1><span className="creator-note-meta"><span className="creator-note-data-time">{creatorDataTimeLabel(profile)}</span><InfoHint label="笔记页面说明">查看已导入的图文、互动数据和评论，筛选笔记作为分析素材。</InfoHint></span></div>
        <div>
          <button type="button" onClick={onImport}>抓取更多笔记</button>
          <button type="button" className="primary" disabled={!notes.length} onClick={onAnalyze}>分析账号</button>
        </div>
      </div>
      {!notes.length && <p className="empty-card">导入账号后，你的笔记会出现在这里。</p>}
      <CreatorNoteBrowser key={profile?.id} notes={notes} mediaAssets={mediaAssets} showFilters={notes.length > 0} />
    </section>
  )
}
