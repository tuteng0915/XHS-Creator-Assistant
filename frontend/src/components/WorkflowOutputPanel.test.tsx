import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import {
  WorkflowOutputPanel,
  type StageView,
  type WorkflowOutputKind,
} from './WorkflowOutputPanel'

function renderPanel(
  views: StageView[],
  outputKind: WorkflowOutputKind = 'analysis',
) {
  const renderStageResult = vi.fn((stage: StageView) =>
    stage.result ? <div>结果：{String(stage.result)}</div> : null,
  )
  render(
    <WorkflowOutputPanel
      targetTab="account"
      views={views}
      outputKind={outputKind}
      runError=""
      renderStageResult={renderStageResult}
    />,
  )
  return { renderStageResult }
}

describe('WorkflowOutputPanel', () => {
  it('renders empty analysis state with product copy', () => {
    renderPanel([])

    expect(screen.getByText('账号诊断待运行')).toBeInTheDocument()
    expect(screen.getByText('运行后结果会渐进渲染，并保存到分析结果。')).toBeInTheDocument()
  })

  it('renders empty simulation state separately from analysis copy', () => {
    renderPanel([], 'simulation')

    expect(screen.getByText('受众模拟待运行')).toBeInTheDocument()
  })

  it('shows a clearly unfinished reading preview with progress', () => {
    renderPanel([{
      key: 'profile', n: '①', title: '账号画像', status: 'running',
      progress: {phase: 'reading', status: 'running', completed: 2, total: 3,
        preview: '《第一篇》：用动作交代过程。\n《第二篇》：并列两种选择。'},
    }])
    expect(screen.getByText('逐篇细读 · 2/3')).toBeInTheDocument()
    expect(screen.getByText('阶段阅读摘要，完整报告仍在生成')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('《第一篇》')
    expect(screen.getByRole('status')).toHaveTextContent('《第二篇》')
    expect(screen.queryByText('已完成')).not.toBeInTheDocument()
  })

  it('renders stage status, errors, loading state, and delegated results', () => {
    const { renderStageResult } = renderPanel([
      {
        key: 'profile',
        n: '①',
        title: '主页诊断',
        status: 'completed',
        result: '完成',
      },
      {
        key: 'pain_points',
        n: '②',
        title: '痛点归类',
        status: 'running',
      },
      {
        key: 'topics',
        n: '③',
        title: '选题生成',
        status: 'failed',
        error: '模型返回格式错误',
      },
    ])

    expect(screen.getByText('主页诊断')).toBeInTheDocument()
    expect(screen.getByText('已完成')).toBeInTheDocument()
    expect(screen.getByText('结果：完成')).toBeInTheDocument()
    expect(screen.getAllByText('分析中…').length).toBeGreaterThan(0)
    expect(screen.getByText('失败')).toBeInTheDocument()
    expect(screen.getByText('模型返回格式错误')).toBeInTheDocument()
    expect(renderStageResult).toHaveBeenCalledTimes(3)
  })
})
