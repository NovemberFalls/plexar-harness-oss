// @vitest-environment jsdom
/** The Models section: chat and classifier groups, serving pills, and tags. */

import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ModelsSection } from '../src/client/ModelsSection.tsx'
import type { ModelRow, ModelsSectionComponentProps, ModelsState } from '../src/client/ModelsSection.tsx'
import { modelsEn } from '../src/client/locales.ts'

afterEach(cleanup)

const t = (key: keyof typeof modelsEn, params?: Record<string, string>) => {
  const raw = modelsEn[key]
  return params === undefined ? raw : raw.replace(/\{(\w+)\}/g, (_match, name: string) => params[name] ?? '')
}

const CHAT_SERVING: ModelRow = { id: 'qwen3.8-27b', name: 'Qwen3.8 27B', serving: true, contextWindow: 131072, input: ['text', 'image'] }
const CHAT_DOWN: ModelRow = { id: 'gemma-4-26b-fp8', name: 'Gemma 4 26B', serving: false, contextWindow: null, input: ['text'] }
const CLASSIFIER: ModelRow = { id: 'guard-1', name: 'Guard', serving: true, contextWindow: 8192, input: null }

function renderSection(state: ModelsState, overrides: Partial<ModelsSectionComponentProps> = {}) {
  const ensure = vi.fn()
  const useModels = (selector: (value: ModelsState) => unknown) => selector(state)
  const props = { t, useModels, ensure, ...overrides } as ModelsSectionComponentProps
  const result = render(<ModelsSection {...props} />)
  return { ensure, unmount: result.unmount }
}

describe('ModelsSection', () => {
  it('calls ensure on mount to trigger the Host read', () => {
    const { ensure } = renderSection({ status: 'loading' })
    expect(ensure).toHaveBeenCalled()
  })

  it('shows the unavailable copy when the Host has no roster', () => {
    renderSection({ status: 'unavailable' })
    expect(screen.getByText(modelsEn.unavailable)).toBeTruthy()
  })

  it('lists chat models under their group heading with name, id, and a serving pill', () => {
    renderSection({ status: 'ready', chat: [CHAT_SERVING], classifiers: [] })
    expect(screen.getByRole('heading', { name: modelsEn['group.chat'] })).toBeTruthy()
    expect(screen.getByText('Qwen3.8 27B')).toBeTruthy()
    expect(screen.getByText('qwen3.8-27b')).toBeTruthy()
    expect(screen.getByText(modelsEn.servingPill)).toBeTruthy()
  })

  it('shows the not-serving pill for a model that is not serving', () => {
    renderSection({ status: 'ready', chat: [CHAT_DOWN], classifiers: [] })
    expect(screen.getByText(modelsEn.notServingPill)).toBeTruthy()
  })

  it('shows an images tag only when the model input includes image', () => {
    renderSection({ status: 'ready', chat: [CHAT_SERVING], classifiers: [] })
    expect(screen.getByText(modelsEn.imagesTag)).toBeTruthy()
  })

  it('omits the images tag when input does not include image', () => {
    renderSection({ status: 'ready', chat: [CHAT_DOWN], classifiers: [] })
    expect(screen.queryByText(modelsEn.imagesTag)).toBeNull()
  })

  it('shows a context-window tag in K when known', () => {
    renderSection({ status: 'ready', chat: [CHAT_SERVING], classifiers: [] })
    expect(screen.getByText('128K context')).toBeTruthy()
  })

  it('omits the context tag when the context window is unknown', () => {
    renderSection({ status: 'ready', chat: [CHAT_DOWN], classifiers: [] })
    expect(screen.queryByText(/context$/)).toBeNull()
  })

  it('shows classifiers under their own group with a classifier tag, and hides the group when empty', () => {
    const { unmount } = renderSection({ status: 'ready', chat: [CHAT_SERVING], classifiers: [CLASSIFIER] })
    expect(screen.getByRole('heading', { name: modelsEn['group.classifiers'] })).toBeTruthy()
    expect(screen.getByText('Guard')).toBeTruthy()
    expect(screen.getByText(modelsEn.classifierTag)).toBeTruthy()
    unmount()

    renderSection({ status: 'ready', chat: [CHAT_SERVING], classifiers: [] })
    expect(screen.queryByRole('heading', { name: modelsEn['group.classifiers'] })).toBeNull()
  })
})
