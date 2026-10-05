import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { CreatorEditSnapshot } from './CreatorEditSnapshot'

afterEach(cleanup)
const snapshot = {schemaVersion:'creator-edit/v1',workspaceId:'w',topicId:'t',
  before:{title:'原题',body:'原文\n\n🌱',updatedAt:'v1'},
  suggested:{title:'新题',body:'新正文'},after:{title:'新题',body:'新正文',updatedAt:'v2'}}
const props = {workspaceId:'w',topicId:'t'}

it('starts collapsed and shows frozen before and applied text, without duplicate suggestion', () => {
  const {container} = render(<CreatorEditSnapshot {...props} metadata={{canvasApplyStatus:'applied',canvasEditSnapshot:snapshot}} />)
  const details = container.querySelector('details')!
  expect(details.open).toBe(false)
  fireEvent.click(screen.getByText('当时已应用 · 查看修改'))
  expect(details.open).toBe(true)
  expect(within(screen.getByRole('region',{name:'修改前'})).getByText('原文 🌱')).toBeInTheDocument()
  expect(screen.getByRole('region',{name:'修改前'}).querySelector('p')?.textContent).toBe('原文\n\n🌱')
  expect(screen.getAllByText('新正文')).toHaveLength(1)
  expect(screen.getByText('这是该次修改的历史记录，不代表当前稿件。')).toBeInTheDocument()
  expect(screen.queryByRole('button')).not.toBeInTheDocument()
})

it('does not present a conflicted suggestion as an applied result', () => {
  render(<CreatorEditSnapshot {...props} metadata={{canvasApplyStatus:'conflict',canvasEditSnapshot:snapshot}} />)
  fireEvent.click(screen.getByText('未应用 · 查看原稿与建议'))
  expect(screen.getByRole('region',{name:'AI 建议（未应用）'})).toHaveTextContent('新正文')
  expect(screen.queryByRole('region',{name:'当时应用后'})).not.toBeInTheDocument()
})

it('keeps suggested and actually applied text distinct if they differ', () => {
  render(<CreatorEditSnapshot {...props} metadata={{canvasApplyStatus:'applied',canvasEditSnapshot:{...snapshot,after:{title:'落库标题',body:'落库正文'}}}} />)
  fireEvent.click(screen.getByText('当时已应用 · 查看修改'))
  expect(screen.getByRole('region',{name:'当时应用后'})).toHaveTextContent('落库正文')
  expect(screen.getByRole('region',{name:'当时的 AI 建议'})).toHaveTextContent('新正文')
})

it('does not invent before or applied text for legacy messages', () => {
  render(<CreatorEditSnapshot {...props} metadata={{canvasApplyStatus:'applied',canvasUpdate:{title:'旧建议',body:'旧文'}}} />)
  fireEvent.click(screen.getByText('当时已应用 · 查看修改'))
  expect(screen.getByText('此记录未保存可读的修改前快照。')).toBeInTheDocument()
  expect(screen.getByText('此记录未保存可读的应用后快照。')).toBeInTheDocument()
  expect(screen.getByRole('region',{name:'当时的 AI 建议'})).toHaveTextContent('旧文')
})

it('handles malformed text without stringifying objects or rendering HTML', () => {
  render(<CreatorEditSnapshot {...props} metadata={{canvasApplyStatus:'conflict',canvasEditSnapshot:{...snapshot,before:[],suggested:{title:'<img src=x>',body:{bad:true}},after:null}}} />)
  fireEvent.click(screen.getByText('未应用 · 查看原稿与建议'))
  expect(screen.getByText('此记录未保存可读的建议正文。')).toBeInTheDocument()
  expect(document.querySelector('img')).toBeNull()
  expect(document.body).not.toHaveTextContent('[object Object]')
})

it('hides snapshots belonging to another account or topic, including legacy fallback', () => {
  const {rerender}=render(<CreatorEditSnapshot {...props} metadata={{canvasApplyStatus:'applied',canvasEditSnapshot:{...snapshot,workspaceId:'other'},canvasUpdate:{title:'不可回退',body:'私有'}}} />)
  expect(screen.getByText('此修改记录与当前选题不符，未展示内容。')).toBeInTheDocument()
  expect(document.body).not.toHaveTextContent('私有')
  rerender(<CreatorEditSnapshot {...props} metadata={{canvasApplyStatus:'applied',canvasEditSnapshot:{...snapshot,topicId:'other'}}} />)
  expect(document.body).not.toHaveTextContent('原文')
})

it('does not show an edit receipt for discussion, model failure or fact checks', () => {
  const {container,rerender}=render(<CreatorEditSnapshot {...props} metadata={{}} />)
  expect(container).toBeEmptyDOMElement()
  rerender(<CreatorEditSnapshot {...props} metadata={{canvasApplyStatus:'needs_confirmation',canvasEditSnapshot:snapshot}} />)
  expect(container).toBeEmptyDOMElement()
  rerender(<CreatorEditSnapshot {...props} metadata={{status:'failed',canvasApplyStatus:'applied',canvasEditSnapshot:snapshot}} />)
  expect(container).toBeEmptyDOMElement()
})
