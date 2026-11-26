/**
 * Tool scaffolding for small local models.
 *
 * `toolProfile: 'lean'` removes the tools in `leanDeny` from each new agent's view through
 * `tools.restrict()`, so a 27-35B model chooses among fewer tools. Tools the agent cannot see
 * are skipped. A restriction applies to agents created afterwards.
 *
 * `deny` removes tools in every profile, for tools the product mounts but cannot serve (such as
 * `web_search` without a search provider).
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
  /** Tool names removed from each new agent in every profile. */
  deny: string[]
  /** Append the parameter schema and a retry line to invalid-argument errors. */
  repairHints: boolean
  /** Maximum characters of the schema JSON included in a hint; longer schemas are truncated. */
  schemaHintMaxChars: number
}

export const Config: z<Partial<Config>, Config> = z.object({
  toolProfile: z.union(['full', 'lean']).default('full'),
  leanDeny: z.array(z.string()).default(LEAN_DENY),
  deny: z.array(z.string()).default([]),
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
 * Hide tools from one agent through `tools.restrict()`.
 *
 * A tool counts when the agent sees it, wherever it is registered: the global layer (headless,
 * acp, sdk) or an ancestor scope such as the agent's preset composition (the Web profile, where
 * every tool row is mounted inside the preset). A tool registered in the agent's own scope
 * cannot be restricted; it is removed from the agent's assembled tool list instead and its
 * calls are refused by an agent-scoped guard.
 *
 * `restrict()` accepts only names the agent can already see, and a preset registers some tools
 * after the agent is created (`subagent`), so a name that is not visible yet is hidden when a
 * `tools/change` makes it visible, for the agent's lifetime.
 * @param agentCtx - the agent's scoped context.
 * @param names - tool names to hide.
 * @returns the names hidden right away.
 */
export function denyForAgent(agentCtx: Context, names: readonly string[]): string[] {
  const scope = scopeOf(agentCtx)
  const pending = new Set(names)
  // Tools the agent registers in its own scope, which restrict() cannot mask (the preset's `subagent`
  // installs a per-agent definition). They are dropped from the tool list each request carries and
  // refused by a guard if the model calls one anyway.
  const own = new Set<string>()
  const hideOwn = (tool: string): void => {
    if (own.size === 0) {
      agentCtx.on('system-prompt/assemble', async (_assembly, _context, next) => {
        const assembled = await next()
        return { ...assembled, tools: assembled.tools.filter(schema => !own.has(schema.name)) }
      })
      agentCtx.tools.guard(exec => own.has(exec.name) ? `tool "${exec.name}" is not available to this agent` : undefined)
    }
    own.add(tool)
  }
  const sweep = (): string[] => {
    const visible = [...pending].filter(tool => agentCtx.tools.get(tool, scope) !== undefined)
    if (visible.length === 0) return []
    // Removed before restrict(), which emits `tools/change` and re-enters this sweep.
    for (const tool of visible) pending.delete(tool)
    try {
      agentCtx.tools.restrict({ deny: visible })
    } catch {
      // One of them is registered in the agent's own scope; restrict the others one by one.
      for (const tool of visible) {
        try {
          agentCtx.tools.restrict({ deny: [tool] })
        } catch {
          hideOwn(tool)
        }
      }
    }
    return visible
  }
  const hidden = sweep()
  if (pending.size > 0) {
    const stop = agentCtx.on('tools/change', () => {
      sweep()
      if (pending.size === 0) stop()
    })
  }
  return hidden
}

/**
 * Apply the denied tool set and the invalid-argument hints.
 * @param ctx - the plugin context.
 * @param config - the resolved plugin configuration.
 */
export function apply(ctx: Context, config: Config): void {
  const denied = config.toolProfile === 'lean' ? [...new Set([...config.deny, ...config.leanDeny])] : config.deny
  if (denied.length > 0) {
    ctx.on('agent/created', ({ agent }) => {
      denyForAgent(agent.ctx, denied)
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
