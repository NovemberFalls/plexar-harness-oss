/**
 * Ask-before-run for shell commands, in place of OS sandboxing (the Claude Code model).
 *
 * Shell tools run unconfined. Before a `bash` or `pwsh` call dispatches, this plugin decides from the
 * session's permission mode (the `sandboxPolicy` mode the `/permission` presets set):
 *
 * - `danger-full-access`: run without asking.
 * - `read-only` and `workspace-write`: run without asking only when every segment of the command
 *   (split on `&&`, `||`, `;`, `|`) starts with an allowed prefix and the command has no output
 *   redirection or command substitution; otherwise return an `ask` decision, which the tool registry
 *   routes to the user through the approval service.
 *
 * Allowed prefixes are the configured `allow` list plus prefixes the user adds for the session with
 * `/allow <prefix>`. Session additions live in memory only; they end with the process.
 *
 * @module @plexar/dsh-plexar/command-approval
 */

import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import type { Session } from '@deepseek-ai/dsh-session'
import type { PreToolDecision } from '@deepseek-ai/dsh-tools'
import type {} from '@deepseek-ai/dsh-sandbox-policy'
import { CommandDefinitionId } from '@deepseek-ai/dsh-commands/brand'

export const name = 'plexar-command-approval'
export const inject = ['sandboxPolicy', 'commands']

/** Plugin configuration. */
export interface Config {
  /** Tool names whose `command` argument is gated. */
  tools: string[]
  /** Command prefixes that run without asking in `read-only` and `workspace-write`. */
  allow: string[]
}

export const Config: z<Config> = z.object({
  tools: z.array(z.string()).default(['bash', 'pwsh']),
  allow: z.array(z.string()).default([]),
})

/** Output redirection, command or process substitution: any of these makes a command ask. */
const UNSAFE = /[<>`]|\$\(/

/**
 * Whether every segment of a command starts with an allowed prefix.
 * @param command - the shell command the model asked to run.
 * @param allow - allowed prefixes; a prefix matches a whole word or the whole segment.
 * @returns true when the command may run without asking.
 */
export function isAllowed(command: string, allow: Iterable<string>): boolean {
  if (UNSAFE.test(command)) return false
  const prefixes = [...allow].map(p => p.trim()).filter(p => p.length > 0)
  const segments = command.split(/&&|\|\||;|\||\r?\n/).map(s => s.trim()).filter(s => s.length > 0)
  return segments.length > 0 && segments.every(segment =>
    prefixes.some(p => segment === p || segment.startsWith(`${p} `)))
}

function commandOf(args: unknown): string | undefined {
  if (typeof args !== 'object' || args === null) return undefined
  const command = (args as { command?: unknown }).command
  return typeof command === 'string' ? command : undefined
}

/**
 * Register the pre-execute gate and the `/allow` command.
 * @param ctx - context carrying the permission policy and the command registry.
 * @param config - gated tools and the deployment allowlist.
 */
export function apply(ctx: Context, config: Config): void {
  const sessionAllow = new WeakMap<Session, Set<string>>()
  const allowedFor = (session: Session): string[] => [...config.allow, ...sessionAllow.get(session) ?? []]

  ctx.on('tools/pre-execute', async (exec, next): Promise<PreToolDecision> => {
    if (!config.tools.includes(exec.name) || exec.agent === undefined) return next()
    const session = exec.agent.session
    if (ctx.sandboxPolicy.resolve({ session }).mode === 'danger-full-access') return next()
    const command = commandOf(exec.arguments)
    if (command !== undefined && isAllowed(command, allowedFor(session))) return next()
    return { kind: 'ask', reason: command === undefined ? `run ${exec.name}` : `run: ${command}` }
  })

  ctx.effect(() => ctx.commands.register({
    definitionId: CommandDefinitionId('@plexar/dsh-plexar/allow'),
    name: 'allow',
    description: 'Let a command prefix run without asking in this session',
    input: { hint: '<command prefix>' },
    handler: (invocation) => {
      const prefix = invocation.rawInput.trim()
      const session = invocation.agent.session
      if (prefix.length === 0) {
        const added = [...sessionAllow.get(session) ?? []]
        return { kind: 'success', text: `Added this session: ${added.length ? added.join(', ') : 'none'}\nAlways allowed: ${config.allow.join(', ')}\nUsage: /allow <command prefix>` }
      }
      if (UNSAFE.test(prefix)) return { kind: 'error', text: 'A prefix cannot contain redirection or command substitution.' }
      const set = sessionAllow.get(session) ?? new Set<string>()
      set.add(prefix)
      sessionAllow.set(session, set)
      return { kind: 'success', text: `Commands starting with "${prefix}" now run without asking in this session.` }
    },
  }), 'plexar allow command')
}
