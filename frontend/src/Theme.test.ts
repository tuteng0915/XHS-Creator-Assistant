// @vitest-environment node
import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const sourceRoot = fileURLToPath(new URL('.', import.meta.url))
const appStyles = readFileSync(resolve(sourceRoot, 'App.css'), 'utf8')
const styles = Object.fromEntries(readdirSync(sourceRoot, { recursive: true, encoding: 'utf8' })
  .filter(path => path.endsWith('.css'))
  .map(path => [path, readFileSync(resolve(sourceRoot, path), 'utf8')]))

function token(name: string): string {
  const value = appStyles.match(new RegExp(`--${name}:\\s*(#[0-9a-f]{6});`, 'i'))?.[1]
  if (!value) throw new Error(`Missing color token: ${name}`)
  return value
}

function channels(hex: string): number[] {
  return [1, 3, 5].map(offset => parseInt(hex.slice(offset, offset + 2), 16) / 255)
}

function luminance(hex: string): number {
  const [r, g, b] = channels(hex).map(value => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4)
  return r * 0.2126 + g * 0.7152 + b * 0.0722
}

function contrast(first: string, second: string): number {
  const values = [luminance(first), luminance(second)].sort((a, b) => b - a)
  return (values[0] + 0.05) / (values[1] + 0.05)
}

describe('creator red theme', () => {
  it('keeps primary, hover and pressed labels readable on red', () => {
    for (const name of ['accent', 'accent-hover', 'accent-active']) {
      expect(contrast(token(name), '#ffffff'), name).toBeGreaterThanOrEqual(4.5)
    }
  })

  it('keeps accent and secondary text readable on light surfaces', () => {
    expect(contrast(token('accent-ink'), token('accent-soft'))).toBeGreaterThanOrEqual(4.5)
    expect(contrast(token('sub'), token('surface-muted'))).toBeGreaterThanOrEqual(4.5)
  })

  it('uses neutral or warm UI colors without legacy blue theme tokens', () => {
    for (const [path, css] of Object.entries(styles)) {
      expect(css, path).not.toMatch(/var\(--(?:blue|indigo)(?:-soft)?\)/)
      for (const hex of css.match(/#[0-9a-f]{6}\b/gi) ?? []) {
        const [r, g, b] = channels(hex)
        const delta = Math.max(r, g, b) - Math.min(r, g, b)
        // Ignore near-neutral grays; reject the former blue/indigo accent family.
        expect(b > r && b >= g && delta > 0.08, `${path}: ${hex}`).toBe(false)
      }
    }
  })
})
