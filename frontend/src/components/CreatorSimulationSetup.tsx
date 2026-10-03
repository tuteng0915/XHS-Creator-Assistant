import { useState } from 'react'
import { useReaderSelection } from '../hooks/useReaderSelection'
import type { useSimulatedFans } from '../hooks/useSimulatedFans'
import type { ReaderSelectionLink } from '../readerSelection'
import type { Topic } from '../types'
import { SimulatedFanPicker } from './SimulatedFansPage'

interface Props {
  workspaceId: string
  positioning: string
  topics: Topic[]
  topic: Topic | null
  fans: ReturnType<typeof useSimulatedFans>
  running: boolean
  onSelect: (topic: Topic | null) => void
  onRun: (topic: Topic, recommendation?: ReaderSelectionLink) => void
  onAddFans: () => void
}

export function CreatorSimulationSetup(props: Props) {
  const {workspaceId, positioning, topic, topics, fans, running, onSelect, onRun, onAddFans} = props
  const scope = `${workspaceId}:${topic?.id || ''}`
  const revision = JSON.stringify([topic?.title, topic?.body, positioning,
    fans.rows.map(f => [f.id, f.status, f.updatedAt])])
  const recommendation = useReaderSelection(workspaceId, topic?.id || '', revision)
  const [adopted, setAdopted] = useState<(ReaderSelectionLink & {scope: string}) | null>(null)
  const [applyError, setApplyError] = useState('')
  const [applying, setApplying] = useState(false)
  const record = recommendation.record
  const proposals = record?.result?.proposedReaders || []
  const valid = !recommendation.busy && !recommendation.error && record?.freshness?.status === 'current'
    && ['completed', 'partially_completed'].includes(record.status) && proposals.length > 0
  const activeAdoption = adopted?.scope === scope ? adopted : null
  const adoptionReady = !activeAdoption || (valid && record?.id === activeAdoption.readerSelectionId
    && record.inputHash === activeAdoption.readerSelectionInputHash)

  async function apply() {
    setApplyError(''); setApplying(true)
    try {
      const checked = await recommendation.refresh()
      if (!checked || checked.freshness?.status !== 'current' || !checked.result?.proposedReaders.length) {
        setApplyError('推荐已变化或暂时无法核验，名单未改变。'); return
      }
      const ids = checked.result.proposedReaders.map(p => p.fanId)
      if (!fans.applySelection(ids)) { setApplyError('读者已不可用，请刷新名单后重试。'); return }
      setAdopted({scope, readerSelectionId: checked.id, readerSelectionInputHash: checked.inputHash})
    } finally { setApplying(false) }
  }

  return <section className="creator-diagnosis-controls creator-simulation-setup" aria-label="模拟准备">
    <label className="simulation-target">选题
      <select aria-label="模拟选题" value={topic?.id || ''} disabled={running || applying}
        onChange={e => onSelect(topics.find(t => t.id === e.target.value) || null)}>
        <option value="">选择选题</option>
        {topics.filter(t => t.status !== 'archived').map(t => <option key={t.id} value={t.id}>{t.title}</option>)}
      </select>
    </label>
    {topic && <details className="simulation-target-preview"><summary>{topic.body ? '查看待测正文' : '仅预演选题概念'}</summary>
      <p><strong>{topic.title}</strong>{topic.body && <><br />{topic.body}</>}</p></details>}
    <div className="reader-recommendation" aria-label="读者推荐">
      <div className="reader-recommendation-actions">
        <button type="button" disabled={!topic || running || recommendation.busy || applying}
          onClick={() => {setApplyError(''); void recommendation.recommend(Math.max(1, fans.slots.length))}}>
          {recommendation.busy ? '正在读取推荐…' : record ? '重新推荐读者' : '推荐读者'}</button>
        {recommendation.error && <button type="button" disabled={running || applying}
          onClick={() => void (recommendation.hasReceipt ? recommendation.refresh() : recommendation.recommend(fans.slots.length))}>
          {recommendation.hasReceipt ? '重试读取' : '重试原请求'}</button>}
      </div>
      {recommendation.error && <p role="alert">{recommendation.error}</p>}
      {record?.freshness?.status === 'stale' && <p role="status">内容或读者已变化，请重新推荐，或继续手动选择。</p>}
      {record?.freshness?.status === 'unavailable' && <p role="status">这份推荐的来源暂不可核验，仍可手动选择。</p>}
      {record?.status === 'failed' && <p role="status">{record.errorCode === 'input_too_large' ? '资料较长，请先手动选择读者。' : '本次推荐未完成，可重新推荐或手动选择。'}</p>}
      {record?.status === 'partially_completed' && <p role="status">部分完成，已保留有效读者。</p>}
      {!!proposals.length && <ul>{proposals.map(p => <li key={p.fanId}>
        <strong>{record?.inputSnapshot.candidates.find(f => f.id === p.fanId)?.name || '已保存读者'}</strong>
        <p>{p.fitReason}</p><details><summary>试读角度</summary>{p.contribution}</details>
      </li>)}</ul>}
      {record?.status === 'completed' && !proposals.length && <p role="status">{record.result?.unmatchedReason || '暂未找到合适读者。'}</p>}
      {!!proposals.length && <button type="button" disabled={!valid || running || applying} onClick={() => void apply()}>使用这组</button>}
      {applyError && <p role="alert">{applyError}</p>}
      {activeAdoption && <div className="reader-recommendation-actions"><span role="status">{adoptionReady ? '已采用推荐，可继续调整名单。' : '已采用的推荐需要重新核验。'}</span>
        <button type="button" disabled={running} onClick={() => setAdopted(null)}>仅按当前手选名单继续</button></div>}
    </div>
    {fans.error && <p role="alert">{fans.error}</p>}
    <fieldset className="simulation-reader-controls" disabled={running || applying}>
      <SimulatedFanPicker rows={fans.rows} slots={fans.slots} onSlotChange={fans.setSlot} onAddSlot={fans.addSlot} onRemoveSlot={fans.removeSlot} />
    </fieldset>
    {!fans.rows.some(r => r.status === 'active') && <button type="button" onClick={onAddFans}>从受众分析添加模拟粉丝</button>}
    <button className="primary" disabled={running || applying || !fans.ids.length || !topic || !adoptionReady}
      onClick={() => {if(topic) onRun(topic, activeAdoption ? {
        readerSelectionId: activeAdoption.readerSelectionId,
        readerSelectionInputHash: activeAdoption.readerSelectionInputHash,
      } : undefined)}}>开始模拟</button>
  </section>
}
