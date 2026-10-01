import { useState, type FormEvent } from 'react'

import type { TextInputAsset, Workspace, XhsCaptureJob } from '../types'
import { xhsCreatorProfileSummaryFromAsset } from '../xhsCreatorProfile'
import { CreatorDialog } from './CreatorDialog'

type CreatorStartPageProps = {
  workspace: Workspace | null
  xhsCreatorProfile: TextInputAsset | null
  profileUrl: string
  captureJob: XhsCaptureJob | null
  submitting: boolean
  error: string
  noteLimit?: number
  onNoteLimitChange?: (value: number) => void
  onProfileUrlChange: (value: string) => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
  onOpenMaterials: () => void
  onOpenDiagnosis: () => void
}

const ACTIVE_CAPTURE_STATUSES = new Set([
  'pending',
  'waiting_for_login',
  'running',
  'processing',
])

export function CreatorStartPage({
  workspace,
  xhsCreatorProfile,
  profileUrl,
  captureJob,
  submitting,
  error,
  noteLimit = 10,
  onNoteLimitChange,
  onProfileUrlChange,
  onSubmit,
  onOpenMaterials,
  onOpenDiagnosis,
}: CreatorStartPageProps) {
  const [settingsOpen, setSettingsOpen] = useState(false)
  const summary = xhsCreatorProfileSummaryFromAsset(xhsCreatorProfile || undefined)
  const hasSavedProfileUrl = Boolean(xhsCreatorProfile && profileUrl)
  const visibleProfileUrl = (() => {
    try {
      const parsed = new URL(profileUrl)
      return `${parsed.origin}${parsed.pathname}`
    } catch {
      return profileUrl
    }
  })()
  const isActive = captureJob ? ACTIVE_CAPTURE_STATUSES.has(captureJob.status) : false
  const completed = captureJob?.status === 'completed'
  const captureProgress = captureJob?.progress
  const commentTotal = captureProgress?.commentNotesTotal
  const progressPercent = completed
    ? 100
    : captureProgress?.phase === 'comments' && commentTotal != null && commentTotal > 0
      ? Math.min(100, Math.round(100 * captureProgress.commentNotesCompleted / commentTotal))
      : null

  return (
    <section className="creator-start-page">
      <div className="creator-start-hero">
        <h1>{xhsCreatorProfile ? '更新账号笔记' : '导入你的账号'}</h1>
        <form className="creator-url-form" onSubmit={onSubmit}>
          {hasSavedProfileUrl
            ? <label>已记录的小红书主页</label>
            : <label htmlFor="xhs-profile-url">{xhsCreatorProfile ? '补充小红书用户主页 URL' : '小红书用户主页 URL'}</label>}
          <div>
            {hasSavedProfileUrl
              ? <span className="creator-linked-url" title={visibleProfileUrl}>{visibleProfileUrl}</span>
              : <input
                  id="xhs-profile-url"
                  type="url"
                  value={profileUrl}
                  placeholder="https://www.xiaohongshu.com/user/profile/..."
                  onChange={(event) => onProfileUrlChange(event.target.value)}
                  disabled={submitting || isActive}
                  required
                />}
            <button type="submit" className="primary" disabled={submitting || isActive}>
              {isActive ? '正在导入' : hasSavedProfileUrl ? '继续读取' : '开始导入'}
            </button>
          </div>
        </form>
        <div className="creator-range-row">
          <span>{noteLimit === 0 ? '读取全部可见笔记' : `读取最近 ${noteLimit} 条笔记`} · 包含评论</span>
          <button type="button" disabled={submitting || isActive} onClick={() => setSettingsOpen(true)}>调整范围</button>
        </div>
        {settingsOpen && (
          <CreatorDialog title="读取范围" onClose={() => setSettingsOpen(false)}>
            <label htmlFor="capture-note-limit">笔记数量</label>
            <select id="capture-note-limit" value={noteLimit} onChange={(event) => onNoteLimitChange?.(Number(event.target.value))}>
              <option value={10}>最近 10 条（推荐）</option>
              <option value={20}>最近 20 条</option>
              <option value={50}>最近 50 条</option>
              <option value={100}>最近 100 条</option>
              <option value={0}>全部可见笔记</option>
            </select>
            <p>读取越多，等待越久。置顶内容可能包含在内；全部读取仍可能因平台限制或超时提前结束。</p>
            <button type="button" className="primary" onClick={() => setSettingsOpen(false)}>完成</button>
          </CreatorDialog>
        )}
        {error && <p className="creator-import-error">{error}</p>}
      </div>

      {captureJob && (
        <article className={`creator-capture-status ${captureJob.status}`}>
          <div>
            <span>导入状态</span>
            <strong>{captureJob.statusMessage}</strong>
          </div>
          <small>
            {captureJob.noteLimit === 0 ? '读取全部可见笔记' : `最多读取 ${captureJob.noteLimit} 条笔记`}
            {captureJob.includeComments ? '，包含一级评论' : '，不读取评论'}
          </small>
          <div
            className={`creator-capture-progress ${progressPercent === null && isActive ? 'indeterminate' : ''}`}
            role="progressbar"
            aria-label={captureProgress?.phase === 'comments' ? '评论读取进度' : '账号导入进度'}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={progressPercent ?? undefined}
            aria-valuetext={captureProgress?.phase === 'comments' && commentTotal != null
              ? `已完成 ${captureProgress.commentNotesCompleted}/${commentTotal} 个评论读取任务`
              : progressPercent === null ? '正在读取，当前阶段总量未知' : `${progressPercent}%`}
          >
            <span style={progressPercent === null ? undefined : { width: `${progressPercent}%` }} />
          </div>
          {captureProgress && (captureProgress.capturedNotes > 0 || captureProgress.capturedComments > 0) && (
            <p className="creator-capture-counts">
              已读取 {captureProgress.capturedNotes} 条笔记
              {captureJob.includeComments && ` · ${captureProgress.capturedComments} 条评论`}
              {captureProgress.phase === 'comments' && commentTotal != null && commentTotal > 0 &&
                ` · 已完成 ${captureProgress.commentNotesCompleted}/${commentTotal} 个评论读取任务`}
            </p>
          )}
          {captureJob.error && <details><summary>查看失败原因</summary><pre>{captureJob.error}</pre></details>}
          {captureJob.status === 'waiting_for_login' && (
            <p>请查看本机新打开的浏览器窗口，并使用小红书扫码完成登录。</p>
          )}
          {completed && (
            <div className="creator-start-actions">
              <button type="button" className="secondary-button" onClick={onOpenMaterials}>
                查看账号材料
              </button>
              <button type="button" className="small-primary" onClick={onOpenDiagnosis}>
                开始账号诊断
              </button>
            </div>
          )}
        </article>
      )}

      {summary && <article className="creator-profile-overview">
        <div className="detail-head compact">
          <div>
            <h3>{workspace?.name}</h3>
          </div>
        </div>
        {summary ? (
          <div className="creator-overview-metrics">
            <span>账号：{summary.displayName}</span>
            <span>笔记：{summary.noteCount}</span>
            <span>评论：{summary.commentCount}</span>
            <span>视频笔记：{summary.videoNoteCount}</span>
          </div>
        ) : (
          <p className="empty-card compact">粘贴主页链接开始；旧的离线导入能力仍保留为内部回退方式。</p>
        )}
      </article>}
    </section>
  )
}
