/**
 * Plexar accent palette. The design platform draws its accents (send button, links, focus rings,
 * active states) from the `--dsw-static-deepseek-*` scale; this sheet redefines that scale in the
 * Plexar orange for both themes. Selectors match the platform's own (`body`, `body[data-ds-dark-theme]`)
 * with one extra `html` so this sheet wins regardless of load order. Every step is derived from the
 * shared `--px-accent` token (see `tokens/`) by mixing it toward white (lighter steps) or black
 * (darker steps), so a token update re-derives the whole scale.
 */
const SCALE: Record<string, string> = {
  '50': 'color-mix(in srgb, var(--px-accent) 8%, white)',
  '100': 'color-mix(in srgb, var(--px-accent) 18%, white)',
  '200': 'color-mix(in srgb, var(--px-accent) 34%, white)',
  '300': 'color-mix(in srgb, var(--px-accent) 52%, white)',
  '400': 'color-mix(in srgb, var(--px-accent) 72%, white)',
  '450': 'var(--px-accent)',
  '500': 'color-mix(in srgb, var(--px-accent) 88%, black)',
  '600': 'color-mix(in srgb, var(--px-accent) 72%, black)',
  '700-delete': 'color-mix(in srgb, var(--px-accent) 55%, black)',
  '800': 'color-mix(in srgb, var(--px-accent) 32%, black)',
  '900': 'color-mix(in srgb, var(--px-accent) 20%, black)',
}

const declarations = Object.entries(SCALE).map(([step, value]) => `--dsw-static-deepseek-${step}: ${value};`).join(' ')

/** Stylesheet text applying the Plexar accent scale in light and dark themes. */
export const PLEXAR_PALETTE_CSS = `html body, html body[data-ds-dark-theme] { ${declarations} }`

/**
 * Add the palette sheet to the document.
 * @param doc - the page document.
 * @returns removes the sheet.
 */
export function installPalette(doc: Document): () => void {
  const style = doc.createElement('style')
  style.dataset.plexarPalette = ''
  style.textContent = PLEXAR_PALETTE_CSS
  doc.head.appendChild(style)
  return () => { style.remove() }
}

/**
 * Plexar glassmorphism sheet. Overrides the design platform's surface tokens
 * (`--dsw-specific-sidebar-fill`, `--dsw-specific-input-major`, `--dsw-specific-menu`,
 * `--dsw-alias-bg-layer-2`, `--dsw-alias-toast-bg`) with translucent rgba fills — the
 * sidebar (`SidebarRoot.module.css`) and the settings modal's layer-2 surface pick these
 * up through the variables alone, with no selector needed. `backdrop-filter:
 * blur(...) saturate(140%)` plus hairline borders are added directly to the surfaces
 * that carry a stable, non-hashed hook: the composer card (`[data-composer-card]`),
 * dropdown menus and popovers (`[role=menu]`), the settings modal and other dialogs
 * (`[role=dialog]`), and toasts (`[role=alert]`). `--dsw-alias-bg-base` gets a soft
 * radial Plexar-orange gradient so the blur has visible content behind it.
 * `prefers-reduced-transparency: reduce` restores opaque surfaces and drops the blur.
 *
 * The light-theme fills stay literal near-white rgba (the shared `--px-*` tokens are a dark
 * design with no light-theme surface values to map onto); the dark-theme fills and both themes'
 * orange background glow are derived from `--px-bg`/`--px-bg-2`/`--px-surface`/`--px-elev` and
 * `--px-accent`/`--px-accent-soft` with `color-mix` transparency instead.
 */
export const PLEXAR_GLASS_CSS = `
html body {
  --dsw-specific-sidebar-fill: rgba(255, 246, 238, 0.55);
  --dsw-specific-input-major: rgba(255, 255, 255, 0.55);
  --dsw-specific-menu: rgba(255, 255, 255, 0.65);
  --dsw-alias-bg-layer-2: rgba(255, 255, 255, 0.6);
  --dsw-alias-toast-bg: rgba(255, 255, 255, 0.72);
  background-image: radial-gradient(ellipse at top left, color-mix(in srgb, var(--px-accent) 8%, transparent), transparent 60%),
    radial-gradient(ellipse at bottom right, color-mix(in srgb, var(--px-accent-soft) 10%, transparent), transparent 55%);
  background-attachment: fixed;
}

html body[data-ds-dark-theme] {
  --dsw-alias-bg-base: var(--px-bg);
  --dsw-specific-sidebar-fill: color-mix(in srgb, var(--px-bg-2) 50%, transparent);
  --dsw-specific-input-major: color-mix(in srgb, var(--px-surface) 55%, transparent);
  --dsw-specific-menu: color-mix(in srgb, var(--px-surface) 68%, transparent);
  --dsw-alias-bg-layer-2: color-mix(in srgb, var(--px-surface) 60%, transparent);
  --dsw-alias-toast-bg: color-mix(in srgb, var(--px-elev) 75%, transparent);
  background-image: radial-gradient(ellipse at top left, color-mix(in srgb, var(--px-accent) 14%, transparent), transparent 60%),
    radial-gradient(ellipse at bottom right, color-mix(in srgb, var(--px-accent-soft) 10%, transparent), transparent 55%);
  background-attachment: fixed;
}

html body [data-composer-card],
html body [role="menu"],
html body [role="dialog"],
html body [role="alert"] {
  backdrop-filter: blur(20px) saturate(140%);
  -webkit-backdrop-filter: blur(20px) saturate(140%);
  border: 1px solid rgba(255, 255, 255, 0.1);
}

html body[data-ds-dark-theme] [data-composer-card],
html body[data-ds-dark-theme] [role="menu"],
html body[data-ds-dark-theme] [role="dialog"],
html body[data-ds-dark-theme] [role="alert"] {
  border-color: rgba(255, 255, 255, 0.1);
}

html body:not([data-ds-dark-theme]) [data-composer-card],
html body:not([data-ds-dark-theme]) [role="menu"],
html body:not([data-ds-dark-theme]) [role="dialog"],
html body:not([data-ds-dark-theme]) [role="alert"] {
  border-color: rgba(0, 0, 0, 0.08);
}

@media (prefers-reduced-transparency: reduce) {
  html body {
    --dsw-specific-sidebar-fill: var(--dsw-static-neutral-bluish-50);
    --dsw-specific-input-major: var(--dsw-static-neutral-bluish-00);
    --dsw-specific-menu: var(--dsw-static-neutral-bluish-00);
    --dsw-alias-bg-layer-2: var(--dsw-static-neutral-bluish-00);
    --dsw-alias-toast-bg: var(--dsw-static-neutral-bluish-800);
    background-image: none;
  }

  html body[data-ds-dark-theme] {
    --dsw-specific-sidebar-fill: var(--dsw-static-neutral-bluish-900);
    --dsw-specific-input-major: var(--dsw-static-neutral-bluish-850);
    --dsw-specific-menu: var(--dsw-static-neutral-bluish-850);
    --dsw-alias-bg-layer-2: var(--dsw-static-neutral-bluish-850);
    --dsw-alias-toast-bg: var(--dsw-static-neutral-bluish-750);
    background-image: none;
  }

  html body [data-composer-card],
  html body [role="menu"],
  html body [role="dialog"],
  html body [role="alert"] {
    backdrop-filter: none;
    -webkit-backdrop-filter: none;
  }
}
`

/**
 * Add the glassmorphism sheet to the document.
 * @param doc - the page document.
 * @returns removes the sheet.
 */
export function installGlass(doc: Document): () => void {
  const style = doc.createElement('style')
  style.dataset.plexarGlass = ''
  style.textContent = PLEXAR_GLASS_CSS
  doc.head.appendChild(style)
  return () => { style.remove() }
}
