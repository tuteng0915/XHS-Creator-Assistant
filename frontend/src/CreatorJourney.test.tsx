import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'

afterEach(() => { cleanup(); vi.restoreAllMocks(); window.history.replaceState({}, '', '/') })

function setup() {
  window.history.replaceState({}, '', '/')
  const workspaces = ['甲', '乙'].map((name, index) => ({ id: `account-${index}`, name,
    accountPositioning: '', positioningVersion: 1, currentTopicId: null, createdAt: '', updatedAt: '' }))
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    if (init?.method === 'POST' && url.endsWith('/analysis-runs')) {
      return new Response(JSON.stringify({ detail: '测试停止于执行前' }), { status: 422 })
    }
    if (url === '/api/workspaces') return Response.json(workspaces)
    const workspace = workspaces.find((item) => url.startsWith(`/api/workspaces/${item.id}`))
    if (!workspace) throw new Error(`Unexpected ${url}`)
    if (url === `/api/workspaces/${workspace.id}`) return Response.json(workspace)
    if (url.endsWith('/input-assets')) return Response.json([{
      id: `profile-${workspace.id}`, workspaceId: workspace.id, type: 'xhs_creator_profile',
      name: workspace.name, createdAt: '', updatedAt: '', content: JSON.stringify({
        schemaVersion: 'xhs-creator-profile/v1', creator: { displayName: workspace.name },
        notes: [{ noteId: `note-${workspace.id}`, title: `${workspace.name}的笔记`, desc: `${workspace.name}的正文`, comments: [] }],
      }),
    }])
    return Response.json([])
  })
  render(<App />)
  return fetchMock
}

describe('public creator journey', () => {
  it('switches accounts without displaying the previous accounts notes', async () => {
    setup()
    await screen.findByText('甲的笔记')
    fireEvent.click(screen.getByRole('button', { name: /我的笔记/ }))
    fireEvent.change(screen.getByLabelText('当前账号档案'), { target: { value: 'account-1' } })
    await screen.findByText('乙的笔记')
    expect(screen.queryByText('甲的笔记')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Skills' })).not.toBeInTheDocument()
    expect(screen.queryByText('热点分析')).not.toBeInTheDocument()
  })

  it('uses the current profile, live model and ten-note default for diagnosis', async () => {
    const fetchMock = setup()
    await screen.findByText('甲的笔记')
    fireEvent.click(screen.getByRole('button', { name: /账号诊断/ }))
    fireEvent.click(screen.getByRole('button', { name: '开始分析' }))
    await screen.findByText(/测试停止于执行前/)
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([url, init]) => String(url).endsWith('/analysis-runs') && init?.method === 'POST')
      expect(call).toBeDefined()
      expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({
        xhsCreatorProfileInputAssetId: 'profile-account-0', analysisScope: 'recent_10', mode: 'live',
      })
    })
  })
})
