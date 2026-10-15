// @vitest-environment jsdom
/** The sidebar update notice: state pill (wide) or dot icon button (collapsed). */

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { UpdateNotice } from '../src/client/UpdateNotice.tsx'
import type { UpdateNoticeComponentProps, UpdateNoticeState } from '../src/client/UpdateNotice.tsx'
import { updateEn } from '../src/client/locales.ts'

afterEach(cleanup)

const t = (key: keyof typeof updateEn, params: Record<string, string> = {}) =>
  updateEn[key].replace(/\{(\w+)\}/g, (_, name: string) => params[name] ?? '')

function renderNotice(status: UpdateNoticeState, wide: boolean, overrides: Partial<UpdateNoticeComponentProps> = {}) {
  const apply = vi.fn()
  const restart = vi.fn()
  const props = {
    t,
    wide,
    useStatus: (selector: (value: UpdateNoticeState) => unknown) => selector(status),
    apply,
    restart,
    ...overrides,
  } as UpdateNoticeComponentProps
  const { container } = render(<UpdateNotice {...props} />)
  return { apply, restart, container }
}

describe('UpdateNotice', () => {
  it('renders nothing when current', () => {
    const { container } = renderNotice({ state: 'current' }, true)
    expect(container.firstChild).toBeNull()
  })

  it('shows an available pill with an Update button', () => {
    const { apply } = renderNotice({ state: 'available' }, true)
    expect(screen.getByText(updateEn.available)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: updateEn.updateButton }))
    expect(apply).toHaveBeenCalled()
  })

  it('shows the current and latest versions when both are known', () => {
    renderNotice({ state: 'available', current: '0.1.0', latest: '0.2.0' }, true)
    expect(screen.getByText('v0.1.0 → v0.2.0')).toBeTruthy()
  })

  it('shows an updating pill with no interactive button', () => {
    renderNotice({ state: 'updating' }, true)
    expect(screen.getByText(updateEn.updating)).toBeTruthy()
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('shows a restart-required pill with a Restart button', () => {
    const { restart } = renderNotice({ state: 'restart-required' }, true)
    fireEvent.click(screen.getByRole('button', { name: updateEn.restartButton }))
    expect(restart).toHaveBeenCalled()
  })

  it('shows a failed pill with the error on a title line', () => {
    renderNotice({ state: 'failed', error: 'network unreachable' }, true)
    expect(screen.getByText(updateEn.failed)).toBeTruthy()
    expect(screen.getByText(updateEn.failed).closest('[data-state="failed"]')?.getAttribute('title')).toBe('network unreachable')
  })

  it('collapses to a dot icon button when not wide, wired to apply() when available', () => {
    const { apply } = renderNotice({ state: 'available' }, false)
    expect(screen.queryByText(updateEn.available)).toBeNull()
    const button = screen.getByRole('button')
    fireEvent.click(button)
    expect(apply).toHaveBeenCalled()
  })

  it('collapses to a disabled dot while updating', () => {
    renderNotice({ state: 'updating' }, false)
    expect(screen.getByRole('button').hasAttribute('disabled')).toBe(true)
  })

  it('collapses to a dot wired to restart() when restart-required', () => {
    const { restart } = renderNotice({ state: 'restart-required' }, false)
    fireEvent.click(screen.getByRole('button'))
    expect(restart).toHaveBeenCalled()
  })
})
