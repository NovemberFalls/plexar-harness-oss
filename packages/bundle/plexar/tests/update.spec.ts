/** Host update status/apply state machine: mocked git/pnpm/fetch, no network or real subprocesses. */

import { EventEmitter } from 'node:events'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { Context } from '@deepseek-ai/cordis'
import { RemoteError } from '@deepseek-ai/dsh-typert-protocol'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as childProcess from 'node:child_process'

vi.mock('node:child_process', async () => {
  const actual = await vi.importActual<typeof import('node:child_process')>('node:child_process')
  return { ...actual, spawn: vi.fn() }
})

/** One queued fake child process outcome. */
interface FakeOutcome {
  readonly stdout?: string
  readonly code?: number
  readonly error?: Error
}

/**
 * Fake `ChildProcess` good enough for the code under test (only `.on`/`.emit`, `.stdout.on`/`.emit`,
 * and `.kill()` are exercised): emits `data` then `close`/`error` on the next microtask.
 */
function fakeChild(outcome: FakeOutcome): childProcess.ChildProcess {
  const stdout = new EventEmitter()
  // Test double, not a real ChildProcess: matches the existing precedent at
  // packages/sdk/client/tests/dispose.spec.ts for the same situation (mocking
  // node:child_process's return value with only the members production code reads).
  const emitter = Object.assign(new EventEmitter(), { stdout, kill: vi.fn() }) as unknown as childProcess.ChildProcess
  Promise.resolve().then(() => {
    if (outcome.stdout !== undefined) stdout.emit('data', Buffer.from(outcome.stdout))
    if (outcome.error) emitter.emit('error', outcome.error)
    else emitter.emit('close', outcome.code ?? 0)
  })
  return emitter
}

describe('PlexarUpdate', () => {
  let root: Context
  let spawnMock: ReturnType<typeof vi.fn>
  let queue: FakeOutcome[]

  beforeEach(() => {
    root = new Context()
    queue = []
    spawnMock = vi.mocked(childProcess.spawn)
    spawnMock.mockImplementation(() => {
      const next = queue.shift()
      if (!next) throw new Error('unexpected spawn call: fixture queue is empty')
      return fakeChild(next)
    })
  })

  afterEach(async () => {
    try {
      await root.fiber.dispose()
    } catch {
      // ignored: the disposal test already disposed `root` itself
    }
    vi.restoreAllMocks()
  })

  /** Queue the calls `computeStatus()` makes while current: branch, local HEAD, local manifest, remote ls-remote. */
  function queueStatus(branch: string, head: string, remote: string): void {
    queue.push({ stdout: branch }, { stdout: head }, { stdout: '{"version":"0.1.0"}' }, { stdout: remote })
  }

  /** Queue an available check: remote `bbbbbbbbbb` is ahead, then the fetch and the remote manifest read. */
  function queueAvailable(): void {
    queue.push(
      { stdout: 'main' }, { stdout: 'aaaaaaaaaa' }, { stdout: '{"version":"0.1.0"}' }, { stdout: 'bbbbbbbbbb' }, { code: 1 },
      { stdout: '' }, { stdout: '{"version":"0.2.0"}' },
    )
  }

  /** Drain the microtask queue enough for every queued fake child to settle. */
  async function flush(): Promise<void> {
    for (let i = 0; i < 40; i++) await Promise.resolve()
  }

  async function load(checkIntervalMs = 3600000): Promise<import('../src/update.ts').PlexarUpdate> {
    const { PlexarUpdate } = await import('../src/update.ts')
    const service = new PlexarUpdate(root, { checkIntervalMs })
    await flush()
    return service
  }

  it('does not block load on the initial background check', async () => {
    queueStatus('main', 'aaaaaaaaaa', 'aaaaaaaaaa')
    const { PlexarUpdate } = await import('../src/update.ts')
    const service = new PlexarUpdate(root, { checkIntervalMs: 3600000 })
    // Constructed synchronously; the check has not resolved yet, so status still reads the initial default.
    expect(await service.status()).toEqual({ state: 'current' })
    await flush()
  })

  it('reports current when local HEAD matches the remote tip', async () => {
    queueStatus('main', 'aaaaaaaaaa', 'aaaaaaaaaa')
    const service = await load()
    expect(await service.status()).toMatchObject({ state: 'current', remote: 'aaaaaaaaaa', branch: 'main' })
  })

  it('reports available when the remote tip is ahead and not an ancestor', async () => {
    queueAvailable()
    const service = await load()
    expect(await service.status()).toMatchObject({
      state: 'available', remote: 'bbbbbbbbbb', branch: 'main', localVersion: '0.1.0', remoteVersion: '0.2.0',
    })
  })

  it('re-checks on the configured interval', async () => {
    vi.useFakeTimers()
    try {
      queueStatus('main', 'aaaaaaaaaa', 'aaaaaaaaaa')
      const service = await load(1000)
      expect(await service.status()).toMatchObject({ state: 'current' })

      queueAvailable()
      await vi.advanceTimersByTimeAsync(1000)
      expect(await service.status()).toMatchObject({ state: 'available' })
    } finally {
      vi.useRealTimers()
    }
  })

  it('clears the periodic timer on disposal', async () => {
    vi.useFakeTimers()
    try {
      queueStatus('main', 'aaaaaaaaaa', 'aaaaaaaaaa')
      await load(1000)
      const before = spawnMock.mock.calls.length
      await root.fiber.dispose()
      await vi.advanceTimersByTimeAsync(5000)
      expect(spawnMock.mock.calls.length).toBe(before)
    } finally {
      vi.useRealTimers()
    }
  })

  it('transitions current -> available -> updating -> restart-required across apply()', async () => {
    queueAvailable()
    const service = await load()
    expect(await service.status()).toMatchObject({ state: 'available' })

    // apply(): dirty check, git pull, pnpm install, tsc build, then a final computeStatus().
    queue.push(
      { stdout: '' },
      { code: 0 },
      { code: 0 },
      { code: 0 },
      { stdout: 'main' }, { stdout: 'bbbbbbbbbb' }, { stdout: '{"version":"0.2.0"}' }, { stdout: 'bbbbbbbbbb' },
    )
    const applyPromise = service.apply()
    const result = await applyPromise
    expect(result).toMatchObject({ state: 'restart-required', remote: 'bbbbbbbbbb' })
    expect(await service.status()).toMatchObject({ state: 'restart-required' })
  })

  it('coalesces a concurrent apply() call onto the in-flight run', async () => {
    queueStatus('main', 'aaaaaaaaaa', 'aaaaaaaaaa')
    const service = await load()
    queue.push(
      { stdout: '' },
      { code: 0 },
      { code: 0 },
      { code: 0 },
      { stdout: 'main' }, { stdout: 'aaaaaaaaaa' }, { stdout: 'aaaaaaaaaa' },
    )
    const first = service.apply()
    const second = service.apply()
    // A concurrent call while one is in flight coalesces onto the same promise rather than
    // starting a second `git pull`/`pnpm install`/build run against the same working tree.
    expect(second).toBe(first)
    await first
    await second
    // Exactly the seven spawn calls of one run: nothing queued for a second run remains.
    expect(queue.length).toBe(0)
  })

  it('reports failed with the error populated when a step fails', async () => {
    queueStatus('main', 'aaaaaaaaaa', 'aaaaaaaaaa')
    const service = await load()
    queue.push({ stdout: '' }, { code: 1 })
    const result = await service.apply()
    expect(result.state).toBe('failed')
    expect(result.error).toContain('git pull')
  })

  it('rejects restart() without PLEXAR_DESKTOP=1', async () => {
    delete process.env['PLEXAR_DESKTOP']
    queueStatus('main', 'aaaaaaaaaa', 'aaaaaaaaaa')
    const service = await load()
    await expect(service.restart()).rejects.toBeInstanceOf(RemoteError)
  })

  it('exits the process with code 75 when PLEXAR_DESKTOP=1', async () => {
    process.env['PLEXAR_DESKTOP'] = '1'
    const exit = vi.spyOn(process, 'exit').mockImplementation(() => undefined as never)
    try {
      queueStatus('main', 'aaaaaaaaaa', 'aaaaaaaaaa')
      const service = await load()
      await service.restart()
      await new Promise((resolvePromise) => { setTimeout(resolvePromise, 10) })
      expect(exit).toHaveBeenCalledWith(75)
    } finally {
      delete process.env['PLEXAR_DESKTOP']
    }
  })
})

describe('PlexarUpdate on an installed copy (no .git)', () => {
  let root: Context
  let installedRoot: string
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    root = new Context()
    installedRoot = mkdtempSync(join(tmpdir(), 'plexar-update-'))
    mkdirSync(join(installedRoot, 'packages', 'bundle', 'plexar'), { recursive: true })
    writeFileSync(
      join(installedRoot, 'packages', 'bundle', 'plexar', 'package.json'),
      JSON.stringify({ version: '0.1.0' }),
    )
    process.env['PLEXAR_HARNESS_ROOT'] = installedRoot
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    vi.mocked(childProcess.spawn).mockImplementation(() => {
      throw new Error('installed copy must not spawn git/pnpm')
    })
  })

  afterEach(async () => {
    await root.fiber.dispose()
    delete process.env['PLEXAR_HARNESS_ROOT']
    rmSync(installedRoot, { recursive: true, force: true })
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  async function loadInstalled(): Promise<import('../src/update.ts').PlexarUpdate> {
    const { PlexarUpdate } = await import('../src/update.ts')
    const service = new PlexarUpdate(root, { checkIntervalMs: 3600000 })
    for (let i = 0; i < 10; i++) await Promise.resolve()
    return service
  }

  it('reports available when the manifest version is newer', async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({ version: '0.2.0' }) })
    const service = await loadInstalled()
    expect(await service.status()).toMatchObject({ state: 'available', localVersion: '0.1.0', remoteVersion: '0.2.0' })
  })

  it('reports current when the manifest version is the same', async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({ version: '0.1.0' }) })
    const service = await loadInstalled()
    expect(await service.status()).toMatchObject({ state: 'current' })
  })

  it('reports current when the manifest version is older', async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({ version: '0.0.9' }) })
    const service = await loadInstalled()
    expect(await service.status()).toMatchObject({ state: 'current' })
  })

  it('reports current on a 404', async () => {
    fetchMock.mockResolvedValue({ ok: false, json: async () => ({}) })
    const service = await loadInstalled()
    expect(await service.status()).toMatchObject({ state: 'current' })
  })

  it('reports current when offline (fetch rejects)', async () => {
    fetchMock.mockRejectedValue(new Error('getaddrinfo ENOTFOUND'))
    const service = await loadInstalled()
    expect(await service.status()).toMatchObject({ state: 'current' })
  })

  it('reports current on invalid JSON', async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => { throw new Error('not json') } })
    const service = await loadInstalled()
    expect(await service.status()).toMatchObject({ state: 'current' })
  })

  it('honours the fetch timeout: an unresolved fetch aborts and reports current', async () => {
    vi.useFakeTimers()
    try {
      fetchMock.mockImplementation((_url: string, options: { signal: AbortSignal }) => new Promise((_resolvePromise, reject) => {
        options.signal.addEventListener('abort', () => { reject(new Error('aborted')) })
      }))
      const { PlexarUpdate } = await import('../src/update.ts')
      const service = new PlexarUpdate(root, { checkIntervalMs: 3600000 })
      await vi.advanceTimersByTimeAsync(5000)
      expect(await service.status()).toMatchObject({ state: 'current' })
    } finally {
      vi.useRealTimers()
    }
  })

  it('apply() fails with installer guidance instead of running git/pnpm', async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({ version: '0.1.0' }) })
    const service = await loadInstalled()
    const result = await service.apply()
    expect(result.state).toBe('failed')
    expect(result.error).toContain('https://harness.plexar.tech')
  })
})
