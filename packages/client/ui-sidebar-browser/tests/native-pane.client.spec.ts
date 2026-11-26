// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import type { PaneState } from '../src/client/native/bridge.ts'
import { nativePaneBridge } from '../src/client/native/bridge.ts'
import { nativeFixture } from './native-harness.client.ts'

const target = { kind: 'https' as const, url: 'https://example.test/', title: 'Example' }
const fixtures: ReturnType<typeof nativeFixture>[] = []
function fixture(options?: Parameters<typeof nativeFixture>[0]) {
  const h = nativeFixture(options)
  fixtures.push(h)
  return h
}
afterEach(async () => {
  for (const h of fixtures.splice(0)) await h.dispose()
  vi.restoreAllMocks()
})

it('opens on mount and navigation, and maps pane state, failures and new-tab requests', async () => {
  const h = fixture()
  h.frame.goBack()
  h.frame.reload()
  h.frame.loadUrl(target)
  expect(h.bridge.open).not.toHaveBeenCalled()
  h.mount()
  await vi.waitFor(() => { expect(h.bridge.open).toHaveBeenCalledExactlyOnceWith(target.url) })
  await vi.waitFor(() => { expect(h.frame.getSnapshot().address).toBe('requested') })
  h.emit('plexar-browser:state', h.state('browser-pane-1', { url: target.url, title: 'Title', loading: true, canGoBack: true }))
  expect(h.frame.getSnapshot()).toMatchObject({ address: 'observed', target: { ...target, title: 'Title' },
    loading: true, canGoBack: true, canGoForward: false, sandboxEnabled: undefined })
  expect(h.persist).toHaveBeenLastCalledWith(expect.objectContaining({ entries: [{ ...target, title: 'Title' }] }))
  h.emit('plexar-browser:state', h.state('browser-pane-9', { url: 'https://other.test/' }))
  expect(h.frame.getSnapshot().target?.url).toBe(target.url)
  h.emit('plexar-browser:load-failed', { id: 'browser-pane-1', code: -3 })
  expect(h.frame.getSnapshot().error).toBeUndefined()
  h.emit('plexar-browser:load-failed', { id: 'browser-pane-1', code: -105, description: 'NAME_NOT_RESOLVED' })
  expect(h.frame.getSnapshot()).toMatchObject({ loading: false, error: { code: -105, description: 'NAME_NOT_RESOLVED' } })
  h.emit('plexar-browser:state', h.state('browser-pane-1', { url: target.url, loading: true, canGoBack: true, canGoForward: true }))
  expect(h.frame.getSnapshot()).toMatchObject({ error: undefined, loading: true, target: { title: 'example.test' } })
  h.frame.goBack()
  h.frame.goForward()
  h.frame.reload()
  expect(h.bridge.command.mock.calls).toEqual([['browser-pane-1', 'back'], ['browser-pane-1', 'forward'], ['browser-pane-1', 'reload']])
  h.frame.loadUrl({ ...target, url: 'https://example.test/next' })
  expect(h.bridge.navigate).toHaveBeenCalledExactlyOnceWith('browser-pane-1', 'https://example.test/next')
  h.emit('plexar-browser:open-requested', { id: 'browser-pane-2', url: 'https://ignored.test/' })
  h.emit('plexar-browser:open-requested', { id: 'browser-pane-1', url: 'https://new.test/' })
  expect(h.openRequested).toHaveBeenCalledExactlyOnceWith('https://new.test/')
  expect(h.bridge.open).toHaveBeenCalledOnce()
})

it('navigates an address requested while the pane was opening', async () => {
  const h = fixture()
  const opening = Promise.withResolvers<PaneState>()
  h.bridge.open.mockReturnValueOnce(opening.promise)
  h.mount()
  h.frame.loadUrl(target)
  h.frame.loadUrl({ ...target, url: 'https://example.test/later' })
  opening.resolve(h.state('browser-pane-1'))
  await vi.waitFor(() => { expect(h.bridge.navigate).toHaveBeenCalledExactlyOnceWith('browser-pane-1', 'https://example.test/later') })
  expect(h.bridge.open).toHaveBeenCalledOnce()
})

it('closes once on dispose, joins repeated calls and removes every listener', async () => {
  const h = fixture()
  h.mount()
  h.frame.loadUrl(target)
  await vi.waitFor(() => { expect(h.pending()).toBe(1) })
  const disposed = h.frame.dispose()
  expect(h.frame.dispose()).toBe(disposed)
  await disposed
  expect(h.bridge.close).toHaveBeenCalledExactlyOnceWith('browser-pane-1')
  expect(h.listenerCount()).toBe(0)
  h.frame.loadUrl(target)
  h.frame.reload()
  expect(h.bridge.open).toHaveBeenCalledOnce()
})

it('closes a pane whose opening finishes after dispose', async () => {
  const h = fixture()
  const opening = Promise.withResolvers<PaneState>()
  h.bridge.open.mockReturnValueOnce(opening.promise)
  h.mount()
  h.frame.loadUrl(target)
  const disposed = h.frame.dispose()
  opening.resolve(h.state('browser-pane-7'))
  await disposed
  expect(h.bridge.close).toHaveBeenCalledExactlyOnceWith('browser-pane-7')
  expect(h.bridge.setBounds).not.toHaveBeenCalled()
})

it('adopts the named pane instead of opening one', async () => {
  const h = fixture({ pane: 'browser-pane-4' })
  h.bridge.adopt.mockResolvedValueOnce(h.state('browser-pane-4', { url: target.url, title: 'Agent', owner: 'ui', session: 's1' }))
  h.mount()
  await vi.waitFor(() => { expect(h.frame.getSnapshot()).toMatchObject({ address: 'observed', target: { url: target.url, title: 'Agent' } }) })
  expect(h.bridge.adopt).toHaveBeenCalledExactlyOnceWith('browser-pane-4')
  expect(h.bridge.open).not.toHaveBeenCalled()
  expect(h.bridge.navigate).not.toHaveBeenCalled()
  h.frame.reload()
  expect(h.bridge.command).toHaveBeenCalledExactlyOnceWith('browser-pane-4', 'reload')
})

it('behaves like an empty tab when adoption fails', async () => {
  const h = fixture({ pane: 'browser-pane-gone' })
  h.bridge.adopt.mockRejectedValueOnce('unknown pane')
  h.mount()
  await vi.waitFor(() => { expect(h.bridge.adopt).toHaveBeenCalledOnce() })
  await Promise.resolve()
  expect(h.bridge.open).not.toHaveBeenCalled()
  expect(h.frame.getSnapshot()).toMatchObject({ address: 'empty', error: undefined })
  h.frame.loadUrl(target)
  await vi.waitFor(() => { expect(h.bridge.open).toHaveBeenCalledExactlyOnceWith(target.url) })
  expect(h.bridge.adopt).toHaveBeenCalledOnce()
})

it('drops a pane the shell closed, keeps its target and reopens on reload', async () => {
  const h = fixture()
  h.mount()
  h.frame.loadUrl(target)
  await vi.waitFor(() => { expect(h.pending()).toBe(1) })
  h.emit('plexar-browser:state', h.state('browser-pane-1', { url: target.url, canGoBack: true }))
  h.emit('plexar-browser:closed', { id: 'browser-pane-2' })
  expect(h.frame.getSnapshot().canGoBack).toBe(true)
  h.emit('plexar-browser:closed', { id: 'browser-pane-1' })
  expect(h.frame.getSnapshot()).toMatchObject({ target: { url: target.url }, canGoBack: false, loading: false })
  h.emit('plexar-browser:open-requested', { id: 'browser-pane-1', url: 'https://late.test/' })
  expect(h.openRequested).not.toHaveBeenCalled()
  h.frame.reload()
  await vi.waitFor(() => { expect(h.bridge.open).toHaveBeenCalledTimes(2) })
  expect(h.bridge.open).toHaveBeenLastCalledWith(target.url)
  await h.frame.dispose()
  expect(h.bridge.close).toHaveBeenCalledExactlyOnceWith('browser-pane-2')
})

it('contains open and command failures and keeps retry available', async () => {
  const h = fixture()
  const error = vi.spyOn(console, 'error').mockImplementation(() => {})
  h.bridge.open.mockRejectedValueOnce(new Error('open failed'))
  h.mount()
  h.frame.loadUrl(target)
  await vi.waitFor(() => { expect(h.frame.getSnapshot().error).toBeDefined() })
  h.frame.reload()
  await vi.waitFor(() => { expect(h.bridge.open).toHaveBeenCalledTimes(2) })
  await vi.waitFor(() => { expect(h.frame.getSnapshot().error).toBeUndefined() })
  h.emit('plexar-browser:state', h.state('browser-pane-1', { url: target.url }))
  h.bridge.command.mockRejectedValueOnce(new Error('command failed'))
  h.frame.reload()
  await vi.waitFor(() => { expect(h.frame.getSnapshot().error).toBeDefined() })
  expect(error).toHaveBeenCalledTimes(2)
})

it('detects the shell synchronously and unlistens a subscription that resolves after removal', async () => {
  expect(nativePaneBridge({})).toBeUndefined()
  expect(nativePaneBridge({ __TAURI__: { core: {} } })).toBeUndefined()
  expect(nativePaneBridge({ __TAURI__: { core: { invoke: () => {} }, event: {} } })).toBeUndefined()
  const unlisten = vi.fn()
  const subscribed = Promise.withResolvers<() => void>()
  const handlers: ((event: { payload: unknown }) => void)[] = []
  const invoke = vi.fn(async () => null)
  const bridge = nativePaneBridge({ __TAURI__: { core: { invoke }, event: {
    listen: vi.fn((_event: string, handler: (event: { payload: unknown }) => void) => {
      handlers.push(handler)
      return subscribed.promise
    }),
  } } })!
  const listener = vi.fn()
  const stop = bridge.listen('plexar-browser:closed', listener)
  stop()
  handlers[0]!({ payload: { id: 'x' } })
  subscribed.resolve(unlisten)
  await vi.waitFor(() => { expect(unlisten).toHaveBeenCalledOnce() })
  expect(listener).not.toHaveBeenCalled()
  await bridge.setBounds('browser-pane-1', { x: 1, y: 2, width: 3, height: 4, visible: true })
  await bridge.open(undefined)
  await bridge.command('browser-pane-1', 'stop')
  expect(invoke.mock.calls).toEqual([
    ['browser_pane_set_bounds', { id: 'browser-pane-1', x: 1, y: 2, width: 3, height: 4, visible: true }],
    ['browser_pane_open', {}],
    ['browser_pane_command', { id: 'browser-pane-1', command: 'stop' }],
  ])
})
