import { useEffect, useRef, useState } from 'react'
import { audienceAnalysisApi } from '../api'
import { creatorNotesFromPayload, type CreatorNote } from '../creatorNotes'
import type { AudienceAnalysis } from '../types'
import { CreatorNoteBrowser } from './CreatorNoteBrowser'
import { ReaderAvatar } from './ReaderAvatar'
import './AudienceResults.css'

const BASIS_LABELS: Record<string, string> = {
  mixed: '笔记与评论', comment_observed: '评论表达', content_inferred: '从笔记内容推断',
}

function snapshotNotes(run: AudienceAnalysis): CreatorNote[] {
  // Match the backend's per-snapshot fallback IDs for older imported material.
  return creatorNotesFromPayload({notes: run.inputSnapshot.notes?.map((raw, i) => {
    const note = raw && typeof raw === 'object' ? raw as Record<string, unknown> : {}
    return {...note, noteId: note.noteId || `snapshot-note-${i}`}
  })})
}

// Parent keys this component by workspace/run; polling summaries do not erase loaded detail.
export function AudienceGroups({run, savingGroup, savedFanKeys, onSave}: {
  run: AudienceAnalysis; savingGroup: string; savedFanKeys: string[]; onSave: (id: string) => void;
}) {
  const [notes, setNotes] = useState<CreatorNote[] | null>(() => Array.isArray(run.inputSnapshot.notes) ? snapshotNotes(run) : null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const fetching = useRef(false)
  const mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  async function loadNotes() {
    if (notes !== null || fetching.current) return
    fetching.current = true; setLoading(true); setError('')
    try {
      const detail = await audienceAnalysisApi.get(run.id)
      if (!mounted.current) return
      if (detail.id !== run.id || detail.workspaceId !== run.workspaceId) throw new Error('分析来源不匹配，请重试。')
      setNotes(snapshotNotes(detail))
    } catch (e) {
      if (mounted.current) setError(e instanceof Error ? e.message : '依据加载失败')
    } finally {
      fetching.current = false
      if (mounted.current) setLoading(false)
    }
  }
  return <div className="audience-groups">{run.result.groups?.map(g => <article className="audience-group-card" key={g.id} aria-label={g.name}>
    <div className="reader-card-heading"><ReaderAvatar id={`${run.id}:${g.id}`} name={g.name} /><h2>{g.name}</h2></div>
    {g.profile?.trim() && <p className="audience-reader-profile">{g.profile}</p>}
    {g.coreConcern?.trim() && <p className="audience-reader-need"><span>想获得</span>{g.coreConcern}</p>}
    {!!g.interests?.filter(interest => interest.trim()).length && <p className="audience-reader-interests" aria-label="兴趣领域">{g.interests.filter(interest => interest.trim()).join(' · ')}</p>}
    <div className="audience-card-action">
      <button disabled={Boolean(savingGroup) || savedFanKeys.includes(`${run.id}:${g.id}`)} onClick={() => onSave(g.id)}>{savedFanKeys.includes(`${run.id}:${g.id}`) ? '已收录' : savingGroup === g.id ? '收录中…' : '收录为模拟读者'}</button>
    </div>
    {g.expressionStyle?.trim() && <details className="audience-reader-details"><summary>阅读与表达习惯</summary>
      <p>{g.expressionStyle}</p>
    </details>}
    {Boolean(g.evidenceRefs?.length || g.evidence?.some(item => item.trim())) && <details className="audience-evidence" onToggle={event => {if (event.currentTarget.open && g.evidenceRefs?.length) void loadNotes()}}>
      <summary>依据</summary>
      <p className="muted">{BASIS_LABELS[g.evidenceBasis || ''] || (g.evidenceRefs?.some(e => e.sourceType === 'comment') ? '评论表达' : g.evidenceRefs?.length ? '从笔记内容推断' : '历史结果')}</p>
      {g.evidenceRefs?.length ? <>
        {loading && <p role="status">正在加载当次笔记…</p>}
        {error && <div role="alert">依据加载失败：{error}<button type="button" onClick={() => void loadNotes()}>重试加载依据</button></div>}
        {g.evidenceRefs.map((ref, index) => {
          const matches = notes?.filter(n => n.noteId === ref.noteId) || []
          const note = matches.length === 1 ? matches[0] : undefined
          const comments = note?.comments.filter((c, i) => (c.commentId || `snapshot-comment-${i}`) === ref.commentId) || []
          const comment = comments.length === 1 ? comments[0] : undefined
          return <div className="audience-evidence-ref" key={index}>
            <p><b>{ref.sourceType === 'comment' ? '引用评论' : '引用笔记'}</b>：{ref.quote}</p>
            {note ? <>
              {ref.sourceType === 'comment' && (comment
                ? comment.content !== ref.quote && <p className="audience-source-text"><span className="muted">评论原文：</span>{comment.content || '图片评论'}</p>
                : <p className="muted">快照中无法唯一定位这条评论，保留历史引用。</p>)}
              <CreatorNoteBrowser notes={[note]} mediaAssets={[]} />
            </> : notes !== null && <p className="muted">当次快照未保留这篇笔记或来源不唯一，仅显示历史引用。</p>}
          </div>
        })}
      </> : <><p className="muted">历史分析依据，尚未核验来源引用。</p>{g.evidence?.map((e, j) => <p key={j}>{e}</p>)}</>}
    </details>}
  </article>)}</div>
}
