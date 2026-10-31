import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, render } from '@testing-library/react'
import { CreatorDiagnosisPage } from './CreatorDiagnosisPage'
import { pageGuides, workflowGuide } from './guideSteps'
import { findGuideTarget } from './guideTargets'
import type { ActivePage } from './WorkspaceShell'
import type { TextInputAsset } from '../types'

beforeEach(() => { vi.spyOn(HTMLElement.prototype, 'getClientRects').mockReturnValue([{}] as unknown as DOMRectList) })
afterEach(() => { cleanup(); vi.restoreAllMocks() })
const visible = (page: ActivePage) => (pageGuides[page] || []).filter(step => findGuideTarget(step.target))

it('introduces import in the real empty diagnosis page and range/run after notes exist', () => {
  const props = {scope: 'recent_10' as const, onScopeChange: vi.fn(), running: false, onRun: vi.fn(), onImport: vi.fn(), onOpenHistory: vi.fn(), children: null}
  const {rerender} = render(<CreatorDiagnosisPage {...props} />)
  expect(visible('account-diagnosis').map(step => step.title)).toEqual(['先导入笔记', '回看诊断历史'])
  const profile = {content: JSON.stringify({notes: [{noteId: 'n', title: '一篇笔记', comments: [], metrics: {}}]})} as TextInputAsset
  rerender(<CreatorDiagnosisPage {...props} profile={profile} running />)
  expect(visible('account-diagnosis').map(step => step.title)).toEqual(['选择分析范围', '开始诊断', '回看诊断历史'])
})

it('explains only the active simulation target and uses dropdown terminology', () => {
  const {rerender} = render(<div className="simulation-account-range" />)
  expect(visible('simulations').map(step => step.title)).toEqual(['选择账号笔记'])
  rerender(<div className="simulation-note-target" />)
  expect(visible('simulations').map(step => step.title)).toEqual(['选择已发布笔记'])
  rerender(<><label className="simulation-target"><select /></label><fieldset className="simulation-reader-controls" /></>)
  expect(visible('simulations').map(step => step.title)).toEqual(['选择创作内容', '确认参与读者'])
  expect(visible('simulations')[1].description).toContain('下拉框')
})

it('distinguishes first-draft adoption from revision and introduces adoption before save', () => {
  const {rerender} = render(<div className="canvas-candidate-preview is-first-draft"><div className="canvas-candidate-preview-actions" /></div>)
  expect(visible('drafts').map(step => step.title)).toEqual(['采用这份首稿'])
  expect(visible('drafts')[0].description).toContain('采用并保存')
  rerender(<><div className="canvas-candidate-preview"><div className="canvas-candidate-preview-actions" /></div><div className="canvas-editor"><div className="save-row" /></div></>)
  expect(visible('drafts').map(step => step.title)).toEqual(['采用这次修改', '保存与复制'])
  expect(visible('drafts')[0].description).toContain('再点击')
  expect(visible('drafts')[1].description).toContain('尚未保存')
})

it('points at actual topic actions instead of highlighting the whole page', () => {
  render(<main className="workspace-main"><div className="creator-topics-page"><section className="history-list"><button className="primary">新建选题</button><button className="topic-row">已有选题</button></section><div className="detail-actions"><button>继续创作</button></div></div></main>)
  const steps = visible('topics')
  expect(steps).toHaveLength(3)
  expect(steps.every(step => findGuideTarget(step.target)?.tagName !== 'MAIN')).toBe(true)
})

it('keeps the overview short and makes optional use clear', () => {
  expect(workflowGuide).toHaveLength(7)
  expect(workflowGuide.every(step => step.description.length <= 60)).toBe(true)
  expect(workflowGuide.at(-1)?.description).toContain('随时可以直接创作')
})
