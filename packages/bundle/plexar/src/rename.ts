/**
 * `/rename <title>`: sets the session title through the harness title service, so the CLI, Studio and
 * the Web sidebar all show it. A user title pins: automatic title generation never overrides it.
 * With no argument it reports the current title. Runs from any command adapter, including ACP prompts.
 * @module @plexar/dsh-plexar/rename
 */

import type { Context } from '@deepseek-ai/cordis'
import { CommandDefinitionId } from '@deepseek-ai/dsh-commands/brand'
import type { CommandInvocation, CommandResult } from '@deepseek-ai/dsh-commands'
import { SessionTitleInvalidError } from '@deepseek-ai/dsh-session-title'

export const name = 'plexar-command-rename'
export const inject = ['commands', 'sessionTitle']

const USAGE = 'Usage: /rename <title>'

/**
 * Rename the invoking agent's session, or report its title when no title is given.
 * @param ctx - context carrying the `sessionTitle` service.
 * @param invocation - the command run; `rawInput` is the new title.
 * @returns the confirmation, or an error naming why the title was refused.
 */
function rename(ctx: Context, invocation: CommandInvocation): CommandResult {
  const title = invocation.rawInput.trim()
  const session = invocation.agent.session
  if (title.length === 0) {
    const current = ctx.sessionTitle.get(session)
    return { kind: 'success', text: current ? `Title: ${current.title}\n${USAGE}` : `No title yet.\n${USAGE}` }
  }
  try {
    const renamed = ctx.sessionTitle.rename(session, title)
    return { kind: 'success', text: `Renamed to "${renamed.title}".` }
  } catch (error: unknown) {
    if (error instanceof SessionTitleInvalidError) return { kind: 'error', text: `${error.message}. ${USAGE}` }
    throw error
  }
}

/**
 * Register `/rename` with the command registry for the plugin's lifetime.
 * @param ctx - context carrying the command registry and the title service.
 */
export function apply(ctx: Context): void {
  ctx.effect(() => ctx.commands.register({
    definitionId: CommandDefinitionId('@plexar/dsh-plexar/rename'),
    name: 'rename',
    description: 'Rename this session',
    input: { hint: '<title>' },
    handler: invocation => rename(ctx, invocation),
  }), 'plexar rename command')
}
