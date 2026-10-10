import {cleanup, render, screen} from '@testing-library/react'
import {createHash} from 'node:crypto'
import {renderToStaticMarkup} from 'react-dom/server'
import {afterEach, expect, it} from 'vitest'
import {ReaderAvatar} from './ReaderAvatar'
import {readerAvatarModel, readerAvatarOptions, type ReaderAvatarModel} from './readerAvatarModel'

afterEach(cleanup)

it('keeps each reader portrait stable when its display name changes', () => {
  const page = render(<ReaderAvatar id="reader-a" name="细节求证型" size={40} />)
  const portrait = screen.getByRole('img', {name: '细节求证型的头像'})
  const drawing = portrait.innerHTML
  expect(portrait).toHaveAttribute('width', '40')
  expect(portrait).toHaveAttribute('height', '40')
  page.rerender(<ReaderAvatar id="reader-a" name="认真核对型" size={40} />)
  expect(screen.getByRole('img', {name: '认真核对型的头像'}).innerHTML).toBe(drawing)
})

it('uses the expanded warm and neutral palettes without the former blue and cyan variants', () => {
  const page = render(<ReaderAvatar id="reader-0" name="模拟读者" />)
  const backgrounds = new Set<string | null>()
  const previousCoolColors = ['#dde7fb', '#315aac', '#eadff3', '#78549c', '#dcecf1', '#326a80', '#364152']
  for (let index = 0; index < 120; index += 1) {
    page.rerender(<ReaderAvatar id={`reader-${index}`} name="模拟读者" />)
    const portrait = screen.getByRole('img', {name: '模拟读者的头像'})
    backgrounds.add(portrait.querySelector('rect')!.getAttribute('fill'))
    for (const color of previousCoolColors) expect(portrait.innerHTML).not.toContain(color)
  }
  expect(backgrounds.size).toBe(readerAvatarOptions.background.length)
})

it('independently combines every pair of decorative dimensions instead of binding them to one seed remainder', () => {
  const portraits = Array.from({length: 4096}, (_, index) => readerAvatarModel(`reader-${index}`))
  const dimensions = Object.keys(readerAvatarOptions) as (keyof ReaderAvatarModel)[]
  for (const [leftIndex, left] of dimensions.entries()) {
    expect(new Set(portraits.map(portrait => portrait[left])).size, left).toBe(readerAvatarOptions[left].length)
    for (const right of dimensions.slice(leftIndex + 1)) {
      const pairs = new Set(portraits.map(portrait => `${portrait[left]}:${portrait[right]}`))
      expect(pairs.size, `${left} × ${right}`).toBe(readerAvatarOptions[left].length * readerAvatarOptions[right].length)
    }
  }
})

function stableUuid(index: number): string {
  const hex = createHash('sha256').update(`reader-avatar-regression-${index}`).digest('hex')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-4${hex.slice(13, 16)}-a${hex.slice(17, 20)}-${hex.slice(20, 32)}`
}

it.each([
  ['sequential IDs', (index: number) => `reader-${index}`],
  ['UUID-shaped IDs', stableUuid],
] as const)('keeps complete drawing collisions low for 1,000 %s', (_, createId) => {
  const drawings = new Set(Array.from({length: 1000}, (_, index) => {
    const markup = renderToStaticMarkup(<ReaderAvatar id={createId(index)} name="模拟读者" size={38} />)
    // Only actual SVG drawing elements count, never the ID, accessible name, or hidden metadata.
    return markup.replace(/^<svg[^>]*>/, '').replace(/<\/svg>$/, '')
  }))
  expect(drawings.size).toBeGreaterThanOrEqual(998)
})

it('keeps unicode IDs deterministic, distinct from their shared leading surrogate, and free of external assets', () => {
  expect(readerAvatarModel('读者-🦊')).toEqual(readerAvatarModel('读者-🦊'))
  expect(readerAvatarModel('读者-🦊')).not.toEqual(readerAvatarModel('读者-🐰'))
  const {container} = render(<ReaderAvatar id="读者-🦊" name="模拟读者" size={38} />)
  expect(container.querySelector('svg')).toHaveAttribute('viewBox', '0 0 48 48')
  expect(container.querySelectorAll('image, use, foreignObject, [id], [data-id], [href]')).toHaveLength(0)
})
