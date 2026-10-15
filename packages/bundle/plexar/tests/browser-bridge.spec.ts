/** The Plexar Browser Bridge relay, the per-process hub, and the per-Session choice between the person's Chrome and a launched browser. */

import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { WebSocket } from 'ws'
import { BridgeHub, chooseBrowser, Config, PLEXAR_BRIDGE_EXTENSION_ID, PLEXAR_BRIDGE_STORE_EXTENSION_ID, useMyChromeOn } from '../src/browser-bridge/index.ts'
import { CDP_ENDPOINT_ENV, playwrightMcpLaunch } from '@deepseek-ai/dsh-experimental-browser-use-playwright-mcp'
import { extensionInstalled, userDataDirs } from '../src/browser-bridge/chrome.ts'
import { CdpRelayServer } from '../src/browser-bridge/relay.ts'

const EXTENSION_ORIGIN = `chrome-extension://${PLEXAR_BRIDGE_EXTENSION_ID}`
const relays: CdpRelayServer[] = []

function relay(
  openConnectPage: (url: string) => Promise<void> = () => Promise.resolve(),
  extensionId: string = PLEXAR_BRIDGE_EXTENSION_ID,
): CdpRelayServer {
  const created = new CdpRelayServer({ openConnectPage, extensionId })
  relays.push(created)
  return created
}

/** Open a WebSocket and report whether the upgrade was accepted. */
function connect(url: string, origin?: string): Promise<{ accepted: boolean; ws: WebSocket }> {
  const ws = new WebSocket(url, origin === undefined ? {} : { origin })
  return new Promise((resolve) => {
    ws.once('open', () => { resolve({ accepted: true, ws }) })
    ws.once('error', () => { resolve({ accepted: false, ws }) })
  })
}

/** One JSON message on a relay WebSocket. */
interface WireMessage {
  id?: number
  method?: string
  params?: unknown[]
  result?: { targetId?: string }
}

/** A CDP event a client received. */
interface CdpEvent { params?: { targetInfo?: { targetId?: string } } }

/** Commands a fake extension received, as [method, params]. */
type Received = [string | undefined, unknown[] | undefined][]

/** A tab as the extension reports it. */
const tabOf = (id: number): object => ({ id, index: 0, windowId: 1, active: true, pinned: false })

/**
 * A fake extension that connects, reports its initial tabs, completes the protocol v2 handshake, and answers
 * every command: `chrome.tabs.create` with a fresh tab id from 100, `Target.getTargetInfo` with `t<tabId>`.
 */
async function fakeExtension(
  url: string,
  origin: string = EXTENSION_ORIGIN,
  initialTabs: number[] = [],
  received: Received = [],
): Promise<WebSocket> {
  const { accepted, ws } = await connect(url, origin)
  expect(accepted).toBe(true)
  let nextTab = 100
  ws.on('message', (data) => {
    const { id, method, params } = JSON.parse(String(data)) as WireMessage
    received.push([method, params])
    let result: unknown = {}
    if (method === 'chrome.tabs.create') result = tabOf(nextTab++)
    if (method === 'chrome.debugger.sendCommand' && params?.[1] === 'Target.getTargetInfo') {
      const target = params[0] as { tabId: number }
      result = { targetInfo: { targetId: `t${target.tabId}`, type: 'page' } }
    }
    ws.send(JSON.stringify({ id, result }))
  })
  for (const tabId of initialTabs) ws.send(JSON.stringify({ method: 'chrome.tabs.onCreated', params: [tabOf(tabId)] }))
  ws.send(JSON.stringify({ method: 'extension.initialized', params: [] }))
  return ws
}

/** A Playwright-side CDP client that sends commands and collects events. */
async function cdpClient(endpoint: string): Promise<{
  call: (method: string, params?: object) => Promise<WireMessage>
  events: CdpEvent[]
  ws: WebSocket
}> {
  const { accepted, ws } = await connect(endpoint)
  expect(accepted).toBe(true)
  const events: CdpEvent[] = []
  const pending = new Map<number, (message: WireMessage) => void>()
  let lastId = 0
  ws.on('message', (data) => {
    const message = JSON.parse(String(data)) as WireMessage & CdpEvent
    if (message.id === undefined) events.push(message)
    else pending.get(message.id)?.(message)
  })
  const call = (method: string, params?: object): Promise<WireMessage> => new Promise((resolve) => {
    const id = ++lastId
    pending.set(id, resolve)
    ws.send(JSON.stringify({ id, method, params }))
  })
  return { call, events, ws }
}

/** A hub whose relays connect a fake extension; `opened` collects connect URLs. */
function hub(opened: string[] = [], received: Received = [], initialTabs: number[] = [], timeoutMs = 5000): BridgeHub {
  return new BridgeHub({
    clientName: 'repo',
    timeoutMs,
    createRelay: id => relay(async (url) => {
      opened.push(url)
      void fakeExtension(new URL(url).searchParams.get('mcpRelayUrl')!, `chrome-extension://${id}`, initialTabs, received)
    }, id),
  })
}

/** Poll until `check` holds, failing after two seconds. */
async function until(check: () => boolean): Promise<void> {
  for (let i = 0; i < 200 && !check(); i++) await new Promise(resolve => setTimeout(resolve, 10))
  expect(check()).toBe(true)
}

const tempDirs: string[] = []

afterEach(() => {
  for (const created of relays.splice(0)) created.stop()
  for (const dir of tempDirs.splice(0)) rmSync(dir, { recursive: true, force: true })
})

/** A temp user-data directory whose profiles hold the given preference files. */
function userData(profiles: Record<string, Record<string, string>>): string {
  const dir = mkdtempSync(join(tmpdir(), 'plexar-bridge-'))
  tempDirs.push(dir)
  for (const [profile, files] of Object.entries(profiles)) {
    mkdirSync(join(dir, profile))
    for (const [file, text] of Object.entries(files)) writeFileSync(join(dir, profile, file), text)
  }
  return dir
}

const listing = (id: string): string => JSON.stringify({ extensions: { settings: { [id]: { path: 'x' } } } })

describe('extensionInstalled', () => {
  const id = PLEXAR_BRIDGE_EXTENSION_ID

  it('finds the id in a profile Preferences file', () => {
    const dir = userData({
      'Default': { Preferences: listing('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa') },
      'Profile 2': { Preferences: listing(id) },
    })
    expect(extensionInstalled(id, [dir])).toBe(true)
  })

  it('finds the id in Secure Preferences only', () => {
    const dir = userData({ Default: { 'Preferences': listing('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'), 'Secure Preferences': listing(id) } })
    expect(extensionInstalled(id, [dir])).toBe(true)
  })

  it('reports not installed without the id, with malformed JSON, or without the directory', () => {
    const without = userData({ Default: { Preferences: listing('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa') } })
    const malformed = userData({ Default: { 'Preferences': '{not json', 'Secure Preferences': '[]' } })
    expect(extensionInstalled(id, [without, malformed, join(without, 'missing')])).toBe(false)
  })

  it('lists the standard Chrome and Edge user-data directories', () => {
    expect(userDataDirs('win32', { LOCALAPPDATA: 'L' }, 'H')).toEqual([
      join('L', 'Google', 'Chrome', 'User Data'),
      join('L', 'Microsoft', 'Edge', 'User Data'),
    ])
    expect(userDataDirs('darwin', {}, 'H')).toEqual([
      join('H', 'Library', 'Application Support', 'Google', 'Chrome'),
      join('H', 'Library', 'Application Support', 'Microsoft Edge'),
    ])
    expect(userDataDirs('linux', {}, 'H')).toEqual([join('H', '.config', 'google-chrome'), join('H', '.config', 'microsoft-edge')])
  })
})

describe('Config', () => {
  it('defaults the extension id and rejects a malformed one', () => {
    expect(Config({}).extensionIds).toEqual([PLEXAR_BRIDGE_STORE_EXTENSION_ID, PLEXAR_BRIDGE_EXTENSION_ID])
    expect(() => Config({ extensionIds: ['not-an-id'] })).toThrow()
    expect(() => Config({ extensionIds: [] })).toThrow()
  })
})

describe('CdpRelayServer', () => {
  it('binds 127.0.0.1 only', async () => {
    const server = relay()
    await server.start()
    expect(server.address().address).toBe('127.0.0.1')
    expect(server.addClient().endpoint).toMatch(/^ws:\/\/127\.0\.0\.1:\d+\/cdp\/[\w-]{43}$/u)
    expect(server.extensionEndpoint()).toMatch(/^ws:\/\/127\.0\.0\.1:\d+\/extension\/[\w-]{43}$/u)
  })

  it('gives each relay and each client a fresh token', async () => {
    const first = relay()
    const second = relay()
    await Promise.all([first.start(), second.start()])
    const token = (endpoint: string): string => endpoint.split('/').at(-1)!
    expect(token(first.extensionEndpoint())).not.toBe(token(second.extensionEndpoint()))
    expect(token(first.addClient().endpoint)).not.toBe(token(first.addClient().endpoint))
  })

  it('refuses a wrong token path and a foreign origin', async () => {
    const server = relay()
    await server.start()
    const base = new URL(server.extensionEndpoint())
    const wrong = `ws://${base.host}/extension/not-the-token`
    expect((await connect(wrong, EXTENSION_ORIGIN)).accepted).toBe(false)
    expect((await connect(`ws://${base.host}/cdp/not-the-token`)).accepted).toBe(false)
    expect((await connect(server.extensionEndpoint(), 'https://example.test')).accepted).toBe(false)
    expect((await connect(server.addClient().endpoint, 'https://example.test')).accepted).toBe(false)
    const accepted = await connect(server.extensionEndpoint(), EXTENSION_ORIGIN)
    expect(accepted.accepted).toBe(true)
    accepted.ws.close()
  })

  it('opens a connect page carrying the pinned extension id and the relay URL', async () => {
    const opened: string[] = []
    const server = relay(async (url) => { opened.push(url) })
    await server.start()
    await server.establishExtensionConnection('Plexar Harness', 1)
    expect(opened).toHaveLength(1)
    const url = new URL(opened[0]!)
    expect(url.protocol).toBe('chrome-extension:')
    expect(url.host).toBe(PLEXAR_BRIDGE_EXTENSION_ID)
    expect(url.pathname).toBe('/connect.html')
    expect(url.searchParams.get('mcpRelayUrl')).toBe(server.extensionEndpoint())
    expect(url.searchParams.get('protocolVersion')).toBe('2')
    expect(JSON.parse(url.searchParams.get('client')!)).toEqual({ name: 'Plexar Harness' })
    expect(url.searchParams.has('token')).toBe(false)
  })

  it('uses the configured extension id for the connect page and the origin check', async () => {
    const other = 'abcdefghijklmnopabcdefghijklmnop'
    const opened: string[] = []
    const server = relay(async (url) => { opened.push(url) }, other)
    await server.start()
    expect((await connect(server.extensionEndpoint(), EXTENSION_ORIGIN)).accepted).toBe(false)
    const accepted = await connect(server.extensionEndpoint(), `chrome-extension://${other}`)
    expect(accepted.accepted).toBe(true)
    accepted.ws.close()
    await server.establishExtensionConnection('Plexar Harness', 1)
    expect(new URL(opened[0]!).host).toBe(other)
  })

  it('accepts one /extension handshake per token and refuses every later one', async () => {
    const server = relay()
    await server.start()
    const first = await connect(server.extensionEndpoint(), EXTENSION_ORIGIN)
    expect(first.accepted).toBe(true)
    first.ws.close()
    await new Promise<void>((resolve) => { first.ws.once('close', () => { resolve() }) })
    expect((await connect(server.extensionEndpoint(), EXTENSION_ORIGIN)).accepted).toBe(false)
  })

  it('expires the /extension token when the connect wait times out', async () => {
    const server = relay()
    await server.start()
    expect(await server.establishExtensionConnection('Plexar Harness', 1)).toBe(false)
    expect((await connect(server.extensionEndpoint(), EXTENSION_ORIGIN)).accepted).toBe(false)
  })
})

describe('shared relay', () => {
  it('gives the connect page tab to the first client and keeps each client to its own tabs', async () => {
    const shared = hub([], [], [7])
    const first = await shared.attach(PLEXAR_BRIDGE_EXTENSION_ID, new AbortController().signal)
    const second = await shared.attach(PLEXAR_BRIDGE_EXTENSION_ID, new AbortController().signal)
    const a = await cdpClient(first!.endpoint)
    const b = await cdpClient(second!.endpoint)
    await a.call('Target.setAutoAttach', { autoAttach: true })
    await b.call('Target.setAutoAttach', { autoAttach: true })
    expect(a.events.map(e => e.params?.targetInfo?.targetId)).toEqual(['t7'])
    expect(b.events).toEqual([])
    const created = await b.call('Target.createTarget', { url: 'about:blank' })
    expect(created.result).toEqual({ targetId: 't100' })
    expect(a.events).toHaveLength(1)
    expect(b.events.map(e => e.params?.targetInfo?.targetId)).toEqual(['t100'])
  })

  it('closes the tabs of a disconnected client and keeps the tabs of the others', async () => {
    const received: Received = []
    const removed = (): Received => received.filter(([method]) => method === 'chrome.tabs.remove')
    const shared = hub([], received, [7])
    const first = await shared.attach(PLEXAR_BRIDGE_EXTENSION_ID, new AbortController().signal)
    const second = await shared.attach(PLEXAR_BRIDGE_EXTENSION_ID, new AbortController().signal)
    const a = await cdpClient(first!.endpoint)
    const b = await cdpClient(second!.endpoint)
    await a.call('Target.setAutoAttach', { autoAttach: true })
    await b.call('Target.createTarget', { url: 'about:blank' })
    b.ws.close()
    await until(() => removed().length === 1)
    expect(removed()).toEqual([['chrome.tabs.remove', [[100]]]])
    first!.close()
    await until(() => removed().length === 2)
    expect(removed()[1]).toEqual(['chrome.tabs.remove', [[7]]])
  })

  it('refuses a second connection on a client endpoint', async () => {
    const shared = hub()
    const client = await shared.attach(PLEXAR_BRIDGE_EXTENSION_ID, new AbortController().signal)
    await cdpClient(client!.endpoint)
    expect((await connect(client!.endpoint)).accepted).toBe(false)
  })
})

describe('BridgeHub', () => {
  it('opens one connect page for every Session of the process, named for the process', async () => {
    const opened: string[] = []
    const shared = hub(opened)
    const signal = new AbortController().signal
    const [first, second] = await Promise.all([
      shared.attach(PLEXAR_BRIDGE_EXTENSION_ID, signal),
      shared.attach(PLEXAR_BRIDGE_EXTENSION_ID, signal),
    ])
    const third = await shared.attach(PLEXAR_BRIDGE_EXTENSION_ID, signal)
    expect(opened).toHaveLength(1)
    expect(JSON.parse(new URL(opened[0]!).searchParams.get('client')!)).toEqual({ name: 'repo' })
    expect(new Set([first!.endpoint, second!.endpoint, third!.endpoint]).size).toBe(3)
  })

  it('treats a miss as final for the process', async () => {
    let created = 0
    const shared = new BridgeHub({ clientName: 'repo', timeoutMs: 20, createRelay: (id) => { created++; return relay(undefined, id) } })
    const signal = new AbortController().signal
    expect(await shared.attach(PLEXAR_BRIDGE_EXTENSION_ID, signal)).toBeUndefined()
    expect(await shared.attach(PLEXAR_BRIDGE_EXTENSION_ID, signal)).toBeUndefined()
    expect(created).toBe(1)
  })

  it('reconnects with a new connect page after the extension disconnects', async () => {
    const opened: string[] = []
    const shared = new BridgeHub({
      clientName: 'repo',
      timeoutMs: 5000,
      createRelay: id => relay(async (url) => {
        opened.push(url)
        const ws = await fakeExtension(new URL(url).searchParams.get('mcpRelayUrl')!, `chrome-extension://${id}`)
        if (opened.length === 1) setTimeout(() => { ws.close() }, 20)
      }, id),
    })
    const signal = new AbortController().signal
    await shared.attach(PLEXAR_BRIDGE_EXTENSION_ID, signal)
    await new Promise(resolve => setTimeout(resolve, 100))
    expect(await shared.attach(PLEXAR_BRIDGE_EXTENSION_ID, signal)).toBeDefined()
    expect(opened).toHaveLength(2)
  })

  it('rejects an aborted Session and keeps the shared connection for the others', async () => {
    const shared = hub()
    const aborted = new AbortController()
    aborted.abort(new Error('session closed'))
    await expect(shared.attach(PLEXAR_BRIDGE_EXTENSION_ID, aborted.signal)).rejects.toThrow('session closed')
    expect(await shared.attach(PLEXAR_BRIDGE_EXTENSION_ID, new AbortController().signal)).toBeDefined()
  })
})

describe('chooseBrowser', () => {
  it('attaches through the hub once the extension connects', async () => {
    const choice = await chooseBrowser({
      useMyChrome: true,
      installedExtensionId: () => PLEXAR_BRIDGE_EXTENSION_ID,
      signal: new AbortController().signal,
      hub: hub(),
    })
    expect(choice).toMatchObject({ mode: 'attach', endpoint: expect.stringMatching(/^ws:\/\/127\.0\.0\.1:\d+\/cdp\/[\w-]{43}$/u) })
  })

  it('passes the relay endpoint to the Playwright server in its environment, not its arguments', () => {
    const endpoint = 'ws://127.0.0.1:1/cdp/secret-token'
    const launch = playwrightMcpLaunch({ mode: 'attach', endpoint }, { endpointInEnv: true })
    expect(launch.args.join(' ')).not.toContain('secret-token')
    expect(launch.env[CDP_ENDPOINT_ENV]).toBe(endpoint)
  })

  it('opens the relay for the installed extension id it was given', async () => {
    const opened: string[] = []
    const choice = await chooseBrowser({
      useMyChrome: true,
      installedExtensionId: () => PLEXAR_BRIDGE_STORE_EXTENSION_ID,
      signal: new AbortController().signal,
      hub: hub(opened),
    })
    expect(new URL(opened[0]!).host).toBe(PLEXAR_BRIDGE_STORE_EXTENSION_ID)
    expect(choice.mode).toBe('attach')
    if (choice.mode === 'attach') choice.close()
  })

  it('falls back to launch when the extension never connects', async () => {
    const choice = await chooseBrowser({
      useMyChrome: true,
      installedExtensionId: () => PLEXAR_BRIDGE_EXTENSION_ID,
      signal: new AbortController().signal,
      hub: new BridgeHub({ clientName: 'repo', timeoutMs: 50, createRelay: id => relay(undefined, id) }),
    })
    expect(choice).toEqual({ mode: 'launch', extensionMissing: true })
    expect((await connect(relays[0]!.extensionEndpoint(), EXTENSION_ORIGIN)).accepted).toBe(false)
  })

  it('falls back to launch when no browser can be opened', async () => {
    const choice = await chooseBrowser({
      useMyChrome: true,
      installedExtensionId: () => PLEXAR_BRIDGE_EXTENSION_ID,
      signal: new AbortController().signal,
      hub: new BridgeHub({ clientName: 'repo', timeoutMs: 5000, createRelay: id => relay(() => Promise.reject(new Error('no Chrome or Edge installation found')), id) }),
    })
    expect(choice).toEqual({ mode: 'launch', extensionMissing: true })
  })

  it('launches without starting a relay when the switch is off', async () => {
    const off = useMyChromeOn([{ ns: 'plexar-feature-toggles', value: { off: ['shell', 'useMyChrome'] } }])
    expect(off).toBe(false)
    const choice = await chooseBrowser({
      useMyChrome: off,
      installedExtensionId: () => PLEXAR_BRIDGE_EXTENSION_ID,
      signal: new AbortController().signal,
      hub: hub(),
    })
    expect(choice).toEqual({ mode: 'launch', extensionMissing: false })
    expect(relays).toHaveLength(0)
  })

  it('launches at once without opening a browser when the extension is not installed', async () => {
    const opened: string[] = []
    const started = Date.now()
    const choice = await chooseBrowser({
      useMyChrome: true,
      installedExtensionId: () => undefined,
      signal: new AbortController().signal,
      hub: hub(opened, [], [], 20000),
    })
    expect(choice).toEqual({ mode: 'launch', extensionMissing: true })
    expect(opened).toEqual([])
    expect(relays).toHaveLength(0)
    expect(Date.now() - started).toBeLessThan(1000)
  })

  it('treats the switch as on by default', () => {
    expect(useMyChromeOn(undefined)).toBe(true)
    expect(useMyChromeOn([{ ns: 'plexar-feature-toggles', value: {} }])).toBe(true)
    expect(useMyChromeOn([{ ns: 'plexar-feature-toggles', value: { off: ['shell'] } }])).toBe(true)
  })
})
