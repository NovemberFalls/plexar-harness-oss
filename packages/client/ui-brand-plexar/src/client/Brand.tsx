import { useEffect } from 'react'
import type { SidebarBrandMarkOwnerProps } from '@deepseek-ai/dsh-client-ui-sidebar/client'
import { PLEXAR_MARK_PNG } from './mark.ts'
import { auroraHeroOccupantMounted } from './aurora.ts'

/** Orange gradient text used for the product name wherever it appears, from the shared accent tokens. */
const GRADIENT_TEXT = {
  background: 'linear-gradient(90deg, var(--px-accent), var(--px-accent-soft))',
  WebkitBackgroundClip: 'text',
  backgroundClip: 'text',
  color: 'transparent',
  fontFamily: 'var(--px-font-display)',
} as const

/** The Plexar P mark. */
export function PlexarBrandMark({ size }: SidebarBrandMarkOwnerProps) {
  return (
    <img
      src={PLEXAR_MARK_PNG}
      width={size}
      height={size}
      alt=""
      aria-hidden="true"
      style={{ borderRadius: Math.round(size * 0.22), display: 'block' }}
    />
  )
}

/**
 * The blank-session headline: the product name in the Plexar orange gradient. Rendered only when
 * a session has no conversation yet; its mount/unmount drives the aurora background's visibility.
 */
export function PlexarHeroHeadline() {
  useEffect(() => auroraHeroOccupantMounted(), [])
  return <span style={{ fontWeight: 600, ...GRADIENT_TEXT }}>Plexar Harness</span>
}

/**
 * The Plexar P mark sized for the blank-session headline. Rendered only when a session has no
 * conversation yet; its mount/unmount drives the aurora background's visibility.
 */
export function PlexarHeroMark({ size, className }: { size: number; className?: string | undefined }) {
  useEffect(() => auroraHeroOccupantMounted(), [])
  return (
    <span className={className} style={{ display: 'inline-flex' }}>
      <PlexarBrandMark size={Math.round(size * 1.3)} />
    </span>
  )
}

/** The Plexar name in the orange gradient, at the sidebar's own size. */
export function PlexarBrandName() {
  return <span style={{ fontWeight: 600, letterSpacing: '0.02em', ...GRADIENT_TEXT }}>Plexar Harness</span>
}
