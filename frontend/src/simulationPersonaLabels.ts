import type { StageView } from './components/WorkflowOutputPanel'

function rows(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> =>
    Boolean(item) && typeof item === 'object' && !Array.isArray(item)) : []
}

function text(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

export function replyPersonaId(item: Record<string, unknown>): string {
  // The current discussion replies to an initial message. Prefer its explicit ID.
  const reply = text(item.replyToId)
  return reply.startsWith('initial:') ? reply.slice('initial:'.length) : text(item.targetedAt)
}

export function simulationPersonaLabels(personas: unknown, reactions: unknown, debates: unknown): Map<string, string> {
  const names = new Map<string, string>()
  for (const persona of rows(personas)) {
    const id = text(persona.id)
    if (id && !names.has(id)) names.set(id, text(persona.name) || text(persona.archetype))
  }
  const discussion = [...rows(reactions), ...rows(debates)]
  for (const item of discussion) {
    const id = text(item.personaId)
    if (id && !names.has(id)) names.set(id, '')
  }
  for (const item of rows(debates)) {
    const id = replyPersonaId(item)
    if (id && !names.has(id)) names.set(id, '')
  }
  const counts = new Map<string, number>()
  for (const name of names.values()) if (name) counts.set(name, (counts.get(name) || 0) + 1)
  return new Map([...names].map(([id, name], index) => [id,
    !name ? `受众 ${index + 1}` : (counts.get(name) || 0) > 1 ? `${name}（受众 ${index + 1}）` : name,
  ]))
}

export function withSimulationPersonaLabels(stages: StageView[]): StageView[] {
  function result(key: string): Record<string, unknown> {
    const value = stages.find(stage => stage.key === key)?.result
    return value && typeof value === 'object' ? value as Record<string, unknown> : {}
  }
  const labels = simulationPersonaLabels(result('personas').personas,
    result('initial_reactions').reactions, result('debate_responses').debateResponses)
  // Always replace the map: never retain names from a previous execution.
  const personaIds = rows(result('personas').personas).map(p => text(p.id)).filter(Boolean)
  return stages.map(stage => ({...stage, personaLabels: labels, personaIds}))
}
