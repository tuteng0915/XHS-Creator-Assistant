import type { SimulationCategory, SimulationRunSummary } from '../types'
import { simulationCategoryFor } from '../simulationChat'
import './SimulationHub.css'

const SIMULATION_CATEGORIES: Array<{id: SimulationCategory; name: string; description: string}> = [
  {id: 'account', name: '账号级', description: '从选中的笔记出发，了解读者对账号的期待与内容方向。'},
  {id: 'published_note', name: '已发布笔记级', description: '复盘已有笔记，为下一篇同类内容积累经验。'},
  {id: 'creation', name: '创作级', description: '试读正在创作的选题或稿件，讨论本篇怎么改。'},
]

export function SimulationCategoryTabs({value, runs, onChange}: {
  value: SimulationCategory
  runs: SimulationRunSummary[]
  onChange: (category: SimulationCategory) => void
}) {
  return <section className="simulation-hub-heading" aria-label="受众模拟分类">
    <h1>受众模拟</h1>
    <div className="simulation-category-tabs" role="tablist" aria-label="模拟类别">
      {SIMULATION_CATEGORIES.map((category, index) => <button type="button" role="tab"
        key={category.id} id={`simulation-category-${category.id}`} aria-controls="simulation-category-content"
        aria-selected={value === category.id} tabIndex={value === category.id ? 0 : -1}
        onClick={() => onChange(category.id)}
        onKeyDown={event => {
          const offset = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0
          if (!offset && event.key !== 'Home' && event.key !== 'End') return
          event.preventDefault()
          const next = event.key === 'Home' ? 0 : event.key === 'End' ? SIMULATION_CATEGORIES.length - 1
            : (index + offset + SIMULATION_CATEGORIES.length) % SIMULATION_CATEGORIES.length
          onChange(SIMULATION_CATEGORIES[next].id)
          document.getElementById(`simulation-category-${SIMULATION_CATEGORIES[next].id}`)?.focus()
        }}>
        <span>{category.name}</span><small>{runs.filter(run => simulationCategoryFor(run) === category.id).length} 次讨论</small>
      </button>)}
    </div>
    <p className="simulation-category-description">{SIMULATION_CATEGORIES.find(category => category.id === value)?.description}</p>
  </section>
}
