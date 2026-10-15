/**
 * Sidebar footer update notice: renders nothing while the tracked checkout is
 * current, and otherwise a small state pill (or, collapsed, a dot icon
 * button) driving `apply()`/`restart()` on the Host `plexarUpdate` Remote.
 */
import type { HostObservable, InjectFace, PropsLocale, PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import type { UpdateLocaleKey } from './locales.ts'
import css from './UpdateNotice.module.css'

/** The states {@link UpdateNotice} renders explicitly; `'current'` renders nothing. */
export type UpdateNoticeState =
  /** `current` and `latest` are the Plexar versions of the checkout and of `origin`'s tip. */
  | { readonly state: 'available'; readonly current?: string; readonly latest?: string }
  | { readonly state: 'updating' }
  | { readonly state: 'restart-required' }
  | { readonly state: 'failed'; readonly error?: string }
  | { readonly state: 'current' }

/** Registration-side business face the sidebar footer action slot entry injects. */
export interface UpdateNoticeInjected {
  hooks: {
    status: HostObservable<UpdateNoticeState>
  }
  /** Start (or coalesce onto) an update run. */
  apply: () => void
  /** Ask the desktop app to restart the Host after a finished update. */
  restart: () => void
}

/** Full component props: sidebar footer owner share plus the registration-side face. */
export type UpdateNoticeComponentProps =
  PropsRuntime<'sidebar.footer.action'>
  & PropsLocale<'settings.plexar.update'>
  & InjectFace<UpdateNoticeInjected>

/**
 * Render the sidebar update notice for the current status, respecting the
 * collapsed (`wide: false`) sidebar rail.
 * @param props - composed slot props.
 * @returns the notice element tree, or null when current.
 */
export function UpdateNotice({ t, wide, useStatus, apply, restart }: UpdateNoticeComponentProps) {
  const status = useStatus(value => value)
  if (status.state === 'current') return null

  if (!wide) {
    const onClick = status.state === 'restart-required' ? restart : status.state === 'available' ? apply : undefined
    return (
      <button
        type="button"
        className={css.dot}
        aria-label={status.state === 'failed' ? t('failed') : t('available')}
        disabled={onClick === undefined}
        onClick={onClick}
      />
    )
  }

  if (status.state === 'updating') {
    return (
      <div className={css.pill} data-state="updating">
        <span className={css.label}>{t('updating')}</span>
      </div>
    )
  }

  if (status.state === 'available') {
    return (
      <div className={css.pill} data-state="available">
        <div className={css.text}>
          <span className={css.label}>{t('available')}</span>
          {status.current !== undefined && status.latest !== undefined && (
            <span className={css.versions}>{t('versions', { current: status.current, latest: status.latest })}</span>
          )}
        </div>
        <button type="button" className={css.action} onClick={apply}>{t('updateButton')}</button>
      </div>
    )
  }

  if (status.state === 'restart-required') {
    return (
      <div className={css.pill} data-state="restart-required">
        <span className={css.label}>{t('available')}</span>
        <button type="button" className={css.action} onClick={restart}>{t('restartButton')}</button>
      </div>
    )
  }

  return (
    <div className={css.pill} data-state="failed" title={status.error}>
      <span className={css.label}>{t('failed')}</span>
    </div>
  )
}

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap {
    /** Sidebar update notice copy. */
    'settings.plexar.update': UpdateLocaleKey
  }
}
