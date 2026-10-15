/**
 * Plexar Features section: grouped toggle lists over the features users may
 * switch (see FEATURE_GROUPS). Each row shows a friendly name, a chevron that
 * expands a plain-language description, and a switch.
 */
import { useState } from 'react'
import type { HostObservable, InjectFace, PropsLocale, PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import type { FeaturesLocaleKey } from './locales.ts'
import css from './FeaturesSection.module.css'

/** One row the section renders: a catalog feature joined with its friendly copy and Host state. */
export interface FeatureRow {
  /** Catalog feature id. */
  readonly id: string
  readonly name: string
  readonly description: string
  readonly enabled: boolean
  /** True while a toggle for this row is crossing the wire. */
  readonly busy: boolean
}

/** One titled group with at least one row. */
export interface FeatureGroupRows {
  readonly id: string
  readonly title: string
  readonly rows: readonly FeatureRow[]
}

/** What the section reads and does; `status` mirrors the Host read. */
export interface FeaturesState {
  readonly status: 'idle' | 'loading' | 'ready' | 'unavailable'
  readonly groups: readonly FeatureGroupRows[]
}

/** Registration-side business face the section slot entry injects. */
export interface FeaturesSectionInjected {
  hooks: {
    features: HostObservable<FeaturesState>
  }
  /** Read the Host once the section first renders. */
  ensure: () => void
  /** Turn a catalog feature on or off. */
  setEnabled: (id: string, enabled: boolean) => void
}

/** Full component props: section owner share plus the registration-side face. */
export type FeaturesSectionComponentProps =
  PropsRuntime<'settings.section'>
  & PropsLocale<'settings.plexar.features'>
  & InjectFace<FeaturesSectionInjected>

/**
 * Render the Features section content column.
 * @param props - composed slot props.
 * @returns the section element tree.
 */
export function FeaturesSection({ t, useFeatures, ensure, setEnabled }: FeaturesSectionComponentProps) {
  ensure()
  const state = useFeatures(value => value)
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set())
  const toggleOpen = (name: string): void => {
    setOpen((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  return (
    <div className={css.section}>
      <h2 className={css.heading}>{t('title')}</h2>
      <p className={css.intro}>{t('intro')}</p>
      {state.status === 'loading' && <p className={css.empty}>{t('loading')}</p>}
      {state.status === 'unavailable' && <p className={css.empty}>{t('unavailable')}</p>}
      {state.status === 'ready' && state.groups.length === 0 && <p className={css.empty}>{t('empty')}</p>}
      {state.status === 'ready' && state.groups.map(group => (
        <section key={group.id} className={css.group} aria-label={group.title}>
          <h3 className={css.groupTitle}>{group.title}</h3>
          <ul className={css.list}>
            {group.rows.map(row => (
              <li key={row.id} className={css.item}>
                <div className={css.row}>
                  <button
                    type="button"
                    className={css.expander}
                    aria-expanded={open.has(row.id)}
                    aria-label={open.has(row.id) ? t('hideDetails') : t('showDetails')}
                    onClick={() => { toggleOpen(row.id) }}
                  >
                    <span className={css.chevron} data-open={open.has(row.id) ? 'true' : undefined} aria-hidden="true">›</span>
                    <span className={css.name}>{row.name}</span>
                  </button>
                  {row.busy ? (
                    <span className={css.busy}>{t('settingUp')}</span>
                  ) : (
                    <button
                      type="button"
                      role="switch"
                      aria-checked={row.enabled}
                      aria-label={row.name}
                      className={css.toggle}
                      data-on={row.enabled ? 'true' : undefined}
                      onClick={() => { setEnabled(row.id, !row.enabled) }}
                    >
                      <span className={css.thumb} />
                    </button>
                  )}
                </div>
                {open.has(row.id) && <p className={css.details}>{row.description}</p>}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap {
    /** Plexar Features section copy. */
    'settings.plexar.features': FeaturesLocaleKey
  }
}
