// @vitest-environment jsdom
/** The Features section: grouped toggle rows with expandable descriptions. */

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { FeaturesSection } from '../src/client/FeaturesSection.tsx'
import type { FeatureRow, FeaturesSectionComponentProps, FeaturesState } from '../src/client/FeaturesSection.tsx'
import { featuresEn } from '../src/client/locales.ts'

afterEach(cleanup)

const t = (key: keyof typeof featuresEn) => featuresEn[key]

const SHELL_ROW: FeatureRow = {
  id: 'shell',
  name: 'Terminal commands',
  description: 'A description.',
  enabled: true,
  busy: false,
}

function ready(rows: readonly FeatureRow[]): FeaturesState {
  return { status: 'ready', groups: [{ id: 'coding', title: 'Coding', rows }] }
}

function renderSection(state: FeaturesState, overrides: Partial<FeaturesSectionComponentProps> = {}) {
  const setEnabled = vi.fn()
  const ensure = vi.fn()
  const props = {
    t,
    useFeatures: (selector: (value: FeaturesState) => unknown) => selector(state),
    ensure,
    setEnabled,
    ...overrides,
  } as FeaturesSectionComponentProps
  render(<FeaturesSection {...props} />)
  return { setEnabled, ensure }
}

describe('FeaturesSection', () => {
  it('says so when there are no optional features', () => {
    renderSection({ status: 'ready', groups: [] })
    expect(screen.getByText(featuresEn.empty)).toBeTruthy()
  })

  it('renders a toggle per feature with its description collapsed behind a dropdown', () => {
    renderSection(ready([SHELL_ROW]))
    expect(screen.queryByText('A description.')).toBeNull()
    const toggle = screen.getByRole('switch', { name: 'Terminal commands' })
    expect(toggle.getAttribute('aria-checked')).toBe('true')
    const expander = screen.getByRole('button', { name: featuresEn.showDetails })
    expect(expander.getAttribute('aria-expanded')).toBe('false')
    fireEvent.click(expander)
    expect(screen.getByText('A description.')).toBeTruthy()
    expect(screen.getByRole('button', { name: featuresEn.hideDetails }).getAttribute('aria-expanded')).toBe('true')
    fireEvent.click(screen.getByRole('button', { name: featuresEn.hideDetails }))
    expect(screen.queryByText('A description.')).toBeNull()
  })

  it('shows each group under its title', () => {
    renderSection(ready([SHELL_ROW]))
    expect(screen.getByRole('region', { name: 'Coding' })).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Coding' })).toBeTruthy()
  })

  it('shows a busy label instead of the switch while a change applies', () => {
    renderSection(ready([{ ...SHELL_ROW, busy: true }]))
    expect(screen.queryByRole('switch')).toBeNull()
    expect(screen.getByText(featuresEn.settingUp)).toBeTruthy()
  })

  it('toggling a row calls setEnabled with the feature id and the flipped state', () => {
    const { setEnabled } = renderSection(ready([SHELL_ROW]))
    fireEvent.click(screen.getByRole('switch', { name: 'Terminal commands' }))
    expect(setEnabled).toHaveBeenCalledWith('shell', false)
  })

  it('calls ensure on mount to trigger the Host read', () => {
    const { ensure } = renderSection({ status: 'loading', groups: [] })
    expect(ensure).toHaveBeenCalled()
    expect(screen.getByText(featuresEn.loading)).toBeTruthy()
  })
})
