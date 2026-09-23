import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { CreatorDraftEditor } from './CreatorDraftEditor'

it('edits text fields while preserving nested structure and metadata', () => {
  const original = { brief: { topicTitle: '原题', argumentPath: ['第一点'] }, confidence: 0.8 }
  const onChange = vi.fn()
  render(<CreatorDraftEditor value={JSON.stringify(original)} onChange={onChange} />)
  fireEvent.change(screen.getByLabelText('选题标题'), { target: { value: '修改后的标题' } })
  expect(JSON.parse(onChange.mock.calls[0][0])).toEqual({
    brief: { topicTitle: '修改后的标题', argumentPath: ['第一点'] }, confidence: 0.8,
  })
  expect(original.brief.topicTitle).toBe('原题')
})
