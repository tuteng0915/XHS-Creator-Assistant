import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { CreatorMaterialsPage } from './CreatorMaterialsPage'
import { CreatorDiagnosisPage } from './CreatorDiagnosisPage'
import { SimulationCategoryTabs } from './SimulationCategoryTabs'
import { pageGuides } from './guideSteps'

afterEach(cleanup)

it('places note help after the data date and shows one sentence on demand', () => {
  render(<CreatorMaterialsPage mediaAssets={[]} onImport={vi.fn()} onAnalyze={vi.fn()} />)
  const button = screen.getByRole('button', {name: '笔记页面说明'})
  expect(button.closest('.creator-note-meta')?.firstElementChild).toHaveClass('creator-note-data-time')
  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  fireEvent.click(button)
  expect(screen.getByRole('tooltip')).toHaveTextContent('查看已导入的图文、互动数据和评论，筛选笔记作为分析素材。')
  fireEvent.keyDown(document, {key: 'Escape'})
  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
})

it('puts diagnosis help in its heading without stealing the history guide target', () => {
  const run = vi.fn(), history = vi.fn()
  render(<CreatorDiagnosisPage scope="recent_10" running={false} onScopeChange={vi.fn()} onRun={run} onImport={vi.fn()} onOpenHistory={history}>{null}</CreatorDiagnosisPage>)
  const button = screen.getByRole('button', {name: '账号诊断说明'})
  expect(button.closest('h1')).toHaveTextContent('账号诊断')
  fireEvent.click(button)
  expect(screen.getByRole('tooltip')).toHaveTextContent('从选定笔记中了解账号的内容特点、历史表现、读者反馈和可改进的方向。')
  const step = pageGuides['account-diagnosis']!.find(step => step.title === '回看诊断历史')!
  expect(document.querySelector(step.target)).toBe(screen.getByRole('button', {name: '诊断历史'}))
  expect(run).not.toHaveBeenCalled()
  expect(history).not.toHaveBeenCalled()
})

it('puts simulation help beside the page title without changing category', () => {
  const change = vi.fn()
  render(<SimulationCategoryTabs value="account" runs={[]} onChange={change} />)
  const button = screen.getByRole('button', {name: '受众模拟说明'})
  expect(button.closest('h1')).toHaveTextContent('受众模拟')
  fireEvent.click(button)
  expect(screen.getByRole('tooltip')).toHaveTextContent('邀请模拟读者讨论账号方向、复盘已发布笔记或试读创作稿，了解不同视角的反馈。')
  expect(change).not.toHaveBeenCalled()
})
