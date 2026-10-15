/**
 * Settings > Features tool switches for Plexar.
 *
 * `features` maps each switchable feature id to the tool names it contributes. The `off` setting
 * (a live settings field on this plugin's namespace) lists the feature ids the user turned off.
 * When an agent is created, every tool of an off feature that the agent can see is removed from
 * its view through `tools.restrict()`. The restriction masks tools inherited from the agent's
 * preset as well as global ones, and applies to helper agents too.
 *
 * A change applies to agents created afterwards; running agents keep their tools. The tool list
 * each request carried is recorded by the `request/header` session event, so the log shows what
 * the model could call. Tools a preset adds after the agent was created are not masked.
 *
 * @module @plexar/dsh-plexar/feature-toggles
 */

import type { Context, Volatile } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import { scopeOf } from '@deepseek-ai/dsh-scope'
import type {} from '@deepseek-ai/dsh-tools'
import type {} from '@deepseek-ai/dsh-agent'
import type {} from '@deepseek-ai/dsh-settings'

export const name = 'plexar-feature-toggles'
export const inject = ['tools']

/** Plugin configuration. */
export interface Config {
  /** Feature id to the tool names it contributes. */
  features: Record<string, string[]>
  /** Feature ids the user turned off (live setting); unset means every feature is on. */
  off: Volatile<string[] | undefined>
}

export const Config: z<Config> = z.object({
  features: z.dict(z.array(z.string())).required(),
  off: z.array(z.string()).volatile(),
}) as z<Config>

/**
 * Tool names hidden by a set of off features.
 * @param features - feature id to tool names.
 * @param off - feature ids turned off.
 * @returns the tool names to hide, without duplicates, and the off ids `features` does not define.
 */
export function hiddenTools(
  features: Readonly<Record<string, readonly string[]>>,
  off: readonly string[],
): { tools: string[]; unknown: string[] } {
  return {
    tools: [...new Set(off.flatMap(id => features[id] ?? []))],
    unknown: off.filter(id => !Object.hasOwn(features, id)),
  }
}

/**
 * Validate the configuration and mask off features' tools on each new agent.
 * @param ctx - the plugin context.
 * @param config - the resolved plugin configuration.
 */
export function apply(ctx: Context, config: Config): void {
  const unknownAtLoad = hiddenTools(config.features, config.off.get() ?? []).unknown
  if (unknownAtLoad.length > 0) throw new Error(`plexar-feature-toggles: off names unknown feature ${unknownAtLoad.join(', ')}`)
  // Settings > Features is this namespace's page; no generated form.
  ctx.inject(['settings'], (child) => { child.effect(() => child.settings.configure({ auto: false }, ctx.fiber)) })
  ctx.on('agent/created', ({ agent }) => {
    // The setting changed after load; an unknown id is reported here rather than failing agent creation.
    const { tools: hidden, unknown } = hiddenTools(config.features, config.off.get() ?? [])
    if (unknown.length > 0) ctx.logger.error(`off names unknown feature ${unknown.join(', ')}; its tools stay visible`)
    const scope = scopeOf(agent.ctx)
    const visible = hidden.filter(tool => agent.ctx.tools.get(tool, scope) !== undefined)
    if (visible.length > 0) agent.ctx.tools.restrict({ deny: visible })
    return undefined
  })
}
