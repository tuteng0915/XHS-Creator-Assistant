import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react'
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest'
import App from './App'
import {memoryStorage} from './test/storage'
import type {AnalysisRun} from './types'

class ControlledAnalysisEvents {
  static instances: ControlledAnalysisEvents[] = []
  private listeners = new Map<string, EventListener[]>()
  onerror: (() => void) | null = null
  closed = false

  constructor(readonly url: string) {ControlledAnalysisEvents.instances.push(this)}
  addEventListener(type: string, listener: EventListener) {
    this.listeners.set(type, [...(this.listeners.get(type) || []), listener])
  }
  close() {this.closed = true}
  finish(status: 'completed' | 'failed' = 'completed') {
    const type = status === 'completed' ? 'run.succeeded' : 'run.failed'
    const event = new MessageEvent(type, {data: JSON.stringify({
      eventId: 'diagnosis-finished', runId: 'current-run', runType: 'account_diagnosis',
      stageKey: null, status, sequence: 1, occurredAt: '2026-10-12T00:00:02Z',
      data: {eventType: type},
    })})
    this.listeners.get(type)?.forEach(listener => listener(event))
  }
}

beforeEach(() => {
  window.history.replaceState({}, '', '/')
  vi.stubGlobal('localStorage', memoryStorage())
  ControlledAnalysisEvents.instances = []
  vi.stubGlobal('EventSource', ControlledAnalysisEvents)
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  window.history.replaceState({}, '', '/')
})

function makeRun(id: string, workspaceId: string, result: string): AnalysisRun {
  return {
    id, workspaceId, workflowType: 'account_diagnosis', status: 'completed',
    userNotes: '', reviewStatus: 'unreviewed', inputSnapshot: {},
    stageResults: {profile: {profile: {pillars: [result]}}}, stageErrors: {}, modelMetadata: {},
    createdAt: '2026-10-11T00:00:00Z', startedAt: '2026-10-11T00:00:00Z',
    completedAt: '2026-10-11T00:00:01Z', updatedAt: '2026-10-11T00:00:01Z',
  }
}

function setup({emptyHistory = false}: {emptyHistory?: boolean} = {}) {
  const workspaces = ['甲', '乙'].map((name, index) => ({
    id: `account-${index}`, name, accountPositioning: '', positioningVersion: 1,
    currentTopicId: null, createdAt: '', updatedAt: '',
  }))
  const historicalRuns = [
    makeRun('old-account-0', 'account-0', '甲账号的历史诊断结论'),
    makeRun('old-account-1', 'account-1', '乙账号的历史诊断结论'),
  ]
  const runningRun: AnalysisRun = {
    ...makeRun('current-run', 'account-0', ''), status: 'running', stageResults: {},
    createdAt: '2026-10-12T00:00:00Z', completedAt: null,
  }
  let currentRun = runningRun
  let created = false
  const pendingCreations: Array<(response: Response) => void> = []
  const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    const method = init?.method || 'GET'
    if (url === '/api/workspaces') return Response.json(workspaces)
    if (url === '/api/workspaces/account-0/analysis-runs' && method === 'POST') {
      return new Promise<Response>(resolve => pendingCreations.push(resolve))
    }
    if (url === '/api/analysis-runs/current-run') return Response.json(currentRun)
    const historical = historicalRuns.find(run => url === `/api/analysis-runs/${run.id}`)
    if (historical) return Response.json(historical)
    const workspace = workspaces.find(row => url.startsWith(`/api/workspaces/${row.id}`))
    if (!workspace || method !== 'GET') throw new Error(`Unexpected request: ${method} ${url}`)
    if (url === `/api/workspaces/${workspace.id}`) return Response.json(workspace)
    if (url.endsWith('/input-assets')) return Response.json([{
      id: `profile-${workspace.id}`, workspaceId: workspace.id, type: 'xhs_creator_profile',
      name: workspace.name, createdAt: '', updatedAt: '',
      content: JSON.stringify({schemaVersion: 'xhs-creator-profile/v1', creator: {displayName: workspace.name},
        notes: [{noteId: `note-${workspace.id}`, title: `${workspace.name}的笔记`, desc: '账号笔记正文', comments: []}]}),
    }])
    if (url.endsWith('/analysis-runs')) return Response.json([
      ...(created && workspace.id === 'account-0' ? [currentRun] : []),
      ...(!emptyHistory ? historicalRuns.filter(run => run.workspaceId === workspace.id) : []),
      {...makeRun(`trend-${workspace.id}`, workspace.id, '不应展示的热点报告'), workflowType: 'trend_analysis'},
    ])
    return Response.json([])
  })
  render(<App />)
  return {
    fetch,
    pendingCreations,
    create() {
      created = true
      pendingCreations.shift()?.(Response.json(runningRun, {status: 201}))
    },
    rejectCreation() {
      pendingCreations.shift()?.(Response.json({detail: '本轮诊断创建失败'}, {status: 422}))
    },
    finish(status: 'completed' | 'failed' = 'completed') {
      currentRun = {
        ...runningRun, status, completedAt: '2026-10-12T00:00:02Z',
        stageResults: status === 'completed' ? {profile: {profile: {pillars: ['本轮全新的诊断结论']}}} : {},
        stageErrors: status === 'failed' ? {profile: '本轮诊断执行失败'} : {},
      }
      ControlledAnalysisEvents.instances[0].finish(status)
    },
  }
}

function navigate(name: string) {
  if (name === '诊断历史') {
    fireEvent.click(screen.getByRole('button', {name}))
    return
  }
  fireEvent.click(within(screen.getByRole('navigation', {name: '创作者功能导航'})).getByRole('button', {name}))
}

async function openDiagnosis() {
  await screen.findByText('甲的笔记')
  navigate('账号诊断')
  return screen.findByRole('region', {name: '诊断历史'})
}

function openOnlyHistoryRow(history: HTMLElement) {
  const list = within(history).getByText('◷ 诊断历史').closest('section') as HTMLElement
  fireEvent.click(within(list).getByRole('button'))
}

describe('diagnosis history on the public diagnosis page', () => {
  it('shows the shared account-only history below the controls without starting analysis', async () => {
    const control = setup()
    const history = await openDiagnosis()
    const start = screen.getByRole('button', {name: '开始分析'})
    expect(start.compareDocumentPosition(history) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(within(history).getAllByRole('button')).toHaveLength(1)
    expect(within(history).queryByText('热点分析')).not.toBeInTheDocument()
    expect(within(history).queryByText('未复盘')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', {name: '分析历史'})).not.toBeInTheDocument()
    expect(within(screen.getByRole('navigation')).queryByRole('button', {name: '诊断历史'})).not.toBeInTheDocument()
    expect(screen.getByRole('button', {name: '诊断历史'}).closest('.creator-page-head')).toBeTruthy()

    openOnlyHistoryRow(history)
    expect(await within(history).findByText('甲账号的历史诊断结论')).toBeVisible()
    expect(within(history).queryByText('未复盘')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', {name: '账号诊断', level: 1})).toBeVisible()
    expect(screen.getByRole('button', {name: '开始分析'})).toBeVisible()
    expect(screen.queryByText('在输出区打开')).not.toBeInTheDocument()
    expect(control.fetch.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(0)

    navigate('诊断历史')
    expect(await screen.findByText('甲账号的历史诊断结论')).toBeVisible()
    expect(screen.queryByText('未复盘')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', {name: '开始分析'})).not.toBeInTheDocument()
    navigate('账号诊断')
    expect(await screen.findByRole('region', {name: '诊断历史'})).toBeVisible()
    expect(screen.getByText('甲账号的历史诊断结论')).toBeVisible()
  })

  it('shows an empty history before the first run', async () => {
    setup({emptyHistory: true})
    const history = await openDiagnosis()
    expect(within(history).getByText('暂无诊断记录。完成分析后会保存在这里。')).toBeVisible()
    expect(screen.getByRole('button', {name: '开始分析'})).toBeEnabled()
  })

  it('hides history immediately, throughout execution and after completion, including a navigation round trip', async () => {
    const control = setup()
    const history = await openDiagnosis()
    openOnlyHistoryRow(history)
    await screen.findByText('甲账号的历史诊断结论')
    fireEvent.click(screen.getByRole('button', {name: '开始分析'}))

    expect(screen.queryByRole('region', {name: '诊断历史'})).not.toBeInTheDocument()
    expect(screen.queryByText('甲账号的历史诊断结论')).not.toBeInTheDocument()
    expect(screen.getByRole('button', {name: '正在分析…'})).toBeDisabled()
    await waitFor(() => expect(control.pendingCreations).toHaveLength(1))
    expect(ControlledAnalysisEvents.instances).toHaveLength(0)
    await act(async () => control.create())
    await waitFor(() => expect(ControlledAnalysisEvents.instances).toHaveLength(1))
    expect(screen.queryByRole('region', {name: '诊断历史'})).not.toBeInTheDocument()
    await act(async () => control.finish())
    expect(await screen.findByText('本轮全新的诊断结论')).toBeVisible()
    await waitFor(() => expect(screen.getByRole('button', {name: '开始分析'})).toBeEnabled())
    expect(screen.queryByRole('region', {name: '诊断历史'})).not.toBeInTheDocument()

    navigate('诊断历史')
    expect(await screen.findByRole('region', {name: '诊断历史'})).toBeVisible()
    expect(screen.getByText('甲账号的历史诊断结论')).toBeVisible()
    navigate('账号诊断')
    expect(screen.queryByRole('region', {name: '诊断历史'})).not.toBeInTheDocument()
    expect(screen.getByText('本轮全新的诊断结论')).toBeVisible()
    expect(screen.queryByText('甲账号的历史诊断结论')).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('当前账号档案'), {target: {value: 'account-1'}})
    await screen.findByText('乙的笔记')
    navigate('账号诊断')
    const nextHistory = await screen.findByRole('region', {name: '诊断历史'})
    expect(screen.queryByText('本轮全新的诊断结论')).not.toBeInTheDocument()
    expect(screen.queryByText('甲账号的历史诊断结论')).not.toBeInTheDocument()
    openOnlyHistoryRow(nextHistory)
    expect(await screen.findByText('乙账号的历史诊断结论')).toBeVisible()
  })

  it.each(['creation', 'execution'] as const)('keeps old history separate when the current %s fails', async failure => {
    const control = setup()
    const history = await openDiagnosis()
    openOnlyHistoryRow(history)
    await screen.findByText('甲账号的历史诊断结论')
    fireEvent.click(screen.getByRole('button', {name: '开始分析'}))
    await waitFor(() => expect(control.pendingCreations).toHaveLength(1))
    if (failure === 'creation') {
      await act(async () => control.rejectCreation())
      await screen.findByText(/本轮诊断创建失败/)
    } else {
      await act(async () => control.create())
      await waitFor(() => expect(ControlledAnalysisEvents.instances).toHaveLength(1))
      await act(async () => control.finish('failed'))
      await screen.findByText('本轮诊断执行失败')
    }
    await waitFor(() => expect(screen.getByRole('button', {name: '开始分析'})).toBeEnabled())
    expect(screen.queryByRole('region', {name: '诊断历史'})).not.toBeInTheDocument()
    expect(screen.queryByText('甲账号的历史诊断结论')).not.toBeInTheDocument()
    navigate('诊断历史')
    expect(await screen.findByText('甲账号的历史诊断结论')).toBeVisible()
    navigate('账号诊断')
    expect(screen.queryByRole('region', {name: '诊断历史'})).not.toBeInTheDocument()
    expect(screen.queryByText('甲账号的历史诊断结论')).not.toBeInTheDocument()
    expect(control.fetch.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1)
  })
})
