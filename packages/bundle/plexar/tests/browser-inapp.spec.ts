/** The in-app browser route: the shell endpoint check, the shell lines, readiness polling, and the route order. */

import { describe, expect, it } from 'vitest'
import { chooseBrowser, inAppBrowserOn } from '../src/browser-bridge/index.ts'
import type { BridgeHub } from '../src/browser-bridge/index.ts'
import { attachInApp, inAppEndpoint, INAPP_CDP_ENV } from '../src/browser-bridge/inapp.ts'

const ENSURE = 'plexar shell: {"op":"browser.ensure","session":"s1"}\n'
const RELEASE = 'plexar shell: {"op":"browser.release","session":"s1"}\n'
const ENDPOINT = 'http://127.0.0.1:9222'

/** A fake `/json/list` that is empty until `pages` holds a page entry; `urls` collects every polled URL. */
function fakeList(): { fetchJson: (url: string, signal: AbortSignal) => Promise<unknown>; pages: object[]; urls: string[] } {
  const pages: object[] = []
  const urls: string[] = []
  return { pages, urls, fetchJson: (url) => { urls.push(url); return Promise.resolve([...pages]) } }
}

const wait = (ms: number): Promise<void> => new Promise((resolve) => { setTimeout(resolve, ms) })

describe('inAppEndpoint', () => {
  it('accepts exactly http://127.0.0.1:<port>', () => {
    expect(inAppEndpoint({ [INAPP_CDP_ENV]: ENDPOINT })).toBe(ENDPOINT)
    expect(inAppEndpoint({ [INAPP_CDP_ENV]: 'http://127.0.0.1:65535' })).toBe('http://127.0.0.1:65535')
  })

  it('rejects every other form', () => {
    for (const value of [
      'http://localhost:9222',
      'https://127.0.0.1:1',
      'http://127.0.0.1',
      'http://127.0.0.1:0',
      'http://127.0.0.1:70000',
      'http://127.0.0.1:9222/x',
      'http://evil.example:9222',
      '',
    ]) expect(inAppEndpoint({ [INAPP_CDP_ENV]: value }), value).toBeUndefined()
    expect(inAppEndpoint({})).toBeUndefined()
  })
})

describe('attachInApp', () => {
  it('writes browser.ensure first, then resolves once /json/list holds a page', async () => {
    const list = fakeList()
    const written: string[] = []
    const result = attachInApp({
      endpoint: ENDPOINT, session: 's1', timeoutMs: 2000, signal: new AbortController().signal,
      write: line => written.push(line), fetchJson: list.fetchJson, intervalMs: 5,
    })
    expect(written).toEqual([ENSURE])
    await wait(30)
    list.pages.push({ type: 'service_worker' })
    await wait(30)
    list.pages.push({ type: 'page', id: 'p1' })
    const attached = await result
    expect(attached?.endpoint).toBe(ENDPOINT)
    expect(list.urls.every(url => url === `${ENDPOINT}/json/list`)).toBe(true)
    expect(written).toEqual([ENSURE])
    const polls = list.urls.length
    await wait(30)
    expect(list.urls).toHaveLength(polls)
  })

  it('times out to undefined after writing one release line, and stops polling', async () => {
    const list = fakeList()
    const written: string[] = []
    const result = await attachInApp({
      endpoint: ENDPOINT, session: 's1', timeoutMs: 40, signal: new AbortController().signal,
      write: line => written.push(line), fetchJson: list.fetchJson, intervalMs: 5,
    })
    expect(result).toBeUndefined()
    expect(written).toEqual([ENSURE, RELEASE])
    const polls = list.urls.length
    expect(polls).toBeGreaterThan(1)
    await wait(30)
    expect(list.urls).toHaveLength(polls)
  })

  it('keeps polling through a failing fetch', async () => {
    const written: string[] = []
    let calls = 0
    const attached = await attachInApp({
      endpoint: ENDPOINT, session: 's1', timeoutMs: 2000, signal: new AbortController().signal,
      write: line => written.push(line), intervalMs: 5,
      fetchJson: () => (++calls < 3 ? Promise.reject(new Error('refused')) : Promise.resolve([{ type: 'page' }])),
    })
    expect(attached).toBeDefined()
    expect(calls).toBe(3)
  })

  it('writes one release line on close(), however often it is called', async () => {
    const written: string[] = []
    const attached = await attachInApp({
      endpoint: ENDPOINT, session: 's1', timeoutMs: 2000, signal: new AbortController().signal,
      write: line => written.push(line), intervalMs: 5, fetchJson: () => Promise.resolve([{ type: 'page' }]),
    })
    expect(written).toEqual([ENSURE])
    attached!.close()
    attached!.close()
    expect(written).toEqual([ENSURE, RELEASE])
  })

  it('rejects with the abort reason after writing one release line, and stops polling', async () => {
    const list = fakeList()
    const written: string[] = []
    const controller = new AbortController()
    const result = attachInApp({
      endpoint: ENDPOINT, session: 's1', timeoutMs: 2000, signal: controller.signal,
      write: line => written.push(line), fetchJson: list.fetchJson, intervalMs: 5,
    })
    await wait(20)
    controller.abort(new Error('session closed'))
    await expect(result).rejects.toThrow('session closed')
    expect(written).toEqual([ENSURE, RELEASE])
    const polls = list.urls.length
    await wait(30)
    expect(list.urls).toHaveLength(polls)
  })

  it('does not write a second release after a timeout or abort when close() runs later', async () => {
    const written: string[] = []
    const aborted = new AbortController()
    const waiting = attachInApp({
      endpoint: ENDPOINT, session: 's1', timeoutMs: 2000, signal: aborted.signal,
      write: line => written.push(line), intervalMs: 5, fetchJson: () => Promise.resolve([]),
    })
    aborted.abort(new Error('stop'))
    await expect(waiting).rejects.toThrow('stop')
    expect(written.filter(line => line === RELEASE)).toHaveLength(1)
  })

  it('writes nothing when the signal is already aborted', async () => {
    const written: string[] = []
    const aborted = new AbortController()
    aborted.abort(new Error('gone'))
    await expect(attachInApp({
      endpoint: ENDPOINT, session: 's1', timeoutMs: 50, signal: aborted.signal, write: line => written.push(line),
    })).rejects.toThrow('gone')
    expect(written).toEqual([])
  })
})

describe('inAppBrowserOn', () => {
  it('is on unless the Features off list names inAppBrowser', () => {
    expect(inAppBrowserOn(undefined)).toBe(true)
    expect(inAppBrowserOn([])).toBe(true)
    expect(inAppBrowserOn([{ ns: 'plexar-feature-toggles', value: {} }])).toBe(true)
    expect(inAppBrowserOn([{ ns: 'plexar-feature-toggles', value: { off: ['useMyChrome'] } }])).toBe(true)
    expect(inAppBrowserOn([{ ns: 'other', value: { off: ['inAppBrowser'] } }])).toBe(true)
    expect(inAppBrowserOn([{ ns: 'plexar-feature-toggles', value: { off: ['shell', 'inAppBrowser'] } }])).toBe(false)
  })
})

describe('chooseBrowser route order', () => {
  const signal = new AbortController().signal
  const hubOf = (client: { endpoint: string; close: () => void } | undefined): Pick<BridgeHub, 'attach'> => ({
    attach: () => Promise.resolve(client),
  })
  const pane = (): { endpoint: string; close: () => void } => ({ endpoint: ENDPOINT, close: () => {} })

  it('lets the extension win without consulting the in-app route', async () => {
    let asked = 0
    const client = { endpoint: 'ws://127.0.0.1:1/cdp/t', close: () => {} }
    const choice = await chooseBrowser({
      useMyChrome: true, installedExtensionId: () => 'x', signal, hub: hubOf(client),
      inApp: () => { asked++; return Promise.resolve(pane()) },
    })
    expect(choice).toEqual({ mode: 'attach', endpoint: client.endpoint, close: client.close })
    expect(asked).toBe(0)
  })

  it('falls to the in-app pane when the extension is missing or does not connect', async () => {
    for (const installed of [undefined, 'x']) {
      const choice = await chooseBrowser({
        useMyChrome: true, installedExtensionId: () => installed, signal, hub: hubOf(undefined), inApp: () => Promise.resolve(pane()),
      })
      expect(choice).toMatchObject({ mode: 'attach', endpoint: ENDPOINT })
    }
  })

  it('launches when the in-app route yields nothing, keeping the extension-miss flag', async () => {
    const choice = await chooseBrowser({
      useMyChrome: true, installedExtensionId: () => undefined, signal, hub: hubOf(undefined), inApp: () => Promise.resolve(undefined),
    })
    expect(choice).toEqual({ mode: 'launch', extensionMissing: true })
  })

  it('uses the in-app pane alone when useMyChrome is off', async () => {
    const choice = await chooseBrowser({
      useMyChrome: false, installedExtensionId: () => 'x', signal, hub: hubOf(undefined), inApp: () => Promise.resolve(pane()),
    })
    expect(choice).toMatchObject({ mode: 'attach', endpoint: ENDPOINT })
    expect(await chooseBrowser({
      useMyChrome: false, installedExtensionId: () => 'x', signal, hub: hubOf(undefined), inApp: () => Promise.resolve(undefined),
    })).toEqual({ mode: 'launch', extensionMissing: false })
  })

  it('launches as before when no in-app route is offered', async () => {
    expect(await chooseBrowser({ useMyChrome: false, installedExtensionId: () => 'x', signal, hub: hubOf(undefined) }))
      .toEqual({ mode: 'launch', extensionMissing: false })
  })
})
