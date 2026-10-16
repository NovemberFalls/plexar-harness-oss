/**
 * Tool scaffolding for small local models.
 *
 * `toolProfile: 'lean'` removes the tools in `leanDeny` from each new agent's view through
 * `tools.restrict()`, so a 27-35B model chooses among fewer tools. Tools the agent cannot see
 * are skipped. A restriction applies to agents created afterwards.
 *
 * `repairHints` rewrites the result of a call whose arguments failed schema validation
 * (error code `INVALID_ARGS`) through the `tools/post-execute` waterfall: the original error text
 * is kept and followed by the tool's parameter JSON schema, truncated to `schemaHintMaxChars`,
 * and one line telling the model to call the tool again. The rewritten result is the normal tool
 * result, so the session log records exactly what the model sees.
 *
 * @module @plexar/dsh-plexar/tool-scaffold
 */

import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import { scopeOf } from '@deepseek-ai/dsh-scope'
import type { PostToolDecision } from '@deepseek-ai/dsh-tools'
import type {} from '@deepseek-ai/dsh-agent'

export const name = 'plexar-tool-scaffold'
export const inject = ['tools']

/** Tools a lean profile removes: delegation, goals, and background-job management. */
const LEAN_DENY: string[] = [
  'subagent', 'subagent_fork', 'list_subagent_models', 'send_message', 'list_agents',
  'interrupt_agent', 'workflow', 'create_goal', 'get_goal', 'update_goal',
  'job_output', 'job_kill', 'job_list',
]

/** Plugin configuration. */
export interface Config {
  /** `full` leaves the tool set untouched; `lean` denies `leanDeny` on each new agent. */
  toolProfile: 'full' | 'lean'
  /** Tool names a `lean` profile removes. */
  leanDeny: string[]
  /** Append the parameter schema and a retry line to invalid-argument errors. */
  repairHints: boolean
  /** Maximum characters of the schema JSON included in a hint; longer schemas are truncated. */
  schemaHintMaxChars: number
}

export const Config: z<Partial<Config>, Config> = z.object({
  toolProfile: z.union(['full', 'lean']).default('full'),
  leanDeny: z.array(z.string()).default(LEAN_DENY),
  repairHints: z.boolean().default(true),
  schemaHintMaxChars: z.number().min(1).step(1).default(2000),
}) as z<Partial<Config>, Config>

/**
 * Build the model-visible hint for an invalid-argument failure.
 * @param tool - the called tool's name.
 * @param parameters - the tool's parameter JSON schema.
 * @param maxChars - cap on the schema JSON length.
 * @returns the schema (compact JSON, truncated with an ellipsis past the cap) and the retry line.
 */
export function schemaHint(tool: string, parameters: unknown, maxChars: number): string {
  const json = JSON.stringify(parameters)
  const schema = json.length > maxChars ? `${json.slice(0, maxChars)}...` : json
  return `Parameter schema for ${tool}: ${schema}\nCall ${tool} again with arguments matching this schema.`
}

/**
 * Apply the lean tool set and the invalid-argument hints.
 * @param ctx - the plugin context.
 * @param config - the resolved plugin configuration.
 */
export function apply(ctx: Context, config: Config): void {
  if (config.toolProfile === 'lean') {
    ctx.on('agent/created', ({ agent }) => {
      const scope = scopeOf(agent.ctx)
      const visible = config.leanDeny.filter(tool => agent.ctx.tools.get(tool, scope) !== undefined)
      if (visible.length > 0) agent.ctx.tools.restrict({ deny: visible })
      return undefined
    })
  }
  if (config.repairHints) {
    ctx.on('tools/post-execute', async (exec, result, next): Promise<PostToolDecision> => {
      const decision = await next()
      if (!result.isError || result.error.info?.code !== 'INVALID_ARGS') return decision
      const definition = ctx.tools.get(exec.name, exec.agent)
      if (definition === undefined) return decision
      const hint = schemaHint(exec.name, definition.parameters, config.schemaHintMaxChars)
      return { kind: 'block', feedback: [...result.content, { type: 'text', text: hint }] }
    })
  }
}
