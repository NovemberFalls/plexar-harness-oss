/**
 * Workspace fence for file tools, applied in every permission mode including `danger-full-access`.
 *
 * Plexar profiles run without an OS sandbox, and the filesystem backend leaves reads unfenced in every
 * mode and writes unfenced in `danger-full-access`. Before a configured file tool dispatches, this plugin
 * resolves each path argument (`file_path` for `read`, `read_image`, `write`, `edit`; `path` and an
 * absolute or `..`-leading `pattern` prefix for `glob`; `path` for `grep`; `file_path` for `lsp`; each
 * `files[].path` for `present`) against the session workspace root. A path starting with `\\` or `//`
 * (UNC, `\\?\UNC\`, device paths) is outside without any filesystem access, so no SMB connection opens.
 * Each path resolves to its real path when it exists, otherwise to the real path of its nearest
 * existing ancestor plus the remaining segments, so a symlink inside the workspace that points outside
 * counts as outside. Comparison ignores case and separator style on Windows.
 *
 * A path outside the workspace root and outside every `extraRoots` entry yields an `ask` decision, which
 * the tool registry routes to the user through the approval service, or a `deny` decision naming the
 * root, per `outside`. Paths inside call `next()`.
 *
 * Shell tools (`bash`, `pwsh`) are not fenced here: a command string names paths the plugin cannot
 * resolve reliably. `command-approval` gates those.
 *
 * @module @plexar/dsh-plexar/workspace-fence
 */

import { realpath } from 'node:fs/promises'
import { dirname, isAbsolute, join, relative, resolve } from 'node:path'
import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import type { PreToolDecision } from '@deepseek-ai/dsh-tools'
import type {} from '@deepseek-ai/dsh-sandbox-policy'

export const name = 'plexar-workspace-fence'
export const inject = ['sandboxPolicy']

/** Plugin configuration. */
export interface Config {
  /** Whether the fence runs. */
  enabled: boolean
  /** Tool names whose path arguments are fenced. */
  tools: string[]
  /** Absolute directories, besides the workspace root, that file tools may reach without a decision. */
  extraRoots: string[]
  /** Decision for a path outside every allowed root. */
  outside: 'deny' | 'ask'
}

export const Config: z<Config> = z.object({
  enabled: z.boolean().default(true),
  tools: z.array(z.string()).default(['read', 'read_image', 'write', 'edit', 'glob', 'grep', 'lsp', 'present']),
  extraRoots: z.array(z.string()).default([]),
  outside: z.union(['deny', 'ask'] as const).default('ask'),
})

const windows = process.platform === 'win32'

function comparable(path: string): string {
  const normalized = resolve(path)
  return windows ? normalized.replace(/\//g, '\\').toLowerCase() : normalized
}

/**
 * Whether `path` equals `root` or sits beneath it, after normalizing case and separators on Windows.
 * @param path - absolute candidate path.
 * @param root - absolute root directory.
 * @returns true when the path is the root or a descendant of it.
 */
export function isPathUnder(path: string, root: string): boolean {
  const rel = relative(comparable(root), comparable(path))
  return rel === '' || (!rel.startsWith('..') && !isAbsolute(rel))
}

/**
 * Resolve a path to its real location: the real path when it exists, otherwise the real path of its
 * nearest existing ancestor joined with the remaining segments.
 * @param path - absolute path, possibly containing `..` segments.
 * @returns the absolute real path.
 */
export async function realLocation(path: string): Promise<string> {
  let current = resolve(path)
  const rest: string[] = []
  for (;;) {
    try {
      return join(await realpath(current), ...rest.reverse())
    } catch (error) {
      // `error`: the path does not exist or cannot be resolved; climb to its parent.
      void error
      const parent = dirname(current)
      if (parent === current) return join(current, ...rest.reverse())
      rest.push(current.slice(parent.length).replace(/^[\\/]+/, ''))
      current = parent
    }
  }
}

/**
 * Whether a raw path argument names a UNC, `\\?\` or device path, which resolving could reach over the network.
 * @param raw - the path argument as given.
 * @returns true when the trimmed path starts with `\\` or `//`.
 */
export function isNetworkPath(raw: string): boolean {
  const trimmed = raw.trim()
  return trimmed.startsWith('\\\\') || trimmed.startsWith('//')
}

const GLOB_CHAR = /[*?[\]{}]/

/** The literal directory prefix of a glob pattern, or undefined when the pattern is relative and stays local. */
function patternRoot(pattern: string): string | undefined {
  if (!isAbsolute(pattern) && !pattern.startsWith('..')) return undefined
  const segments = pattern.split(/[\\/]/)
  const index = segments.findIndex(segment => GLOB_CHAR.test(segment))
  const literal = index === -1 ? segments : segments.slice(0, index)
  const joined = literal.join('/')
  return joined.length === 0 ? '/' : joined
}

/**
 * The path arguments a fenced tool call names.
 * @param tool - the tool name.
 * @param args - the parsed tool arguments.
 * @returns every path-valued argument, relative or absolute, as given.
 */
export function pathArguments(tool: string, args: unknown): string[] {
  if (typeof args !== 'object' || args === null) return []
  const record = args as { file_path?: unknown; path?: unknown; pattern?: unknown; files?: unknown }
  const paths: string[] = []
  if (typeof record.file_path === 'string') paths.push(record.file_path)
  if (typeof record.path === 'string') paths.push(record.path)
  if (Array.isArray(record.files)) {
    for (const file of record.files) {
      const item: unknown = file
      if (typeof item === 'object' && item !== null && 'path' in item && typeof item.path === 'string') paths.push(item.path)
    }
  }
  if (tool === 'glob' && typeof record.pattern === 'string') {
    const root = patternRoot(record.pattern)
    if (root !== undefined) paths.push(root)
  }
  return paths
}

/**
 * Decide one tool call against the fence.
 * @param tool - the tool name.
 * @param args - the parsed tool arguments.
 * @param workspaceRoot - absolute session workspace root.
 * @param config - fence configuration.
 * @returns a deny or ask decision for the first outside path, or undefined when every path is inside.
 */
export async function fenceDecision(
  tool: string,
  args: unknown,
  workspaceRoot: string,
  config: Config,
): Promise<PreToolDecision | undefined> {
  const roots = await Promise.all([workspaceRoot, ...config.extraRoots].map(realLocation))
  for (const raw of pathArguments(tool, args)) {
    const network = isNetworkPath(raw)
    const real = network ? raw.trim() : await realLocation(resolve(workspaceRoot, raw))
    if (!network && roots.some(root => isPathUnder(real, root))) continue
    return config.outside === 'deny'
      ? { kind: 'deny', reason: `${tool} cannot access ${raw}: it resolves to ${real}, outside the workspace ${workspaceRoot}. File tools may only reach paths inside the workspace.` }
      : { kind: 'ask', reason: `${tool} outside the workspace: ${real}` }
  }
  return undefined
}

/**
 * Register the pre-execute fence.
 * @param ctx - context carrying the permission policy.
 * @param config - fenced tools, extra roots, and the outside decision.
 */
export function apply(ctx: Context, config: Config): void {
  if (!config.enabled) return
  ctx.on('tools/pre-execute', async (exec, next): Promise<PreToolDecision> => {
    if (!config.tools.includes(exec.name) || exec.agent === undefined) return next()
    const { workspaceRoot } = ctx.sandboxPolicy.resolve({ session: exec.agent.session })
    return await fenceDecision(exec.name, exec.arguments, workspaceRoot, config) ?? next()
  })
}
