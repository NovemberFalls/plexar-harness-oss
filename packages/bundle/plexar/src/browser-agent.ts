/**
 * The browser agent: with `delegate` on, only an agent spawned through the `browse` tool gets the Playwright browser
 * tools. The `browse` row (a `tool-subagent` row in cordis.patch.yml) stamps its children with
 * `AgentOptions.subagentRole: 'browser'`; the browser bridge admits a browser MCP server only for such an agent,
 * hides the delegation tools from it, and keys its in-app pane by the top-level Session so the page survives
 * between two `browse` calls of one Session. With `delegate` off every agent is admitted and `browse` is hidden.
 * @module @plexar/dsh-plexar/browser-agent
 */

import type { Agent } from '@deepseek-ai/dsh-agent'
import type { SessionId } from '@deepseek-ai/dsh-session'

/** Model-facing name of the delegation tool that spawns the browser agent. */
export const BROWSE_TOOL = 'browse'

/** `AgentOptions.subagentRole` the `browse` row stamps on its children. */
export const BROWSER_AGENT_ROLE = 'browser'

/** Name of the `browse` argument that picks the browser. */
export const BROWSER_ARGUMENT = 'browser'

/** `browser` value for the in-app browser (the default) and for the person's Chrome through the extension. */
export const IN_APP_BROWSER = 'in_app'
export const MY_CHROME_BROWSER = 'my_chrome'

/** Tools a browser agent never sees: it cannot spawn agents or hand work to another browser agent. */
export const BROWSER_AGENT_DENY: readonly string[] = [
  BROWSE_TOOL, 'subagent', 'subagent_fork', 'list_subagent_models', 'send_message', 'list_agents',
  'interrupt_agent', 'workflow',
]

/**
 * Whether the agent was spawned through `browse`.
 * @param agent - the agent to classify.
 * @returns true when its options carry the browser role.
 */
export function isBrowserAgent(agent: Pick<Agent, 'options'>): boolean {
  return (agent.options as { subagentRole?: unknown }).subagentRole === BROWSER_AGENT_ROLE
}

/**
 * Whether the agent gets a browser MCP server and the browser tools.
 * @param agent - the new agent.
 * @param delegate - the bridge's `delegate` setting.
 * @returns every agent when `delegate` is off, else only a browser agent.
 */
export function admitsBrowserTools(agent: Pick<Agent, 'options'>, delegate: boolean): boolean {
  return !delegate || isBrowserAgent(agent)
}

/**
 * The route a new agent's browser server asks for.
 * @param agent - the admitted agent.
 * @param delegate - the bridge's `delegate` setting.
 * @returns `auto` (the old order) when `delegate` is off; else `my-chrome` only when the `browse` call asked for it.
 */
export function browserRoute(agent: Pick<Agent, 'options'>, delegate: boolean): 'auto' | 'in-app' | 'my-chrome' {
  if (!delegate) return 'auto'
  // Set only by the `browse` row from the main agent's argument; the browser agent cannot call `browse`.
  return isBrowserAgent(agent) && (agent.options as { subagentVariant?: unknown }).subagentVariant === MY_CHROME_BROWSER
    ? 'my-chrome'
    : 'in-app'
}

/**
 * Browser MCP tools no agent may hold. `browser_run_code_unsafe` runs its snippet in the MCP server's
 * Node process: its `vm` wrapper is escaped through the `page` object, which reaches `process`, the
 * file system and `child_process` with no command approval. A page's text could steer the agent to it.
 */
export const UNSAFE_BROWSER_TOOLS: readonly string[] = ['mcp__playwright-mcp__browser_run_code_unsafe']

/**
 * Tool names to deny on a new agent so its tool set matches the `delegate` setting.
 * @param agent - the new agent.
 * @param delegate - the bridge's `delegate` setting.
 * @returns `browse` for every agent when `delegate` is off; the delegation tools for a browser agent; else none.
 *   An agent that holds the browser tools is also denied {@link UNSAFE_BROWSER_TOOLS}.
 */
export function deniedTools(agent: Pick<Agent, 'options'>, delegate: boolean): readonly string[] {
  if (!delegate) return [BROWSE_TOOL, ...UNSAFE_BROWSER_TOOLS]
  return isBrowserAgent(agent) ? [...BROWSER_AGENT_DENY, ...UNSAFE_BROWSER_TOOLS] : []
}

/**
 * The top-level Session id above an agent: its own id, or the last parent Session reachable through live agents.
 * @param agent - the agent whose root is wanted.
 * @param lookup - finds a live agent by Session id.
 * @returns the root Session id.
 */
export function rootSessionId(
  agent: Pick<Agent, 'session'>,
  lookup: (id: SessionId) => Pick<Agent, 'session'> | undefined,
): SessionId {
  let id = agent.session.header.id
  let parent = agent.session.header.parentSession
  const seen = new Set<SessionId>([id])
  while (parent !== undefined && !seen.has(parent)) {
    seen.add(parent)
    id = parent
    parent = lookup(parent)?.session.header.parentSession
  }
  return id
}

/**
 * In-app panes kept for a root Session after the browser agent that opened them is gone. A browser agent's `close`
 * keeps the pane while its root agent is live; the root's disposal (or the bridge stopping) releases it.
 */
export class RootPanes {
  private readonly _held = new Map<string, () => void>()
  // Attachments not yet closed, per root; a root's disposal is remembered only while one is open, so the set stays
  // bounded and a reopened Session starts clean.
  private readonly _open = new Map<string, number>()
  private readonly _disposed = new Set<string>()

  /**
   * @param isLive - whether the root Session's agent is still live.
   */
  constructor(private readonly isLive: (root: string) => boolean) {}

  /**
   * Wrap one attachment's release.
   * @param root - the pane key, the root Session id.
   * @param release - writes `browser.release` for the pane.
   * @returns the `close` for the browser agent's server: releases now when the root is gone, else holds the pane.
   */
  hold(root: string, release: () => void): () => void {
    this._open.set(root, (this._open.get(root) ?? 0) + 1)
    let closed = false
    return () => {
      if (closed) return
      closed = true
      const open = (this._open.get(root) ?? 1) - 1
      const gone = this._disposed.has(root) || !this.isLive(root)
      if (open === 0) {
        this._open.delete(root)
        this._disposed.delete(root)
      } else {
        this._open.set(root, open)
      }
      if (gone) {
        release()
        return
      }
      // A later agent's release names the same pane; one is enough.
      if (!this._held.has(root)) this._held.set(root, release)
    }
  }

  /**
   * A root Session's agent was created (again): forget an earlier disposal so its pane is kept between calls.
   * @param root - the created agent's Session id.
   */
  rootCreated(root: string): void {
    this._disposed.delete(root)
  }

  /**
   * Release the pane held for a root Session, if any.
   * @param root - the disposed agent's Session id.
   */
  rootDisposed(root: string): void {
    if (this._open.has(root)) this._disposed.add(root)
    const release = this._held.get(root)
    if (release === undefined) return
    this._held.delete(root)
    release()
  }

  /** Release every held pane. */
  releaseAll(): void {
    for (const [root, release] of [...this._held]) {
      this._held.delete(root)
      release()
    }
  }
}
