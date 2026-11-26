/** A fake desktop shell and observation environment; navigation and placement stay real. */
import { vi } from 'vitest'
import type { BrowserTabState } from '../src/client/browser/BrowserPersistence.ts'
import type { NativePaneBridge, PaneEvents, PaneState } from '../src/client/native/bridge.ts'
import { createNativePanePage } from '../src/client/native/pages.ts'
import type { NativePresentationEnvironment } from '../src/client/native/NativePanePresentation.ts'

let sequence = 0

/** @returns a shell double whose events each test emits explicitly. */
export function fakeShell() {
  const listeners = new Map<string, Set<(payload: never) => void>>()
  let panes = 0
  const state = (id: string, fields: Partial<PaneState> = {}): PaneState => ({ id, url: 'about:blank', title: '',
    loading: false, canGoBack: false, canGoForward: false, owner: 'ui', ...fields })
  const bridge = {
    open: vi.fn(async (_url: string | undefined) => state(`browser-pane-${++panes}`)),
    adopt: vi.fn(async (id: string): Promise<PaneState> => state(id)),
    navigate: vi.fn(async (_id: string, _url: string) => {}),
    command: vi.fn(async (_id: string, _command: string) => {}),
    setBounds: vi.fn(async (_id: string, _bounds: object) => {}),
    close: vi.fn(async (_id: string) => {}),
    list: vi.fn(async (): Promise<readonly PaneState[]> => []),
    listen: vi.fn((event: string, listener: (payload: never) => void) => {
      const set = listeners.get(event) ?? new Set()
      listeners.set(event, set)
      set.add(listener)
      return () => { set.delete(listener) }
    }),
  } satisfies NativePaneBridge
  return {
    bridge, state,
    emit<E extends keyof PaneEvents>(event: E, payload: PaneEvents[E]): void {
      for (const listener of [...listeners.get(event) ?? []]) listener(payload as never)
    },
    listenerCount: () => [...listeners.values()].reduce((total, set) => total + set.size, 0),
  }
}

/** @returns observation primitives with manual animation frames and observer triggers. */
export function fakeEnvironment() {
  const frames = new Map<number, () => void>()
  let handles = 0
  const observers = new Set<() => void>()
  class Observer {
    constructor(private readonly callback: () => void) {}
    observe(): void { observers.add(this.callback) }
    disconnect(): void { observers.delete(this.callback) }
    unobserve(): void {}
    takeRecords(): never[] { return [] }
  }
  const environment: NativePresentationEnvironment = {
    window,
    ResizeObserver: Observer as unknown as typeof ResizeObserver,
    IntersectionObserver: Observer as unknown as typeof IntersectionObserver,
    requestAnimationFrame: (callback) => { frames.set(++handles, callback); return handles },
    cancelAnimationFrame: (handle) => { frames.delete(handle) },
  }
  return {
    environment, observers,
    /** Run every queued animation frame. */
    flush(): void {
      const queued = [...frames.values()]
      frames.clear()
      for (const callback of queued) callback()
    },
    pending: () => frames.size,
    /** Simulate the element's box changing. */
    observe(): void { for (const callback of observers) callback() },
  }
}

/**
 * Give an element a fixed or hidden box; jsdom performs no layout.
 * @param element - content container.
 * @param box - left, top, width and height in CSS pixels.
 */
export function setBox(element: HTMLElement, box: { x: number; y: number; width: number; height: number }): void {
  element.getBoundingClientRect = () => ({ left: box.x, top: box.y, x: box.x, y: box.y, width: box.width, height: box.height,
    right: box.x + box.width, bottom: box.y + box.height, toJSON: () => ({}) })
}

/** @returns one isolated native page with a mounted-able content container. */
export function nativeFixture(options: { initial?: BrowserTabState; pane?: string } = {}) {
  const shell = fakeShell()
  const observation = fakeEnvironment()
  const persist = vi.fn()
  const openRequested = vi.fn()
  const page = createNativePanePage({ initial: options.initial, persist, openRequested,
    ...options.pane === undefined ? {} : { pane: options.pane } }, shell.bridge, observation.environment)
  const host = document.createElement('div')
  host.id = `native-fixture-${++sequence}`
  setBox(host, { x: 10, y: 20, width: 300, height: 400 })
  document.body.append(host)
  return {
    ...page, ...shell, ...observation, persist, openRequested, host,
    mount: () => page.presentation.mount(host.id),
    async dispose() {
      await page.frame.dispose()
      host.remove()
    },
  }
}
