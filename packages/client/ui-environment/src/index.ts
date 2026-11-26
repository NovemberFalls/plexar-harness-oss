/**
 * Environment rail, node half: the one Host fact the rail cannot read from a
 * Client store — the git branch of a Session's workspace folder. The caller
 * names the Session only; the folder comes from the Host's own workspace
 * registry, so no client-supplied path ever reaches `git`.
 */

import { execFile } from 'node:child_process'
import { stat } from 'node:fs/promises'
import { delimiter, isAbsolute, join } from 'node:path'
import type { Context } from '@deepseek-ai/cordis'
import type { SessionId } from '@deepseek-ai/dsh-session'
import { Remote, TypertRemoteService } from '@deepseek-ai/dsh-typert-protocol'
import type { EnvironmentBranch } from './types.ts'

declare module '@deepseek-ai/cordis' {
  interface Context {
    /** Host facts for the Web UI's environment rail. */
    environmentRail: EnvironmentRail
  }
}

export type * from './types.ts'

/** The slice of the workspace registry (`@deepseek-ai/dsh-workspace`) this read needs. */
interface WorkspaceLookup {
  list(): readonly { readonly path: string; readonly sessionIds: readonly SessionId[] }[]
}

/** How long one `git rev-parse` may run before the answer is null. */
const GIT_TIMEOUT_MS = 2_000

/**
 * Find git on PATH as an absolute file. Windows' process search tries the
 * working directory before PATH, so spawning a bare `git` there would run a
 * `git.exe` planted in the workspace; only absolute PATH entries are used, so
 * the workspace folder is never searched.
 * @returns the absolute git executable, or null when PATH holds none.
 */
export async function resolveGit(): Promise<string | null> {
  const name = process.platform === 'win32' ? 'git.exe' : 'git'
  for (const directory of (process.env.PATH ?? '').split(delimiter)) {
    if (directory === '' || !isAbsolute(directory)) continue
    const candidate = join(directory, name)
    try {
      if ((await stat(candidate)).isFile()) return candidate
    } catch (_absent) {
      // Not in this PATH entry.
    }
  }
  return null
}

/**
 * Read the checked-out branch of one folder.
 * @param cwd - Host-resolved workspace folder.
 * @returns the branch name, or null on failure, without git on PATH, outside a repository, or on a detached HEAD.
 */
async function readBranch(cwd: string): Promise<string | null> {
  const git = await resolveGit()
  if (git === null) return null
  return new Promise((resolve) => {
    execFile(git, ['rev-parse', '--abbrev-ref', 'HEAD'], { cwd, timeout: GIT_TIMEOUT_MS, windowsHide: true, encoding: 'utf8' }, (error, stdout) => {
      const branch = error === null ? stdout.trim() : ''
      resolve(branch === '' || branch === 'HEAD' ? null : branch)
    })
  })
}

/** Remote namespace behind the rail's Branch section. */
export default class EnvironmentRail extends TypertRemoteService {
  static inject = ['workspaceRegistry']

  constructor(ctx: Context) {
    super(ctx, 'environmentRail')
  }

  /**
   * Resolve a Session's workspace folder on the Host and read its git branch.
   * @param sessionId - the Session whose workspace to inspect; the only input.
   * @returns the branch, null when the Session has no workspace or git gives no branch.
   */
  @Remote
  async branch(sessionId: SessionId): Promise<EnvironmentBranch> {
    try {
      const registry = this.ctx.get('workspaceRegistry') as WorkspaceLookup | undefined
      const workspace = registry?.list().find(entry => entry.sessionIds.includes(sessionId))
      if (workspace === undefined) return { branch: null }
      return { branch: await readBranch(workspace.path) }
    } catch (_unavailable) {
      return { branch: null }
    }
  }
}
