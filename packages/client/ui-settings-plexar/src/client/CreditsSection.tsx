/** Plexar Credits section: warm thanks to DeepSeek Harness and a list of the open-source parts Plexar ships. */
import type { PropsLocale, PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import type { CreditsLocaleKey } from './locales.ts'
import { PLEXAR_MARK_PNG } from './mark.ts'
import css from './CreditsSection.module.css'

/** Full component props: section owner share plus the Credits locale seat. */
export type CreditsSectionComponentProps = PropsRuntime<'settings.section'> & PropsLocale<'settings.plexar.credits'>

/**
 * Render the Credits section content column.
 * @param props - composed slot props.
 * @returns the section element tree.
 */
export function CreditsSection({ t }: CreditsSectionComponentProps) {
  return (
    <div className={css.section}>
      <img className={css.mark} src={PLEXAR_MARK_PNG} alt="" width={48} height={48} />
      <h2 className={css.heading}>{t('title')}</h2>
      <p className={css.thanks}>
        {t('thanksIntro')}
        {' '}
        <a className={css.link} href="https://github.com/deepseek-ai" target="_blank" rel="noreferrer">
          {t('thanksLink')}
        </a>
      </p>
      <h3 className={css.partsHeading}>{t('partsHeading')}</h3>
      <ul className={css.parts}>
        <li>{t('part.cordis')}</li>
        <li>{t('part.sensevoice')}</li>
        <li>{t('part.playwright')}</li>
        <li>{t('part.tauri')}</li>
      </ul>
    </div>
  )
}

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap {
    /** Plexar Credits section copy. */
    'settings.plexar.credits': CreditsLocaleKey
  }
}
