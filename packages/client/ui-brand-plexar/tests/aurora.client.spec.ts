// @vitest-environment jsdom
/**
 * The aurora layer: hidden with no hero occupant mounted, shown while one is mounted, hidden
 * again on unmount, and the viewer switch still wins when off with a hero mounted.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { auroraHeroOccupantMounted, installAurora, setAuroraEnabled } from '../src/client/aurora.ts'

describe('installAurora hero-driven visibility', () => {
  let dispose: () => void

  beforeEach(() => {
    setAuroraEnabled(true)
    dispose = installAurora(document)
  })

  afterEach(() => {
    dispose()
    localStorage.removeItem('plexar.aurora')
  })

  const layer = (): Element | null => document.body.querySelector('[data-plexar-aurora]')

  it('hides the layer when no hero occupant is mounted', () => {
    expect(layer()?.hasAttribute('data-visible')).toBe(false)
  })

  it('shows the layer while a hero occupant is mounted', () => {
    const unmount = auroraHeroOccupantMounted()
    expect(layer()?.hasAttribute('data-visible')).toBe(true)
    unmount()
  })

  it('hides the layer again once the hero occupant unmounts', () => {
    const unmount = auroraHeroOccupantMounted()
    expect(layer()?.hasAttribute('data-visible')).toBe(true)
    unmount()
    expect(layer()?.hasAttribute('data-visible')).toBe(false)
  })

  it('keeps the layer hidden with the viewer switch off, even with a hero mounted', () => {
    setAuroraEnabled(false)
    const unmount = auroraHeroOccupantMounted()
    expect(layer()?.hasAttribute('data-visible')).toBe(false)
    unmount()
  })

  it('stays visible for a second occupant while the first is still mounted, and hides only once both unmount', () => {
    const unmountFirst = auroraHeroOccupantMounted()
    const unmountSecond = auroraHeroOccupantMounted()
    unmountFirst()
    expect(layer()?.hasAttribute('data-visible')).toBe(true)
    unmountSecond()
    expect(layer()?.hasAttribute('data-visible')).toBe(false)
  })
})
