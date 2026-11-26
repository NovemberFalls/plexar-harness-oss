/** What the browser half registers, how the toggle persists, and how Branch reads the Host. */

import { Context } from '@deepseek-ai/cordis'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SlotRegistry } from '@deepseek-ai/dsh-client-ui-renderer/client'
import { RemoteError, TestRemote } from '@deepseek-ai/dsh-client-test-runtime'
import { LocaleRuntime } from '@deepseek-ai/dsh-client-locale/client'
import type { SessionId } from '@deepseek-ai/dsh-session/types'
import { apply, inject } from '../src/client/index.ts'
import type { EnvironmentPanelInjected, EnvironmentRailInjected, EnvironmentToggleInjected } from '../src/client/index.ts'
import { NS } from '../src/client/locales.ts'
import { SHOWN_KEY } from '../src/client/rail-state.ts'

const SESSION = 's-1' as SessionId

afterEach(() => { vi.unstubAllGlobals() })

/** A Map-backed localStorage; the client lane has no jsdom window. */
function stubStorage(initial: Record<string, string> = {}) {
  const values = new Map(Object.entries(initial))
  const storage = {
    getItem: vi.fn((key: string) => values.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => { values.set(key, value) }),
  }
  vi.stubGlobal('localStorage', storage)
  return { values, storage }
}

function fakeLayout() {
  return { openEnvbar: vi.fn(), closeEnvbar: vi.fn(), toggleEnvbar: vi.fn() }
}

async function bench(branch: ((sessionId: SessionId) => Promise<unknown>) | null = () => Promise.resolve({ ok: true, value: { branch: 'main' } })) {
  const ctx = new Context()
  await ctx.plugin(SlotRegistry).await()
  ctx.provide('locale', new LocaleRuntime(ctx))
  const layout = fakeLayout()
  ctx.provide('layout', layout as never)
  const branchCall = vi.fn(branch ?? (() => Promise.resolve(null)))
  new TestRemote(ctx, branch === null ? {} : { environmentRail: { branch: branchCall } })
  const slots = ctx.get('slots') as SlotRegistry
  slots.register({
    name: 'root',
    children: {
      'envbar': { kind: 'single', scope: 'root' },
      'conversation.session.header.actions': { kind: 'list', scope: 'session' },
    },
  } as never, () => null)
  return { ctx, slots, layout, branchCall }
}

async function mount(branch?: ((sessionId: SessionId) => Promise<unknown>) | null) {
  const env = await bench(branch)
  const fiber = env.ctx.plugin({ inject: [...inject], apply })
  await fiber.await()
  await vi.waitFor(() => { expect(env.slots.entries('envbar.session')).toHaveLength(1) })
  const rail = (env.slots.entries('envbar')[0]!.inject as unknown as () => EnvironmentRailInjected)()
  const panel = (env.slots.entries('envbar.session')[0]!.inject as unknown as () => EnvironmentPanelInjected)()
  const toggle = (env.slots.entries('conversation.session.header.actions')[0]!.inject as unknown as () => EnvironmentToggleInjected)()
  return { ...env, fiber, rail, panel, toggle }
}

describe('ui-environment apply', () => {
  it('declares the services it requires; jobs, workspaces and its Remote stay optional', () => {
    expect(inject).toEqual(['slots', 'locale', 'layout', 'remote'])
  })

  it('occupies envbar with the rail and its Session-bound body, and adds the header toggle', async () => {
    stubStorage()
    const { slots, fiber } = await mount()
    expect(slots.entries('envbar')).toHaveLength(1)
    expect(slots.entries('envbar')[0]!.locale).toBe(NS)
    expect(slots.spec('envbar.session')).toEqual({ kind: 'single', scope: 'session-maybe' })
    const actions = slots.entries('conversation.session.header.actions')
    expect(actions).toHaveLength(1)
    expect(actions[0]!.options).toMatchObject({ id: 'environment', order: 40 })
    await fiber.dispose()
    expect(slots.entries('envbar')).toHaveLength(0)
    expect(slots.entries('conversation.session.header.actions')).toHaveLength(0)
  })

  it('starts hidden without a remembered choice', async () => {
    stubStorage()
    const { layout, toggle } = await mount()
    expect(layout.closeEnvbar).toHaveBeenCalledOnce()
    expect(layout.openEnvbar).not.toHaveBeenCalled()
    expect(toggle.hooks.railShown.getSnapshot()).toBe(false)
  })

  it('applies a remembered shown choice on start', async () => {
    stubStorage({ [SHOWN_KEY]: '1' })
    const { layout, toggle } = await mount()
    expect(layout.openEnvbar).toHaveBeenCalledOnce()
    expect(toggle.hooks.railShown.getSnapshot()).toBe(true)
  })

  it('toggles through ctx.layout and persists each result; close hides and persists', async () => {
    const { values } = stubStorage()
    const { layout, toggle, rail, panel } = await mount()
    toggle.toggle()
    expect(layout.toggleEnvbar).toHaveBeenCalledOnce()
    expect(values.get(SHOWN_KEY)).toBe('1')
    expect(toggle.hooks.railShown.getSnapshot()).toBe(true)
    expect(panel.hooks.railShown.getSnapshot()).toBe(true)
    toggle.toggle()
    expect(values.get(SHOWN_KEY)).toBe('0')
    toggle.toggle()
    rail.close()
    expect(layout.closeEnvbar).toHaveBeenCalledTimes(2)
    expect(values.get(SHOWN_KEY)).toBe('0')
    expect(toggle.hooks.railShown.getSnapshot()).toBe(false)
  })

  it('keeps working when browser storage throws', async () => {
    vi.stubGlobal('localStorage', {
      getItem: () => { throw new Error('blocked') },
      setItem: () => { throw new Error('blocked') },
    })
    const { toggle } = await mount()
    expect(toggle.hooks.railShown.getSnapshot()).toBe(false)
    expect(() => { toggle.toggle() }).not.toThrow()
    expect(toggle.hooks.railShown.getSnapshot()).toBe(true)
  })

  it('reads the branch from the Host with the Session id only', async () => {
    stubStorage()
    const { panel, branchCall } = await mount()
    await expect(panel.readBranch(SESSION)).resolves.toBe('main')
    expect(branchCall).toHaveBeenCalledWith(SESSION)
  })

  it('reads a failed or absent Host answer as no branch', async () => {
    stubStorage()
    const failed = await mount(() => Promise.resolve({ ok: false, error: new RemoteError('gateway/internal', 'down', {}) }))
    await expect(failed.panel.readBranch(SESSION)).resolves.toBeNull()
    const thrown = await mount(() => Promise.reject(new Error('no namespace')))
    await expect(thrown.panel.readBranch(SESSION)).resolves.toBeNull()
  })

  it('loads and reads no branch when the profile has no Host half (its Remote namespace is absent)', async () => {
    stubStorage()
    const { panel, slots } = await mount(null)
    expect(slots.entries('envbar')).toHaveLength(1)
    await expect(panel.readBranch(SESSION)).resolves.toBeNull()
  })

  it('renders without the optional jobs and workspaces services', async () => {
    stubStorage()
    const { panel } = await mount()
    expect(panel.hooks.workspaceList.getSnapshot()).toBeUndefined()
    expect(panel.hooks.jobRows.getSnapshot()).toBeUndefined()
    expect(() => { panel.hooks.jobRows.subscribe(() => {})() }).not.toThrow()
    expect(() => { panel.watchRows(SESSION)() }).not.toThrow()
  })

  it('reads the optional services once they are provided', async () => {
    stubStorage()
    const { ctx, panel } = await mount()
    const rows = { rows: { [SESSION]: [] }, observed: {} }
    const stop = vi.fn()
    const watchRows = vi.fn(() => stop)
    ctx.provide('jobs', { state: { getSnapshot: () => rows, subscribe: () => () => {} }, watchRows } as never)
    expect(panel.hooks.jobRows.getSnapshot()).toBe(rows)
    panel.watchRows(SESSION)()
    expect(watchRows).toHaveBeenCalledWith(SESSION)
    expect(stop).toHaveBeenCalledOnce()
  })
})
