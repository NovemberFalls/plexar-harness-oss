/**
 * Plexar Models section: the signed-in person's chat models and classifiers,
 * read once from the Host `plexarModels` Remote on first render.
 */
import type { HostObservable, InjectFace, PropsLocale, PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import type { ModelsLocaleKey } from './locales.ts'
import css from './ModelsSection.module.css'

/** One model row the section renders. */
export interface ModelRow {
  readonly id: string
  readonly name: string
  readonly serving: boolean
  readonly contextWindow: number | null
  readonly input: readonly string[] | null
}

/** What the section reads; `status` mirrors the Host read. */
export type ModelsState =
  | { readonly status: 'loading' }
  | { readonly status: 'unavailable' }
  | { readonly status: 'ready'; readonly chat: readonly ModelRow[]; readonly classifiers: readonly ModelRow[] }

/** Registration-side business face the section slot entry injects. */
export interface ModelsSectionInjected {
  hooks: {
    models: HostObservable<ModelsState>
  }
  /** Read the Host once the section first renders. */
  ensure: () => void
}

/** Full component props: section owner share plus the registration-side face. */
export type ModelsSectionComponentProps =
  PropsRuntime<'settings.section'>
  & PropsLocale<'settings.plexar.models'>
  & InjectFace<ModelsSectionInjected>

/** One model row: name, id, serving pill, and its tags. */
/** Props of one model row. */
interface ModelRowItemProps {
  row: ModelRow
  t: (key: ModelsLocaleKey, params?: Record<string, string>) => string
  classifier: boolean
}

function ModelRowItem({ row, t, classifier }: ModelRowItemProps) {
  const images = row.input !== null && row.input.includes('image')
  return (
    <li className={css.item}>
      <div className={css.main}>
        <span className={css.name}>{row.name}</span>
        {row.name !== row.id && <span className={css.id}>{row.id}</span>}
      </div>
      <div className={css.tags}>
        {classifier && <span className={css.tag}>{t('classifierTag')}</span>}
        {images && <span className={css.tag}>{t('imagesTag')}</span>}
        {row.contextWindow !== null && <span className={css.tag}>{t('contextTag', { n: String(Math.round(row.contextWindow / 1024)) })}</span>}
        <span className={css.pill} data-serving={row.serving ? 'true' : undefined}>{t(row.serving ? 'servingPill' : 'notServingPill')}</span>
      </div>
    </li>
  )
}

/**
 * Render the Models section content column.
 * @param props - composed slot props.
 * @returns the section element tree.
 */
export function ModelsSection({ t, useModels, ensure }: ModelsSectionComponentProps) {
  ensure()
  const state = useModels(value => value)

  return (
    <div className={css.section}>
      <h2 className={css.heading}>{t('title')}</h2>
      <p className={css.intro}>{t('intro')}</p>
      {state.status === 'unavailable' && <p className={css.empty}>{t('unavailable')}</p>}
      {state.status === 'ready' && (
        <>
          <section className={css.group} aria-label={t('group.chat')}>
            <h3 className={css.groupTitle}>{t('group.chat')}</h3>
            <ul className={css.list}>
              {state.chat.map(row => <ModelRowItem key={row.id} row={row} t={t} classifier={false} />)}
            </ul>
          </section>
          {state.classifiers.length > 0 && (
            <section className={css.group} aria-label={t('group.classifiers')}>
              <h3 className={css.groupTitle}>{t('group.classifiers')}</h3>
              <ul className={css.list}>
                {state.classifiers.map(row => <ModelRowItem key={row.id} row={row} t={t} classifier />)}
              </ul>
            </section>
          )}
        </>
      )}
    </div>
  )
}

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap {
    /** Plexar Models section copy. */
    'settings.plexar.models': ModelsLocaleKey
  }
}
