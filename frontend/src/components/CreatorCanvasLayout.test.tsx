import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { Topic } from '../types'
import { CreatorCanvasPage } from './CreatorCanvasPage'

vi.mock('./ContentCollaborationChat', async () => {
  const { useEffect, useRef, useState } = await import('react')
  return { ContentCollaborationChat: ({composeIntent, onPreview}: {
    composeIntent?: {id: string; text: string} | null
    onPreview: (candidate: {kind: 'copy_option'; title: string; body: string}) => void
  }) => {
    const [text, setText] = useState('')
    const composer = useRef<HTMLTextAreaElement>(null)
    useEffect(() => {if (composeIntent) {setText(composeIntent.text); composer.current?.focus()}}, [composeIntent])
    return <section aria-label="创作对话" className="canvas-chat">
      <div className="collaboration-messages" data-testid="transcript">已有的对话</div>
      <textarea ref={composer} aria-label="给创作助手的消息" value={text} onChange={event => setText(event.target.value)} />
      <button onClick={() => onPreview({kind:'copy_option',title:'建议开头',body:'从一个具体的决定开始。'})}>预览建议</button>
    </section>
  }}
})
vi.mock('./PanelEditWorkspace', () => ({PanelEditWorkspace: () => null}))

const topic: Topic = {id:'topic',workspaceId:'w',title:'原题',body:'原文第一段。',angle:'',associatedPainPoint:'',whyItFits:'',generatedSnapshot:{},sourceAnalysisRunId:null,sourceWorkflow:'manual',status:'candidate',createdAt:'v1',updatedAt:'v1'}
const props = {workspaceId:'w',topic,topics:[topic],onSelect:vi.fn(),onUpdated:vi.fn()}
let matches = false
let resize: (() => void) | undefined
beforeEach(() => {
  matches = false
  resize = undefined
  vi.stubGlobal('matchMedia', vi.fn(() => ({get matches() {return matches}, addEventListener: (_name: string, listener: () => void) => {resize = listener}, removeEventListener: vi.fn()})))
})
afterEach(() => {cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals()})

it('places dialogue before the draft in DOM order and resizes the left dialogue with arrow keys', () => {
  render(<CreatorCanvasPage {...props} />)
  const dialogue = screen.getByLabelText('创作对话')
  const draft = screen.getByLabelText('创作正文')
  expect(dialogue.compareDocumentPosition(draft) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
  const divider = screen.getByRole('separator', {name:'调整对话和稿件宽度'})
  expect(divider).toHaveAttribute('aria-valuenow', '44')
  fireEvent.keyDown(divider, {key:'ArrowRight'})
  expect(divider).toHaveAttribute('aria-valuetext', '对话 49% · 稿件 51%')
  fireEvent.keyDown(divider, {key:'Home'})
  fireEvent.keyDown(divider, {key:'ArrowLeft'})
  expect(divider).toHaveAttribute('aria-valuenow', '30')
  fireEvent.keyDown(divider, {key:'End'})
  fireEvent.keyDown(divider, {key:'ArrowRight'})
  expect(divider).toHaveAttribute('aria-valuenow', '70')
})

it('uses the same left-pane percentage for pointer resizing and clamps both ends', () => {
  vi.stubGlobal('PointerEvent', MouseEvent)
  render(<CreatorCanvasPage {...props} />)
  const divider = screen.getByRole('separator')
  divider.setPointerCapture = vi.fn()
  divider.hasPointerCapture = vi.fn(() => true)
  divider.releasePointerCapture = vi.fn()
  vi.spyOn(divider.parentElement!, 'getBoundingClientRect').mockReturnValue({left:100,width:1000} as DOMRect)
  fireEvent.pointerDown(divider, {clientX:540})
  fireEvent.pointerMove(divider, {clientX:700})
  expect(divider).toHaveAttribute('aria-valuenow', '60')
  fireEvent.pointerMove(divider, {clientX:1400})
  expect(divider).toHaveAttribute('aria-valuenow', '70')
  fireEvent.pointerMove(divider, {clientX:100})
  expect(divider).toHaveAttribute('aria-valuenow', '30')
  fireEvent.pointerCancel(divider)
  expect(divider.releasePointerCapture).toHaveBeenCalled()
})

it('preserves both inputs and scroll position while narrow-screen tabs hide only the inactive pane', () => {
  matches = true
  render(<CreatorCanvasPage {...props} />)
  const composer = screen.getByLabelText('给创作助手的消息')
  const editor = screen.getByLabelText('创作正文')
  const transcript = screen.getByTestId('transcript')
  fireEvent.change(composer, {target:{value:'还没发出的要求'}})
  transcript.scrollTop = 145
  expect(editor).not.toBeVisible()
  expect(screen.queryByRole('separator')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('tab', {name:'稿件'}))
  expect(editor).toBeVisible()
  expect(composer).not.toBeVisible()
  fireEvent.change(editor, {target:{value:'还没保存的稿件'}})
  editor.scrollTop = 63
  fireEvent.click(screen.getByRole('tab', {name:'对话'}))
  expect(screen.getByLabelText('给创作助手的消息')).toBe(composer)
  expect(composer).toHaveValue('还没发出的要求')
  expect(transcript.scrollTop).toBe(145)
  fireEvent.keyDown(screen.getByRole('tab', {name:'对话'}), {key:'ArrowRight'})
  expect(screen.getByRole('tab', {name:'稿件'})).toHaveFocus()
  expect(editor).toHaveValue('还没保存的稿件')
  expect(editor.scrollTop).toBe(63)
  expect(screen.getByTitle('有未保存修改')).toBeInTheDocument()
})

it('opens dialogue for a local rewrite and opens the draft before focusing a candidate preview', () => {
  matches = true
  render(<CreatorCanvasPage {...props} />)
  fireEvent.click(screen.getByRole('tab', {name:'稿件'}))
  const editor = screen.getByLabelText('创作正文') as HTMLTextAreaElement
  editor.focus(); editor.setSelectionRange(0, 2); fireEvent.select(editor)
  fireEvent.click(screen.getByRole('button', {name:'更简洁'}))
  expect(screen.getByRole('tab', {name:'对话'})).toHaveAttribute('aria-selected', 'true')
  expect(screen.getByLabelText('给创作助手的消息')).toHaveFocus()
  fireEvent.click(screen.getByRole('button', {name:'预览建议'}))
  expect(screen.getByRole('tab', {name:'稿件'})).toHaveAttribute('aria-selected', 'true')
  expect(screen.getByLabelText('写作建议预览')).toBeVisible()
  expect(screen.getByLabelText('写作建议预览')).toHaveFocus()
  expect(editor).toHaveValue(topic.body)
  fireEvent.click(screen.getByRole('button', {name:'确认放入画布'}))
  expect(editor).toHaveValue('原文第一段。\n\n从一个具体的决定开始。')
  expect(editor).toHaveFocus()
  expect(screen.getByText('有未保存修改')).toBeInTheDocument()
})

it('keeps the focused draft visible when resizing from desktop to narrow layout', () => {
  render(<CreatorCanvasPage {...props} />)
  const editor = screen.getByLabelText('创作正文')
  editor.focus()
  act(() => {matches = true; resize?.()})
  expect(screen.getByRole('tab', {name:'稿件'})).toHaveAttribute('aria-selected', 'true')
  expect(editor).toBeVisible()
  expect(editor).toHaveFocus()
  act(() => {matches = false; resize?.()})
  expect(screen.getByLabelText('给创作助手的消息')).toBeVisible()
  expect(editor).toBeVisible()
})
