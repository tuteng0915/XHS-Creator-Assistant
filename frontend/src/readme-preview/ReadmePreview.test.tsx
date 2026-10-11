import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, it } from 'vitest'
import * as api from '../api'
import { contentCollaborationApi } from '../contentCollaboration'
import { panelInterviewApi } from '../panelInterview'
import { ReadmePreview } from './ReadmePreview'
import { installPreviewApi } from './installPreviewApi'
import { accountRun, notes, topic, workspace } from './fixtures'

const originalFetch = window.fetch
const groups = [...Object.values(api), contentCollaborationApi, panelInterviewApi]
  .filter(group => !!group && typeof group === 'object')
const originals = groups.map(group => ({ group, values: { ...group } }))

beforeEach(() => installPreviewApi())
afterEach(() => {
  cleanup()
  window.fetch = originalFetch
  for (const { group, values } of originals) Object.assign(group, values)
  window.history.replaceState(null, '', '/')
})

it('blocks all network calls and unstubbed operations without contacting a backend', async () => {
  await expect(window.fetch('/api/workspaces')).rejects.toThrow('不连接后端')
  await expect(api.workspaceApi.list()).rejects.toThrow('不连接后端')
  await expect(contentCollaborationApi.send(workspace.id, 'session', '生成文案', 'writing', 'key')).rejects.toThrow('不连接后端')
  expect(await api.analysisRunApi.get(accountRun.id)).toEqual(accountRun)
  const updated = await api.topicApi.update(topic.id, { title: '仅内存修改', expectedUpdatedAt: topic.updatedAt })
  expect(updated.title).toBe('仅内存修改')
  expect(topic.title).not.toBe('仅内存修改')
})

it('renders the shipped account report with exact fictional quotes and body structure', () => {
  window.history.replaceState(null, '', '/readme-preview.html?view=account')
  render(<ReadmePreview />)
  expect(screen.getByRole('heading', { name: '账号诊断' })).toBeVisible()
  expect(screen.getByText(`“${notes[0].title}”`)).toBeVisible()
  expect(screen.getByText('“每天只写一句。”')).toBeVisible()
  expect(screen.getByText('表达结构 · 从卡住到迈出第一步')).toBeVisible()
  expect(screen.getByText('写出小变化，也保留真实的限度：“房间没有突然焕然一新，但我终于不再害怕开始。”')).toBeVisible()
})

it('renders the shipped canvas with three selected references and one unadopted suggestion', async () => {
  window.history.replaceState(null, '', '/readme-preview.html?view=writing')
  render(<ReadmePreview />)
  expect(await screen.findByRole('heading', { name: '从那个周日晚上写起' })).toBeVisible()
  await waitFor(() => expect(screen.getByRole('button', { name: /^原笔记 · / })).toBeVisible())
  expect(screen.getByRole('button', { name: /^账号分析 · / })).toBeVisible()
  expect(screen.getByRole('button', { name: /^受众分析 · / })).toBeVisible()
  expect(screen.getByRole('button', { name: '预览并编辑这条建议' })).toBeVisible()
  expect(screen.getByLabelText('创作正文')).toHaveValue(topic.body)
  expect(screen.getByText(/周日晚，计划表列了很长：读书、运动、整理照片。/)).toBeVisible()
  expect(screen.queryByText(/周日晚九点|读完一本|把它划掉/)).not.toBeInTheDocument()
})

it('renders three distinct fictional readers in the shipped discussion room', async () => {
  window.history.replaceState(null, '', '/readme-preview.html?view=panel')
  render(<ReadmePreview />)
  expect(screen.getByText('3 位读者')).toBeVisible()
  expect(within(screen.getByRole('log', { name: '试读发言' })).getByText(/十分钟到了就停，我反而有点不确定/)).toBeVisible()
  expect(screen.getByText(/如果第二天没做/)).toBeVisible()
  expect(screen.queryByText(/这次未生成可用的修改建议/)).not.toBeInTheDocument()
  expect(screen.getByRole('heading', { name: '补清计时结束后的选择' })).toBeVisible()
  expect(screen.getByText('如果十分钟到了还想继续读，你会停下来还是继续？补一句你自己的选择。')).toBeVisible()
  fireEvent.click(screen.getByText('查看依据与原文'))
  expect(screen.getByText('关心具体方法的人 · 试读顾虑记录（非公开原话）')).toBeVisible()
  expect(document.querySelector('.feedback-original mark')).toHaveTextContent('手机计时响了，就把书签放进去。')
  await waitFor(() => expect(screen.getByRole('log', { name: '试读发言' })).toBeVisible())
})
