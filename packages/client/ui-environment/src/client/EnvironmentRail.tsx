/**
 * The rail's three surfaces: the root occupant of the frame's `envbar` column
 * (title, close button, and the Session-bound body), the body itself, and the
 * header toggle. The body is a `session-maybe` child so the framework hands it
 * the current Session and its projections; without one it shows a single line.
 */
import { useEffect, useState, type ReactNode } from 'react'
import type { JobsSnapshot, JobView } from '@deepseek-ai/dsh-api-job-controller/client'
import type { WorkspaceSnapshot, WorkspaceView } from '@deepseek-ai/dsh-api-workspace-controller/client'
import type { SessionId } from '@deepseek-ai/dsh-session/types'
// Also pulls the `contextPressure` projection key merge.
import { contextOccupancy } from '@deepseek-ai/dsh-token-meter/client'
import { IconCloseOutlineRegular, IconInfoOutlineRegular, Tooltip } from '@deepseek-ai/dsh-client-ui-primitives'
import type { HostObservable, InjectFace, PropsLocale, PropsRenderSlots, PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
// Type-only: the 'conversation.session.header.actions' SlotMap entry.
import type {} from '@deepseek-ai/dsh-client-ui-conversation/client'
// Type-only: the 'envbar' SlotMap entry.
import type {} from '@deepseek-ai/dsh-client-ui-layout/client'
import type { NS } from './locales.ts'
import css from './EnvironmentRail.module.css'

/** How often the Branch section asks again while the rail is shown. */
export const BRANCH_REFRESH_MS = 30_000

/** Longest folder path drawn in full; longer ones lose their middle. */
const PATH_MAX = 36

/** Longest background-task label drawn in full. */
const TASK_MAX = 40

/** The rail occupant's face: closing is the same as toggling it off. */
export interface EnvironmentRailInjected {
  close: () => void
}

/** The body's face. Jobs and Workspaces are optional services: their sources read absence as no data. */
export interface EnvironmentPanelInjected {
  hooks: {
    /** Whether the rail is shown; nothing is fetched or watched while hidden. */
    railShown: HostObservable<boolean>
    /** Workspace rows, or undefined without the workspaces service. */
    workspaceList: HostObservable<WorkspaceSnapshot | undefined>
    /** Job rosters, or undefined without the jobs service. */
    jobRows: HostObservable<JobsSnapshot | undefined>
  }
  /** Keep one Session's job roster current; returns the stop function. */
  watchRows: (sessionId: SessionId) => () => void
  /** The Host's answer for the Session's branch; null on any failure. */
  readBranch: (sessionId: SessionId) => Promise<string | null>
}

/** The header toggle's face. */
export interface EnvironmentToggleInjected {
  hooks: { railShown: HostObservable<boolean> }
  toggle: () => void
}

/** Rail occupant props: the frame's envbar seat, the body renderer, copy, and the close action. */
export type EnvironmentRailProps =
  & PropsRuntime<'envbar'>
  & PropsRenderSlots<'envbar.session'>
  & PropsLocale<typeof NS>
  & InjectFace<EnvironmentRailInjected>

/** Body props: the current Session (if any), copy, and the optional-service sources. */
export type EnvironmentPanelProps =
  & PropsRuntime<'envbar.session'>
  & PropsLocale<typeof NS>
  & InjectFace<EnvironmentPanelInjected>

/** Header toggle props. */
export type EnvironmentToggleProps =
  & PropsRuntime<'conversation.session.header.actions'>
  & PropsLocale<typeof NS>
  & InjectFace<EnvironmentToggleInjected>

/**
 * Shorten text by removing its middle.
 * @param text - full text.
 * @param max - longest result.
 * @returns the text, or its two ends around an ellipsis.
 */
export function truncateMiddle(text: string, max: number): string {
  if (text.length <= max) return text
  const head = Math.ceil((max - 1) / 2)
  const tail = Math.floor((max - 1) / 2)
  return `${text.slice(0, head)}…${text.slice(text.length - tail)}`
}

/**
 * Shorten text at its end.
 * @param text - full text.
 * @param max - longest result.
 * @returns the text, or its start and an ellipsis.
 */
function truncateEnd(text: string, max: number): string {
  return text.length <= max ? text : `${text.slice(0, max - 1)}…`
}

function isLive(job: JobView): boolean {
  return job.status === 'running' || job.status === 'stopping'
}

/** One titled section of the body. */
function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className={css.section}>
      <h3 className={css.sectionTitle}>{title}</h3>
      {children}
    </section>
  )
}

/** The frame's rail column: title row, close button, and the Session-bound body. */
export function EnvironmentRail({ renderSlot, close, t }: EnvironmentRailProps) {
  return (
    <aside className={css.rail} aria-label={t('title')} data-environment-rail>
      <header className={css.header}>
        <h2 className={css.title}>{t('title')}</h2>
        <button type="button" className={css.iconButton} aria-label={t('close')} onClick={close}>
          <IconCloseOutlineRegular />
        </button>
      </header>
      <div className={css.body}>
        {renderSlot('envbar.session', {})}
      </div>
    </aside>
  )
}

/** The rail body for the current Session: Workspace, Branch, Context, Background tasks. */
export function EnvironmentPanel({
  sessionId, useProjection, useRailShown, useWorkspaceList, useJobRows, watchRows, readBranch, t,
}: EnvironmentPanelProps) {
  const shown = useRailShown(value => value)
  const workspace: WorkspaceView | undefined = useWorkspaceList(snapshot => sessionId === undefined
    ? undefined
    : snapshot?.items.find(item => item.sessionIds.includes(sessionId)))
  const jobs: readonly JobView[] | undefined = useJobRows(snapshot => sessionId === undefined ? undefined : snapshot?.rows[sessionId])
  const occupancy = contextOccupancy(useProjection('contextPressure'))
  const [branch, setBranch] = useState<{ sessionId: SessionId; value: string | null } | undefined>(undefined)

  // Asked on Session change and then on an interval, only while shown.
  useEffect(() => {
    if (!shown || sessionId === undefined) return undefined
    let live = true
    const ask = (): void => {
      void readBranch(sessionId).then((value) => { if (live) setBranch({ sessionId, value }) })
    }
    ask()
    const timer = setInterval(ask, BRANCH_REFRESH_MS)
    return () => {
      live = false
      clearInterval(timer)
    }
  }, [shown, sessionId, readBranch])

  // The roster streams only while someone can see it.
  useEffect(() => (shown && sessionId !== undefined ? watchRows(sessionId) : undefined), [shown, sessionId, watchRows])

  if (sessionId === undefined) return <p className={css.empty}>{t('empty')}</p>

  const branchName = branch?.sessionId === sessionId ? branch.value : null
  const running = (jobs ?? []).filter(isLive)
  const finished = (jobs ?? []).length - running.length
  return (
    <>
      <Section title={t('workspace')}>
        {workspace === undefined
          ? <p className={css.muted}>{t('workspaceNone')}</p>
          : (
            <>
              <p className={css.value}>{workspace.title}</p>
              <p className={css.path} title={workspace.path}>{truncateMiddle(workspace.path, PATH_MAX)}</p>
            </>
          )}
      </Section>
      {branchName !== null && (
        <Section title={t('branch')}>
          <p className={css.value} data-environment-branch>{branchName}</p>
        </Section>
      )}
      {occupancy !== null && (
        <Section title={t('context')}>
          <p className={css.value}>{t('contextUsed', { percent: occupancy.percent })}</p>
          <div
            className={css.bar}
            role="progressbar"
            aria-label={t('context')}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={occupancy.percent}
          >
            <div className={css.barFill} style={{ width: `${occupancy.percent}%` }} />
          </div>
        </Section>
      )}
      {(running.length > 0 || finished > 0) && (
        <Section title={t('tasks')}>
          {running.length > 0 && (
            <ul className={css.tasks}>
              {running.map(job => (
                <li key={job.id} className={css.task} title={job.label}>{truncateEnd(job.label, TASK_MAX)}</li>
              ))}
            </ul>
          )}
          {finished > 0 && <p className={css.muted}>{t('tasksFinished', { count: finished })}</p>}
        </Section>
      )}
    </>
  )
}

/** The conversation header's show/hide control for the rail. */
export function EnvironmentToggle({ useRailShown, toggle, t }: EnvironmentToggleProps) {
  const shown = useRailShown(value => value)
  return (
    <Tooltip label={t('toggle')} side="bottom" delayMs={500}>
      <button
        type="button"
        className={css.iconButton}
        aria-label={t('toggle')}
        aria-pressed={shown}
        data-environment-toggle
        onClick={toggle}
      >
        <IconInfoOutlineRegular />
      </button>
    </Tooltip>
  )
}
