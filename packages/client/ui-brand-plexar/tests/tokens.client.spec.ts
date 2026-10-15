// @vitest-environment jsdom
/**
 * The token loader: `embedFont` embeds the font as a data URL (the relative `fonts/...` URL
 * would 404 on the Host page) and passes every other declaration through unchanged, and
 * `installTokens` disposal removes the injected `<style>`. `embedFont` is exercised against the
 * real file content read from disk rather than the bundler's `?inline` import, which the test
 * environment mocks to an empty string.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { embedFont, installTokens, PLEXAR_TOKENS_CSS } from '../src/client/tokens/index.ts'

const RAW_CSS = readFileSync(
  resolve(process.cwd(), 'packages/client/ui-brand-plexar/src/client/tokens/plexar-tokens.css'),
  'utf8',
)

describe('embedFont', () => {
  it('replaces the relative font URL with a data URL', () => {
    const embedded = embedFont(RAW_CSS)
    expect(embedded).not.toContain("url('fonts/montserrat-medium.woff2')")
    expect(embedded).toContain('url("data:font/woff2;base64,')
  })

  it('also replaces the unquoted URL the minified client build produces', () => {
    const minified = '@font-face{font-family:Montserrat;src:url(fonts/montserrat-medium.woff2)format("woff2")}'
    const embedded = embedFont(minified)
    expect(embedded).not.toContain('url(fonts/montserrat-medium.woff2)')
    expect(embedded).toContain('url("data:font/woff2;base64,')
  })

  it('carries every other declaration through unchanged', () => {
    const embedded = embedFont(RAW_CSS)
    expect(embedded).toContain('--px-accent: #f28a2e;')
    expect(embedded).toContain('--px-bg: #0a0a0b;')
    expect(embedded.replace(/url\("data:font\/woff2;base64,[^)]*"\)/, "url('fonts/montserrat-medium.woff2')")).toBe(RAW_CSS)
  })

  it('leaves text with no matching font URL unchanged', () => {
    expect(embedFont('')).toBe('')
  })
})

describe('installTokens', () => {
  afterEach(() => {
    document.head.querySelectorAll('style[data-plexar-tokens]').forEach(style => style.remove())
  })

  it('prepends one style element carrying the sheet so later brand sheets can read var(--px-*), and disposal removes it', () => {
    const dispose = installTokens(document)
    const style = document.head.querySelector('style[data-plexar-tokens]')
    expect(style?.textContent).toBe(PLEXAR_TOKENS_CSS)
    expect(document.head.firstElementChild).toBe(style)

    dispose()
    expect(document.head.querySelector('style[data-plexar-tokens]')).toBeNull()
  })
})
