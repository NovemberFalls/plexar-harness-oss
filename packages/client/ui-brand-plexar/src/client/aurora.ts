/**
 * Plexar aurora: slow, blurred light ribbons along the bottom of the window, drawn behind the
 * app's content as a light-only glow: fixed above the page with no pointer events, blended with
 * `screen` on dark themes (it can only brighten, so text stays readable) and a faint `multiply`
 * tint on light themes. Only `transform` and `opacity` animate, which the compositor
 * handles without repainting the page. `prefers-reduced-motion: reduce` stops the movement;
 * `prefers-reduced-transparency: reduce` hides the layer. The teal and violet ribbon stops stay
 * literal decorative colors with no brand-token equivalent; the orange stops derive from the
 * shared `--px-accent`/`--px-accent-soft` tokens.
 *
 * The layer shows only while the viewer's switch is on AND at least one blank-session hero
 * occupant (`PlexarHeroMark` / `PlexarHeroHeadline` in `Brand.tsx`) is mounted — those slots
 * render only on the empty/loading screen, never behind an open conversation or terminal output.
 * `auroraHeroOccupantMounted()` tracks the mounted count; the layer's `data-visible` attribute
 * cross-fades over ~600ms rather than popping.
 */

/** Aurora sheet: the container, three ribbons, and their drift and flicker keyframes. */
export const PLEXAR_AURORA_CSS = `
[data-plexar-aurora] {
  position: fixed;
  inset: auto 0 0 0;
  height: 42vh;
  z-index: 2147483000;
  pointer-events: none;
  mix-blend-mode: screen;
  opacity: 0;
  transition: opacity 600ms ease;
  overflow: hidden;
  -webkit-mask-image: linear-gradient(to top, #000 0%, #000 35%, transparent 100%);
  mask-image: linear-gradient(to top, #000 0%, #000 35%, transparent 100%);
}

[data-plexar-aurora][data-visible] {
  opacity: 0.32;
}

[data-plexar-aurora][hidden] {
  display: none;
}

[data-plexar-aurora] > span {
  position: absolute;
  left: -25%;
  width: 150%;
  height: 60%;
  border-radius: 50%;
  filter: blur(48px);
  will-change: transform, opacity;
}

[data-plexar-aurora] > span:nth-child(1) {
  bottom: -18%;
  background: linear-gradient(90deg, transparent 5%, color-mix(in srgb, var(--px-accent) 55%, transparent) 30%, color-mix(in srgb, var(--px-accent-soft) 45%, transparent) 55%, transparent 85%);
  animation: plexar-aurora-drift-a 26s ease-in-out infinite alternate, plexar-aurora-flicker 12s ease-in-out infinite;
}

[data-plexar-aurora] > span:nth-child(2) {
  bottom: -6%;
  background: linear-gradient(90deg, transparent 10%, rgba(64, 214, 170, 0.32) 35%, rgba(90, 170, 255, 0.28) 60%, transparent 90%);
  animation: plexar-aurora-drift-b 34s ease-in-out infinite alternate, plexar-aurora-flicker 17s ease-in-out -4s infinite;
}

[data-plexar-aurora] > span:nth-child(3) {
  bottom: -26%;
  background: linear-gradient(90deg, transparent 15%, rgba(214, 90, 255, 0.28) 40%, color-mix(in srgb, var(--px-accent) 35%, transparent) 70%, transparent 95%);
  animation: plexar-aurora-drift-a 41s ease-in-out -12s infinite alternate-reverse, plexar-aurora-flicker 14s ease-in-out -7s infinite;
}

html body:not([data-ds-dark-theme]) [data-plexar-aurora][data-visible] {
  mix-blend-mode: multiply;
  opacity: 0.12;
}

@keyframes plexar-aurora-drift-a {
  from { transform: translateX(-8%) skewX(-8deg) scaleY(0.9); }
  to { transform: translateX(8%) skewX(6deg) scaleY(1.15); }
}

@keyframes plexar-aurora-drift-b {
  from { transform: translateX(10%) skewX(10deg) scaleY(1.1); }
  to { transform: translateX(-10%) skewX(-6deg) scaleY(0.85); }
}

@keyframes plexar-aurora-flicker {
  0%, 100% { opacity: 0.55; }
  40% { opacity: 1; }
  70% { opacity: 0.7; }
}

@media (prefers-reduced-motion: reduce) {
  [data-plexar-aurora] > span {
    animation: none;
  }
}

@media (prefers-reduced-transparency: reduce) {
  [data-plexar-aurora] {
    display: none;
  }
}
`

/** The per-viewer aurora switch, provided as `ctx.plexarAurora` for the Settings > Features row. */
export interface AuroraPreference {
  /** Whether the aurora currently shows. */
  isEnabled(): boolean
  /**
   * Show or hide the aurora on the open page and remember the choice in this browser.
   * @param enabled - whether the aurora shows.
   */
  setEnabled(enabled: boolean): void
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    plexarAurora: AuroraPreference
  }
}

/** Browser-storage key of the per-viewer aurora preference: `'off'` hides it; anything else shows it. */
const PREFERENCE_KEY = 'plexar.aurora'
/** Window event carrying a changed preference to the installed layer. */
const CHANGE_EVENT = 'plexar:aurora'
/** Window event carrying a changed hero-occupant mount count to the installed layer. */
const HERO_MOUNT_CHANGE_EVENT = 'plexar:aurora-hero-mount'

/**
 * Count of currently mounted blank-session hero occupants (`PlexarHeroMark` / `PlexarHeroHeadline`),
 * module-scoped because a page runs one installed aurora layer. Owned by this module; hero
 * components change it only through `auroraHeroOccupantMounted`.
 */
let heroOccupantMountCount = 0

/**
 * Record that a blank-session hero occupant mounted, called from the occupant's own effect.
 * The aurora shows only while this count is above zero (and the viewer switch is on).
 * @returns unmount callback the same effect calls on cleanup; idempotent against double calls.
 */
export function auroraHeroOccupantMounted(): () => void {
  heroOccupantMountCount += 1
  window.dispatchEvent(new CustomEvent(HERO_MOUNT_CHANGE_EVENT))
  let unmounted = false
  return () => {
    if (unmounted) return
    unmounted = true
    heroOccupantMountCount -= 1
    window.dispatchEvent(new CustomEvent(HERO_MOUNT_CHANGE_EVENT))
  }
}

/**
 * Whether the aurora is switched on for this viewer. On unless switched off; storage that
 * cannot be read counts as on.
 * @returns the current preference.
 */
export function isAuroraEnabled(): boolean {
  try {
    return localStorage.getItem(PREFERENCE_KEY) !== 'off'
  } catch (error) {
    // Storage blocked (private window, locked-down WebView): the default applies.
    void error
    return true
  }
}

/**
 * Switch the aurora on or off for this viewer and apply it to the open page at once.
 * @param enabled - whether the aurora shows.
 */
export function setAuroraEnabled(enabled: boolean): void {
  try {
    localStorage.setItem(PREFERENCE_KEY, enabled ? 'on' : 'off')
  } catch (error) {
    // Storage blocked: the change still applies to this page, it just is not remembered.
    void error
  }
  window.dispatchEvent(new CustomEvent<boolean>(CHANGE_EVENT, { detail: enabled }))
}

/**
 * Add the aurora layer and its sheet to the document. The layer cross-fades to visible only
 * while the viewer's switch is on AND a blank-session hero occupant is mounted; the switch
 * always wins when off.
 * @param doc - the page document.
 * @returns removes both and stops listening for preference and mount-count changes.
 */
export function installAurora(doc: Document): () => void {
  const style = doc.createElement('style')
  style.dataset.plexarAuroraSheet = ''
  style.textContent = PLEXAR_AURORA_CSS
  doc.head.appendChild(style)
  const layer = doc.createElement('div')
  layer.dataset.plexarAurora = ''
  layer.setAttribute('aria-hidden', 'true')
  for (let i = 0; i < 3; i++) layer.appendChild(doc.createElement('span'))
  doc.body.prepend(layer)
  const updateVisibility = (): void => {
    if (isAuroraEnabled() && heroOccupantMountCount > 0) layer.setAttribute('data-visible', '')
    else layer.removeAttribute('data-visible')
  }
  updateVisibility()
  window.addEventListener(CHANGE_EVENT, updateVisibility)
  window.addEventListener(HERO_MOUNT_CHANGE_EVENT, updateVisibility)
  return () => {
    window.removeEventListener(CHANGE_EVENT, updateVisibility)
    window.removeEventListener(HERO_MOUNT_CHANGE_EVENT, updateVisibility)
    layer.remove()
    style.remove()
  }
}
