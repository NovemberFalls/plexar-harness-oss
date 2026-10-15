// @vitest-environment jsdom
/**
 * The glassmorphism sheet: it names the surfaces the card requires, restores
 * opaque surfaces under `prefers-reduced-transparency: reduce`, and disposal
 * removes the injected `<style>`.
 */
import { afterEach, describe, expect, it } from 'vitest'
import { installGlass, PLEXAR_GLASS_CSS } from '../src/client/palette.ts'

describe('PLEXAR_GLASS_CSS', () => {
  it('applies backdrop-filter blur to the composer card, menus, dialogs, and toasts', () => {
    for (const selector of ['[data-composer-card]', '[role="menu"]', '[role="dialog"]', '[role="alert"]']) {
      expect(PLEXAR_GLASS_CSS).toContain(selector)
    }
    expect(PLEXAR_GLASS_CSS).toContain('backdrop-filter: blur(20px) saturate(140%)')
  })

  it('gives the sidebar and settings layer translucent rgba fills via the design platform tokens', () => {
    expect(PLEXAR_GLASS_CSS).toContain('--dsw-specific-sidebar-fill: rgba(')
    expect(PLEXAR_GLASS_CSS).toContain('--dsw-alias-bg-layer-2: rgba(')
    expect(PLEXAR_GLASS_CSS).toContain('--dsw-alias-toast-bg: rgba(')
  })

  it('paints a soft Plexar-orange radial gradient behind the glass in both themes, from the shared accent tokens', () => {
    expect(PLEXAR_GLASS_CSS).toContain('color-mix(in srgb, var(--px-accent)')
    expect(PLEXAR_GLASS_CSS).toContain('color-mix(in srgb, var(--px-accent-soft)')
  })

  it('maps the dark-theme base background and glass fills onto the shared --px-* tokens', () => {
    expect(PLEXAR_GLASS_CSS).toContain('--dsw-alias-bg-base: var(--px-bg);')
    expect(PLEXAR_GLASS_CSS).toContain('color-mix(in srgb, var(--px-bg-2)')
    expect(PLEXAR_GLASS_CSS).toContain('color-mix(in srgb, var(--px-surface)')
    expect(PLEXAR_GLASS_CSS).toContain('color-mix(in srgb, var(--px-elev)')
  })

  it('falls back to opaque surfaces and no blur under prefers-reduced-transparency', () => {
    const reduced = PLEXAR_GLASS_CSS.slice(PLEXAR_GLASS_CSS.indexOf('prefers-reduced-transparency'))
    expect(reduced).toContain('backdrop-filter: none')
    expect(reduced).toContain('--dsw-specific-sidebar-fill: var(--dsw-static-neutral-bluish-50)')
    expect(reduced).toContain('background-image: none')
  })
})

describe('installGlass', () => {
  afterEach(() => {
    document.head.querySelectorAll('style[data-plexar-glass]').forEach(style => style.remove())
  })

  it('appends one style element carrying the sheet, and disposal removes it', () => {
    const dispose = installGlass(document)
    const style = document.head.querySelector('style[data-plexar-glass]')
    expect(style?.textContent).toBe(PLEXAR_GLASS_CSS)

    dispose()
    expect(document.head.querySelector('style[data-plexar-glass]')).toBeNull()
  })
})
