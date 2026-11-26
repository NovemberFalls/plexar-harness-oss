/** Native pane navigation and lifetime, independent from placement. */
import { createSnapshotStore, type SnapshotStore } from '@deepseek-ai/dsh-client-store'
import { emptyBrowserFrame, type BrowserFrame, type BrowserFrameState, type BrowserLoadError } from '../browser/BrowserFrame.ts'
import type { BrowserPageOptions } from '../browser/BrowserPage.ts'
import { browserAddressCheckpoint, currentBrowserTarget } from '../browser/BrowserPersistence.ts'
import { parseBrowserAddress, type BrowserTarget } from '../browser/url.ts'
import type { NativePaneBridge, PaneCommand, PaneState } from './bridge.ts'
import type { NativePanePresentation } from './NativePanePresentation.ts'

/** Chromium's code for a cancelled navigation, which is not a failure. */
const ERR_ABORTED = -3

/** Owns one shell pane and translates its reported state into common frame state. */
export class NativePaneImpl implements BrowserFrame {
  private readonly store: SnapshotStore<BrowserFrameState>
  private readonly lifetime = new AbortController()
  private readonly unlisten: readonly (() => void)[]
  private pane: string | undefined
  private opening: Promise<void> | undefined
  private attached = false
  private adoption: string | undefined
  private pending: BrowserTarget | undefined
  private revision = 0
  private checkpoint: BrowserTarget | undefined
  private disposal: Promise<void> | undefined

  /**
   * @param options - saved address, optional pane to adopt, persistence and source-tab opening callback.
   * @param bridge - shell pane operations and events.
   * @param presentation - placement adapter for the current pane.
   */
  constructor(private readonly options: BrowserPageOptions, private readonly bridge: NativePaneBridge,
    private readonly presentation: NativePanePresentation) {
    this.checkpoint = currentBrowserTarget(options.initial)
    this.adoption = options.pane
    this.store = createSnapshotStore(emptyBrowserFrame())
    this.unlisten = [
      bridge.listen('plexar-browser:state', (state) => { if (this.owns(state.id)) this.observe(state) }),
      bridge.listen('plexar-browser:open-requested', ({ id, url }) => { if (this.owns(id)) this.options.openRequested(url) }),
      bridge.listen('plexar-browser:load-failed', ({ id, code, description }) => {
        if (this.owns(id) && code !== ERR_ABORTED) this.failed({ code, description })
      }),
      bridge.listen('plexar-browser:closed', ({ id }) => { if (this.owns(id)) this.lost() }),
    ]
  }

  /** @returns immutable carrier-neutral navigation state. */
  getSnapshot = (): BrowserFrameState => this.store.getSnapshot()
  /** @param listener - state invalidation. @returns unsubscribe callback. */
  subscribe = (listener: () => void): (() => void) => this.store.subscribe(listener)

  /** A physical mount adopts or reopens a pane when one is wanted; ordinary Sidebar hiding never calls this. */
  attach(): void {
    if (this.lifetime.signal.aborted) return
    this.attached = true
    if (this.pane !== undefined) return
    this.pending ??= this.store.getSnapshot().target
    if (this.pending !== undefined) {
      this.store.set({ ...this.store.getSnapshot(), address: 'requested', loading: true,
        canGoBack: false, canGoForward: false, error: undefined })
    }
    if (this.pending !== undefined || this.adoption !== undefined) this.initialize()
  }

  /** The pane stays open and hidden; a later mount places it again. */
  detach(): void {
    this.attached = false
  }

  /** @param target - validated address, loaded in the existing pane when there is one. */
  loadUrl(target: BrowserTarget): void {
    if (this.lifetime.signal.aborted) return
    const current = this.store.getSnapshot()
    if (this.pane !== undefined && current.address === 'observed' && current.target?.url === target.url) {
      this.reload()
      return
    }
    this.revision++
    this.pending = target
    this.store.set({ ...current, target, address: 'requested', loading: true, error: undefined })
    this.persist(target)
    if (this.pane !== undefined) this.loadPending()
    else this.initialize()
  }

  /** Move backward through the pane's history. */
  goBack(): void {
    if (this.store.getSnapshot().canGoBack) this.command('back')
  }

  /** Move forward through the pane's history. */
  goForward(): void {
    if (this.store.getSnapshot().canGoForward) this.command('forward')
  }

  /** Reload the current page, or reopen a lost or failed pane at the last target. */
  reload(): void {
    const current = this.store.getSnapshot()
    if (this.lifetime.signal.aborted || current.target === undefined) return
    if (this.pane === undefined || current.error !== undefined) {
      this.revision++
      this.pending = current.target
      this.store.set({ ...current, loading: true, error: undefined })
      if (this.pane !== undefined) this.loadPending()
      else this.initialize()
    } else this.command('reload')
  }

  /** @returns after listeners are removed and the owned pane, including a late-opened one, is closed. */
  dispose(): Promise<void> {
    if (this.disposal !== undefined) return this.disposal
    this.lifetime.abort()
    this.pending = undefined
    for (const unlisten of this.unlisten) unlisten()
    this.presentation.dispose()
    const pane = this.pane
    this.pane = undefined
    this.disposal = Promise.all([pane === undefined ? undefined : this.close(pane), this.opening]).then(() => {})
    return this.disposal
  }

  private owns(id: string): boolean {
    return !this.lifetime.signal.aborted && this.pane !== undefined && id === this.pane
  }

  private initialize(): void {
    if (!this.attached || this.opening !== undefined || this.pane !== undefined || this.lifetime.signal.aborted) return
    const adoption = this.adoption
    this.adoption = undefined
    const requested = this.pending
    this.opening = this.openPane(adoption, requested).catch((error: unknown) => {
      if (!this.lifetime.signal.aborted) this.commandFailed(error)
    }).finally(() => {
      this.opening = undefined
      if (this.pane === undefined && this.attached && this.pending !== undefined) this.initialize()
    })
  }

  private async openPane(adoption: string | undefined, requested: BrowserTarget | undefined): Promise<void> {
    let state: PaneState | undefined
    if (adoption !== undefined) {
      // A pane that no longer exists leaves the tab as if it had been opened without one.
      state = await this.bridge.adopt(adoption).catch(() => undefined)
      if (state === undefined && (this.pending === undefined || this.lifetime.signal.aborted)) return
    }
    if (state === undefined) {
      state = await this.bridge.open(requested?.url)
      if (this.pending === requested) this.pending = undefined
    }
    if (this.lifetime.signal.aborted) {
      await this.close(state.id)
      return
    }
    this.pane = state.id
    this.presentation.setPane(state.id)
    this.observe(state)
    this.loadPending()
  }

  private loadPending(): void {
    const target = this.pending
    const pane = this.pane
    if (target === undefined || pane === undefined) return
    const revision = this.revision
    this.pending = undefined
    this.bridge.navigate(pane, target.url).catch((error: unknown) => {
      if (this.pane !== pane || this.lifetime.signal.aborted || this.revision !== revision) return
      this.commandFailed(error)
    })
  }

  private command(command: PaneCommand): void {
    const pane = this.pane
    if (this.lifetime.signal.aborted || pane === undefined) return
    this.revision++
    this.pending = undefined
    this.store.set({ ...this.store.getSnapshot(), loading: true, error: undefined })
    this.bridge.command(pane, command).catch((error: unknown) => {
      if (this.pane === pane && !this.lifetime.signal.aborted) this.commandFailed(error)
    })
  }

  private observe(state: PaneState): void {
    const current = this.store.getSnapshot()
    const parsed = parseBrowserAddress(state.url)
    let target = current.target
    let address = current.address
    if (parsed.ok) {
      target = { ...parsed.target, title: state.title || parsed.target.title }
      address = 'observed'
    }
    const error = state.loading && !current.loading ? undefined : current.error
    const loading = error === undefined && state.loading
    if (target?.url !== current.target?.url || target?.title !== current.target?.title || address !== current.address
      || loading !== current.loading || error !== current.error
      || state.canGoBack !== current.canGoBack || state.canGoForward !== current.canGoForward) {
      this.store.set({ ...current, target, address, loading, error,
        canGoBack: state.canGoBack, canGoForward: state.canGoForward })
    }
    if (parsed.ok && target !== undefined) this.persist(target)
  }

  private lost(): void {
    this.pane = undefined
    this.presentation.setPane(undefined)
    this.store.set({ ...this.store.getSnapshot(), loading: false, canGoBack: false, canGoForward: false })
  }

  private persist(target: BrowserTarget): void {
    if (target.url === this.checkpoint?.url && target.title === this.checkpoint.title) return
    this.checkpoint = target
    this.options.persist(browserAddressCheckpoint(target, this.revision))
  }

  private failed(error: BrowserLoadError = { code: undefined, description: undefined }): void {
    if (this.lifetime.signal.aborted) return
    const current = this.store.getSnapshot()
    this.store.set({ ...current, loading: false, error,
      canGoBack: this.pane !== undefined && current.canGoBack, canGoForward: this.pane !== undefined && current.canGoForward })
  }

  private commandFailed(error: unknown): void {
    console.error('Native browser pane operation failed', error)
    this.failed()
  }

  private close(pane: string): Promise<void> {
    return this.bridge.close(pane).catch((error: unknown) => { console.error('Native browser pane close failed', error) })
  }
}
