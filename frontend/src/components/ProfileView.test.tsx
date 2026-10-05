import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { ProfileView } from './StageResultViews'
import type { Observations } from './AccountPortraitView'

afterEach(cleanup)

const data = {
  pillars: ['生活记录'],
  contrast: {
    winners: [{ title: '模型指定的冠军', metric: '收藏999；分享None' }],
    losers: [{ title: '模型指定的低表现', metric: '赞-1' }],
    winFactors: ['收藏率超过30%所以推荐更多'],
    loseFactors: ['分享率低于15%所以内容差'],
    takeaways: ['参考日常记录的开头，下次先讲一个具体场景。'],
  },
}
const observations: Observations = {
  schemaVersion: 'xhs-account-observations/v1',
  coverage: { selectedCount: 2, missingDateCount: 2, capturedCommentCount: 0, missingMetricCounts: { shares: 1 } },
  notes: [
    { noteId: 'first', title: '同名笔记', metrics: { liked: 10, collected: 3, shares: null } },
    { noteId: 'second', title: '同名笔记', metrics: { liked: 20, collected: 5, shares: 0 } },
  ],
}

it('uses frozen counts instead of the model contrast even when more content is expanded', () => {
  const original = JSON.stringify({ data, observations })
  render(<ProfileView data={data} observations={observations} />)
  expect(screen.getByText('更多内容归纳').closest('details')).toHaveAttribute('open')
  expect(screen.getByRole('status')).toHaveTextContent('点赞数据 2 / 2 条 · 中位数 15')
  expect(screen.queryByText(/None|999|30%|15%|模型指定/)).not.toBeInTheDocument()
  expect(screen.queryByText(/高表现 vs 低表现/)).not.toBeInTheDocument()
  expect(screen.getByText('生活记录')).toBeInTheDocument()
  expect(screen.getByText(data.contrast.takeaways[0])).toBeInTheDocument()
  fireEvent.change(screen.getByRole('combobox', { name: '比较指标' }), { target: { value: 'shares' } })
  expect(screen.getByRole('status')).toHaveTextContent('分享数据 1 / 2 条 · 中位数 0 · 1 条未获取')
  expect(JSON.stringify({ data, observations })).toBe(original)
})

it('opens duplicate titles by frozen note ID without inferring a link from the model title', () => {
  render(<ProfileView data={data} observations={observations} notes={[
    { noteId: 'first', title: '同名笔记', desc: '第一份冻结正文', metrics: { liked: 10 }, comments: [] },
    { noteId: 'second', title: '同名笔记', desc: '第二份冻结正文', metrics: { liked: 20 }, comments: [] },
  ]} />)
  const buttons = screen.getAllByRole('button', { name: '同名笔记' })
  fireEvent.click(buttons[0])
  fireEvent.click(screen.getByRole('button', { name: /同名笔记 赞 20/ }))
  expect(screen.getByText('第二份冻结正文')).toBeInTheDocument()
  expect(screen.queryByText('第一份冻结正文')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '关闭' }))
  fireEvent.click(buttons[1])
  fireEvent.click(screen.getByRole('button', { name: /同名笔记 赞 10/ }))
  expect(screen.getByText('第一份冻结正文')).toBeInTheDocument()
  expect(screen.queryByText('第二份冻结正文')).not.toBeInTheDocument()
})

it('does not fall back to model metrics when the structured snapshot is empty', () => {
  render(<ProfileView data={data} observations={{ ...observations, notes: [] }} />)
  expect(screen.getByRole('status')).toHaveTextContent('本次未获取点赞数据')
  expect(screen.queryByText(/None|999|30%|15%|模型指定/)).not.toBeInTheDocument()
})

it('keeps reports without observations readable without rewriting their saved content', () => {
  const original = JSON.stringify(data)
  render(<ProfileView data={data} />)
  expect(screen.getByText('模型指定的冠军')).toBeInTheDocument()
  expect(screen.getByText(data.contrast.winFactors[0])).toBeInTheDocument()
  expect(screen.getByText(data.contrast.takeaways[0])).toBeInTheDocument()
  expect(screen.queryByRole('combobox', { name: '比较指标' })).not.toBeInTheDocument()
  expect(JSON.stringify(data)).toBe(original)
})

it('does not leave an empty advice heading when contrast is absent', () => {
  render(<ProfileView data={{ pillars: ['生活记录'] }} observations={observations} />)
  expect(screen.queryByText('可尝试的写法：')).not.toBeInTheDocument()
  expect(screen.getByText('生活记录')).toBeInTheDocument()
})
