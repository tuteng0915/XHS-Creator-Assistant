import type { StageView } from './WorkflowOutputPanel'
import { missingReactionPeople, simulationStageItems, stageDisplayStatus } from '../simulationStageStatus'

export function SimulationStageNotice({ stage }: { stage: StageView }) {
  const results = simulationStageItems(stage)
  const errors = Object.entries(stage.executionErrors || {})
  const namedErrors = new Set(errors.filter(([key]) => key.startsWith(`${stage.key}.`)).map(([key]) => key.slice(stage.key.length + 1)))
  const missing = missingReactionPeople(stage).filter(id => !namedErrors.has(id))
  const label = (id: string) => stage.personaLabels?.get(id) || '未记录姓名的受众'
  const silence = results.filter(item => stage.key === 'initial_reactions'
    ? item.action === 'no_comment' || item.action === 'skip'
    : !String(item.response || item.text || '').trim()).length
  const isReaction = stage.key === 'initial_reactions'
  const spoken = results.filter(item => isReaction
    ? (!item.action || item.action === 'comment') && String(item.quote || item.text || '').trim()
    : String(item.response || item.text || '').trim()).length
  const unspecified = results.length - silence - spoken
  return <>
    {results.length > 0 && <p className="simulation-coverage">
      已返回 {results.length} 位 · {spoken} 位{isReaction ? '评论' : '回应'} · {silence} 位{isReaction ? '不评论' : '不追加回应'}
      {unspecified > 0 && ` · ${unspecified} 位未注明行为`}
    </p>}
    {(errors.length > 0 || stage.error || missing.length > 0) && <details className="simulation-stage-issues">
      <summary>{stageDisplayStatus(stage).label === '部分完成' ? '部分角色未完成，已保留成功结果' : '查看未完成原因'}</summary>
      {errors.length ? <ul>{errors.map(([key, message]) => <li key={key}>
        {key.startsWith(`${stage.key}.`) ? `${label(key.slice(stage.key.length + 1))}：` : ''}{message}
      </li>)}</ul> : stage.error && <p>{stage.error}</p>}
      {missing.length > 0 && <p>未记录反应：{missing.map(label).join('、')}。没有返回结果不等于选择不评论。</p>}
    </details>}
  </>
}
