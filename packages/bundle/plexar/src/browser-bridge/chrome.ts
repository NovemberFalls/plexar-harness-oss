/**
 * Locate the person's installed Chrome or Edge, detect whether an extension is installed in any of
 * their browser profiles, and open a URL in the browser.
 * playwright-core's browser registry is internal to that package, so the standard install
 * locations are listed here: Chrome first, then Edge, per platform.
 * @module @plexar/dsh-plexar/browser-bridge/chrome
 */

import { spawn } from 'node:child_process'
import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'

/**
 * Standard Chrome and Edge executable paths for one platform, in lookup order.
 * @param platform - `process.platform` value.
 * @param env - environment supplying the Windows install roots.
 * @returns candidate absolute paths; Windows roots missing from `env` are skipped.
 */
export function chromeCandidates(platform: NodeJS.Platform, env: NodeJS.ProcessEnv): string[] {
  if (platform === 'win32') {
    const roots = [env['PROGRAMFILES'], env['PROGRAMFILES(X86)'], env['LOCALAPPDATA']]
      .filter((root): root is string => root !== undefined && root !== '')
    return [
      ...roots.map(root => join(root, 'Google', 'Chrome', 'Application', 'chrome.exe')),
      ...roots.map(root => join(root, 'Microsoft', 'Edge', 'Application', 'msedge.exe')),
    ]
  }
  if (platform === 'darwin') {
    return [
      '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
      '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
    ]
  }
  return [
    '/opt/google/chrome/chrome',
    '/usr/bin/google-chrome-stable',
    '/usr/bin/google-chrome',
    '/opt/microsoft/msedge/msedge',
    '/usr/bin/microsoft-edge-stable',
    '/usr/bin/microsoft-edge',
  ]
}

/**
 * Find the first installed Chrome or Edge.
 * @param platform - `process.platform` value.
 * @param env - environment supplying the Windows install roots.
 * @param exists - file existence check.
 * @returns the executable path, or undefined when none is installed.
 */
export function findChrome(
  platform: NodeJS.Platform = process.platform,
  env: NodeJS.ProcessEnv = process.env,
  exists: (path: string) => boolean = existsSync,
): string | undefined {
  return chromeCandidates(platform, env).find(path => exists(path))
}

/**
 * Open a URL in the person's running browser (or start it), detached from this process.
 * @param executable - Chrome or Edge executable.
 * @param url - the page to open.
 * @returns a promise that settles once the browser process started or failed to start.
 */
export function openInBrowser(executable: string, url: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const child = spawn(executable, [url], { windowsHide: true, detached: true, shell: false, stdio: 'ignore' })
    child.once('error', reject)
    child.once('spawn', () => {
      child.unref()
      resolve()
    })
  })
}

/**
 * Standard Chrome and Edge user-data directories for one platform.
 * @param platform - `process.platform` value.
 * @param env - environment supplying `LOCALAPPDATA` on Windows.
 * @param home - the person's home directory.
 * @returns candidate user-data directories; on Windows none when `LOCALAPPDATA` is unset.
 */
export function userDataDirs(platform: NodeJS.Platform, env: NodeJS.ProcessEnv, home: string): string[] {
  if (platform === 'win32') {
    const local = env['LOCALAPPDATA']
    if (local === undefined || local === '') return []
    return [join(local, 'Google', 'Chrome', 'User Data'), join(local, 'Microsoft', 'Edge', 'User Data')]
  }
  if (platform === 'darwin') {
    const support = join(home, 'Library', 'Application Support')
    return [join(support, 'Google', 'Chrome'), join(support, 'Microsoft Edge')]
  }
  return [join(home, '.config', 'google-chrome'), join(home, '.config', 'microsoft-edge')]
}

/** Preference files that record installed extensions under `extensions.settings`. */
const PREFERENCE_FILES = ['Preferences', 'Secure Preferences']

/**
 * Whether one Chromium preference file lists an extension under `extensions.settings`.
 * @param path - a `Preferences` or `Secure Preferences` file.
 * @param extensionId - the extension id.
 * @returns false when the file is missing, unreadable, or not JSON.
 */
function preferencesListExtension(path: string, extensionId: string): boolean {
  let parsed: unknown
  try {
    parsed = JSON.parse(readFileSync(path, 'utf8'))
  } catch (error) {
    // A missing, unreadable, or malformed preference file records no install; `error` is not needed.
    void error
    return false
  }
  const extensions = isRecord(parsed) ? parsed['extensions'] : undefined
  const settings = isRecord(extensions) ? extensions['settings'] : undefined
  return isRecord(settings) && Object.hasOwn(settings, extensionId)
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/**
 * Whether any Chrome or Edge profile has the extension installed, from the store or loaded unpacked.
 * Scans every profile directory of each user-data directory for `Preferences` or `Secure Preferences`
 * listing the id under `extensions.settings`.
 * @param extensionId - the extension id.
 * @param dirs - user-data directories; defaults to this platform's standard locations.
 * @returns true when at least one profile lists the extension.
 */
export function extensionInstalled(
  extensionId: string,
  dirs: readonly string[] = userDataDirs(process.platform, process.env, homedir()),
): boolean {
  return dirs.some((dir) => {
    let profiles: string[]
    try {
      profiles = readdirSync(dir, { withFileTypes: true }).filter(entry => entry.isDirectory()).map(entry => entry.name)
    } catch (error) {
      // A missing or unreadable user-data directory means this browser holds no install; `error` is not needed.
      void error
      return false
    }
    return profiles.some(profile => PREFERENCE_FILES.some(file => preferencesListExtension(join(dir, profile, file), extensionId)))
  })
}
