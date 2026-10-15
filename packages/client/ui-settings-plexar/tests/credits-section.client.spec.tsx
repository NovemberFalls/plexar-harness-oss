// @vitest-environment jsdom
/** The Credits section: thanks to DeepSeek Harness and the deepseek-ai link. */

import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { CreditsSection } from '../src/client/CreditsSection.tsx'
import type { CreditsSectionComponentProps } from '../src/client/CreditsSection.tsx'
import { creditsEn } from '../src/client/locales.ts'

afterEach(cleanup)

const t = (key: keyof typeof creditsEn) => creditsEn[key]

describe('CreditsSection', () => {
  it('thanks DeepSeek Harness and links to github.com/deepseek-ai', () => {
    render(<CreditsSection {...{ t } as CreditsSectionComponentProps} />)

    expect(screen.getByText(/DeepSeek Harness/)).toBeTruthy()
    const link = screen.getByRole('link', { name: creditsEn.thanksLink })
    expect(link.getAttribute('href')).toBe('https://github.com/deepseek-ai')
  })

  it('lists the shipped open-source parts', () => {
    render(<CreditsSection {...{ t } as CreditsSectionComponentProps} />)

    expect(screen.getByText(creditsEn['part.cordis'])).toBeTruthy()
    expect(screen.getByText(creditsEn['part.sensevoice'])).toBeTruthy()
    expect(screen.getByText(creditsEn['part.playwright'])).toBeTruthy()
    expect(screen.getByText(creditsEn['part.tauri'])).toBeTruthy()
  })
})
