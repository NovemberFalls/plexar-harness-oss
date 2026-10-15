/**
 * The shipped Plexar patch files parse with the same overlay parser the dsh launcher uses. A patch that
 * fails to parse makes the launcher skip the whole Plexar bundle, which silently drops the `plexar` model
 * provider ("no adapter registered for provider") rather than failing one row.
 */
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { loadOverlayPatches } from '@deepseek-ai/dsh-app-boot'

const bundle = join(import.meta.dirname, '..')

describe('shipped patch files', () => {
  for (const file of ['cordis.patch.yml', 'profiles/plexar-acp.patch.yml', 'profiles/plexar-web.patch.yml']) {
    it(`${file} parses with the launcher's overlay parser`, () => {
      expect(loadOverlayPatches('plexar-test', join(bundle, file)).length).toBeGreaterThan(0)
    })
  }
})
