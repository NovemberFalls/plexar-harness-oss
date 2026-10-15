/**
 * Plexar Account section: who is signed in, and a sign-out control with a confirm step. Reads
 * the Host `plexarAuth` Remote once on first render; sign-out is a two-step action (the button
 * asks "Sign out of Plexar on this computer?" before it does anything) since it revokes the key
 * server-side and deletes it from the OS credential store.
 */
import { useState } from 'react'
import type { HostObservable, InjectFace, PropsLocale, PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import type { AccountLocaleKey } from './locales.ts'
import css from './AccountSection.module.css'

/** Where the active key came from. */
export type AccountSource = 'keychain' | 'env' | 'none'

/** What the section reads; `status` mirrors the Host read. */
export type AccountState =
  | { readonly status: 'loading' }
  | { readonly status: 'unavailable' }
  | { readonly status: 'ready'; readonly signedIn: boolean; readonly email?: string; readonly source: AccountSource }

/** Registration-side business face the section slot entry injects. */
export interface AccountSectionInjected {
  hooks: {
    account: HostObservable<AccountState>
  }
  /** Read the Host once the section first renders. */
  ensure: () => void
  /** Revoke the stored key server-side, delete it locally, and (under the desktop app) stop the Host. */
  signOut: () => Promise<{ readonly ok: boolean }>
}

/** Full component props: section owner share plus the registration-side face. */
export type AccountSectionComponentProps =
  PropsRuntime<'settings.section'>
  & PropsLocale<'settings.plexar.account'>
  & InjectFace<AccountSectionInjected>

/**
 * Render the Account section content column.
 * @param props - composed slot props.
 * @returns the section element tree.
 */
export function AccountSection({ t, useAccount, ensure, signOut }: AccountSectionComponentProps) {
  ensure()
  const state = useAccount(value => value)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)

  async function handleConfirm(): Promise<void> {
    setBusy(true)
    try {
      await signOut()
    } finally {
      setBusy(false)
      setConfirming(false)
    }
  }

  return (
    <div className={css.section}>
      <h2 className={css.heading}>{t('title')}</h2>
      {state.status !== 'ready' && <p className={css.status}>{t('loading')}</p>}
      {state.status === 'ready' && !state.signedIn && <p className={css.status}>{t('signedOut')}</p>}
      {state.status === 'ready' && state.signedIn && state.source === 'env' && (
        <p className={css.status}>{t('devKey')}</p>
      )}
      {state.status === 'ready' && state.signedIn && state.source !== 'env' && !confirming && (
        <div className={css.row}>
          <p className={css.status}>{t('signedInAs', { email: state.email ?? '' })}</p>
          <button type="button" className={css.signOutButton} onClick={() => { setConfirming(true) }}>
            {t('signOut')}
          </button>
        </div>
      )}
      {state.status === 'ready' && state.signedIn && state.source !== 'env' && confirming && (
        <div className={css.confirm}>
          <p className={css.confirmText}>{t('confirmPrompt')}</p>
          <div className={css.confirmActions}>
            <button type="button" className={css.signOutButton} disabled={busy} onClick={() => { void handleConfirm() }}>
              {t('signOut')}
            </button>
            <button type="button" className={css.cancelButton} disabled={busy} onClick={() => { setConfirming(false) }}>
              {t('cancel')}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap {
    /** Plexar Account section copy. */
    'settings.plexar.account': AccountLocaleKey
  }
}
