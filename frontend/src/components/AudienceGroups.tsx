import { useEffect, useRef, useState } from 'react'
import { audienceAnalysisApi } from '../api'
import { creatorNotesFromPayload, type CreatorNote } from '../creatorNotes'
import type { AudienceAnalysis } from '../types'
import { CreatorNoteBrowser } from './CreatorNoteBrowser'

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
  return <div className="audience-groups">{run.result.groups?.map(g => <article className="asset-detail-card audience-group-card" key={g.id}>
    <h2>{g.name}</h2><p>{g.profile}</p>
    {!!g.interests?.length && <p><span className="muted">兴趣领域：</span>{g.interests.join(' · ')}</p>}
    <p><span className="muted">具体需求：</span>{g.coreConcern}</p>
    {g.expressionStyle && <p><span className="muted">说话风格：</span>{g.expressionStyle}</p>}
    <details className="audience-evidence" onToggle={event => {if (event.currentTarget.open && g.evidenceRefs?.length) void loadNotes()}}>
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
              {ref.sourceType === 'comment' && (comment ? <p className="audience-source-text"><span className="muted">评论原文：</span>{comment.content || '图片评论'}</p> : <p className="muted">快照中无法唯一定位这条评论，保留历史引用。</p>)}
              <CreatorNoteBrowser notes={[note]} mediaAssets={[]} />
            </> : notes !== null && <p className="muted">当次快照未保留这篇笔记或来源不唯一，仅显示历史引用。</p>}
          </div>
        })}
      </> : <><p className="muted">历史分析依据，尚未核验来源引用。</p>{g.evidence?.map((e, j) => <p key={j}>{e}</p>)}</>}
    </details>
    <button disabled={Boolean(savingGroup) || savedFanKeys.includes(`${run.id}:${g.id}`)} onClick={() => onSave(g.id)}>{savedFanKeys.includes(`${run.id}:${g.id}`) ? '已保存为模拟粉丝' : savingGroup === g.id ? '保存中…' : '保存为模拟粉丝'}</button>
  </article>)}</div>
}
