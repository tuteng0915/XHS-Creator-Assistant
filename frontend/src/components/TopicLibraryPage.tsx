import { useEffect, useRef, useState, type FormEvent } from 'react'
import { CreatorDialog } from './CreatorDialog'
import { PendingSuggestions } from './PendingSuggestions'

import { EmptyState, JsonPreview } from './CommonUi'
import { SaveIndicator, type SaveState } from './StageResultViews'
import type { Topic, TopicSourceWorkflow } from '../types'

type TopicFilter = TopicSourceWorkflow | 'all'

type Props = {
  publicMode?: boolean
  busy?: boolean
  onLeaveGuardChange?: (message: string | null) => void
  onOpenCanvas?: (topic: Topic) => void
  onTogglePinned?: (topic: Topic) => void | Promise<unknown>
  onSimulateTopic?: (topic: Topic) => void
  visibleTopics: Topic[]
  selectedTopic: Topic | null
  topicFilter: TopicFilter
  manualTopicTitle: string
  manualTopicAngle: string
  topicDraft: { title: string; angle: string; body?: string }
  manualTopicSaveState: SaveState
  topicSaveState: SaveState
  onManualTopicTitleChange: (value: string) => void
  onManualTopicAngleChange: (value: string) => void
  onSaveManualTopic: (event: FormEvent<HTMLFormElement>) => void | Promise<boolean>
  onTopicFilterChange: (value: TopicFilter) => void
  onSelectTopicRow: (topic: Topic) => void
  onSelectCurrentTopic: (topic: Topic) => void | Promise<unknown>
  onGenerateBrief: (topic: Topic) => void
  onGenerateDraft: (topic: Topic) => void
  onArchiveTopic: (topic: Topic) => void | Promise<unknown>
  onTopicDraftChange: (draft: { title: string; angle: string; body?: string }) => void
  onSaveTopicEdits: () => void
}

function topicSourceLabel(source: TopicSourceWorkflow | 'all'): string {
  if (source === 'all') return '全部'
  if (source === 'account_diagnosis') return '账号诊断'
  if (source === 'trend_analysis') return '热点分析'
  return '手动'
}

function topicStatusLabel(status: Topic['status']): string {
  return { candidate: '待创作', selected: '当前选题', archived: '已归档' }[status]
}

export function TopicLibraryPage({
  publicMode = false,
  busy = false,
  onLeaveGuardChange,
  onOpenCanvas,
  onTogglePinned,
  onSimulateTopic,
  visibleTopics,
  selectedTopic,
  topicFilter,
  manualTopicTitle,
  manualTopicAngle,
  topicDraft,
  manualTopicSaveState,
  topicSaveState,
  onManualTopicTitleChange,
  onManualTopicAngleChange,
  onSaveManualTopic,
  onTopicFilterChange,
  onSelectTopicRow,
  onSelectCurrentTopic,
  onGenerateBrief,
  onGenerateDraft,
  onArchiveTopic,
  onTopicDraftChange,
  onSaveTopicEdits,
}: Props) {
  const [creating, setCreating] = useState(false)
  const [more, setMore] = useState(false)
  const [confirmArchive, setConfirmArchive] = useState(false)
  const [actionBusy, setActionBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const actionLock = useRef(false)
  const active = useRef(true)
  useEffect(() => {active.current = true; return () => {active.current = false}}, [])
  const dirty = Boolean(selectedTopic && (topicDraft.title !== selectedTopic.title || topicDraft.angle !== selectedTopic.angle || (topicDraft.body || '') !== (selectedTopic.body || '')))
  const actionDisabled = publicMode && (dirty || busy || actionBusy || topicSaveState.phase === 'saving')
  useEffect(() => {
    const message = publicMode && dirty ? '选题有未保存修改。请取消并保存，或确定放弃修改后离开。' : null
    onLeaveGuardChange?.(message)
    const warn = (event: BeforeUnloadEvent) => {event.preventDefault(); event.returnValue = ''}
    if (message) window.addEventListener('beforeunload', warn)
    return () => {onLeaveGuardChange?.(null); window.removeEventListener('beforeunload', warn)}
  }, [publicMode, dirty, onLeaveGuardChange])
  useEffect(() => {setMore(false); setConfirmArchive(false); setActionError('')}, [selectedTopic?.id])
  async function runTopicAction(action: (topic: Topic) => void | Promise<unknown>) {
    if (!selectedTopic || actionDisabled || actionLock.current) return
    actionLock.current = true; setActionBusy(true); setActionError('')
    try {await action(selectedTopic); if (active.current) {setMore(false); setConfirmArchive(false)}}
    catch (error) {if (active.current) setActionError(error instanceof Error ? error.message : String(error))}
    finally {actionLock.current = false; if (active.current) setActionBusy(false)}
  }
  const manualForm = (
    <form className="manual-topic" onSubmit={async (event) => {
      event.preventDefault()
      if (await onSaveManualTopic(event)) setCreating(false)
    }}>
      <input aria-label="手动选题标题" placeholder="选题标题" required value={manualTopicTitle} onChange={(event) => onManualTopicTitleChange(event.target.value)} />
      <textarea aria-label="手动选题角度" placeholder="切入角度" rows={3} value={manualTopicAngle} onChange={(event) => onManualTopicAngleChange(event.target.value)} />
      <div className="save-row"><button className="primary" disabled={manualTopicSaveState.phase === 'saving' || !manualTopicTitle.trim()}>保存选题</button><SaveIndicator state={manualTopicSaveState} /></div>
    </form>
  )
  return (
    <div className={`workspace-page topics-page${publicMode ? ' creator-topics-page' : ''}`}>
      <section className="history-list">
        {publicMode ? <h1 className="creator-topics-title">选题库</h1> : <div className="panel-title">◇ 选题库</div>}
        {publicMode ? <>
          <button type="button" className="primary" disabled={actionDisabled} onClick={() => setCreating(true)}>＋ 新建选题</button>
          {creating && <CreatorDialog title="新建选题" onClose={() => setCreating(false)}>{manualForm}</CreatorDialog>}
        </> : <form className="manual-topic" onSubmit={onSaveManualTopic}>
          <input
            aria-label="手动选题标题"
            placeholder="手动输入选题"
            value={manualTopicTitle}
            onChange={(event) => onManualTopicTitleChange(event.target.value)}
          />
          <textarea
            aria-label="手动选题角度"
            placeholder="切入角度"
            rows={2}
            value={manualTopicAngle}
            onChange={(event) => onManualTopicAngleChange(event.target.value)}
          />
          <div className="save-row">
            <button className="primary">保存选题</button>
            <SaveIndicator state={manualTopicSaveState} />
          </div>
        </form>}
        <div className="filter-row">
          {(['all', 'account_diagnosis', 'trend_analysis', 'manual'] as const).filter((item) => !publicMode || item !== 'trend_analysis').map(
            (item) => (
              <button
                key={item}
                className={topicFilter === item ? 'active' : ''}
                aria-pressed={topicFilter === item}
                onClick={() => onTopicFilterChange(item)}
              >
                {topicSourceLabel(item)}
              </button>
            ),
          )}
        </div>
        {[...visibleTopics].sort((a,b) => Number(Boolean(b.pinned))-Number(Boolean(a.pinned)) || b.updatedAt.localeCompare(a.updatedAt)).map((topic) => (
          <button
            key={topic.id}
            className={`topic-row ${selectedTopic?.id === topic.id ? 'active' : ''}`}
            aria-pressed={selectedTopic?.id === topic.id}
            disabled={actionBusy}
            onClick={() => onSelectTopicRow(topic)}
          >
            <span>{topic.pinned ? '📌 ' : ''}{topic.title}</span>
            <b>{publicMode ? topicStatusLabel(topic.status) : topic.status}</b>
            <small>{publicMode ? topicSourceLabel(topic.sourceWorkflow) : topic.sourceWorkflow}</small>
          </button>
        ))}
      </section>
      <section className="history-detail">
        {selectedTopic ? (
          <>
            <div className="detail-head asset-detail-head">
              <div>
                <h2>{selectedTopic.title}</h2>
                <p>
                  {publicMode ? topicSourceLabel(selectedTopic.sourceWorkflow) : selectedTopic.sourceWorkflow} · {publicMode ? topicStatusLabel(selectedTopic.status) : selectedTopic.status}
                </p>
              </div>
              <div className="detail-actions">
                {!publicMode && <button disabled={actionDisabled} onClick={() => onSelectCurrentTopic(selectedTopic)}>
                  设为当前
                </button>}
                <button className="primary" disabled={actionDisabled} onClick={() => publicMode ? selectedTopic.status === 'archived' ? void runTopicAction(onSelectCurrentTopic) : onOpenCanvas?.(selectedTopic) : onGenerateBrief(selectedTopic)}>
                  {publicMode ? selectedTopic.status === 'archived' ? '恢复并设为当前' : 'AI 创作助手' : '生成创作 Brief'}
                </button>
                {!publicMode && <button disabled={actionDisabled} onClick={() => onGenerateDraft(selectedTopic)}>
                  生成内容结构
                </button>}
                {publicMode && selectedTopic.status !== 'archived' && <button disabled={actionDisabled} onClick={() => onSimulateTopic?.(selectedTopic)}>受众模拟</button>}
                {publicMode ? <button type="button" disabled={actionDisabled} onClick={() => {setActionError(''); setMore(true)}}>更多</button> : <button onClick={() => onArchiveTopic(selectedTopic)}>归档</button>}
              </div>
            </div>
            {actionError && !more && <p role="alert">{actionError}</p>}
            {more && <CreatorDialog title={confirmArchive ? '归档这条选题？' : '选题操作'} onClose={() => {if (!actionBusy) {setMore(false); setConfirmArchive(false)}}}>
              {confirmArchive ? <>
                <p>归档后仍保留稿件和历史，可以恢复并设为当前选题。</p>
                <div className="detail-actions"><button type="button" disabled={actionBusy} onClick={() => setConfirmArchive(false)}>取消</button>
                  <button type="button" className="danger" disabled={actionBusy} onClick={() => void runTopicAction(onArchiveTopic)}>{actionBusy ? '正在归档…' : '确认归档'}</button></div>
              </> : <div className="detail-actions">
                {selectedTopic.status !== 'archived' && <button type="button" disabled={actionBusy} onClick={() => void runTopicAction(onSelectCurrentTopic)}>设为当前</button>}
                {onTogglePinned && <button type="button" disabled={actionBusy} onClick={() => void runTopicAction(onTogglePinned)}>{selectedTopic.pinned ? '取消置顶' : '置顶'}</button>}
                {selectedTopic.status !== 'archived' && <button type="button" className="danger" disabled={actionBusy} onClick={() => setConfirmArchive(true)}>归档</button>}
              </div>}
              {actionBusy && !confirmArchive && <p role="status">正在更新选题…</p>}
              {actionError && <p role="alert">操作未完成：{actionError}。可以重试。</p>}
            </CreatorDialog>}
            <div className="asset-detail-card">
              {!publicMode && <div className="asset-section-head">
                <h3>可编辑资产字段</h3>
                <span>用户编辑区</span>
              </div>}
              <label htmlFor="topic-title">标题</label>
              <input
                id="topic-title"
                disabled={actionBusy}
                value={topicDraft.title}
                onChange={(event) =>
                  onTopicDraftChange({
                    ...topicDraft,
                    title: event.target.value,
                  })
                }
              />
              <label htmlFor="topic-angle">切入角度</label>
              <textarea
                id="topic-angle"
                disabled={actionBusy}
                rows={4}
                value={topicDraft.angle}
                onChange={(event) =>
                  onTopicDraftChange({
                    ...topicDraft,
                    angle: event.target.value,
                  })
                }
              />
              {publicMode && <><label htmlFor="topic-body">正文</label><textarea id="topic-body" disabled={actionBusy} rows={12} value={topicDraft.body || ''} onChange={event => onTopicDraftChange({...topicDraft,body:event.target.value})} /></>}
              <div className="save-row">
                <button className="primary" disabled={publicMode && (!dirty || actionBusy || topicSaveState.phase === 'saving')} onClick={onSaveTopicEdits}>
                  {publicMode ? '保存修改' : '保存选题资产'}
                </button>
                <SaveIndicator state={topicSaveState} />
                {publicMode && dirty && <small>保存修改后可继续生成或模拟。</small>}
              </div>
            </div>
            <div className="asset-detail-card readonly">
              <div className="asset-section-head">
                <h3>来源与适配理由</h3>
                <span>只读</span>
              </div>
              {!publicMode && <div className="asset-meta-grid">
                <div>
                  <b>来源 workflow</b>
                  <span>{selectedTopic.sourceWorkflow}</span>
                </div>
                <div>
                  <b>来源分析</b>
                  <span>{selectedTopic.sourceAnalysisRunId || '无'}</span>
                </div>
                <div>
                  <b>创建时间</b>
                  <span>{new Date(selectedTopic.createdAt).toLocaleString()}</span>
                </div>
                <div>
                  <b>更新时间</b>
                  <span>{new Date(selectedTopic.updatedAt).toLocaleString()}</span>
                </div>
              </div>}
              <label>关联痛点</label>
              <div className="readonly-box">
                {selectedTopic.associatedPainPoint || '无'}
              </div>
              <label>为什么适合</label>
              <div className="readonly-box">{selectedTopic.whyItFits || '无'}</div>
              <PendingSuggestions value={selectedTopic.generatedSnapshot.pendingSuggestions} />
              {!publicMode && <details className="asset-json-details">
                <summary>Generated Snapshot</summary>
                <JsonPreview value={selectedTopic.generatedSnapshot} />
              </details>}
            </div>
          </>
        ) : (
          <EmptyState>选择或创建一个选题。</EmptyState>
        )}
      </section>
    </div>
  )
}
