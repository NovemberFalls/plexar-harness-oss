/**
 * The Features catalog: every switch the Features section offers, grouped by
 * what a person uses it for. A feature is a tool feature (`tools`: its id is a
 * key of the Host `plexar-feature-toggles` config, and switching it edits that
 * plugin's `off` setting), a whole bundle (`bundle`), or a set of Loader plugins
 * switched together (`modules`, exact package names). A feature absent from the
 * running profile, or whose plugins the profile patch cannot address, renders
 * no row.
 */
import type { FeaturesLocaleKey } from './locales.ts'

/** One switch: the copy keys plus the bundle or plugins it turns on and off. */
export interface FeatureSpec {
  readonly id: string
  readonly nameKey: FeaturesLocaleKey
  readonly descriptionKey: FeaturesLocaleKey
  /** Bundle package name, switched through `setBundleEnabled`. */
  readonly bundle?: string
  /** Plugin package names, each switched through `setPluginEnabled`. */
  readonly modules?: readonly string[]
  /** True for a tool feature switched through the `plexar-feature-toggles` `off` setting. */
  readonly tools?: true
  /** True for the animated background, a per-viewer preference kept in this browser. */
  readonly aurora?: true
}

/** A titled group of switches. */
export interface FeatureGroup {
  readonly id: string
  readonly titleKey: FeaturesLocaleKey
  readonly features: readonly FeatureSpec[]
}

const pkg = (name: string): string => `@deepseek-ai/dsh-${name}`

/** Display order of groups and of switches within each group. */
export const FEATURE_GROUPS: readonly FeatureGroup[] = [
  {
    id: 'coding',
    titleKey: 'group.coding',
    features: [
      { id: 'shell', nameKey: 'feature.shell.name', descriptionKey: 'feature.shell.description', tools: true },
      { id: 'files', nameKey: 'feature.files.name', descriptionKey: 'feature.files.description', tools: true },
    ],
  },
  {
    id: 'web',
    titleKey: 'group.web',
    features: [
      { id: 'webSearch', nameKey: 'feature.webSearch.name', descriptionKey: 'feature.webSearch.description', tools: true },
      { id: 'browser', nameKey: 'feature.browserUse.name', descriptionKey: 'feature.browserUse.description', modules: [pkg('browser-use'), '@plexar/dsh-plexar/browser-bridge'] },
      { id: 'useMyChrome', nameKey: 'feature.useMyChrome.name', descriptionKey: 'feature.useMyChrome.description', tools: true },
    ],
  },
  {
    id: 'helpers',
    titleKey: 'group.helpers',
    features: [
      { id: 'subagents', nameKey: 'feature.subagents.name', descriptionKey: 'feature.subagents.description', tools: true },
      { id: 'workflows', nameKey: 'feature.workflows.name', descriptionKey: 'feature.workflows.description', tools: true },
      { id: 'agentTeams', nameKey: 'feature.agentTeams.name', descriptionKey: 'feature.agentTeams.description', bundle: pkg('experimental-agent-team-profile') },
    ],
  },
  {
    id: 'planning',
    titleKey: 'group.planning',
    features: [
      { id: 'todos', nameKey: 'feature.todos.name', descriptionKey: 'feature.todos.description', tools: true },
      { id: 'goals', nameKey: 'feature.goals.name', descriptionKey: 'feature.goals.description', tools: true },
    ],
  },
  {
    id: 'background',
    titleKey: 'group.background',
    features: [
      { id: 'jobs', nameKey: 'feature.jobs.name', descriptionKey: 'feature.jobs.description', tools: true },
      { id: 'skills', nameKey: 'feature.skills.name', descriptionKey: 'feature.skills.description', tools: true },
    ],
  },
  {
    id: 'appearance',
    titleKey: 'group.appearance',
    features: [
      { id: 'aurora', nameKey: 'feature.aurora.name', descriptionKey: 'feature.aurora.description', aurora: true },
    ],
  },
  {
    id: 'input',
    titleKey: 'group.input',
    features: [
      { id: 'voiceInput', nameKey: 'feature.voiceInput.name', descriptionKey: 'feature.voiceInput.description', bundle: pkg('experimental-voice-input-bundle') },
    ],
  },
]
