import { expect, it } from 'vitest'
import { simulationPersonaLabels, withSimulationPersonaLabels } from './simulationPersonaLabels'
import { stageSeedFromSimulation } from './workflowStageViews'
import type { SimulationRun } from './types'

it('uses frozen names, legacy archetypes and disambiguates duplicates by run order', () => {
  const labels = simulationPersonaLabels([
    {id:'a',name:'行动派',archetype:'旧分类'}, {id:'b',name:'行动派'},
    {id:'c',archetype:'查证派'}, {id:'d',name:'  '},
  ], [], [])
  expect([...labels.values()]).toEqual(['行动派（受众 1）','行动派（受众 2）','查证派','受众 4'])
})

it('assigns stable fallback labels across reaction order and discussion recipients', () => {
  const labels = simulationPersonaLabels(null, [{personaId:'a'},{personaId:'b'}],
    [{personaId:'b',replyToId:'initial:a'},{personaId:'a',targetedAt:'missing'}])
  expect([...labels]).toEqual([['a','受众 1'],['b','受众 2'],['missing','受众 3']])
})

it('ignores malformed definitions and uses the first definition for duplicate IDs', () => {
  const labels = simulationPersonaLabels([null,[],42,{name:'没有ID'},{id:'a',name:'第一份'}, {id:'a',name:'第二份'}], undefined, [])
  expect([...labels]).toEqual([['a','第一份']])
})

it('replaces stale mappings even when the next execution has no persona definitions', () => {
  const source = [{key:'initial_reactions',n:'2',title:'反应',status:'completed' as const,
    result:{reactions:[{personaId:'a'}]},personaLabels:new Map([['a','另一个账号']])}]
  const stages = withSimulationPersonaLabels(source)
  expect(stages[0].personaLabels?.get('a')).toBe('受众 1')
  expect(source[0].personaLabels.get('a')).toBe('另一个账号')
})

it('reopened results use only that runs definitions and never the current asset or input override', () => {
  const run = {status:'completed',inputSnapshot:{audiencePersonas:[{id:'a',name:'输入旧名称'}]},
    personaDefinitions:[{id:'a',name:'当时的名字'},{id:'b',name:'当时的另一位'}],
    reactionResults:[{personaId:'a',quote:'内容'}],debateResults:[{personaId:'b',replyToId:'initial:a'}],synthesis:{},stageErrors:{}} as unknown as SimulationRun
  const before = JSON.stringify(run)
  const stages = stageSeedFromSimulation(run)
  expect(stages.find(s=>s.key==='debate_responses')?.personaLabels?.get('a')).toBe('当时的名字')
  expect(JSON.stringify(run)).toBe(before)
  const next = stageSeedFromSimulation({...run,workspaceId:'other',personaDefinitions:[{id:'a',name:'另一账号同ID'}]})
  expect(next[0].personaLabels?.get('a')).toBe('另一账号同ID')
  expect(stages[0].personaLabels?.get('a')).toBe('当时的名字')
})
