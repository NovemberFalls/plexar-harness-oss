/** What the browser half registers, which catalog features become rows, and toggling wired to the Remote. */

import { describe, expect, it, onTestFinished, vi } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import type { BundleInfo, PluginEntryId, PluginInfo } from '@deepseek-ai/dsh-api-remotes/client'
import { resolveSlotLabel } from '@deepseek-ai/dsh-client-ui-slots'
import { SlotRegistry } from '@deepseek-ai/dsh-client-ui-renderer/client'
import { LocaleRuntime } from '@deepseek-ai/dsh-client-locale/client'
import { TestRemote } from '@deepseek-ai/dsh-client-test-runtime'
import { apply, inject } from '../src/client/index.ts'
import type { FeaturesSectionInjected, ModelsSectionInjected, AccountSectionInjected } from '../src/client/index.ts'

/** The plexarAuth.status() value, as the Host sends it. */
type AuthStatus = { signedIn: boolean; source: 'keychain' | 'env' | 'none'; email?: string }

function ok<T>(value: T) {
  return { ok: true as const, value }
}

const PLEXAR_BUNDLE: BundleInfo = {
  name: '@plexar/dsh-plexar', enabled: true, installed: true, optional: false, removable: false, rows: [], overrides: [],
}

const VOICE_BUNDLE: BundleInfo = {
  name: '@deepseek-ai/dsh-experimental-voice-input-bundle', enabled: false, installed: false, optional: true, removable: true, rows: [], overrides: [],
}

const OTHER_BUNDLE: BundleInfo = {
  name: '@deepseek-ai/dsh-unknown-thing', enabled: true, installed: true, optional: true, removable: true, rows: [], overrides: [],
}

function plugin(moduleName: string, enabled: boolean, readOnly = false): PluginInfo {
  const base = { entryId: `e-${moduleName}` as PluginEntryId, moduleName, enabled, fiberPhase: 'active' }
  return (readOnly ? { ...base, readOnlyReason: 'unaddressable' } : { ...base, patchId: `p-${moduleName}` }) as PluginInfo
}

const PLUGINS: readonly PluginInfo[] = [
  plugin('@deepseek-ai/dsh-browser-use', true),
  plugin('@plexar/dsh-plexar/browser-bridge', false),
  plugin('@deepseek-ai/dsh-tool-web', true, true),
  plugin('@deepseek-ai/dsh-unknown-tool', true),
]

/** The Host tool-toggle namespace as `settings.describe` reports it. */
const TOGGLES_VIEW = {
  ns: 'plexar-feature-toggles',
  value: { off: ['files'] },
}

async function benchSlots(bundles: readonly BundleInfo[] = [PLEXAR_BUNDLE, VOICE_BUNDLE, OTHER_BUNDLE]) {
  const ctx = new Context()
  onTestFinished(async () => { await ctx.fiber.dispose() })
  await ctx.plugin(SlotRegistry).await()
  const slots = ctx.get('slots') as SlotRegistry
  const locale = new LocaleRuntime(ctx)
  locale.setLocale('en')
  ctx.provide('locale', locale)
  const setBundleEnabled = vi.fn(() => Promise.resolve(ok({ changed: true, application: 'applied', stage: 'enable', target: 'x' })))
  const listBundles = vi.fn(() => Promise.resolve(ok(bundles)))
  const listPlugins = vi.fn(() => Promise.resolve(ok(PLUGINS)))
  const setPluginEnabled = vi.fn(() => Promise.resolve(ok({ changed: true, application: 'applied', stage: 'enable', target: 'x' })))
  const describe = vi.fn(() => Promise.resolve(ok({ writable: true, hasDocument: true, namespaces: [TOGGLES_VIEW] })))
  const update = vi.fn(() => Promise.resolve(ok(TOGGLES_VIEW)))
  const inventory = { list: vi.fn(() => Promise.resolve(ok({ entries: [], managementAvailable: true }))) }
  const plexarUpdate = {
    status: vi.fn(() => Promise.resolve(ok({ state: 'current' as const }))),
    apply: vi.fn(() => Promise.resolve(ok({ state: 'restart-required' as const }))),
    restart: vi.fn(() => Promise.resolve(ok(undefined))),
  }
  const plexarModels = {
    list: vi.fn(() => Promise.resolve(ok({
      source: 'plexar' as const,
      chat: [{ id: 'qwen3.8-27b', name: 'Qwen3.8 27B', serving: true, contextWindow: 131072, input: ['text', 'image'] }],
      classifiers: [{ id: 'guard-1', name: 'Guard', serving: true, contextWindow: null, input: null }],
    }))),
  }
  const plexarAuth = {
    status: vi.fn(() => Promise.resolve(ok<AuthStatus>({ signedIn: true, source: 'keychain', email: 'person@example.com' }))),
    signOut: vi.fn(() => Promise.resolve(ok({ ok: true as const }))),
  }
  const remote = new TestRemote(ctx, {
    pluginInventory: inventory,
    pluginManager: { listBundles, setBundleEnabled, listPlugins, setPluginEnabled },
    settings: { describe, update },
    plexarUpdate,
    plexarModels,
    plexarAuth,
  })
  // The update notice's, the Models section's, and the Account section's own Remote contribution
  // is generator output this bench does not build; TestRemote's $mount deliberately rejects for
  // that ("needs the real Client Remote service"), so this spec scripts a no-op mount instead,
  // matching `remote.plexarUpdate` / `remote.plexarModels` / `remote.plexarAuth` above being
  // provided directly.
  remote.$mount = () => Promise.resolve(() => Promise.resolve())
  ctx.provide('plexarAurora', { isEnabled: () => true, setEnabled: vi.fn() })
  return { ctx, slots, listBundles, setBundleEnabled, setPluginEnabled, update, inventory, plexarUpdate, plexarModels, plexarAuth }
}

/** The Settings shell's section slot and the sidebar footer action slot, as their owners declare them. */
function declareRoot(slots: SlotRegistry): () => void {
  return slots.register({
    name: 'root',
    children: {
      'settings.section': { kind: 'list', scope: 'root' },
      'sidebar.footer.action': { kind: 'list', scope: 'root' },
    },
  } as never, () => null)
}

/** Narrow the registered inject face to the Features section's shape. */
function featuresFace(raw: Record<string, unknown>): FeaturesSectionInjected {
  if (!isFeaturesFace(raw)) throw new Error('features section inject face is missing hooks or ensure')
  return raw
}

/** Mount the Features face and wait for its first Host read. */
async function readyFace(slots: SlotRegistry): Promise<FeaturesSectionInjected> {
  const features = slots.entries('settings.section').find(entry => entry.options.id === 'plexar-features')!
  const face = featuresFace(features.inject!())
  face.ensure()
  await vi.waitFor(() => { expect(face.hooks.features.getSnapshot().status).toBe('ready') })
  return face
}

/** Narrow the registered inject face to the Models section's shape. */
function modelsFace(raw: Record<string, unknown>): ModelsSectionInjected {
  if (!isModelsFace(raw)) throw new Error('models section inject face is missing hooks or ensure')
  return raw
}

function isModelsFace(raw: Record<string, unknown>): raw is Record<string, unknown> & ModelsSectionInjected {
  return typeof raw.ensure === 'function' && typeof raw.hooks === 'object' && raw.hooks !== null
}

function isFeaturesFace(raw: Record<string, unknown>): raw is Record<string, unknown> & FeaturesSectionInjected {
  return typeof raw.ensure === 'function' && typeof raw.hooks === 'object' && raw.hooks !== null
}

/** Narrow the registered inject face to the Account section's shape. */
function accountFace(raw: Record<string, unknown>): AccountSectionInjected {
  if (!isAccountFace(raw)) throw new Error('account section inject face is missing hooks or ensure')
  return raw
}

function isAccountFace(raw: Record<string, unknown>): raw is Record<string, unknown> & AccountSectionInjected {
  return typeof raw.ensure === 'function' && typeof raw.hooks === 'object' && raw.hooks !== null && typeof raw.signOut === 'function'
}

describe('ui-settings-plexar apply', () => {
  it('declares the services it uses', () => {
    expect(inject).toEqual(['slots', 'locale', 'remote', 'remote.pluginManager', 'remote.pluginInventory', 'remote.settings'])
  })

  it('registers a Features section, a Models section, and a Credits section', async () => {
    const { ctx, slots } = await benchSlots()
    declareRoot(slots)

    await ctx.plugin({ inject: [...inject], apply }).await()

    const entries = slots.entries('settings.section')
    expect(entries).toHaveLength(4)
    const ids = entries.map(entry => entry.options.id)
    expect(ids).toEqual(expect.arrayContaining(['plexar-account', 'plexar-features', 'plexar-models', 'plexar-credits']))
    const account = entries.find(entry => entry.options.id === 'plexar-account')!
    expect(resolveSlotLabel(account.options.label)).toBe('Account')
    const features = entries.find(entry => entry.options.id === 'plexar-features')!
    expect(resolveSlotLabel(features.options.label)).toBe('Features')
    const models = entries.find(entry => entry.options.id === 'plexar-models')!
    expect(resolveSlotLabel(models.options.label)).toBe('Plexar models')
    const credits = entries.find(entry => entry.options.id === 'plexar-credits')!
    expect(resolveSlotLabel(credits.options.label)).toBe('Credits')
  })

  it('reads the plexarAuth status into the Account section on first render', async () => {
    const { ctx, slots, plexarAuth } = await benchSlots()
    declareRoot(slots)
    await ctx.plugin({ inject: [...inject], apply }).await()

    const entries = slots.entries('settings.section')
    const account = entries.find(entry => entry.options.id === 'plexar-account')!
    const face = accountFace(account.inject!())
    face.ensure()
    await vi.waitFor(() => { expect(face.hooks.account.getSnapshot().status).toBe('ready') })
    expect(plexarAuth.status).toHaveBeenCalledTimes(1)
    const state = face.hooks.account.getSnapshot()
    if (state.status !== 'ready') throw new Error('expected ready')
    expect(state).toMatchObject({ signedIn: true, source: 'keychain', email: 'person@example.com' })
  })

  it('signs out through the Account section face and re-reads status', async () => {
    const { ctx, slots, plexarAuth } = await benchSlots()
    declareRoot(slots)
    await ctx.plugin({ inject: [...inject], apply }).await()

    const entries = slots.entries('settings.section')
    const account = entries.find(entry => entry.options.id === 'plexar-account')!
    const face = accountFace(account.inject!())
    face.ensure()
    await vi.waitFor(() => { expect(face.hooks.account.getSnapshot().status).toBe('ready') })

    plexarAuth.status.mockReturnValueOnce(Promise.resolve(ok<AuthStatus>({ signedIn: false, source: 'none' })))
    const result = await face.signOut()
    expect(result).toEqual({ ok: true })
    expect(plexarAuth.signOut).toHaveBeenCalledTimes(1)
    expect(plexarAuth.status).toHaveBeenCalledTimes(2)
  })

  it('shows catalog features present in the profile, grouped', async () => {
    const { ctx, slots } = await benchSlots()
    declareRoot(slots)
    await ctx.plugin({ inject: [...inject], apply }).await()
    const face = await readyFace(slots)

    const groups = face.hooks.features.getSnapshot().groups
    expect(groups.map(group => [group.title, group.rows.map(row => [row.id, row.enabled])])).toEqual([
      ['Coding', [['shell', true], ['files', false]]],
      ['Web', [['webSearch', true], ['browser', true], ['useMyChrome', true]]],
      ['Helper agents', [['subagents', true], ['workflows', true]]],
      ['Planning', [['todos', true], ['goals', true]]],
      ['Background work', [['jobs', true], ['skills', true]]],
      ['Appearance', [['aurora', true]]],
      ['Input', [['voiceInput', false]]],
    ])
    expect(groups[0]!.rows[0]!.name).toBe('Terminal commands')
    expect(groups.at(-1)!.rows[0]!.description).toContain('never leaves the machine')
  })

  it('turns a tool feature off by adding it to the Host off setting', async () => {
    const { ctx, slots, update } = await benchSlots()
    declareRoot(slots)
    await ctx.plugin({ inject: [...inject], apply }).await()
    const face = await readyFace(slots)

    face.setEnabled('shell', false)
    await vi.waitFor(() => { expect(update).toHaveBeenCalledWith('plexar-feature-toggles', { off: ['files', 'shell'] }, undefined) })
  })

  it('turns a tool feature on by removing it from the Host off setting', async () => {
    const { ctx, slots, update } = await benchSlots()
    declareRoot(slots)
    await ctx.plugin({ inject: [...inject], apply }).await()
    const face = await readyFace(slots)

    face.setEnabled('files', true)
    await vi.waitFor(() => { expect(update).toHaveBeenCalledWith('plexar-feature-toggles', { off: [] }, undefined) })
  })

  it('switches a plugin feature by setting every one of its plugins that differs', async () => {
    const { ctx, slots, setPluginEnabled } = await benchSlots()
    declareRoot(slots)
    await ctx.plugin({ inject: [...inject], apply }).await()
    const face = await readyFace(slots)

    face.setEnabled('browser', true)
    await vi.waitFor(() => { expect(setPluginEnabled).toHaveBeenCalledTimes(1) })
    expect(setPluginEnabled).toHaveBeenCalledWith('e-@plexar/dsh-plexar/browser-bridge', true)
  })

  it('switches a bundle feature through setBundleEnabled', async () => {
    const { ctx, slots, setBundleEnabled } = await benchSlots()
    declareRoot(slots)
    await ctx.plugin({ inject: [...inject], apply }).await()
    const face = await readyFace(slots)

    face.setEnabled('voiceInput', true)
    await vi.waitFor(() => { expect(setBundleEnabled).toHaveBeenCalledWith('@deepseek-ai/dsh-experimental-voice-input-bundle', true) })
  })

  it('reads the plexarModels roster into the Models section on first render', async () => {
    const { ctx, slots, plexarModels } = await benchSlots()
    declareRoot(slots)
    await ctx.plugin({ inject: [...inject], apply }).await()

    const entries = slots.entries('settings.section')
    const models = entries.find(entry => entry.options.id === 'plexar-models')!
    const face = modelsFace(models.inject!())
    face.ensure()
    await vi.waitFor(() => { expect(face.hooks.models.getSnapshot().status).toBe('ready') })
    expect(plexarModels.list).toHaveBeenCalledTimes(1)
    const state = face.hooks.models.getSnapshot()
    if (state.status !== 'ready') throw new Error('expected ready')
    expect(state.chat.map(row => row.id)).toEqual(['qwen3.8-27b'])
    expect(state.classifiers.map(row => row.id)).toEqual(['guard-1'])
  })

  it('collapses all four sections on teardown', async () => {
    const { ctx, slots } = await benchSlots()
    declareRoot(slots)
    const fiber = ctx.plugin({ inject: [...inject], apply })
    await fiber.await()
    expect(slots.entries('settings.section')).toHaveLength(4)

    await fiber.dispose()

    expect(slots.entries('settings.section')).toHaveLength(0)
  })
})
