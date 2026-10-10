import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react'
import {afterEach, beforeEach, expect, it, vi} from 'vitest'
import App from './App'
import {memoryStorage} from './test/storage'
import type {SimulationRun} from './types'

beforeEach(() => {
  window.history.replaceState({}, '', '/')
  vi.stubGlobal('localStorage', memoryStorage())
})
afterEach(() => {
  cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals()
  window.history.replaceState({}, '', '/')
})

class ControlledEventSource {
  static instances: ControlledEventSource[] = []
  private listeners = new Map<string, EventListener[]>()
  onerror: (() => void) | null = null
  closed = false
  constructor(readonly url: string) {ControlledEventSource.instances.push(this)}
  addEventListener(type: string, listener: EventListener) {
    this.listeners.set(type, [...(this.listeners.get(type) || []), listener])
  }
  close() {this.closed = true}
  complete() {
    const event = new MessageEvent('run.succeeded', {data: JSON.stringify({
      eventId: 'finished-a', runId: 'run-a', runType: 'audience_simulation', stageKey: null,
      status: 'completed', sequence: 2, occurredAt: '2026-10-08T00:00:02Z',
      data: {eventType: 'run.succeeded'},
    })})
    this.listeners.get('run.succeeded')?.forEach(listener => listener(event))
  }
}

function makeRun(id: string, workspaceId: string, status: SimulationRun['status']): SimulationRun {
  return {
    id, workspaceId, status, topicId: null, draftId: null, reviewStatus: 'unreviewed', userNotes: '',
    createdAt: id === 'run-a' ? '2026-10-08T00:00:00Z' : '2026-10-07T00:00:00Z',
    startedAt: '2026-10-08T00:00:00Z', completedAt: status === 'completed' ? '2026-10-08T00:00:01Z' : null,
    updatedAt: '2026-10-08T00:00:01Z',
    inputSnapshot: {topic: {title: `${id}的内容`, body: `${id}的完整正文`}, targetType: 'topic',
      panelTask: {protocolVersion: 'panel/v1', readingMode: 'natural', discussionEnabled: true, focusQuestions: []}},
    personaDefinitions: [{id: 'reader', name: `${id}的读者`, profile: '关注第一步是否清楚'}],
    reactionResults: status === 'completed' ? [{personaId: 'reader', action: 'comment', quote: `${id}的历史发言`}] : [],
    debateResults: [], synthesis: {}, stageErrors: {}, modelMetadata: {},
  }
}

function setup(switchAccount: boolean) {
  ControlledEventSource.instances = []
  vi.stubGlobal('EventSource', ControlledEventSource)
  const workspaces = ['甲', '乙'].map((name, index) => ({id: `account-${index}`, name,
    accountPositioning: '', positioningVersion: 1, currentTopicId: null, createdAt: '', updatedAt: ''}))
  const runningA = makeRun('run-a', 'account-0', 'running')
  const completedA = {...runningA, status: 'completed' as const,
    completedAt: '2026-10-08T00:00:02Z', reactionResults: [{personaId: 'reader', action: 'comment', quote: 'A后来完成的发言'}]}
  const historicalB = makeRun('run-b', switchAccount ? 'account-1' : 'account-0', 'completed')
  let createdA = false
  let finishingA = false
  let finishedA = false
  const delayedA: Array<(response: Response) => void> = []
  const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    if (url === '/api/workspaces') return Response.json(workspaces)
    if (url === '/api/simulation-runs/run-b') return Response.json(historicalB)
    if (url === '/api/simulation-runs/run-a') {
      if (finishingA && !finishedA) return new Promise(resolve => delayedA.push(resolve))
      return Response.json(finishedA ? completedA : runningA)
    }
    if (url === '/api/workspaces/account-0/simulation-runs' && init?.method === 'POST') {
      createdA = true
      return Response.json(runningA, {status: 201})
    }
    const workspace = workspaces.find(row => url.startsWith(`/api/workspaces/${row.id}`))
    if (!workspace) throw new Error(`Unexpected request: ${url}`)
    if (url === `/api/workspaces/${workspace.id}`) return Response.json(workspace)
    if (url.endsWith('/input-assets')) return Response.json([{id: `profile-${workspace.id}`,
      workspaceId: workspace.id, type: 'xhs_creator_profile', name: workspace.name, createdAt: '', updatedAt: '',
      content: JSON.stringify({schemaVersion: 'xhs-creator-profile/v1', creator: {displayName: workspace.name},
        notes: [{noteId: 'note', title: `${workspace.name}的笔记`, desc: '原始正文', comments: []}]}),
    }])
    if (url.endsWith('/topics') && workspace.id === 'account-0') return Response.json([{
      id: 'topic-a', workspaceId: workspace.id, title: '新试读A', body: '新试读的完整正文', angle: '',
      associatedPainPoint: '', whyItFits: '', generatedSnapshot: {}, sourceAnalysisRunId: null,
      sourceWorkflow: 'manual', status: 'candidate', createdAt: '', updatedAt: 'v1',
    }])
    if (url.endsWith('/simulated-fans') && workspace.id === 'account-0') return Response.json([{
      id: 'reader', workspaceId: workspace.id, sourceAnalysisId: 'analysis', sourceGroupId: 'group', original: {},
      editable: {name: '模拟读者', profile: '关注第一步', coreConcern: '', contentPreference: '', expressionStyle: ''},
      status: 'active', createdAt: '', updatedAt: 'v1',
    }])
    if (url.endsWith('/simulation-runs')) return Response.json([
      ...(createdA && workspace.id === 'account-0' ? [finishedA ? completedA : runningA] : []),
      ...(historicalB.workspaceId === workspace.id ? [historicalB] : []),
    ])
    return Response.json([])
  })
  render(<App />)
  return {
    fetch, delayedA,
    beginFinish(transport: 'SSE' | 'polling') {
      finishingA = true
      const source = ControlledEventSource.instances[0]
      if (transport === 'SSE') source.complete()
      else source.onerror?.()
    },
    releaseA() {
      finishedA = true
      delayedA.splice(0).forEach(resolve => resolve(Response.json(completedA)))
    },
  }
}

it.each(['SSE', 'polling'] as const)('late %s completion updates A history without leaving B or erasing its interview question', async transport => {
  const control = setup(false)
  await screen.findByText('甲的笔记')
  fireEvent.click(within(screen.getByRole('navigation', {name: '创作者功能导航'})).getByRole('button', {name: '受众模拟'}))
  fireEvent.click(screen.getByRole('tab', {name: /创作级/}))
  await waitFor(() => expect(screen.getAllByRole('option', {name: '模拟读者'})).toHaveLength(3))
  fireEvent.change(screen.getByLabelText('模拟选题'), {target: {value: 'topic-a'}})
  fireEvent.change(screen.getByLabelText('第 1 位模拟粉丝'), {target: {value: 'reader'}})
  fireEvent.click(screen.getByRole('button', {name: '开始模拟'}))
  await waitFor(() => expect(ControlledEventSource.instances).toHaveLength(1))
  const historyA = screen.getByRole('button', {name: /受众模拟 正在试读/})
  await act(async () => control.beginFinish(transport))
  await waitFor(() => expect(control.delayedA.length).toBeGreaterThan(0))
  const historyB = screen.getByRole('button', {name: /受众模拟 已完成/})
  fireEvent.click(historyB)
  const question = await screen.findByLabelText('作者追问')
  fireEvent.change(question, {target: {value: 'B的哪句话让你误解了？我还没有发送。'}})
  await act(async () => control.releaseA())
  await waitFor(() => expect(historyA).toHaveTextContent('已完成'))
  const room = screen.getByRole('region', {name: '读者试读群聊'})
  expect(within(room).getByText('run-b的内容')).toBeVisible()
  expect(within(room).getByText('run-b的历史发言')).toBeVisible()
  expect(within(room).queryByText('A后来完成的发言')).not.toBeInTheDocument()
  expect(historyB).toHaveClass('active')
  expect(historyA).not.toHaveClass('active')
  expect(screen.getByLabelText('作者追问')).toBe(question)
  expect(question).toHaveValue('B的哪句话让你误解了？我还没有发送。')
  expect(control.fetch.mock.calls.filter(([url, init]) => String(url).endsWith('/interviews') && init?.method === 'POST')).toHaveLength(0)
})

it.each(['SSE', 'polling'] as const)('late %s completion from the previous account cannot replace the current interview', async transport => {
  const control = setup(true)
  await screen.findByText('甲的笔记')
  fireEvent.click(within(screen.getByRole('navigation', {name: '创作者功能导航'})).getByRole('button', {name: '受众模拟'}))
  fireEvent.click(screen.getByRole('tab', {name: /创作级/}))
  await waitFor(() => expect(screen.getAllByRole('option', {name: '模拟读者'})).toHaveLength(3))
  fireEvent.change(screen.getByLabelText('模拟选题'), {target: {value: 'topic-a'}})
  fireEvent.change(screen.getByLabelText('第 1 位模拟粉丝'), {target: {value: 'reader'}})
  fireEvent.click(screen.getByRole('button', {name: '开始模拟'}))
  await waitFor(() => expect(ControlledEventSource.instances).toHaveLength(1))
  await act(async () => control.beginFinish(transport))
  await waitFor(() => expect(control.delayedA.length).toBeGreaterThan(0))
  fireEvent.change(screen.getByLabelText('当前账号档案'), {target: {value: 'account-1'}})
  await screen.findByText('乙的笔记')
  fireEvent.click(within(screen.getByRole('navigation', {name: '创作者功能导航'})).getByRole('button', {name: '受众模拟'}))
  fireEvent.click(screen.getByRole('tab', {name: /创作级/}))
  fireEvent.click(await screen.findByRole('button', {name: /受众模拟 已完成/}))
  const question = await screen.findByLabelText('作者追问')
  fireEvent.change(question, {target: {value: '请继续分析乙账号这篇内容。'}})
  await act(async () => control.releaseA())
  expect(screen.getByLabelText('当前账号档案')).toHaveValue('account-1')
  expect(screen.getByLabelText('作者追问')).toBe(question)
  expect(question).toHaveValue('请继续分析乙账号这篇内容。')
  expect(screen.getByRole('region', {name: '读者试读群聊'})).toHaveTextContent('run-b的内容')
  expect(screen.queryByText('A后来完成的发言')).not.toBeInTheDocument()
  expect(screen.getAllByRole('button', {name: /受众模拟 已完成/})).toHaveLength(1)
})
