/** Native pane placement: the pane is an OS view above the DOM, so it follows a measured element box. */
import type { BrowserPresentation } from '../view/BrowserPresentation.ts'
import type { PaneBounds } from './bridge.ts'

/** Physical attachment notifications; hiding a retained Sidebar body emits neither. */
export interface NativePresentationEvents {
  readonly mounted: () => void
  readonly unmounted: () => void
}

/** Browser observation primitives, injectable because jsdom lacks the observers. */
export interface NativePresentationEnvironment {
  readonly window: Window
  readonly ResizeObserver: typeof ResizeObserver | undefined
  readonly IntersectionObserver: typeof IntersectionObserver | undefined
  readonly requestAnimationFrame: (callback: () => void) => number
  readonly cancelAnimationFrame: (handle: number) => void
}

const HIDDEN: PaneBounds = { x: 0, y: 0, width: 0, height: 0, visible: false }

/**
 * @returns the current global observation primitives, guarding the absent ones.
 */
function globalEnvironment(): NativePresentationEnvironment {
  return {
    window,
    ResizeObserver: typeof ResizeObserver === 'function' ? ResizeObserver : undefined,
    IntersectionObserver: typeof IntersectionObserver === 'function' ? IntersectionObserver : undefined,
    requestAnimationFrame: callback => window.requestAnimationFrame(callback),
    cancelAnimationFrame: (handle) => { window.cancelAnimationFrame(handle) },
  }
}

/**
 * Measure where a pane should be.
 * @param element - content container.
 * @param view - its window.
 * @returns rounded viewport bounds, or the hidden form for a detached, undisplayed, empty or off-screen box.
 */
function measure(element: HTMLElement, view: Window): PaneBounds {
  if (!element.isConnected) return HIDDEN
  const check = (element as HTMLElement & { checkVisibility?: (options?: object) => boolean }).checkVisibility
  if (typeof check === 'function' && !check.call(element, { visibilityProperty: true })) return HIDDEN
  const rect = element.getBoundingClientRect()
  const x = Math.round(rect.left)
  const y = Math.round(rect.top)
  const width = Math.round(rect.width)
  const height = Math.round(rect.height)
  if (width < 1 || height < 1 || x + width <= 0 || y + height <= 0 || x >= view.innerWidth || y >= view.innerHeight) return HIDDEN
  return { x, y, width, height, visible: true }
}

/** Tracks one content container and places the current pane over it. */
export class NativePanePresentation implements BrowserPresentation {
  private element: HTMLElement | undefined
  private pane: string | undefined
  private sent: PaneBounds | undefined
  private frame: number | undefined
  private stopTracking: (() => void) | undefined
  private readonly environment: NativePresentationEnvironment

  /**
   * @param setBounds - shell placement command for one pane.
   * @param events - physical attachment notifications for the navigation provider.
   * @param environment - observation primitives; defaults to the page's globals.
   */
  constructor(private readonly setBounds: (id: string, bounds: PaneBounds) => Promise<void>,
    private readonly events: NativePresentationEvents, environment?: NativePresentationEnvironment) {
    this.environment = environment ?? globalEnvironment()
  }

  /** @param viewportId - committed content container. @returns ends tracking and hides the pane. */
  mount(viewportId: string): () => void {
    const element = document.getElementById(viewportId)
    if (element === null) throw new Error('Native pane presentation: content container is not mounted')
    if (this.element !== undefined) { this.untrack(); this.events.unmounted() }
    this.element = element
    this.track(element)
    this.events.mounted()
    this.schedule()
    return () => {
      if (this.element !== element) return
      this.untrack()
      this.element = undefined
      this.hide()
      this.events.unmounted()
    }
  }

  /**
   * Place a different pane, or none, over the tracked container.
   * @param id - the pane now shown by this tab, or undefined when it has none.
   */
  setPane(id: string | undefined): void {
    if (id === this.pane) return
    this.pane = id
    this.sent = undefined
    this.schedule()
  }

  /** Stop tracking and hide the pane; the provider closes it. */
  dispose(): void {
    this.untrack()
    this.element = undefined
    this.hide()
    this.pane = undefined
  }

  private track(element: HTMLElement): void {
    const { window: view, ResizeObserver: Resize, IntersectionObserver: Intersection } = this.environment
    const schedule = (): void => { this.schedule() }
    const resize = Resize === undefined ? undefined : new Resize(schedule)
    resize?.observe(element)
    const intersection = Intersection === undefined ? undefined : new Intersection(schedule)
    intersection?.observe(element)
    view.addEventListener('resize', schedule)
    view.addEventListener('scroll', schedule, { capture: true })
    this.stopTracking = () => {
      resize?.disconnect()
      intersection?.disconnect()
      view.removeEventListener('resize', schedule)
      view.removeEventListener('scroll', schedule, { capture: true })
    }
  }

  private untrack(): void {
    this.stopTracking?.()
    this.stopTracking = undefined
    if (this.frame !== undefined) this.environment.cancelAnimationFrame(this.frame)
    this.frame = undefined
  }

  private schedule(): void {
    if (this.frame !== undefined || this.element === undefined || this.pane === undefined) return
    this.frame = this.environment.requestAnimationFrame(() => {
      this.frame = undefined
      if (this.element === undefined) return
      const bounds = measure(this.element, this.environment.window)
      this.send(bounds)
      // Position-only moves fire no observer, so a visible pane re-measures every frame; observers restart a hidden one.
      if (bounds.visible) this.schedule()
    })
  }

  private hide(): void {
    if (this.frame !== undefined) this.environment.cancelAnimationFrame(this.frame)
    this.frame = undefined
    this.send(HIDDEN)
  }

  private send(bounds: PaneBounds): void {
    const pane = this.pane
    const sent = this.sent
    if (pane === undefined) return
    if (sent !== undefined && sent.visible === bounds.visible && sent.x === bounds.x && sent.y === bounds.y
      && sent.width === bounds.width && sent.height === bounds.height) return
    this.sent = bounds
    this.setBounds(pane, bounds).catch((error: unknown) => {
      if (this.sent === bounds) this.sent = undefined
      console.error('Native browser pane placement failed', error)
    })
  }
}
