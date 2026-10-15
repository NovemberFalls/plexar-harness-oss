/**
 * Writes the Tauri updater manifest (`latest.json`) for one Plexar Harness Windows release. The
 * desktop app polls `https://downloads.plexar.tech/harness/latest.json` (`plugins.updater` in
 * `apps/plexar-desktop/src-tauri/tauri.conf.json`) and installs the installer at `url` only when
 * `signature` verifies against the configured public key.
 *
 * Usage:
 *   node --import tsx/esm scripts/plexar-release/updater-manifest.ts --version <x.y.z> --sig <installer .sig> --out <latest.json>
 */
import { readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

/** Public download location; the installer lives under `windows/`, the manifest at the root. */
export const DOWNLOAD_BASE = 'https://downloads.plexar.tech/harness'

/**
 * Published installer file name for `version`.
 * @param version - release version, `x.y.z`.
 * @returns the file name.
 */
export function installerName(version: string): string {
  return `PlexarHarness_${version}_x64-setup.exe`
}

/**
 * The manifest object for one release, in the Tauri v2 static-JSON updater format.
 * @param release - version, installer signature text, publish time, optional notes.
 * @returns the manifest object.
 */
/** One platform entry of the manifest. */
export interface PlatformEntry { signature: string; url: string }

/** The Tauri v2 static-JSON updater manifest. */
export interface UpdaterManifest { version: string; notes: string; pub_date: string; platforms: { 'windows-x86_64': PlatformEntry } }

export function updaterManifest({ version, signature, pubDate, notes = `Plexar Harness ${version}` }: { version: string; signature: string; pubDate: Date; notes?: string }): UpdaterManifest {
  if (!/^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/.test(version)) throw new Error(`version ${JSON.stringify(version)} is not x.y.z`)
  const trimmed = signature.trim()
  if (trimmed === '') throw new Error('signature is empty')
  return {
    version,
    notes,
    pub_date: pubDate.toISOString().replace(/\.\d{3}Z$/, 'Z'),
    platforms: {
      'windows-x86_64': { signature: trimmed, url: `${DOWNLOAD_BASE}/windows/${installerName(version)}` },
    },
  }
}

const isMain = process.argv[1] !== undefined && fileURLToPath(import.meta.url) === resolve(process.argv[1])
if (isMain) {
  const args = process.argv.slice(2)
  const value = (flag: string): string => {
    const index = args.indexOf(flag)
    if (index < 0 || args[index + 1] === undefined) throw new Error(`missing ${flag}`)
    return args[index + 1] as string
  }
  try {
    const manifest = updaterManifest({ version: value('--version'), signature: readFileSync(value('--sig'), 'utf8'), pubDate: new Date() })
    writeFileSync(value('--out'), JSON.stringify(manifest, undefined, 2) + '\n')
  } catch (error) {
    process.stderr.write(`updater-manifest: ${(error as Error).message}\n`)
    process.exitCode = 1
  }
}
