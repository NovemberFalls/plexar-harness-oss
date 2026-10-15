/**
 * `src/client/tokens/plexar-tokens.css` and `src/client/tokens/fonts/montserrat-medium.woff2`
 * are byte-for-byte copies of plexar-coord's shared tokens (see `src/client/tokens/SOURCE.md`).
 * plexar-coord is a sibling repository checkout, not always present, so these compare against it
 * only when found and skip otherwise.
 */
import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const SOURCE_ROOT = fileURLToPath(new URL('../../../../../plexar-coord/brand/tokens/', import.meta.url))
const COPY_ROOT = fileURLToPath(new URL('../src/client/tokens/', import.meta.url))

const FILES = ['plexar-tokens.css', 'fonts/montserrat-medium.woff2']

describe('copied token files', () => {
  for (const relativePath of FILES) {
    const sourcePath = `${SOURCE_ROOT}${relativePath}`
    const copyPath = `${COPY_ROOT}${relativePath}`
    const has = existsSync(sourcePath)

    it.skipIf(!has)(`${relativePath} is byte-identical to the plexar-coord source`, () => {
      expect(readFileSync(copyPath)).toEqual(readFileSync(sourcePath))
    })
  }
})
