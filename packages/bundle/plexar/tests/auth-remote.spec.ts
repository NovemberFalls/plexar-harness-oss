/** Host sign-in status/sign-out service: mocked fetch and keychain, no real OS credential store or network. */

import { Context } from '@deepseek-ai/cordis'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

describe('PlexarAuth', () => {
  let root: Context
  let restoreEntry: (() => void) | undefined
  let restoreFetch: (() => void) | undefined

  beforeEach(() => {
    root = new Context()
    delete process.env['PLEXAR_HARNESS_KEY']
    delete process.env['PLEXAR_DESKTOP']
  })

  afterEach(async () => {
    try {
      await root.fiber.dispose()
    } catch {
      // ignored: a disposal test already disposed `root` itself
    }
    restoreEntry?.()
    restoreFetch?.()
    delete process.env['PLEXAR_HARNESS_KEY']
    delete process.env['PLEXAR_DESKTOP']
    vi.restoreAllMocks()
  })

  /** A fake keychain entry: the two mocked methods `auth-remote.ts` reads. */
  interface FakeEntry {
    getPassword: ReturnType<typeof vi.fn<() => string | null>>
    deletePassword: ReturnType<typeof vi.fn<() => boolean>>
  }

  /** Install a fake keychain entry holding `password` (or none), returning the calls made against it. */
  function fakeKeychain(password: string | undefined): FakeEntry {
    return {
      getPassword: vi.fn((): string | null => {
        if (password === undefined) throw new Error('no matching entry found')
        return password
      }),
      deletePassword: vi.fn((): boolean => {
        if (password === undefined) throw new Error('no matching entry found')
        return true
      }),
    }
  }

  /** A mocked `fetch`, typed so it can be passed straight to `_withFetch`. */
  function fakeFetch(impl: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>): ReturnType<typeof vi.fn<typeof fetch>> {
    return vi.fn<typeof fetch>(impl)
  }

  async function load(entry: ReturnType<typeof fakeKeychain>): Promise<import('../src/auth-remote.ts').PlexarAuth> {
    const mod = await import('../src/auth-remote.ts')
    restoreEntry = mod._withEntryFactory(() => entry)
    return new mod.PlexarAuth(root)
  }

  it('reports source "none" with no stored key and no env override', async () => {
    const service = await load(fakeKeychain(undefined))
    expect(await service.status()).toEqual({ signedIn: false, source: 'none' })
  })

  it('reports source "env" and fetches the email when PLEXAR_HARNESS_KEY is set', async () => {
    process.env['PLEXAR_HARNESS_KEY'] = 'env-key'
    const mod = await import('../src/auth-remote.ts')
    restoreFetch = mod._withFetch(fakeFetch(async () => new Response(JSON.stringify({ email: 'dev@example.com' }), { status: 200 })))
    const service = new mod.PlexarAuth(root)
    expect(await service.status()).toEqual({ signedIn: true, source: 'env', email: 'dev@example.com' })
  })

  it('reports source "keychain" and caches the email across repeated status() calls', async () => {
    const entry = fakeKeychain('keychain-key')
    const mod = await import('../src/auth-remote.ts')
    restoreEntry = mod._withEntryFactory(() => entry)
    const fetchMock = fakeFetch(async () => new Response(JSON.stringify({ email: 'person@example.com' }), { status: 200 }))
    restoreFetch = mod._withFetch(fetchMock)
    const service = new mod.PlexarAuth(root)
    expect(await service.status()).toEqual({ signedIn: true, source: 'keychain', email: 'person@example.com' })
    expect(await service.status()).toEqual({ signedIn: true, source: 'keychain', email: 'person@example.com' })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('signOut() refuses and does nothing when the active key came from the env override', async () => {
    process.env['PLEXAR_HARNESS_KEY'] = 'env-key'
    const entry = fakeKeychain('keychain-key')
    const mod = await import('../src/auth-remote.ts')
    restoreEntry = mod._withEntryFactory(() => entry)
    const service = new mod.PlexarAuth(root)
    expect(await service.signOut()).toEqual({ ok: false, reason: 'env' })
    expect(entry.deletePassword).not.toHaveBeenCalled()
  })

  it('signOut() revokes server-side then deletes the keychain entry', async () => {
    const entry = fakeKeychain('keychain-key')
    const mod = await import('../src/auth-remote.ts')
    restoreEntry = mod._withEntryFactory(() => entry)
    const fetchMock = fakeFetch(async () => new Response('{}', { status: 200 }))
    restoreFetch = mod._withFetch(fetchMock)
    const service = new mod.PlexarAuth(root)
    expect(await service.signOut()).toEqual({ ok: true })
    expect(fetchMock).toHaveBeenCalledWith(expect.any(URL), expect.objectContaining({ method: 'POST' }))
    expect(entry.deletePassword).toHaveBeenCalled()
  })

  it('signOut() exits the process with code 76 only under PLEXAR_DESKTOP=1', async () => {
    process.env['PLEXAR_DESKTOP'] = '1'
    const entry = fakeKeychain('keychain-key')
    const mod = await import('../src/auth-remote.ts')
    restoreEntry = mod._withEntryFactory(() => entry)
    restoreFetch = mod._withFetch(fakeFetch(async () => new Response('{}', { status: 200 })))
    const exit = vi.spyOn(process, 'exit').mockImplementation(() => undefined as never)
    const service = new mod.PlexarAuth(root)
    await service.signOut()
    await new Promise((resolvePromise) => { setTimeout(resolvePromise, 10) })
    expect(exit).toHaveBeenCalledWith(76)
  })

  it('does not exit the process when PLEXAR_DESKTOP is unset', async () => {
    const entry = fakeKeychain('keychain-key')
    const mod = await import('../src/auth-remote.ts')
    restoreEntry = mod._withEntryFactory(() => entry)
    restoreFetch = mod._withFetch(fakeFetch(async () => new Response('{}', { status: 200 })))
    const exit = vi.spyOn(process, 'exit').mockImplementation(() => undefined as never)
    const service = new mod.PlexarAuth(root)
    await service.signOut()
    await new Promise((resolvePromise) => { setTimeout(resolvePromise, 10) })
    expect(exit).not.toHaveBeenCalled()
  })
})
