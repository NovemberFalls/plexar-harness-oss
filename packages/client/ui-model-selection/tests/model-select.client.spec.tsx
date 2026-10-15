// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { RemoteError } from '@deepseek-ai/dsh-client-test-runtime'
import { SessionId } from '@deepseek-ai/dsh-session/types'
import type { ModelSelection } from '@deepseek-ai/dsh-api-remotes/client'
import { createSnapshotStore } from '@deepseek-ai/dsh-client-store'
import type { ComponentProps } from 'react'
import type { ModelDirectoryState } from '../src/client/directory.ts'
import { ModelSelect } from '../src/client/ModelSelect.tsx'
import { zh } from '../src/client/locales.ts'
import { zh as commonZh } from '@deepseek-ai/dsh-client-locale/src/locales/zh.ts'

// The seat's key domain is model ∪ common; the stub mirrors the real lookup
// chain: package dictionary, then common vocabulary, then the key.
const t: ComponentProps<typeof ModelSelect>['t'] = (key, params) => {
  const template = (zh as Record<string, string>)[key]
    ?? (commonZh as Record<string, string>)[key]
    ?? key
  return params === undefined
    ? template
    : template.replace(/\{(\w+)\}/g, (match, name: string) => name in params ? String(params[name]) : match)
}

const reasoning = {
  efforts: [
    { id: 'off', name: 'Off' },
    { id: 'high', name: 'High' },
    { id: 'max', name: 'Max', description: 'Largest budget' },
  ],
  defaultEffort: 'high',
}

function state(overrides: Partial<ModelDirectoryState> = {}): ModelDirectoryState {
  return {
    current: { provider: 'deepseek-official', model: 'deepseek-v4-flash' },
    routable: true,
    groups: [{
      id: 'deepseek-official',
      name: 'DeepSeek',
      models: [{
        id: 'deepseek-v4-flash',
        name: 'DeepSeek-V4-Flash',
        description: 'Fast catalog description',
        reasoning,
      }],
    }],
    failures: [],
    status: 'ready',
    error: null,
    ...overrides,
  }
}

afterEach(cleanup)

describe('ModelSelect model and effort pickers', () => {
  it('renders separate model and effort triggers, each opening its own list directly', () => {
    render(<ModelSelect
      locked={false}
      available
      directory={createSnapshotStore(state())}
      load={vi.fn()}
      select={vi.fn().mockResolvedValue({ ok: true, value: undefined })}
      t={t}
    />)

    const modelTrigger = screen.getByRole('button', { name: '选择模型，当前 DeepSeek-V4-Flash' })
    const effortTrigger = screen.getByRole('button', { name: '推理等级，当前 High' })
    expect(modelTrigger.textContent).toContain('DeepSeek-V4-Flash')
    expect(effortTrigger.textContent).toContain('High')

    fireEvent.click(effortTrigger)
    expect(screen.getAllByRole('menuitemradio').map(item => item.textContent))
      .toEqual(['Off', 'High', 'Max'])
    expect(screen.queryByText('Largest budget')).toBeNull()
    fireEvent.click(effortTrigger)
    expect(screen.queryByRole('menu')).toBeNull()

    fireEvent.click(modelTrigger)
    expect(screen.getByRole('menuitemradio', { name: 'DeepSeek-V4-Flash' })).toBeTruthy()
  })

  it('hides the effort picker for a model without reasoning metadata', () => {
    render(<ModelSelect
      locked={false}
      available
      directory={createSnapshotStore(state({
        current: { provider: 'deepseek-official', model: 'plain' },
        groups: [{
          id: 'deepseek-official',
          name: 'DeepSeek',
          models: [{ id: 'plain', name: 'Plain' }],
        }],
      }))}
      load={vi.fn()}
      select={vi.fn().mockResolvedValue({ ok: true, value: undefined })}
      t={t}
    />)

    expect(screen.getByRole('button', { name: '选择模型，当前 Plain' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: /推理等级/ })).toBeNull()
  })

  it('follows the effort list of whichever model is currently selected', async () => {
    const groups = [{
      id: 'deepseek-official',
      name: 'DeepSeek',
      models: [
        { id: 'deepseek-v4-flash', name: 'DeepSeek-V4-Flash', reasoning },
        { id: 'plain', name: 'Plain' },
      ],
    }]
    const directory = createSnapshotStore<ModelDirectoryState>(state({ groups }))
    const select = vi.fn(async (selection: ModelSelection) => {
      directory.set(state({ groups, current: selection }))
      return { ok: true as const, value: undefined }
    })
    render(<ModelSelect
      locked={false}
      available
      directory={directory}
      load={vi.fn()}
      select={select}
      t={t}
    />)

    expect(screen.getByRole('button', { name: /推理等级/ })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /选择模型/ }))
    fireEvent.click(screen.getByRole('menuitemradio', { name: 'Plain' }))
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /推理等级/ })).toBeNull()
    })
  })

  it('submits the chosen effort as part of the session selection', async () => {
    const directory = createSnapshotStore<ModelDirectoryState>(state())
    const select = vi.fn(async (selection: ModelSelection) => {
      directory.set(state({ current: selection }))
      return { ok: true as const, value: undefined }
    })
    render(<ModelSelect
      locked={false}
      available
      directory={directory}
      load={vi.fn()}
      select={select}
      t={t}
    />)

    fireEvent.click(screen.getByRole('button', { name: /推理等级/ }))
    fireEvent.click(screen.getByRole('menuitemradio', { name: /Max/ }))
    await waitFor(() => {
      expect(select).toHaveBeenCalledWith({
        provider: 'deepseek-official',
        model: 'deepseek-v4-flash',
        reasoningEffort: 'max',
      })
      expect(screen.getByRole('button', { name: '推理等级，当前 Max' })).toBeTruthy()
    })
  })

  it('offers provider default only when the adapter does not configure a model default', () => {
    render(<ModelSelect
      locked={false}
      available
      directory={createSnapshotStore(state({
        groups: [{
          id: 'provider',
          name: 'Provider',
          models: [{
            id: 'model',
            name: 'Model',
            reasoning: { efforts: [{ id: 'standard', name: 'Standard' }] },
          }],
        }],
        current: { provider: 'provider', model: 'model' },
      }))}
      load={vi.fn()}
      select={vi.fn().mockResolvedValue({ ok: true, value: undefined })}
      t={t}
    />)

    fireEvent.click(screen.getByRole('button', { name: '推理等级，当前 Default' }))
    expect(screen.getAllByRole('menuitemradio').map(item => item.textContent))
      .toEqual(['Default', 'Standard'])
  })

  it('shows the durable model id when the catalog has no matching display name', () => {
    render(<ModelSelect
      locked={false}
      available
      directory={createSnapshotStore(state({
        current: { provider: 'deepseek-official', model: 'removed-model' },
      }))}
      load={vi.fn()}
      select={vi.fn().mockResolvedValue({ ok: true, value: undefined })}
      t={t}
    />)

    const trigger = screen.getByRole('button', { name: '选择模型，当前 deepseek-official/removed-model' })
    expect(trigger.textContent).toContain('deepseek-official/removed-model')
    expect(screen.queryByRole('button', { name: /推理等级/ })).toBeNull()
    fireEvent.click(trigger)
    expect(screen.queryByRole('menuitemradio', { name: 'removed-model' })).toBeNull()
    expect(screen.getByRole('menuitemradio', { name: 'DeepSeek-V4-Flash' })).toBeTruthy()
    expect(screen.queryByText('Fast catalog description')).toBeNull()
  })

  it('shows loading until the catalog and Session projection are both ready', async () => {
    const directory = createSnapshotStore<ModelDirectoryState>(state({
      current: null,
      routable: null,
      groups: [],
      status: 'loading',
    }))
    render(<ModelSelect
      locked={false}
      available
      directory={directory}
      load={vi.fn()}
      select={vi.fn().mockResolvedValue({ ok: true, value: undefined })}
      t={t}
    />)

    expect(screen.getByRole('button', { name: '正在加载模型…' }).textContent)
      .toContain('正在加载模型…')
    directory.set(state())
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '选择模型，当前 DeepSeek-V4-Flash' })).toBeTruthy()
    })
  })

  it.each([false, true])('announces rejected selections with ownership guidance only for held writers (%s)', async (sessionInUse) => {
    const groups = [{
      id: 'deepseek-official',
      name: 'DeepSeek',
      models: [
        { id: 'deepseek-v4-flash', name: 'DeepSeek-V4-Flash', reasoning },
        { id: 'deepseek-v4-pro', name: 'DeepSeek-V4-Pro' },
      ],
    }]
    const directory = createSnapshotStore<ModelDirectoryState>(state({ groups }))
    const select = vi.fn(async () => {
      const error = sessionInUse
        ? new RemoteError('session/writer-held', 'writer held', { sessionId: SessionId('owned') })
        : new RemoteError('session/model-unavailable', 'session already contains images', { provider: 'deepseek-official', model: 'deepseek-v4-pro' })
      directory.set(state({ groups, status: 'error', error: 'unrelated catalog refresh' }))
      return { ok: false as const, error }
    })
    render(<ModelSelect
      locked={false}
      available
      directory={directory}
      load={vi.fn()}
      select={select}
      t={t}
    />)

    fireEvent.click(screen.getByRole('button', { name: /选择模型/ }))
    fireEvent.click(screen.getByRole('menuitemradio', { name: /DeepSeek-V4-Pro/ }))
    const toast = await screen.findByRole('alert')
    expect(toast.textContent).toBe(sessionInUse
      ? zh['error.sessionInUse']
      : '模型操作失败：session/model-unavailable: session already contains images')
    // The selection failure does not render the in-menu load strip (no Retry).
    expect(screen.queryByRole('button', { name: '重试' })).toBeNull()
  })

  it('portals the placed menu card to body and closes only on truly-outside mousedown', () => {
    const offsetWidth = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetWidth')!
    const offsetHeight = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetHeight')!
    Object.defineProperty(HTMLElement.prototype, 'offsetWidth', { configurable: true, get: () => 200 })
    Object.defineProperty(HTMLElement.prototype, 'offsetHeight', { configurable: true, get: () => 300 })
    try {
      const { container } = render(<ModelSelect
        locked={false}
        available
        directory={createSnapshotStore(state())}
        load={vi.fn()}
        select={vi.fn().mockResolvedValue({ ok: true, value: undefined })}
        t={t}
      />)
      const trigger = screen.getByRole('button', { name: /选择模型/ })
      fireEvent.click(trigger)
      const menu = screen.getByRole('menu')
      // Outside the composer subtree — column overflow clips cannot crop it.
      expect(container.contains(menu)).toBe(false)
      expect(menu.parentElement).toBe(document.body)
      // jsdom anchor rects are all zero, so the measured 200x300 card clamps
      // to the 12px viewport margin on both axes.
      expect(menu.style.left).toBe('12px')
      expect(menu.style.top).toBe('12px')
      // Interactions inside the trigger subtree or the portaled card stay open.
      fireEvent.mouseDown(menu)
      fireEvent.mouseDown(trigger)
      fireEvent.blur(trigger, { relatedTarget: menu })
      expect(screen.getByRole('menu')).toBeTruthy()
      fireEvent.mouseDown(document.body)
      expect(screen.queryByRole('menu')).toBeNull()
    } finally {
      Object.defineProperty(HTMLElement.prototype, 'offsetWidth', offsetWidth)
      Object.defineProperty(HTMLElement.prototype, 'offsetHeight', offsetHeight)
    }
  })

  it('renders no Agent-bound control for an addressed subagent session', () => {
    const load = vi.fn()
    render(<ModelSelect
      locked={false}
      available={false}
      directory={createSnapshotStore(state())}
      load={load}
      select={vi.fn().mockResolvedValue(undefined)}
      t={t}
    />)

    expect(screen.queryByRole('button')).toBeNull()
    expect(load).not.toHaveBeenCalled()
  })
})

describe('ModelSelect keyboard walk', () => {
  function mountOpenModel() {
    const select = vi.fn().mockResolvedValue({ ok: true, value: undefined })
    render(<ModelSelect
      locked={false}
      available
      directory={createSnapshotStore(state())}
      load={vi.fn()}
      select={select}
      t={t}
    />)
    fireEvent.click(screen.getByRole('button', { name: /选择模型/ }))
    return select
  }

  function mountOpenEffort() {
    const select = vi.fn().mockResolvedValue({ ok: true, value: undefined })
    render(<ModelSelect
      locked={false}
      available
      directory={createSnapshotStore(state())}
      load={vi.fn()}
      select={select}
      t={t}
    />)
    fireEvent.click(screen.getByRole('button', { name: /推理等级/ }))
    return select
  }

  it('opens on the checked row and ↑↓ walk the rows, wrapping, and stay open', () => {
    mountOpenEffort()
    const rows = screen.getAllByRole('menuitemradio')
    expect(rows.map(row => row.textContent)).toEqual(['Off', 'High', 'Max'])
    // The pane opens on its checked row, so walking starts from High.
    expect(rows[1]!.getAttribute('aria-checked')).toBe('true')
    expect(document.activeElement).toBe(rows[1])
    fireEvent.keyDown(rows[1]!, { key: 'ArrowDown' })
    expect(document.activeElement).toBe(rows[2])
    fireEvent.keyDown(rows[2]!, { key: 'ArrowDown' }) // wraps to the top
    expect(document.activeElement).toBe(rows[0])
    fireEvent.keyDown(rows[0]!, { key: 'ArrowUp' }) // wraps to the bottom
    expect(document.activeElement).toBe(rows[2])
    expect(screen.getByRole('menu')).toBeTruthy()
  })

  it('a pane whose rows mark no current value opens on its first row', () => {
    mountOpenModel()
    const rows = screen.getAllByRole('menuitemradio')
    expect(rows[0]!.getAttribute('aria-checked')).toBe('true')
    expect(document.activeElement).toBe(rows[0])
  })

  it('Tab settles the focused row like Enter and closes the menu', async () => {
    const select = mountOpenEffort()
    const rows = screen.getAllByRole('menuitemradio')
    fireEvent.keyDown(rows[1]!, { key: 'ArrowDown' }) // High → Max
    expect(fireEvent.keyDown(rows[2]!, { key: 'Tab' })).toBe(false)
    expect(select).toHaveBeenCalledWith({
      provider: 'deepseek-official', model: 'deepseek-v4-flash', reasoningEffort: 'max',
    })
    await waitFor(() => { expect(screen.queryByRole('menu')).toBeNull() })
  })

  it('Escape closes the menu and returns focus to its own trigger', async () => {
    mountOpenEffort()
    const effortTrigger = screen.getByRole('button', { name: /推理等级/ })
    const rows = screen.getAllByRole('menuitemradio')
    fireEvent.keyDown(rows[0]!, { key: 'Escape' })
    expect(screen.queryByRole('menu')).toBeNull()
    await waitFor(() => { expect(document.activeElement).toBe(effortTrigger) })
  })

  it('Shift+Tab closes the menu like Escape', () => {
    mountOpenModel()
    const rows = screen.getAllByRole('menuitemradio')
    expect(fireEvent.keyDown(rows[0]!, { key: 'Tab', shiftKey: true })).toBe(false)
    expect(screen.queryByRole('menu')).toBeNull()
  })

  it('a backward step from outside the list enters at the last row', () => {
    mountOpenEffort()
    const rows = screen.getAllByRole('menuitemradio')
    // Focus starts on the checked (High) row; step onto the top row first.
    rows[0]!.focus()
    expect(fireEvent.keyDown(rows[0]!, { key: 'ArrowUp' })).toBe(false)
    expect(document.activeElement).toBe(rows[2])
  })

  it('only one menu is open at a time: opening the effort menu closes an open model menu', () => {
    mountOpenModel()
    expect(screen.getAllByRole('menuitemradio').length).toBeGreaterThan(0)
    fireEvent.click(screen.getByRole('button', { name: /推理等级/ }))
    const menus = screen.getAllByRole('menu')
    expect(menus).toHaveLength(1)
    expect(screen.getAllByRole('menuitemradio').map(row => row.textContent))
      .toEqual(['Off', 'High', 'Max'])
  })

  it('keeps the card navigable when the model pane has no rows, and leaves a retry its Tab', () => {
    const directory = createSnapshotStore<ModelDirectoryState>(state({
      groups: [], failures: [], status: 'error', error: 'catalog down',
    }))
    render(<ModelSelect
      locked={false}
      available
      directory={directory}
      load={vi.fn()}
      select={vi.fn().mockResolvedValue({ ok: true, value: undefined })}
      t={t}
    />)
    const trigger = screen.getByRole('button', { name: /选择模型/ })
    // A real click focuses the trigger first; jsdom's does not.
    trigger.focus()
    fireEvent.click(trigger)
    // No rows to hand the keyboard to: the trigger keeps it, so the card's
    // keys still reach the menu.
    expect(document.activeElement).toBe(trigger)

    const retry = screen.getByRole('button', { name: '重试' })
    retry.focus()
    // A control that is not a row keeps the browser's traversal.
    expect(fireEvent.keyDown(retry, { key: 'Tab' })).toBe(true)
    // Escape still closes the card.
    fireEvent.keyDown(retry, { key: 'Escape' })
    expect(screen.queryByRole('menu')).toBeNull()
  })
})
