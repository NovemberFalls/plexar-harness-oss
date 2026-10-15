/**
 * Guards against re-forking the shared accent color: no source file outside the copied token
 * sheet and the generated font module may spell the Plexar accent as a hex literal. Every other
 * accent use must go through `var(--px-accent)` / `var(--px-accent-soft)` (see `tokens/`).
 */
import { globSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const SRC_ROOT = fileURLToPath(new URL('../src/', import.meta.url))
const ACCENT_HEX = ['#f28a2e', '#ff8a2a', '#ff6a00', '#ffb066']
const EXCLUDED = new Set(['client/tokens/plexar-tokens.css', 'client/tokens/font.ts'])

describe('accent color literals', () => {
  const files = globSync('**/*.{ts,tsx,css}', { cwd: SRC_ROOT })
    .filter(relativePath => !EXCLUDED.has(relativePath.split('\\').join('/')))

  it.each(files)('%s has no hardcoded Plexar accent hex', (relativePath) => {
    const content = readFileSync(`${SRC_ROOT}${relativePath}`, 'utf8').toLowerCase()
    for (const hex of ACCENT_HEX) {
      expect(content.includes(hex)).toBe(false)
    }
  })
})
