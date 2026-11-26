/** Assemble native pane navigation and placement behind the shared BrowserPage interface. */
import type { BrowserPage, BrowserPageOptions } from '../browser/BrowserPage.ts'
import type { NativePaneBridge } from './bridge.ts'
import { NativePaneImpl } from './NativePaneImpl.ts'
import { NativePanePresentation, type NativePresentationEnvironment } from './NativePanePresentation.ts'

/**
 * Assemble an idle native pane provider; the pane opens on mounting and navigation, or adoption.
 * @param options - checkpoint, optional pane to adopt, and source-tab callbacks.
 * @param bridge - desktop shell pane transport.
 * @param environment - observation primitives for tests; defaults to the page's globals.
 * @returns separate navigation and presentation faces.
 */
export function createNativePanePage(options: BrowserPageOptions, bridge: NativePaneBridge,
  environment?: NativePresentationEnvironment): BrowserPage {
  const presentation = new NativePanePresentation((id, bounds) => bridge.setBounds(id, bounds), {
    mounted: () => { frame.attach() },
    unmounted: () => { frame.detach() },
  }, environment)
  const frame = new NativePaneImpl(options, bridge, presentation)
  return { frame, presentation }
}
