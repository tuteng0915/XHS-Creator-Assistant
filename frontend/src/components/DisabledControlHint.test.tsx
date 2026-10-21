import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { DisabledControlHint } from './DisabledControlHint'

afterEach(cleanup)

it('removes the hint and extra focus stop when the control becomes enabled', () => {
  const { rerender } = render(<DisabledControlHint reason="正在爬取" label="添加暂不可用"><button disabled>添加</button></DisabledControlHint>)
  fireEvent.mouseEnter(screen.getByRole('group'))
  expect(screen.getByRole('tooltip')).toHaveTextContent('正在爬取')

  rerender(<DisabledControlHint reason="正在整理笔记" label="添加暂不可用"><button disabled>添加</button></DisabledControlHint>)
  expect(screen.getByRole('tooltip')).toHaveTextContent('正在整理笔记')

  rerender(<DisabledControlHint label="添加暂不可用"><button>添加</button></DisabledControlHint>)
  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  expect(screen.queryByRole('group')).not.toBeInTheDocument()
  expect(screen.getByRole('button')).toBeEnabled()
  expect(screen.getByRole('button').parentElement).not.toHaveAttribute('tabindex')
})
