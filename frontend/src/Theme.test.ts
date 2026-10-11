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

  it('reserves cool colors for named report observations without restoring the blue brand theme', () => {
    for (const [path, css] of Object.entries(styles)) {
      expect(css, path).not.toMatch(/var\(--(?:blue|indigo)(?:-soft)?\)/)
      const brandStyles = path === 'App.css'
        ? css.replace(/--report-observation-(?:surface|border|ink):\s*#[0-9a-f]{6};/gi, '')
        : css
      for (const hex of brandStyles.match(/#[0-9a-f]{6}\b/gi) ?? []) {
        const [r, g, b] = channels(hex)
        const delta = Math.max(r, g, b) - Math.min(r, g, b)
        // Only the explicit report observation palette may be cool blue.
        expect(b > r && b >= g && delta > 0.08, `${path}: ${hex}`).toBe(false)
      }
    }
  })

  it('keeps report labels and existing body text readable on all semantic surfaces', () => {
    for (const role of ['observation', 'strength', 'suggestion', 'lower']) {
      const surface = token(`report-${role}-surface`)
      for (const ink of [`report-${role}-ink`, 'ink', 'sub']) {
        expect(contrast(token(ink), surface), `${ink} on ${role}`).toBeGreaterThanOrEqual(4.5)
      }
    }
    expect(new Set(['observation', 'strength', 'suggestion'].map(role => token(`report-${role}-surface`))).size).toBe(3)
  })

  it('reserves green for lower-performance comparisons while completed states stay blue', () => {
    expect(appStyles).toContain('--ok: var(--report-observation-ink);')
    expect(appStyles).toContain('--ok-soft: var(--report-observation-surface);')
    expect(contrast(token('report-observation-ink'), '#ffffff')).toBeGreaterThanOrEqual(4.5)
    for (const [path, css] of Object.entries(styles)) {
      const otherStyles = path === 'App.css'
        ? css.replace(/--report-lower-(?:surface|border|ink):\s*#[0-9a-f]{6};/gi, '')
        : css
      for (const hex of otherStyles.match(/#[0-9a-f]{6}\b/gi) ?? []) {
        const [r, g, b] = channels(hex)
        expect(g > r + 5 / 255 && g > b + 2 / 255, `${path}: ${hex}`).toBe(false)
      }
    }
    expect(styles['components/TrialRoom.css']).toMatch(/\.simulation-final-readers\s*\{[^}]*background:var\(--report-observation-surface\)/)
    expect(appStyles).toMatch(/\.panel-edit-compare section:last-child\s*\{[^}]*background: var\(--report-suggestion-surface\)/)
  })

  it('keeps both report generations side by side with red higher and green lower cards', () => {
    const report = styles['components/AccountReport.css']
    expect(report).toMatch(/\.account-report \.account-report-saved-performance \.cmp\s*\{[^}]*grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/)
    expect(report).not.toMatch(/\.cmp\s*\{[^}]*grid-template-columns: minmax\(0, 1fr\)/)
    expect(report).toMatch(/\.account-report-saved-performance \.cmp-win\s*\{[^}]*background: var\(--accent-soft\)/)
    expect(report).toMatch(/\.account-report-saved-performance \.cmp-lose\s*\{[^}]*background: var\(--report-lower-surface\)/)
    expect(styles['components/AccountPerformanceView.css']).toMatch(/\.account-performance-paired\s*\{[^}]*grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/)
  })

  it('keeps report colors independent from primary actions and danger states', () => {
    const buttonStyles = styles['Button.css']
    expect(buttonStyles).toContain('--button-background: var(--accent);')
    expect(buttonStyles).toContain('--button-foreground: #b91c1c;')
    expect(buttonStyles).not.toContain('var(--report-')
    for (const path of ['AccountReport', 'AudienceResults', 'TrialRoom', 'SimulationReviewSummary', 'EditorFeedbackView']) {
      expect(styles[`components/${path}.css`], path).not.toMatch(/--(?:accent(?:-[\w-]+)?|red(?:-soft)?):/)
    }
  })

  it('covers current and legacy account reports, simulated discussion and linked evidence', () => {
    const report = styles['components/AccountReport.css']
    expect(report).toContain('.account-report .account-portrait-strengths > .account-portrait-claims')
    expect(report).toContain('.account-report .account-report-legacy-performance .cmp-win')
    expect(report).toContain('.account-report .account-report-next-steps > ol')
    expect(report).toContain('.account-report .account-report-next-steps > .account-portrait-claims')
    expect(report).toContain('background: var(--report-observation-surface);')
    expect(styles['components/AudienceResults.css']).toContain('.audience-evidence-ref > p')
    expect(styles['components/TrialRoom.css']).toMatch(/\.trial-bubble\s*\{[^}]*background:var\(--report-observation-surface\)/)
    expect(styles['components/TrialRoom.css']).toMatch(/\.trial-takeaways\s*\{[^}]*background:var\(--report-suggestion-surface\)/)
    expect(styles['components/EditorFeedbackView.css']).toContain('.editor-feedback .editor-feedback-card.feedback-keep')
    expect(styles['components/EditorFeedbackView.css']).toMatch(/\.editor-feedback \.feedback-original\s*\{[^}]*background: var\(--report-observation-surface\)/)
  })
})
