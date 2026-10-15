/** Plexar brand: sidebar mark and name, blank-session mark and headline, and the orange accent palette. */
import type { Context as ClientContext } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import type {} from '@deepseek-ai/dsh-client-ui-sidebar/client'
import type {} from '@deepseek-ai/dsh-client-ui-conversation/client'
import { PlexarBrandMark, PlexarBrandName, PlexarHeroHeadline, PlexarHeroMark } from './Brand.tsx'
import { installGlass, installPalette } from './palette.ts'
import { installAurora, isAuroraEnabled, setAuroraEnabled } from './aurora.ts'
import { installTokens } from './tokens/index.ts'

export type { AuroraPreference } from './aurora.ts'

/** Required service: the UI slot registry. */
export const inject = ['slots']

/**
 * Fill the sidebar brand slots as one declaration-aware registration set.
 * @param ctx - Client root context.
 */
export function apply(ctx: ClientContext): void {
  // First: later brand sheets (palette, glass, aurora) read var(--px-*).
  ctx.effect(() => installTokens(document), 'plexar shared tokens')
  ctx.effect(() => installPalette(document), 'plexar accent palette')
  ctx.effect(() => installGlass(document), 'plexar glassmorphism')
  ctx.effect(() => installAurora(document), 'plexar aurora background')
  ctx.provide('plexarAurora', { isEnabled: isAuroraEnabled, setEnabled: setAuroraEnabled })
  ctx.slots.inject('sidebar.brand.mark', () =>
    ctx.slots.inject('sidebar.brand.name', function* () {
      yield ctx.slots.register({ name: 'sidebar.brand.mark' }, PlexarBrandMark)
      yield ctx.slots.register({ name: 'sidebar.brand.name' }, PlexarBrandName)
    }))
  ctx.slots.inject('conversation.hero.brand.mark', () =>
    ctx.slots.inject('conversation.hero.brand.headline', function* () {
      yield ctx.slots.register({ name: 'conversation.hero.brand.mark' }, PlexarHeroMark)
      yield ctx.slots.register({ name: 'conversation.hero.brand.headline' }, PlexarHeroHeadline)
    }))
}
