import type {SimulationCategory, SimulationRunSummary} from './types'

export function simulationCategoryFor(run:SimulationRunSummary & {inputSnapshot?:Record<string,unknown>}):SimulationCategory {
  const category=run.simulationCategory || run.inputSnapshot?.simulationCategory
  if(category==='account'||category==='published_note'||category==='creation')return category
  return run.inputSnapshot?.targetType==='account'?'account':run.inputSnapshot?.targetType==='note'?'published_note':'creation'
}

export const simulationCategoryLabel = (category:SimulationCategory) => ({account:'账号',published_note:'已发布笔记',creation:'创作'}[category])

export const simulationStatusLabel = (status:string) => ({pending:'等待开始',running:'正在试读',completed:'已完成',partially_completed:'已有部分结果',failed:'未完成'}[status] || '历史记录')

export function visibleReply(content:string, people:Array<Record<string,unknown>>) {
  let value = content
  for (const p of people) {
    const id = typeof p.id==='string'?p.id:''
    const name = typeof p.name==='string'?p.name:typeof p.archetype==='string'?p.archetype:'读者'
    if (id) for (const key of [`@initial:${id}`,`@reply:${id}`,`@${id}`,`initial:${id}`,`reply:${id}`]) value = value.replaceAll(key, `@${name}`)
  }
  return value.replace(/@(?:initial:|reply:)?[a-f\d]{8}-[a-f\d-]{27,}/gi, '@读者')
}
