/**
 * The rail's shown/hidden choice: one per viewer, remembered in browser
 * storage and mirrored into the frame through `ctx.layout`. This package is
 * the only writer of the frame's envbar request, so the local snapshot and the
 * frame never disagree.
 */
import { createSnapshotStore, type SnapshotStore } from '@deepseek-ai/dsh-client-store'
import type { ILayout } from '@deepseek-ai/dsh-client-ui-layout/client'

/** Browser-storage key of the remembered choice (`'1'` shown, `'0'` hidden). */
export const SHOWN_KEY = 'plexar.envbar.shown'

/** Read the remembered choice; absent, unreadable, or blocked storage reads as hidden. */
function readShown(): boolean {
  try {
    return globalThis.localStorage.getItem(SHOWN_KEY) === '1'
  } catch (_blocked) {
    return false
  }
}

/** Remember the choice; a blocked or full storage only loses the memory. */
function writeShown(shown: boolean): void {
  try {
    globalThis.localStorage.setItem(SHOWN_KEY, shown ? '1' : '0')
  } catch (_blocked) {
    // The rail still works for this page; only the next visit forgets.
  }
}

/** Shown/hidden state shared by the header toggle, the rail, and the frame. */
export class RailState {
  /** Snapshot the toggle's `aria-pressed` and the panel's polling read. */
  readonly shown: SnapshotStore<boolean>

  /** @param layout - the frame's panel-action face. */
  constructor(private readonly layout: Pick<ILayout, 'openEnvbar' | 'closeEnvbar' | 'toggleEnvbar'>) {
    this.shown = createSnapshotStore(false)
  }

  /** Apply the remembered choice to the frame. */
  restore(): void {
    const shown = readShown()
    this.shown.set(shown)
    if (shown) this.layout.openEnvbar()
    else this.layout.closeEnvbar()
  }

  /** Flip the rail and remember the result. */
  toggle(): void {
    this.layout.toggleEnvbar()
    const shown = !this.shown.getSnapshot()
    this.shown.set(shown)
    writeShown(shown)
  }

  /** Hide the rail and remember that. */
  close(): void {
    this.layout.closeEnvbar()
    this.shown.set(false)
    writeShown(false)
  }
}
