import type { SimulationRun } from '../types'

function object(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}
function rows(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(object).filter(item => Object.keys(item).length > 0) : []
}
function text(value: unknown): string { return typeof value === 'string' ? value.trim() : '' }

export function SimulationReaderSummary({ run }: {run: SimulationRun}) {
  const snapshot = run.inputSnapshot
  const selection = object(snapshot.readerSelection)
  const overrides = object(snapshot.personaOverrides)
  const proposed = rows(selection.proposedReaders).filter(item => text(item.fanId))
  const definitions = run.personaDefinitions.length ? run.personaDefinitions : rows(snapshot.audiencePersonas)
  const actualIds = Array.isArray(selection.actualFanIds)
    ? [...new Set(selection.actualFanIds.filter((id): id is string => typeof id === 'string' && id.length > 0))]
    : [...new Set(definitions.map(item => text(item.id)).filter(Boolean))]
  const names = new Map<string, string>()
  for (const item of [...rows(snapshot.audiencePersonas), ...definitions]) {
    const id = text(item.fanAssetId) || text(item.id)
    if (id) names.set(id, text(item.name) || text(item.archetype))
  }
  // New runs freeze unselected recommendations too. Never query today's fan assets.
  for (const item of proposed) {
    if (text(item.name) && !names.get(text(item.fanId))) names.set(text(item.fanId), text(item.name))
  }
  const allIds = [...new Set([...proposed.map(item => text(item.fanId)), ...actualIds])]
  function label(id: string) {
    const name = names.get(id)
    if (!name) return `读者 ${allIds.indexOf(id) + 1}（姓名未保存）`
    return allIds.filter(other => names.get(other) === name).length > 1
      ? `${name}（${allIds.indexOf(id) + 1}）` : name
  }
  const mode = selection.source === 'recommended' ? '使用推荐'
    : selection.source === 'adjusted' ? '推荐后调整'
      : selection.source === 'manual' ? '手动选择' : '旧记录未保存选择方式'

  return <section className="simulation-reader-summary" aria-label="本次读者选择">
    <div className="account-performance-heading"><h3>本次读者</h3><span className="muted">{mode}</span></div>
    <div className="account-performance-grid">
      <div className="account-performance-group">
        <b>当时推荐</b>
        {proposed.length ? <ul>{proposed.map((item, index) => <li key={`${text(item.fanId)}-${index}`}>
          <span>{text(item.name) && text(item.name) !== names.get(text(item.fanId)) ? text(item.name) : label(text(item.fanId))}</span>
          <small className="muted"> · {actualIds.includes(text(item.fanId)) ? '本次已选' : '未选用'}</small>
          {(text(item.fitReason) || text(item.contribution)) && <details>
            <summary>推荐理由</summary>
            {text(item.fitReason) && <p>{text(item.fitReason)}</p>}
            {text(item.contribution) && <p>{text(item.contribution)}</p>}
          </details>}
        </li>)}</ul> : <p className="muted">{selection.source === 'manual' ? '本次未使用推荐' : '此记录未保存推荐名单'}</p>}
      </div>
      <div className="account-performance-group">
        <b>{run.personaDefinitions.length ? '实际参与者' : '本次选择'}</b>
        {actualIds.length ? <ol>{actualIds.map(id => <li key={id}>{label(id)}
          {Object.keys(object(overrides[id])).length>0&&<details><summary>本次画像已调整</summary>
            {([['profile','视角'],['coreConcern','关切'],['expressionStyle','表达方式']] as const).map(([key,title])=>text(object(overrides[id])[key])&&<p key={key}><b>{title}：</b>{text(object(overrides[id])[key])}</p>)}
            <small className="muted">仅用于这次讨论，未修改长期读者画像。</small>
          </details>}
        </li>)}</ol>
          : <p className="muted">未保存参与者名单</p>}
      </div>
    </div>
    <small className="muted">按本次保存的名单展示，反应是否完成见下方结果。</small>
  </section>
}
