// @vitest-environment jsdom
/** The rail's surfaces rendered from fake sources. */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { makeTranslate } from '@deepseek-ai/dsh-client-test-runtime'
import type { JobsSnapshot, JobView } from '@deepseek-ai/dsh-api-job-controller/client'
import type { WorkspaceSnapshot, WorkspaceView } from '@deepseek-ai/dsh-api-workspace-controller/client'
import type { SessionId } from '@deepseek-ai/dsh-session/types'
import {
  BRANCH_REFRESH_MS, EnvironmentPanel, EnvironmentRail, EnvironmentToggle, truncateMiddle,
  type EnvironmentPanelProps, type EnvironmentRailProps, type EnvironmentToggleProps,
} from '../src/client/EnvironmentRail.tsx'
import { en } from '../src/client/locales.ts'

const SESSION = 's-1' as SessionId
const t = makeTranslate(en) as EnvironmentPanelProps['t']

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

/** A selector hook over a fixed value. */
function hookOf<T>(value: T) {
  return <S,>(select: (snapshot: T) => S): S => select(value)
}

function workspace(path: string): WorkspaceView {
  return { workspaceId: 'w-1', path, title: 'harness', sessionIds: [SESSION], createdAt: '', updatedAt: '' } as unknown as WorkspaceView
}

function job(id: string, label: string, status: JobView['status']): JobView {
  return { id, label, status } as unknown as JobView
}

interface PanelFakes {
  sessionId?: SessionId | undefined
  shown?: boolean
  workspaces?: WorkspaceSnapshot | undefined
  jobs?: JobsSnapshot | undefined
  pressure?: { projectedTokens?: number; contextWindow?: number } | undefined
  branch?: (sessionId: SessionId) => Promise<string | null>
}

function panelProps(fakes: PanelFakes = {}) {
  const watchRows = vi.fn((_sessionId: SessionId) => vi.fn())
  const readBranch = vi.fn(fakes.branch ?? (() => Promise.resolve('feat/in-app-browser')))
  const props = {
    sessionId: 'sessionId' in fakes ? fakes.sessionId : SESSION,
    useProjection: (key: string) => (key === 'contextPressure' ? fakes.pressure : undefined),
    useRailShown: hookOf(fakes.shown ?? true),
    useWorkspaceList: hookOf(fakes.workspaces),
    useJobRows: hookOf(fakes.jobs),
    watchRows,
    readBranch,
    t,
  } as unknown as EnvironmentPanelProps
  return { props, watchRows, readBranch }
}

const LONG_PATH = '<harness-checkout>/packages/client/ui-environment'
const workspaces = { items: [workspace(LONG_PATH)] } as unknown as WorkspaceSnapshot

describe('EnvironmentPanel', () => {
  it('shows one line of empty-state copy without a Session, and asks nothing', () => {
    const { props, readBranch, watchRows } = panelProps({ sessionId: undefined, workspaces })
    render(<EnvironmentPanel {...props} />)
    expect(screen.getByText(en.empty)).toBeTruthy()
    expect(screen.queryByText(en.workspace)).toBeNull()
    expect(readBranch).not.toHaveBeenCalled()
    expect(watchRows).not.toHaveBeenCalled()
  })

  it('renders Workspace, Branch, Context and Background tasks from fakes', async () => {
    const jobs = {
      rows: { [SESSION]: [job('j1', 'pnpm run dev', 'running'), job('j2', 'pnpm test', 'completed'), job('j3', 'lint', 'failed')] },
      observed: {},
    } as unknown as JobsSnapshot
    const { props, watchRows } = panelProps({ workspaces, jobs, pressure: { projectedTokens: 45_000, contextWindow: 100_000 } })
    render(<EnvironmentPanel {...props} />)
    expect(screen.getByText('harness')).toBeTruthy()
    const path = screen.getByTitle(LONG_PATH)
    expect(path.textContent).toBe(truncateMiddle(LONG_PATH, 36))
    expect(path.textContent).toContain('…')
    expect(await screen.findByText('feat/in-app-browser')).toBeTruthy()
    expect(screen.getByText('45% used')).toBeTruthy()
    expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('45')
    expect(screen.getByText(en.tasks)).toBeTruthy()
    expect(screen.getByTitle('pnpm run dev')).toBeTruthy()
    expect(screen.queryByText('pnpm test')).toBeNull()
    expect(screen.getByText('2 finished')).toBeTruthy()
    expect(watchRows).toHaveBeenCalledWith(SESSION)
  })

  it('keeps Workspace and hides every empty section', async () => {
    const { props, readBranch } = panelProps({ branch: () => Promise.resolve(null) })
    render(<EnvironmentPanel {...props} />)
    expect(screen.getByText(en.workspace)).toBeTruthy()
    expect(screen.getByText(en.workspaceNone)).toBeTruthy()
    await act(async () => { await readBranch.mock.results[0]!.value })
    expect(screen.queryByText(en.branch)).toBeNull()
    expect(screen.queryByText(en.context)).toBeNull()
    expect(screen.queryByText(en.tasks)).toBeNull()
  })

  it('neither asks for the branch nor watches jobs while the rail is hidden', () => {
    const { props, readBranch, watchRows } = panelProps({ shown: false, workspaces })
    render(<EnvironmentPanel {...props} />)
    expect(readBranch).not.toHaveBeenCalled()
    expect(watchRows).not.toHaveBeenCalled()
  })

  it('asks again on the refresh interval while shown', async () => {
    vi.useFakeTimers()
    const { props, readBranch } = panelProps({ workspaces })
    const { unmount } = render(<EnvironmentPanel {...props} />)
    expect(readBranch).toHaveBeenCalledTimes(1)
    await act(async () => { await vi.advanceTimersByTimeAsync(BRANCH_REFRESH_MS) })
    expect(readBranch).toHaveBeenCalledTimes(2)
    unmount()
    await vi.advanceTimersByTimeAsync(BRANCH_REFRESH_MS)
    expect(readBranch).toHaveBeenCalledTimes(2)
  })
})

describe('EnvironmentRail', () => {
  it('renders the title, the body slot, and a close button that closes', () => {
    const close = vi.fn()
    const renderSlot = vi.fn(() => <div data-testid="body" />)
    const props = { renderSlot, close, t } as unknown as EnvironmentRailProps
    render(<EnvironmentRail {...props} />)
    expect(screen.getByRole('complementary', { name: en.title })).toBeTruthy()
    expect(screen.getByTestId('body')).toBeTruthy()
    expect(renderSlot).toHaveBeenCalledWith('envbar.session', {})
    fireEvent.click(screen.getByRole('button', { name: en.close }))
    expect(close).toHaveBeenCalledOnce()
  })
})

describe('EnvironmentToggle', () => {
  it.each([true, false])('reflects shown=%s in aria-pressed and toggles on click', (shown) => {
    const toggle = vi.fn()
    const props = { useRailShown: hookOf(shown), toggle, t } as unknown as EnvironmentToggleProps
    render(<EnvironmentToggle {...props} />)
    const button = screen.getByRole('button', { name: en.toggle })
    expect(button.getAttribute('aria-pressed')).toBe(String(shown))
    fireEvent.click(button)
    expect(toggle).toHaveBeenCalledOnce()
  })
})

describe('truncateMiddle', () => {
  it('keeps short text and removes the middle of long text', () => {
    expect(truncateMiddle('abc', 5)).toBe('abc')
    expect(truncateMiddle('abcdefghij', 5)).toBe('ab…ij')
  })
})
