/** Typed access to the desktop shell's native browser panes; the only module that reads `__TAURI__`. */

/** One native pane as the shell reports it. */
export interface PaneState {
  /** The shell's webview label, for example `browser-pane-3`. */
  readonly id: string
  /** Current top-level URL; `about:blank` before the first navigation. */
  readonly url: string
  /** Document title; empty when unknown. */
  readonly title: string
  readonly loading: boolean
  readonly canGoBack: boolean
  readonly canGoForward: boolean
  readonly owner: 'ui' | 'agent'
  /** Present on panes the shell created for an agent Session. */
  readonly session?: string
}

/** Pane placement in CSS pixels relative to the main webview's viewport. */
export interface PaneBounds {
  readonly x: number
  readonly y: number
  readonly width: number
  readonly height: number
  readonly visible: boolean
}

/** History commands a pane accepts. */
export type PaneCommand = 'back' | 'forward' | 'reload' | 'stop'

/** Shell event names and their payloads. */
export interface PaneEvents {
  readonly 'plexar-browser:state': PaneState
  readonly 'plexar-browser:open-requested': { readonly id: string; readonly url: string }
  readonly 'plexar-browser:agent-opened': { readonly id: string; readonly session: string }
  readonly 'plexar-browser:closed': { readonly id: string }
  readonly 'plexar-browser:load-failed': { readonly id: string; readonly code?: number; readonly description?: string }
}

/** Pane commands and events, with no Tauri objects crossing the interface. */
export interface NativePaneBridge {
  /** @param url - optional first address. @returns the new UI-owned pane. */
  open(url: string | undefined): Promise<PaneState>
  /** @param id - agent pane to take over. @returns its state, now UI-owned. */
  adopt(id: string): Promise<PaneState>
  /** @param id - pane. @param url - allowed HTTP(S) address. */
  navigate(id: string, url: string): Promise<void>
  /** @param id - pane. @param command - history command. */
  command(id: string, command: PaneCommand): Promise<void>
  /** @param id - pane. @param bounds - placement; `visible: false` hides it. */
  setBounds(id: string, bounds: PaneBounds): Promise<void>
  /** @param id - pane; an unknown id succeeds. */
  close(id: string): Promise<void>
  /** @returns every live pane. */
  list(): Promise<readonly PaneState[]>
  /**
   * @param event - shell event name.
   * @param listener - receives every pane's payload; callers filter by id.
   * @returns unsubscribe callback, effective even before the shell confirmed the subscription.
   */
  listen<E extends keyof PaneEvents>(event: E, listener: (payload: PaneEvents[E]) => void): () => void
}

/** The minimal global Tauri API surface used here (`withGlobalTauri`). */
interface TauriGlobal {
  readonly core?: { readonly invoke?: unknown }
  readonly event?: { readonly listen?: unknown }
}

type Invoke = (command: string, args?: Record<string, unknown>) => Promise<unknown>
type Listen = (event: string, handler: (event: { readonly payload: unknown }) => void) => Promise<() => void>

/**
 * Detect the desktop shell synchronously.
 * @param scope - global object to inspect.
 * @returns a bridge when the Tauri invoke and listen functions are present; never throws.
 */
export function nativePaneBridge(scope: object = globalThis): NativePaneBridge | undefined {
  const tauri = (scope as { readonly __TAURI__?: TauriGlobal }).__TAURI__
  const core = tauri?.core
  const events = tauri?.event
  const invoke = core?.invoke
  const listen = events?.listen
  if (typeof invoke !== 'function' || typeof listen !== 'function') return undefined
  return createNativePaneBridge(invoke.bind(core) as Invoke, listen.bind(events) as Listen)
}

function createNativePaneBridge(invoke: Invoke, listen: Listen): NativePaneBridge {
  return {
    open: async url => await invoke('browser_pane_open', url === undefined ? {} : { url }) as PaneState,
    adopt: async id => await invoke('browser_pane_adopt', { id }) as PaneState,
    navigate: async (id, url) => { await invoke('browser_pane_navigate', { id, url }) },
    command: async (id, command) => { await invoke('browser_pane_command', { id, command }) },
    setBounds: async (id, bounds) => { await invoke('browser_pane_set_bounds', { id, ...bounds }) },
    close: async (id) => { await invoke('browser_pane_close', { id }) },
    list: async () => await invoke('browser_pane_list', {}) as readonly PaneState[],
    listen(event, listener) {
      let stopped = false
      let unlisten: (() => void) | undefined
      listen(event, (message) => { if (!stopped) listener(message.payload as never) }).then((stop) => {
        if (stopped) stop()
        else unlisten = stop
      }, (error: unknown) => { console.error('Native browser event subscription failed', error) })
      return () => {
        if (stopped) return
        stopped = true
        unlisten?.()
        unlisten = undefined
      }
    },
  }
}
