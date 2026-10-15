import { describe, expect, it } from 'vitest'

import { installerName, updaterManifest } from './updater-manifest.ts'

describe('updaterManifest', () => {
  it('writes the Tauri static-JSON fields with the Windows installer URL', () => {
    const manifest = updaterManifest({ version: '0.4.2', signature: 'c2ln\n', pubDate: new Date('2026-09-26T12:34:56.789Z') })
    expect(manifest).toEqual({
      version: '0.4.2',
      notes: 'Plexar Harness 0.4.2',
      pub_date: '2026-09-26T12:34:56Z',
      platforms: {
        'windows-x86_64': {
          signature: 'c2ln',
          url: 'https://downloads.plexar.tech/harness/windows/PlexarHarness_0.4.2_x64-setup.exe',
        },
      },
    })
  })

  it('names the installer after the version', () => {
    expect(installerName('1.2.3')).toBe('PlexarHarness_1.2.3_x64-setup.exe')
  })

  it('rejects a version that is not x.y.z and an empty signature', () => {
    expect(() => updaterManifest({ version: 'v0.4', signature: 'c2ln', pubDate: new Date() })).toThrow(/not x\.y\.z/)
    expect(() => updaterManifest({ version: '0.4.2', signature: ' \n', pubDate: new Date() })).toThrow(/signature is empty/)
  })
})
