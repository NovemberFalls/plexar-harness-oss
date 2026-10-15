/**
 * Loader for the copied shared `--px-*` token sheet (`plexar-tokens.css`, unmodified; see
 * SOURCE.md). Products map their own variables onto `--px-*`; nothing outside this module may
 * redeclare a `--px-*` value, so runtime overrides (a scoped stylesheet or class) keep working.
 */
import tokensCss from './plexar-tokens.css?inline'
import { PLEXAR_TOKENS_FONT_DATA_URL } from './font.ts'

/**
 * The token sheet's `@font-face` points at a relative `fonts/montserrat-medium.woff2`, which
 * 404s once the sheet is injected into the Host page (no such route there). This is the one
 * substitution `embedFont` makes; every other byte of the copied file passes through unchanged.
 * Quoting varies with which CSS transform ran the file through (single quotes from the source,
 * double quotes from a minifier), so the match tolerates either.
 */
// Quotes are optional: the client build minifies the sheet and drops them.
const FONT_URL_PATTERN = /url\(\s*['"]?fonts\/montserrat-medium\.woff2['"]?\s*\)/

/**
 * Replace the token sheet's relative font URL with an embedded `data:` URL.
 * @param css - token sheet text (the real file, or a test's own reading of it).
 * @returns the same text with the font URL substituted; unchanged if the pattern is absent (the
 * test environment mocks CSS imports to an empty string; the pattern always matches in a real build).
 */
export function embedFont(css: string): string {
  return css.replace(FONT_URL_PATTERN, `url(${JSON.stringify(PLEXAR_TOKENS_FONT_DATA_URL)})`)
}

/** The token sheet with its relative font URL replaced by an embedded `data:` URL. */
export const PLEXAR_TOKENS_CSS: string = embedFont(tokensCss)

/**
 * Add the shared token sheet to the document as the first Plexar brand style, before any sheet
 * reading `var(--px-*)`.
 * @param doc - the page document.
 * @returns removes the sheet.
 */
export function installTokens(doc: Document): () => void {
  const style = doc.createElement('style')
  style.dataset.plexarTokens = ''
  style.textContent = PLEXAR_TOKENS_CSS
  doc.head.prepend(style)
  return () => { style.remove() }
}
