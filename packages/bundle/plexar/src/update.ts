/**
 * Host update service for a Plexar install, git checkout or installed copy.
 *
 * In a git checkout, mirrors `plexar-harness update` (cli/update.mjs): refuse a checkout with
 * uncommitted tracked changes, `git pull --ff-only`, `pnpm install`, then build the Plexar bundle.
 * The periodic background check compares local HEAD against the tracked branch's tip on `origin`
 * via `git ls-remote`, the same approach and timeout `cli/update.mjs` uses for its own background
 * check; the two are duplicated in source rather than sharing a helper because the CLI's launch
 * path (plain Node, no bundler) and this plugin's build (typert-generated, tsdown-bundled) resolve
 * modules differently, and the CLI's behavior must stay byte-for-byte unchanged.
 *
 * An installed copy (the Windows installer's runtime: no `.git`) has no `origin` to query, so the
 * background check instead fetches the release manifest ({@link Config.releaseManifestUrl}) and
 * compares its `version` against the local `packages/bundle/plexar/package.json` version; any
 * failure (offline, non-200, invalid JSON, timeout) reports `'current'`, never an error. `apply()`
 * on an installed copy does not touch git or pnpm; it reports `'failed'` with guidance to use the
 * desktop app's own updater or the installer download page.
 * @module @plexar/dsh-plexar/update
 */

import { spawn } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import { Remote, RemoteError, TypertRemoteService } from '@deepseek-ai/dsh-typert-protocol'

declare module '@deepseek-ai/dsh-typert-protocol' {
  interface RemoteErrorDetailsMap {
    /** `restart()` called outside the desktop app. */
    'plexarUpdate/restart-unavailable': Record<never, never>
  }
}

/** `git ls-remote` timeout, matching `cli/update.mjs`'s background check. */
const REMOTE_CHECK_TIMEOUT_MS = 5000

/** Default interval between periodic background update checks, in milliseconds (one hour). */
const DEFAULT_CHECK_INTERVAL_MS = 3600000

/** Default release manifest URL for an installed copy's background check, matching the desktop app's Tauri updater feed. */
const DEFAULT_RELEASE_MANIFEST_URL = 'https://downloads.plexar.tech/harness/latest.json'

/** Timeout for fetching the release manifest, matching {@link REMOTE_CHECK_TIMEOUT_MS}'s git bound. */
const MANIFEST_FETCH_TIMEOUT_MS = 5000

/** Whether `root` is a git checkout (has the git plumbing this service's checkout path needs). */
function isCheckout(root: string): boolean {
  return existsSync(join(root, '.git'))
}

/**
 * The manifest URL to fetch: `PLEXAR_RELEASE_MANIFEST` overrides the configured value.
 * @param configured - {@link Config.releaseManifestUrl}, already defaulted by schemastery.
 */
function resolvedManifestUrl(configured: string): string {
  return process.env['PLEXAR_RELEASE_MANIFEST'] ?? configured
}

/**
 * Compares two `major.minor.patch` semver strings.
 * @returns negative when `a` < `b`, positive when `a` > `b`, zero when equal, or undefined when
 * either string does not start with a parseable `major.minor.patch` prefix.
 */
export function compareSemver(a: string, b: string): number | undefined {
  const pattern = /^(\d+)\.(\d+)\.(\d+)/
  const left = pattern.exec(a)
  const right = pattern.exec(b)
  if (left === null || right === null) return undefined
  for (let i = 1; i <= 3; i++) {
    const diff = Number(left[i]) - Number(right[i])
    if (diff !== 0) return diff
  }
  return 0
}

/**
 * Fetches the release manifest and returns its `version` field, bounded by `timeoutMs`.
 * @returns the version, or undefined on any failure: offline, non-200, invalid JSON, or timeout.
 */
async function fetchManifestVersion(url: string, timeoutMs: number): Promise<string | undefined> {
  const controller = new AbortController()
  const timer = setTimeout(() => { controller.abort() }, timeoutMs)
  try {
    const response = await fetch(url, { signal: controller.signal })
    if (!response.ok) return undefined
    const parsed: unknown = await response.json()
    const version = typeof parsed === 'object' && parsed !== null ? (parsed as { version?: unknown }).version : undefined
    return typeof version === 'string' ? version : undefined
  } catch (error) {
    // Offline, DNS failure, non-JSON body, or the abort from the timeout: no notice, never an error.
    void error
    return undefined
  } finally {
    clearTimeout(timer)
  }
}

/** The local Plexar version of an installed copy, read directly from disk (no git needed). */
function localManifestVersion(root: string): string | undefined {
  try {
    return versionOf(readFileSync(join(root, VERSION_MANIFEST), 'utf8'))
  } catch (error) {
    // A runtime missing its own manifest has no readable version; the notice then shows none.
    void error
    return undefined
  }
}

/** The checkout root this service tracks, matching `cli/acp.mjs`'s `harnessRoot()`. */
function harnessRoot(): string {
  return process.env['PLEXAR_HARNESS_ROOT'] ?? resolve(dirname(fileURLToPath(import.meta.url)), '../../../..')
}

/**
 * Current state of the tracked git checkout and any in-progress or finished update run.
 * `remote` and `branch` are populated once a check has completed; `error` is populated only
 * when `state` is `'failed'`.
 */
export interface UpdateStatus {
  /** Update lifecycle state. */
  readonly state: 'current' | 'available' | 'updating' | 'failed' | 'restart-required'
  /** Commit sha at the tip of the tracked branch on `origin`, once known. */
  readonly remote?: string
  /** Commit sha the checkout is at, once known. */
  readonly local?: string
  /** Plexar version (`packages/bundle/plexar/package.json`) of the checkout, once known. */
  readonly localVersion?: string
  /** Plexar version at `remote`, read after fetching it; set only when `state` is `'available'`. */
  readonly remoteVersion?: string
  /** Tracked local branch name, once known. */
  readonly branch?: string
  /** Failure message, populated only when `state` is `'failed'`. */
  readonly error?: string
  /** When this status was last computed, as epoch milliseconds. */
  readonly checkedAt?: number
}

/** Plexar update service deployment policy. */
export interface Config {
  /** Interval between periodic background update checks, in milliseconds (default 3600000). */
  readonly checkIntervalMs?: number
  /**
   * Release manifest URL an installed copy (no `.git`) polls instead of `git ls-remote`, matching
   * the desktop app's Tauri updater feed by default. `PLEXAR_RELEASE_MANIFEST` overrides it.
   */
  readonly releaseManifestUrl?: string
}

/** Run one git subcommand against the checkout root; returns trimmed stdout, or undefined on a nonzero exit. */
function runGit(root: string, args: readonly string[]): Promise<string | undefined> {
  return new Promise((resolvePromise) => {
    const child = spawn('git', args, { cwd: root, windowsHide: true, stdio: ['ignore', 'pipe', 'ignore'] })
    let out = ''
    child.stdout.on('data', (chunk: Buffer) => { out += chunk.toString() })
    child.on('close', (code) => { resolvePromise(code === 0 ? out.trim() : undefined) })
    child.on('error', () => { resolvePromise(undefined) })
  })
}

/** `git ls-remote origin refs/heads/<branch>`, bounded by {@link REMOTE_CHECK_TIMEOUT_MS}. */
async function lsRemote(root: string, branch: string): Promise<string | undefined> {
  return (await runGitBounded(root, ['ls-remote', 'origin', `refs/heads/${branch}`]))?.split(/\s/)[0]
}

/** Path of the manifest whose `version` is the Plexar version, relative to the checkout root. */
const VERSION_MANIFEST = 'packages/bundle/plexar/package.json'

/**
 * The `version` field of a manifest's JSON text.
 * @param text - package.json contents.
 * @returns the version, or undefined when the text is not a manifest with a string version.
 */
export function versionOf(text: string | undefined): string | undefined {
  if (text === undefined) return undefined
  try {
    const parsed: unknown = JSON.parse(text)
    const version = typeof parsed === 'object' && parsed !== null ? (parsed as { version?: unknown }).version : undefined
    return typeof version === 'string' ? version : undefined
  } catch (error) {
    // A manifest that is not JSON has no readable version; the notice then shows none.
    void error
    return undefined
  }
}

/**
 * The Plexar version at a remote commit: fetches the branch tip (no working-tree change), then reads
 * the manifest from that commit. Both steps are bounded by {@link REMOTE_CHECK_TIMEOUT_MS}.
 */
async function remoteVersion(root: string, branch: string, commit: string): Promise<string | undefined> {
  if (await runGitBounded(root, ['fetch', '--quiet', 'origin', `refs/heads/${branch}`]) === undefined) return undefined
  return versionOf(await runGitBounded(root, ['show', `${commit}:${VERSION_MANIFEST}`]))
}

/** Run one git subcommand bounded by {@link REMOTE_CHECK_TIMEOUT_MS}; trimmed stdout, or undefined on failure. */
function runGitBounded(root: string, args: readonly string[]): Promise<string | undefined> {
  return new Promise((resolvePromise) => {
    const child = spawn('git', args, {
      cwd: root,
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'ignore'],
    })
    let out = ''
    child.stdout.on('data', (chunk: Buffer) => { out += chunk.toString() })
    const timer = setTimeout(() => child.kill(), REMOTE_CHECK_TIMEOUT_MS)
    child.on('close', (code) => {
      clearTimeout(timer)
      resolvePromise(code === 0 ? out.trim() : undefined)
    })
    child.on('error', () => {
      clearTimeout(timer)
      resolvePromise(undefined)
    })
  })
}

/** Run one build/install step to completion, inheriting stdio. Rejects on a nonzero exit or spawn error. */
function runStep(root: string, command: string, args: readonly string[]): Promise<void> {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(command, args, {
      cwd: root,
      stdio: 'inherit',
      shell: process.platform === 'win32',
      windowsHide: true,
    })
    child.on('close', (code) => {
      if (code === 0) resolvePromise()
      else reject(new Error(`${command} ${args.join(' ')} failed (exit ${String(code)})`))
    })
    child.on('error', reject)
  })
}

/**
 * Host service backing the generated `ctx.remote.plexarUpdate` namespace: reports the tracked
 * checkout's update state, applies `plexar-harness update`'s steps on request, and asks for a
 * Host restart after a successful apply when running under the desktop app.
 */
export class PlexarUpdate extends TypertRemoteService {
  static inject: string[] = []

  static Config: z<Config> = z.object({
    checkIntervalMs: z.natural().min(1).default(DEFAULT_CHECK_INTERVAL_MS),
    releaseManifestUrl: z.string().default(DEFAULT_RELEASE_MANIFEST_URL),
  })

  private readonly root: string
  private readonly manifestUrl: string
  private current: UpdateStatus = { state: 'current' }
  /** The single in-flight `apply()` run, if any; a concurrent call coalesces onto it rather than
   * starting a second `git pull`/`pnpm install`/build run, since two overlapping runs would race
   * on the same working tree and node_modules. */
  private applyInFlight: Promise<UpdateStatus> | undefined

  /**
   * @param ctx - Host context this service registers into.
   * @param config - resolved deployment policy (checkIntervalMs has already been defaulted by schemastery).
   */
  constructor(ctx: Context, config: Config) {
    super(ctx, 'plexarUpdate', { namespace: 'plexarUpdate' })
    const resolved = config as Required<Config>
    this.root = harnessRoot()
    this.manifestUrl = resolvedManifestUrl(resolved.releaseManifestUrl)
    // Background check on load, never blocking it; then re-check on the configured interval.
    void this.refresh()
    ctx.effect(() => {
      const timer = setInterval(() => { void this.refresh() }, resolved.checkIntervalMs)
      return () => clearInterval(timer)
    })
  }

  /** Recompute {@link current} from the tracked checkout, unless an apply is in flight. */
  private async refresh(): Promise<void> {
    if (this.applyInFlight !== undefined) return
    this.current = await this.computeStatus()
  }

  /**
   * Compare local HEAD with the tracked branch's tip on `origin` in a checkout, or the local and
   * release-manifest versions in an installed copy.
   */
  private async computeStatus(): Promise<UpdateStatus> {
    if (!isCheckout(this.root)) return this.computeManifestStatus()
    const branch = await runGit(this.root, ['rev-parse', '--abbrev-ref', 'HEAD'])
    if (branch === undefined || branch === 'HEAD') return { state: 'current', checkedAt: Date.now() }
    const head = await runGit(this.root, ['rev-parse', 'HEAD'])
    const localVersion = versionOf(await runGit(this.root, ['show', `HEAD:${VERSION_MANIFEST}`]))
    const remote = await lsRemote(this.root, branch)
    if (head === undefined) return { state: 'current', branch, checkedAt: Date.now() }
    if (remote === undefined) return { state: 'current', local: head, branch, checkedAt: Date.now() }
    if (remote === head) return { state: 'current', local: head, remote, branch, checkedAt: Date.now() }
    // A remote commit the checkout already contains is not an update (local is ahead or equal).
    const ancestor = await runGit(this.root, ['merge-base', '--is-ancestor', remote, 'HEAD'])
    if (ancestor !== undefined) return { state: 'current', local: head, remote, branch, checkedAt: Date.now() }
    return {
      state: 'available', local: head, remote, branch, checkedAt: Date.now(),
      ...localVersion === undefined ? {} : { localVersion },
      ...await remoteVersion(this.root, branch, remote).then(version => version === undefined ? {} : { remoteVersion: version }),
    }
  }

  /**
   * Compare the local `packages/bundle/plexar/package.json` version with the release manifest's
   * `version`. Any failure (offline, non-200, invalid JSON, timeout) reports `'current'`.
   */
  private async computeManifestStatus(): Promise<UpdateStatus> {
    const localVersion = localManifestVersion(this.root)
    const remoteVersion = await fetchManifestVersion(this.manifestUrl, MANIFEST_FETCH_TIMEOUT_MS)
    if (localVersion === undefined || remoteVersion === undefined) return { state: 'current', checkedAt: Date.now() }
    const cmp = compareSemver(remoteVersion, localVersion)
    if (cmp === undefined || cmp <= 0) return { state: 'current', localVersion, checkedAt: Date.now() }
    return { state: 'available', localVersion, remoteVersion, checkedAt: Date.now() }
  }

  /**
   * Read the current update status.
   * @returns the last computed status; a background check keeps it current.
   */
  @Remote
  status(): Promise<UpdateStatus> {
    return Promise.resolve(this.current)
  }

  /**
   * Run `plexar-harness update`'s steps: refuse a dirty tracked checkout, `git pull --ff-only`,
   * `pnpm install`, then build the Plexar bundle. A concurrent call while one run is in flight
   * coalesces onto that run's result instead of starting a second one.
   * @returns the status after the run: `'restart-required'` on success, `'failed'` with `error` set otherwise.
   */
  @Remote
  apply(): Promise<UpdateStatus> {
    if (this.applyInFlight !== undefined) return this.applyInFlight
    const run = this.runApply()
    this.applyInFlight = run
    void run.finally(() => { this.applyInFlight = undefined })
    return run
  }

  /** The body of one `apply()` run. */
  private async runApply(): Promise<UpdateStatus> {
    this.current = { ...this.current, state: 'updating' }
    if (!isCheckout(this.root)) {
      this.current = {
        ...this.current,
        state: 'failed',
        error: 'This is an installed copy; the desktop app installs updates itself on launch, '
          + 'or download the latest installer from https://harness.plexar.tech',
      }
      return this.current
    }
    try {
      const dirty = await runGit(this.root, ['status', '--porcelain', '--untracked-files=no'])
      if (dirty !== undefined && dirty.length > 0) {
        throw new Error(`${this.root} has uncommitted changes; commit or stash them, then try again`)
      }
      await runStep(this.root, 'git', ['pull', '--ff-only'])
      await runStep(this.root, 'pnpm', ['install'])
      await runStep(this.root, 'npx', ['tsc', '-b', 'packages/bundle/plexar'])
      const status = await this.computeStatus()
      this.current = { ...status, state: 'restart-required' }
      return this.current
    } catch (error) {
      this.current = { ...this.current, state: 'failed', error: error instanceof Error ? error.message : String(error) }
      return this.current
    }
  }

  /**
   * Ask for a Host restart after a successful `apply()`. Only available under the desktop app,
   * which respawns the Host and navigates the window on exit code 75.
   * @returns after the restart request is scheduled; the process exits shortly afterward.
   */
  @Remote
  async restart(): Promise<void> {
    if (process.env['PLEXAR_DESKTOP'] !== '1') {
      throw new RemoteError('plexarUpdate/restart-unavailable', 'restart is only available in the desktop app', {})
    }
    // Deferred so this reply reaches the client before the process exits.
    setTimeout(() => { process.exit(75) }, 0)
  }
}

export default PlexarUpdate
