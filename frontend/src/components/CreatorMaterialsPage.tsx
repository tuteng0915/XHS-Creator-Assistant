import type { MediaAsset, TextInputAsset } from '../types'
import { creatorNotes } from '../creatorNotes'
import { CreatorNoteBrowser } from './CreatorNoteBrowser'

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
        <h1>我的笔记</h1>
        <div>
          <button type="button" onClick={onImport}>抓取更多笔记</button>
          <button type="button" className="primary" disabled={!notes.length} onClick={onAnalyze}>分析账号</button>
        </div>
      </div>
      {!notes.length && <p className="empty-card">导入账号后，你的笔记会出现在这里。</p>}
      <CreatorNoteBrowser key={profile?.id} notes={notes} mediaAssets={mediaAssets} />
    </section>
  )
}
