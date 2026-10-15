/**
 * Plexar Settings sections, browser half: a grouped Features toggle list (see
 * FEATURE_GROUPS) and a Credits page. Both register into the `settings.section`
 * slot the same way the shipped General and Built-in plugins sections do.
 *
 * Tool features read and write the `off` setting of the Host
 * `plexar-feature-toggles` plugin through `settings.describe` / `settings.update`.
 * Bundle and plugin features reuse the `pluginManager` Remote methods the
 * Plugins page uses (`listBundles` / `setBundleEnabled`, `listPlugins` /
 * `setPluginEnabled`). It adds no Host-side API of its own.
 */

// Type-only: pulls the locale plugin's Context merge (ctx.locale).
import type {} from '@deepseek-ai/dsh-client-locale/client'
// Type-only: the settings shell's SlotMap merge (the 'settings.section' entry).
import type {} from '@deepseek-ai/dsh-client-ui-settings/client'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
// Type-only: the ctx.remote Context merge.
import type {} from '@deepseek-ai/dsh-api-remotes/client'
// Type-only: the sidebar shell's SlotMap merge (the 'sidebar.footer.action' entry).
import type {} from '@deepseek-ai/dsh-client-ui-sidebar/client'
import type { Context as ClientContext } from '@deepseek-ai/cordis'
import type { BundleInfo, PluginInfo, SettingsNamespaceView } from '@deepseek-ai/dsh-api-remotes/client'
import plexarUpdateRemote from '@plexar/dsh-plexar/remote'
import type { UpdateStatus } from '@plexar/dsh-plexar/update'
import type { PlexarModelsView } from '@plexar/dsh-plexar/models'
import type { AuthStatus } from '@plexar/dsh-plexar/auth-remote'
import { AccountSection } from './AccountSection.tsx'
import type { AccountSectionInjected, AccountState } from './AccountSection.tsx'
import { FeaturesSection } from './FeaturesSection.tsx'
import type { FeaturesSectionInjected, FeatureGroupRows, FeatureRow, FeaturesState } from './FeaturesSection.tsx'
import { CreditsSection } from './CreditsSection.tsx'
import { ModelsSection } from './ModelsSection.tsx'
import type { ModelsSectionInjected, ModelsState } from './ModelsSection.tsx'
import { UpdateNotice } from './UpdateNotice.tsx'
import type { UpdateNoticeInjected, UpdateNoticeState } from './UpdateNotice.tsx'
import { FEATURE_GROUPS } from './catalog.ts'
// Type-only: the ctx.plexarAurora Context merge (provided by the Plexar brand plugin, when loaded).
import type {} from '@plexar/dsh-client-ui-brand/client'
import type { FeatureSpec } from './catalog.ts'
import { featuresEn, featuresZh, creditsEn, creditsZh, modelsEn, modelsZh, updateEn, updateZh, accountEn, accountZh } from './locales.ts'
import type { FeaturesLocaleKey } from './locales.ts'

export type { FeatureGroupRows, FeatureRow, FeaturesSectionInjected, FeaturesState } from './FeaturesSection.tsx'
export type { ModelsSectionInjected, ModelsState, ModelRow as ModelsModelRow } from './ModelsSection.tsx'
export type { AccountSectionInjected, AccountState, AccountSource } from './AccountSection.tsx'
export type { UpdateNoticeInjected, UpdateNoticeState } from './UpdateNotice.tsx'
export { FEATURE_GROUPS } from './catalog.ts'
export type { FeatureGroup, FeatureSpec } from './catalog.ts'

/** Dictionary namespace for the Features section. */
const FEATURES_NS = 'settings.plexar.features'
/** Dictionary namespace for the Credits section. */
const CREDITS_NS = 'settings.plexar.credits'
/** Dictionary namespace for the Models section. */
const MODELS_NS = 'settings.plexar.models'
/** Dictionary namespace for the sidebar update notice. */
const UPDATE_NS = 'settings.plexar.update'
/** Dictionary namespace for the Account section. */
const ACCOUNT_NS = 'settings.plexar.account'
/** Poll interval for the sidebar update notice, in milliseconds. */
const UPDATE_POLL_MS = 60000

/** Settings namespace of the Host `plexar-feature-toggles` plugin. */
const TOGGLES_NS = 'plexar-feature-toggles'

/** Required services (cordis fiber inject). */
export const inject = [
  'slots', 'locale', 'remote', 'remote.pluginManager', 'remote.pluginInventory', 'remote.settings',
]

/** Translate seat for the Features namespace. */
type Translate = (key: FeaturesLocaleKey) => string

/** One Host read, kept until the next read or locale change invalidates it. */
type HostRead = { readonly status: 'loading' | 'unavailable' }
  | { readonly status: 'ready'; readonly bundles: readonly BundleInfo[]; readonly plugins: readonly PluginInfo[]; readonly toggles: ToolToggles | undefined }

/** The Host tool-toggle setting: the tool feature ids turned off. */
interface ToolToggles {
  readonly off: readonly string[]
}

/**
 * Read the tool-toggle setting from its namespace view. The view carries only
 * the live `off` field; the Host config owns which tool ids each feature hides.
 * @param view - the `plexar-feature-toggles` namespace view, when mounted.
 * @returns the off list, or undefined when the Host plugin is not mounted.
 */
function readToggles(view: SettingsNamespaceView | undefined): ToolToggles | undefined {
  if (view === undefined) return undefined
  const off = typeof view.value === 'object' && view.value !== null && !Array.isArray(view.value) ? view.value.off : undefined
  return { off: Array.isArray(off) ? off.filter((id): id is string => typeof id === 'string') : [] }
}

/** The profile plugins a feature switches: present and addressable by the profile patch. */
function switchablePlugins(spec: FeatureSpec, plugins: readonly PluginInfo[]): PluginInfo[] {
  const modules = spec.modules ?? []
  return plugins.filter(plugin => modules.includes(plugin.moduleName) && plugin.readOnlyReason === undefined)
}

/**
 * Reads and toggles the catalog's features for the Features section, caching
 * the localized projection until the read or the locale changes.
 */
class FeaturesController {
  private read: HostRead = { status: 'loading' }
  private busy = new Set<string>()
  private loaded = false
  private listeners = new Set<() => void>()
  private cache: { read: HostRead; busy: number; revision: number; state: FeaturesState } | undefined
  private busyRevision = 0

  constructor(private readonly ctx: ClientContext) {}

  /** Build the face the Features section slot entry injects. */
  inject(t: Translate): FeaturesSectionInjected {
    return {
      hooks: {
        features: {
          getSnapshot: () => this.snapshot(t),
          subscribe: (listener) => {
            this.listeners.add(listener)
            const offLocale = this.ctx.locale.subscribe(listener)
            return () => { this.listeners.delete(listener); offLocale() }
          },
        },
      },
      ensure: () => { if (!this.loaded) { this.loaded = true; void this.load() } },
      setEnabled: (id, enabled) => { void this.setEnabled(id, enabled) },
    }
  }

  private snapshot(t: Translate): FeaturesState {
    const revision = this.ctx.locale.getSnapshot().revision
    const cache = this.cache
    const fresh = cache !== undefined && cache.read === this.read && cache.busy === this.busyRevision && cache.revision === revision
    if (fresh) return cache.state
    const state = this.project(t)
    this.cache = { read: this.read, busy: this.busyRevision, revision, state }
    return state
  }

  private project(t: Translate): FeaturesState {
    const read = this.read
    if (read.status !== 'ready') return { status: read.status, groups: [] }
    const groups: FeatureGroupRows[] = []
    for (const group of FEATURE_GROUPS) {
      const rows: FeatureRow[] = []
      for (const spec of group.features) {
        let enabled: boolean
        if (spec.aurora === true) {
          const aurora = this.ctx.get('plexarAurora')
          if (aurora === undefined) continue
          enabled = aurora.isEnabled()
        } else if (spec.tools === true) {
          if (read.toggles === undefined) continue
          enabled = !read.toggles.off.includes(spec.id)
        } else if (spec.bundle !== undefined) {
          const bundle = read.bundles.find(row => row.name === spec.bundle)
          if (bundle === undefined) continue
          enabled = bundle.enabled
        } else {
          const plugins = switchablePlugins(spec, read.plugins)
          if (plugins.length === 0) continue
          enabled = plugins.some(plugin => plugin.enabled)
        }
        rows.push({ id: spec.id, name: t(spec.nameKey), description: t(spec.descriptionKey), enabled, busy: this.busy.has(spec.id) })
      }
      if (rows.length > 0) groups.push({ id: group.id, title: t(group.titleKey), rows })
    }
    return { status: 'ready', groups }
  }

  private notify(): void {
    for (const listener of this.listeners) listener()
  }

  private async load(): Promise<void> {
    const inventory = await this.ctx.remote.pluginInventory.list()
    if (!inventory.ok || inventory.value.managementAvailable !== true) {
      this.read = { status: 'unavailable' }
      this.notify()
      return
    }
    const [bundles, plugins, settings] = await Promise.all([
      this.ctx.remote.pluginManager.listBundles(),
      this.ctx.remote.pluginManager.listPlugins(),
      this.ctx.remote.settings.describe(),
    ])
    const toggles = settings.ok ? readToggles(settings.value.namespaces.find(row => row.ns === TOGGLES_NS)) : undefined
    this.read = bundles.ok && plugins.ok
      ? { status: 'ready', bundles: bundles.value, plugins: plugins.value, toggles }
      : { status: 'unavailable' }
    this.notify()
  }

  private async setEnabled(id: string, enabled: boolean): Promise<void> {
    const spec = FEATURE_GROUPS.flatMap(group => group.features).find(feature => feature.id === id)
    if (spec === undefined || this.busy.has(id) || this.read.status !== 'ready') return
    if (spec.aurora === true) {
      this.ctx.get('plexarAurora')?.setEnabled(enabled)
      this.busyRevision++
      this.notify()
      return
    }
    const targets = switchablePlugins(spec, this.read.plugins).filter(plugin => plugin.enabled !== enabled)
    const toggles = this.read.toggles
    this.busy.add(id)
    this.busyRevision++
    this.notify()
    try {
      if (spec.tools === true && toggles !== undefined) {
        const off = toggles.off.filter(featureId => featureId !== id)
        await this.ctx.remote.settings.update(TOGGLES_NS, { off: enabled ? off : [...off, id] }, undefined)
      }
      if (spec.bundle !== undefined) await this.ctx.remote.pluginManager.setBundleEnabled(spec.bundle, enabled)
      // One reload per plugin: the manager applies each change before the next.
      for (const plugin of targets) await this.ctx.remote.pluginManager.setPluginEnabled(plugin.entryId, enabled)
    } finally {
      this.busy.delete(id)
      this.busyRevision++
      await this.load()
    }
  }
}

/** Project a Host {@link UpdateStatus} into the notice's render states. */
function projectUpdateStatus(status: UpdateStatus): UpdateNoticeState {
  if (status.state === 'failed') return status.error === undefined ? { state: 'failed' } : { state: 'failed', error: status.error }
  if (status.state === 'available') {
    return status.localVersion === undefined || status.remoteVersion === undefined
      ? { state: 'available' }
      : { state: 'available', current: status.localVersion, latest: status.remoteVersion }
  }
  return { state: status.state }
}

/**
 * Polls the Host `plexarUpdate` Remote on a fixed interval and after a
 * successful `apply()`, and drives the sidebar footer notice from the result.
 */
class UpdateController {
  private read: UpdateNoticeState = { state: 'current' }
  private listeners = new Set<() => void>()

  constructor(private readonly ctx: ClientContext) {}

  /** Build the face the notice slot entry injects. */
  inject(): UpdateNoticeInjected {
    return {
      hooks: {
        status: {
          getSnapshot: () => this.read,
          subscribe: (listener) => { this.listeners.add(listener); return () => { this.listeners.delete(listener) } },
        },
      },
      apply: () => { void this.applyUpdate() },
      restart: () => { void this.restartHost() },
    }
  }

  /** Start polling; returns the disposer. */
  start(): () => void {
    void this.poll()
    const timer = setInterval(() => { void this.poll() }, UPDATE_POLL_MS)
    return () => clearInterval(timer)
  }

  private notify(): void {
    for (const listener of this.listeners) listener()
  }

  private async poll(): Promise<void> {
    const result = await this.ctx.remote.plexarUpdate.status()
    if (result.ok) { this.read = projectUpdateStatus(result.value); this.notify() }
  }

  private async applyUpdate(): Promise<void> {
    await this.ctx.remote.plexarUpdate.apply()
    await this.poll()
  }

  private async restartHost(): Promise<void> {
    await this.ctx.remote.plexarUpdate.restart()
  }
}

/** Project a Host {@link PlexarModelsView} into the section's render state. */
function projectModelsView(view: PlexarModelsView): ModelsState {
  return view.source === 'unavailable' ? { status: 'unavailable' } : { status: 'ready', chat: view.chat, classifiers: view.classifiers }
}

/**
 * Reads the Host `plexarModels` Remote once on first render; the roster does
 * not change over the Host's lifetime, so there is nothing to poll.
 */
class ModelsController {
  private read: ModelsState = { status: 'loading' }
  private loaded = false
  private listeners = new Set<() => void>()

  constructor(private readonly ctx: ClientContext) {}

  /** Build the face the Models section slot entry injects. */
  inject(): ModelsSectionInjected {
    return {
      hooks: {
        models: {
          getSnapshot: () => this.read,
          subscribe: (listener) => { this.listeners.add(listener); return () => { this.listeners.delete(listener) } },
        },
      },
      ensure: () => { if (!this.loaded) { this.loaded = true; void this.load() } },
    }
  }

  private notify(): void {
    for (const listener of this.listeners) listener()
  }

  private async load(): Promise<void> {
    const result = await this.ctx.remote.plexarModels.list()
    this.read = result.ok ? projectModelsView(result.value) : { status: 'unavailable' }
    this.notify()
  }
}

/** Project a Host {@link AuthStatus} into the section's render state. */
function projectAuthStatus(status: AuthStatus): AccountState {
  return { status: 'ready', signedIn: status.signedIn, source: status.source, ...status.email === undefined ? {} : { email: status.email } }
}

/**
 * Reads the Host `plexarAuth` Remote once on first render and drives the Settings Account block;
 * `signOut` re-reads status after a successful call so a desktop app that stays alive (not
 * running under `PLEXAR_DESKTOP=1`) reflects the signed-out state immediately.
 */
class AccountController {
  private read: AccountState = { status: 'loading' }
  private loaded = false
  private listeners = new Set<() => void>()

  constructor(private readonly ctx: ClientContext) {}

  /** Build the face the Account section slot entry injects. */
  inject(): AccountSectionInjected {
    return {
      hooks: {
        account: {
          getSnapshot: () => this.read,
          subscribe: (listener) => { this.listeners.add(listener); return () => { this.listeners.delete(listener) } },
        },
      },
      ensure: () => { if (!this.loaded) { this.loaded = true; void this.load() } },
      signOut: () => this.signOut(),
    }
  }

  private notify(): void {
    for (const listener of this.listeners) listener()
  }

  private async load(): Promise<void> {
    const result = await this.ctx.remote.plexarAuth.status()
    this.read = result.ok ? projectAuthStatus(result.value) : { status: 'unavailable' }
    this.notify()
  }

  private async signOut(): Promise<{ readonly ok: boolean }> {
    const result = await this.ctx.remote.plexarAuth.signOut()
    if (!result.ok) return { ok: false }
    if (!result.value.ok) return { ok: false }
    await this.load()
    return { ok: true }
  }
}

/**
 * Register the sidebar update notice and the Models section. Split out
 * because both mount the package's Remote contribution ({@link plexarUpdateRemote},
 * which carries every `TypertRemoteService` this package declares, `plexarUpdate`,
 * `plexarModels`, and `plexarAuth` alike) and need `remote.plexarUpdate` /
 * `remote.plexarModels` / `remote.plexarAuth` ready before they register, unlike the
 * Features and Credits sections above, whose Remote namespaces this package already
 * statically injects.
 * @param ctx - the browser plugin context.
 * @returns disposer joining UI and Remote withdrawal.
 */
async function registerRemoteSections(ctx: ClientContext): Promise<() => Promise<void>> {
  const disposeRemote = await ctx.remote.$mount(plexarUpdateRemote)
  const ui = ctx.inject(['remote.plexarUpdate', 'remote.plexarModels', 'remote.plexarAuth', 'slots', 'locale'], (child) => {
    child.effect(() => child.locale.register(UPDATE_NS, { en: updateEn, zh: updateZh }), 'ui-settings-plexar: update dictionaries')
    const updateController = new UpdateController(child)
    child.effect(() => updateController.start(), 'ui-settings-plexar: update poll')
    child.slots.inject('sidebar.footer.action', () => child.slots.register({
      name: 'sidebar.footer.action',
      id: 'plexar-update',
      locale: UPDATE_NS,
      inject: () => updateController.inject(),
    }, UpdateNotice))

    child.effect(() => child.locale.register(ACCOUNT_NS, { en: accountEn, zh: accountZh }), 'ui-settings-plexar: account dictionaries')
    const tAccount = child.locale.bind(ACCOUNT_NS)
    const accountController = new AccountController(child)
    child.slots.inject('settings.section', () => child.slots.register({
      name: 'settings.section',
      id: 'plexar-account',
      order: 10,
      label: () => tAccount('nav'),
      locale: ACCOUNT_NS,
      inject: () => accountController.inject(),
    }, AccountSection))

    child.effect(() => child.locale.register(MODELS_NS, { en: modelsEn, zh: modelsZh }), 'ui-settings-plexar: models dictionaries')
    const tModels = child.locale.bind(MODELS_NS)
    const modelsController = new ModelsController(child)
    child.slots.inject('settings.section', () => child.slots.register({
      name: 'settings.section',
      id: 'plexar-models',
      order: 30,
      label: () => tModels('nav'),
      locale: MODELS_NS,
      inject: () => modelsController.inject(),
    }, ModelsSection))
  })
  try {
    await ui
  } catch (error) {
    await ui.dispose()
    await disposeRemote()
    throw error
  }
  return async () => { await ui.dispose(); await disposeRemote() }
}

/**
 * Mount the Plexar Features, Models, and Credits settings sections and the
 * sidebar update notice.
 * @param ctx - the browser plugin context.
 * @returns disposer for the Remote mount and UI registration shared by the
 *   Models section and the update notice.
 */
export async function apply(ctx: ClientContext): Promise<() => Promise<void>> {
  ctx.effect(() => ctx.locale.register(FEATURES_NS, { en: featuresEn, zh: featuresZh }), 'ui-settings-plexar: features dictionaries')
  ctx.effect(() => ctx.locale.register(CREDITS_NS, { en: creditsEn, zh: creditsZh }), 'ui-settings-plexar: credits dictionaries')
  const tFeatures = ctx.locale.bind(FEATURES_NS)
  const tCredits = ctx.locale.bind(CREDITS_NS)

  const controller = new FeaturesController(ctx)

  ctx.slots.inject('settings.section', () => ctx.slots.register({
    name: 'settings.section',
    id: 'plexar-features',
    order: 20,
    label: () => tFeatures('nav'),
    locale: FEATURES_NS,
    inject: () => controller.inject(tFeatures),
  }, FeaturesSection))

  ctx.slots.inject('settings.section', () => ctx.slots.register({
    name: 'settings.section',
    id: 'plexar-credits',
    order: 90,
    label: () => tCredits('nav'),
    locale: CREDITS_NS,
  }, CreditsSection))

  return await registerRemoteSections(ctx)
}
