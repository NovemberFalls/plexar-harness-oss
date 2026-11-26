/**
 * "Use my Chrome": Playwright browser tools that work in the person's own Chrome or Edge through the
 * Plexar Browser Bridge extension, falling back to a browser window of the agent's own.
 *
 * While the `useMyChrome` feature is on and a Chrome or Edge profile has one of the `extensionIds` extensions
 * installed, the first Session of the process starts one relay on 127.0.0.1, opens the extension's connect page
 * in the person's browser, and waits `connectTimeoutMs` for the extension. The extension shows the process as one
 * colored tab group named after the working directory; every Session of the process works in that group through
 * its own relay client, sees only its own tabs, and closes them when it ends. When the process stops or dies the
 * extension closes the tabs the agent opened. Without an install the plugin opens nothing and does not wait. Each
 * Session's Playwright server receives its client's CDP endpoint in its environment. Otherwise (feature off,
 * extension not installed, no Chrome or Edge found, or no extension in time, which is final for the process) the
 * server launches its own isolated Chromium, visible unless `headless`. A miss
 * prints one install hint to the person through the logger, once per activation; the model sees the
 * same browser tools either way.
 *
 * With `delegate` on (the default) only the browser agent, spawned through the `browse` tool, gets a server and the
 * tools; no other agent starts one. Its in-app pane is keyed by the top-level Session and released when that
 * Session's agent is disposed. Its route comes from the `browse` call's `browser` argument: by default the in-app
 * pane or a launched browser, with no contact to the extension; `my_chrome` only the person's Chrome, failing with a
 * message instead of falling back. With `delegate` off every agent gets them in the order above, and `browse` is hidden.
 * @module @plexar/dsh-plexar/browser-bridge
 */

import { randomUUID } from 'node:crypto'
import { tmpdir } from 'node:os'
import { basename, join } from 'node:path'
import type { Context } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'
import z from '@deepseek-ai/schemastery'
import { mountSessionMcp } from '@deepseek-ai/dsh-experimental-browser-use-runtime/mcp'
import type { SessionMcpLaunch } from '@deepseek-ai/dsh-experimental-browser-use-runtime/mcp'
import { playwrightMcpLaunch } from '@deepseek-ai/dsh-experimental-browser-use-playwright-mcp'
import type {} from '@deepseek-ai/dsh-settings'
import { admitsBrowserTools, browserRoute, deniedTools, RootPanes, rootSessionId } from '../browser-agent.ts'
import { denyForAgent } from '../tool-scaffold.ts'
import { extensionInstalled, findChrome, openInBrowser } from './chrome.ts'
import { attachInApp, IN_APP_BROWSER_FEATURE, inAppEndpoint } from './inapp.ts'
import { CdpRelayServer } from './relay.ts'
import type { RelayClient } from './relay.ts'

export const name = 'plexar-browser-bridge'
export const inject = ['browserUse', 'agents', 'tools', 'systemPrompt']

/** Feature id in the `plexar-feature-toggles` `off` setting that turns the bridge off. */
export const USE_MY_CHROME_FEATURE = 'useMyChrome'

/** Settings namespace holding the Features `off` list. */
const FEATURE_TOGGLES_NS = 'plexar-feature-toggles'

/** Id the Chrome Web Store assigned to the published Plexar Browser Bridge. */
export const PLEXAR_BRIDGE_STORE_EXTENSION_ID = 'gnjeciecdiicngbfdancnklpnnmcekll'

/** Id of a load-unpacked development build, pinned by the manifest key in apps/plexar-browser-extension. */
export const PLEXAR_BRIDGE_EXTENSION_ID = 'cnfgenfphpnhddlefhminclbbjdgkbbd'

/** The line shown to the person when the extension did not connect. */
export const INSTALL_HINT = 'Install Plexar Browser Bridge from plexar.tech/harness/browser to let the agent use your Chrome.'

/** Folder under the system temp folder that holds each Session's Playwright output (page snapshots), outside the workspace. */
export const OUTPUT_DIR_NAME = 'plexar-playwright-mcp'

/** Name shown on the connect page and in the tab group title when the working directory has no name. */
const CLIENT_NAME = 'Plexar Harness'

/** Plugin configuration. */
export interface Config {
  /** Milliseconds to wait for the extension before launching the agent's own browser. */
  connectTimeoutMs: number
  /** Milliseconds to wait for the desktop shell's in-app pane before launching the agent's own browser. */
  inAppTimeoutMs: number
  /**
   * Plexar Browser Bridge ids in preference order; the first one installed in any Chrome or Edge profile
   * supplies the connect page and the only origin allowed on /extension.
   */
  extensionIds: string[]
  /** Whether the fallback browser runs without a visible window. */
  headless: boolean
  /** The person's Chrome or Edge executable; omission searches the standard install locations. */
  chromePath?: string
  /** Per-call timeout override in milliseconds; omission uses the MCP client default. */
  toolCallTimeoutMs?: number
  /**
   * Only the browser agent spawned through `browse` gets the browser tools (default). `false` gives them to every
   * agent, as before the browser agent, and hides `browse`.
   */
  delegate: boolean
}

export const Config: z<Partial<Config>, Config> = z.object({
  connectTimeoutMs: z.natural().min(1).default(20000),
  inAppTimeoutMs: z.natural().min(1).default(15000),
  extensionIds: z.array(z.string().pattern(/^[a-p]{32}$/u)).min(1)
    .default([PLEXAR_BRIDGE_STORE_EXTENSION_ID, PLEXAR_BRIDGE_EXTENSION_ID]),
  headless: z.boolean().default(false),
  chromePath: z.string().pattern(/\S/u),
  toolCallTimeoutMs: z.natural().min(1),
  delegate: z.boolean().default(true),
}) as z<Partial<Config>, Config>

/** The relay operations `BridgeHub` uses. */
export interface BridgeRelay {
  start(): Promise<void>
  establishExtensionConnection(clientName: string, timeoutMs: number, signal?: AbortSignal): Promise<boolean>
  extensionConnected(): boolean
  addClient(): RelayClient
  stop(): void
}

/**
 * One harness process's link to the person's browser: a single relay, a single connect page, and so a single tab
 * group, shared by every Session of the process. Each Session attaches as its own relay client and sees only its own
 * tabs. The first attach opens the connect page; later attaches reuse the connection while the extension stays
 * connected and reconnect once it has gone. A miss (no browser, or no extension in time) is final for the process, so
 * later Sessions launch their own browser without opening another connect page.
 */
export class BridgeHub {
  private readonly _options: { createRelay: (extensionId: string) => BridgeRelay; clientName: string; timeoutMs: number }
  private readonly _stopped = new AbortController()
  private _relay: BridgeRelay | undefined
  private _connecting: Promise<BridgeRelay | undefined> | undefined
  private _missed = false

  /**
   * @param options.createRelay - creates an unstarted relay for an installed extension id.
   * @param options.clientName - name shown on the connect page and in the tab group title.
   * @param options.timeoutMs - how long to wait for the extension.
   */
  constructor(options: { createRelay: (extensionId: string) => BridgeRelay; clientName: string; timeoutMs: number }) {
    this._options = options
  }

  /**
   * Attach one Session to the person's browser.
   * @param extensionId - the installed extension id.
   * @param signal - aborts this Session's wait; the shared connect wait continues for other Sessions.
   * @returns the Session's relay client, or undefined after a miss.
   */
  async attach(extensionId: string, signal: AbortSignal): Promise<RelayClient | undefined> {
    signal.throwIfAborted()
    const connecting = this._connect(extensionId)
    let reject: (reason: unknown) => void = () => {}
    const aborted = new Promise<never>((_resolve, rejectAbort) => { reject = rejectAbort })
    const onAbort = (): void => { reject(signal.reason) }
    signal.addEventListener('abort', onAbort, { once: true })
    try {
      return (await Promise.race([connecting, aborted]))?.addClient()
    } finally {
      signal.removeEventListener('abort', onAbort)
    }
  }

  /** Stop the relay; the extension then closes the tabs it opened. */
  stop(): void {
    this._stopped.abort()
    this._relay?.stop()
    this._relay = undefined
  }

  private _connect(extensionId: string): Promise<BridgeRelay | undefined> {
    if (this._missed || this._stopped.signal.aborted) return Promise.resolve(undefined)
    if (this._relay?.extensionConnected()) return Promise.resolve(this._relay)
    this._connecting ??= (async () => {
      this._relay?.stop()
      this._relay = undefined
      const relay = this._options.createRelay(extensionId)
      let connected = false
      try {
        await relay.start()
        connected = await relay.establishExtensionConnection(this._options.clientName, this._options.timeoutMs, this._stopped.signal)
      } catch (error) {
        if (!this._stopped.signal.aborted) throw error
      } finally {
        if (!connected) relay.stop()
      }
      if (!connected || this._stopped.signal.aborted) {
        this._missed = true
        if (connected) relay.stop()
        return undefined
      }
      this._relay = relay
      return relay
    })().finally(() => { this._connecting = undefined })
    return this._connecting
  }
}

/** Failure when the person asked for their Chrome and the `useMyChrome` feature is off. */
export const CHROME_OFF_MESSAGE = 'Use my Chrome is turned off in Settings > Features'

/** Failure when the person asked for their Chrome and the extension is missing or did not attach. */
export const CHROME_NOT_CONNECTED_MESSAGE = 'The Plexar browser extension is not connected in Chrome'

/**
 * Which browser one Session's server asks for: `auto` is the order without the browser agent (the person's
 * Chrome, the in-app pane, a launched one); `in-app` never contacts the extension; `my-chrome` takes only the
 * person's Chrome and fails instead of falling back.
 */
export type BrowserRoute = 'auto' | 'in-app' | 'my-chrome'

/** Where one Session's browser tools run. */
export type BrowserChoice =
  | { mode: 'attach'; endpoint: string; close: () => void }
  | { mode: 'launch'; extensionMissing: boolean }

/**
 * Decide one Session's browser: the person's own through the process's hub, or a launched one.
 * @param options.useMyChrome - whether the `useMyChrome` feature is on.
 * @param options.installedExtensionId - the id of the installed extension, or undefined; consulted only while the feature is on.
 * @param options.hub - the process's hub; not used when the feature is off or no extension is installed.
 * @param options.signal - aborts the wait and rethrows the abort reason.
 * @param options.inApp - the in-app pane route, consulted only when the extension did not attach.
 * @param options.route - which browser is asked for; default `auto`.
 * @returns an attachment owning the Session's relay client or pane, or launch with whether the extension was missed.
 */
export async function chooseBrowser(options: {
  useMyChrome: boolean
  installedExtensionId: () => string | undefined
  hub: Pick<BridgeHub, 'attach'>
  signal: AbortSignal
  inApp?: () => Promise<{ endpoint: string; close: () => void } | undefined>
  route?: BrowserRoute
}): Promise<BrowserChoice> {
  const route = options.route ?? 'auto'
  if (route === 'my-chrome') {
    if (!options.useMyChrome) throw new Error(CHROME_OFF_MESSAGE)
    const extensionId = options.installedExtensionId()
    const client = extensionId === undefined ? undefined : await options.hub.attach(extensionId, options.signal)
    if (client === undefined) throw new Error(CHROME_NOT_CONNECTED_MESSAGE)
    return { mode: 'attach', endpoint: client.endpoint, close: client.close }
  }
  let extensionMissing = false
  if (route === 'auto' && options.useMyChrome) {
    const extensionId = options.installedExtensionId()
    if (extensionId === undefined) {
      extensionMissing = true
    } else {
      const client = await options.hub.attach(extensionId, options.signal)
      if (client !== undefined) return { mode: 'attach', endpoint: client.endpoint, close: client.close }
      extensionMissing = true
    }
  }
  const pane = await options.inApp?.()
  if (pane !== undefined) return { mode: 'attach', endpoint: pane.endpoint, close: pane.close }
  return { mode: 'launch', extensionMissing }
}

/**
 * Whether the person left "Use my Chrome" on; true when the Features plugin or settings are absent.
 * @param forms - live settings forms (`settings.describe()`), or undefined without a settings service.
 * @returns false only when the `plexar-feature-toggles` `off` setting lists `useMyChrome`.
 */
export function useMyChromeOn(forms: readonly { ns: string; value: unknown }[] | undefined): boolean {
  const value = forms?.find(form => form.ns === FEATURE_TOGGLES_NS)?.value
  const off = typeof value === 'object' && value !== null && 'off' in value ? value.off : undefined
  return !(Array.isArray(off) && off.includes(USE_MY_CHROME_FEATURE))
}

/**
 * Whether the person left "In-app browser" on; true when the Features plugin or settings are absent.
 * @param forms - live settings forms (`settings.describe()`), or undefined without a settings service.
 * @returns false only when the `plexar-feature-toggles` `off` setting lists `inAppBrowser`.
 */
export function inAppBrowserOn(forms: readonly { ns: string; value: unknown }[] | undefined): boolean {
  const value = forms?.find(form => form.ns === FEATURE_TOGGLES_NS)?.value
  const off = typeof value === 'object' && value !== null && 'off' in value ? value.off : undefined
  return !(Array.isArray(off) && off.includes(IN_APP_BROWSER_FEATURE))
}

/** The id when the shell can key a pane by it, else a fresh random id. */
function paneKey(id: unknown): string {
  return typeof id === 'string' && id.length > 0 && id.length <= 128 ? id : randomUUID()
}

/** The Session id when the agent exposes one the shell can key a pane by, else a fresh random id. */
function paneSessionId(agent: unknown): string {
  return paneKey((agent as { session?: { header?: { id?: unknown } } } | undefined)?.session?.header?.id)
}

/**
 * Register the Playwright browser provider with a per-Session choice between the person's browser and a launched one.
 * @param ctx - provider context supplying browser use, Agents, tools, and prompt assembly.
 * @param config - the resolved plugin configuration.
 */
export function apply(ctx: Context, config: Config): void {
  // PLEXAR_UNATTENDED (set by `plexar-harness -p`): never attach to the person's Chrome, and keep
  // the launched browser hidden. Each attach opens a connect tab that outlives the run.
  const unattended = process.env.PLEXAR_UNATTENDED === '1'
  const launch = playwrightMcpLaunch({ mode: 'launch', headless: config.headless || unattended })
  let hinted = false
  const hub = new BridgeHub({
    clientName: basename(process.cwd()) || CLIENT_NAME,
    timeoutMs: config.connectTimeoutMs,
    createRelay: extensionId => new CdpRelayServer({
      extensionId,
      openConnectPage: async (url) => {
        const chrome = config.chromePath ?? findChrome()
        if (chrome === undefined) throw new Error('no Chrome or Edge installation found')
        await openInBrowser(chrome, url)
      },
    }),
  })
  ctx.effect(() => () => { hub.stop() }, 'plexar-browser-bridge.hub')
  const delegate = config.delegate
  const panes = new RootPanes(root => ctx.agents.list().some(agent => agent.session.header.id === root))
  ctx.effect(() => () => { panes.releaseAll() }, 'plexar-browser-bridge.panes')
  ctx.on('agent/disposed', ({ agent }) => { panes.rootDisposed(agent.session.header.id) })
  ctx.on('agent/created', ({ agent }) => {
    panes.rootCreated(agent.session.header.id)
    // Global (headless) or preset-scoped (Web) tools, and the preset's per-agent `subagent`.
    denyForAgent(agent.ctx, deniedTools(agent, delegate))
    return undefined
  })
  const prepare = async (agent: Agent, signal: AbortSignal): Promise<SessionMcpLaunch> => {
    const paneEndpoint = inAppEndpoint(process.env)
    // The browser agent's pane belongs to its top-level Session, so the page survives between two `browse` calls.
    const root = delegate ? paneKey(rootSessionId(agent, id => ctx.agents.get(id))) : undefined
    const inApp = !unattended && paneEndpoint !== undefined && inAppBrowserOn(ctx.get('settings')?.describe())
      ? async () => {
        const pane = await attachInApp({
          endpoint: paneEndpoint,
          session: root ?? paneSessionId(agent),
          timeoutMs: config.inAppTimeoutMs,
          signal,
          write: (line) => { process.stdout.write(line) },
        })
        return pane === undefined || root === undefined ? pane : { endpoint: pane.endpoint, close: panes.hold(root, pane.close) }
      }
      : undefined
    // Page snapshots go to a per-Session temp folder, not `<workspace>/.playwright-mcp`, on every route.
    const output = { PLAYWRIGHT_MCP_OUTPUT_DIR: join(tmpdir(), OUTPUT_DIR_NAME, paneSessionId(agent)) }
    const choice = await chooseBrowser({
      route: browserRoute(agent, delegate),
      useMyChrome: !unattended && useMyChromeOn(ctx.get('settings')?.describe()),
      signal,
      installedExtensionId: () => config.extensionIds.find(id => extensionInstalled(id)),
      hub,
      ...inApp === undefined ? {} : { inApp },
    })
    if (choice.mode === 'attach') {
      // The endpoint carries the client token; the child environment keeps it out of process listings.
      const attach = playwrightMcpLaunch({ mode: 'attach', endpoint: choice.endpoint }, { endpointInEnv: true })
      return { args: attach.args, env: { ...attach.env, ...output }, close: choice.close }
    }
    if (choice.extensionMissing && !hinted) {
      // Reached only on launch: a route-2 attachment returned above, so it never logs the hint.
      hinted = true
      ctx.logger.warn(INSTALL_HINT)
    }
    return { args: launch.args, env: output }
  }
  mountSessionMcp(ctx, {
    name: 'playwright-mcp',
    exclusive: false,
    command: process.execPath,
    args: launch.args,
    env: launch.env,
    prepare,
    admit: agent => admitsBrowserTools(agent, delegate),
    ...config.toolCallTimeoutMs === undefined ? {} : { toolCallTimeoutMs: config.toolCallTimeoutMs },
  })
}
