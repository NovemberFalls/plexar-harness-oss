/**
 * Git Bash executor for Windows: the `dsh-pwsh-local` executor with its argv replaced by
 * `<bash.exe> -c <command>`. It inherits the Windows process mechanics (subprocess ranges, kill
 * escalation, output spill). Commands run unconfined; `@plexar/dsh-plexar/command-approval` asks the
 * user before a command runs.
 *
 * Mount it with `dsh-tool-bash` inside a Cordis group that isolates `shell`, so the bash tool and the
 * pwsh tool each see their own executor.
 *
 * @module @plexar/dsh-plexar/git-bash
 */
import { existsSync } from 'node:fs'
import { join } from 'node:path'
import type { Context } from '@deepseek-ai/cordis'
import type { ShellExecSpec } from '@deepseek-ai/dsh-shell'
import { PwshLocalExecutor } from '@deepseek-ai/dsh-pwsh-local'
import type { Config as LocalConfig } from '@deepseek-ai/dsh-pwsh-local'

/** Validated configuration: the pwsh executor budgets; the bash executable is probed. */
export type Config = LocalConfig

/**
 * Git for Windows bash locations, in resolution order. `System32\bash.exe` (the WSL launcher) is never
 * a candidate: it runs commands inside a Linux distro, not against the Windows workspace.
 * @param env - the environment to probe.
 * @returns candidate `bash.exe` paths.
 */
export function candidateBashPaths(env: NodeJS.ProcessEnv = process.env): string[] {
  const roots = [env.ProgramFiles ?? 'C:\\Program Files', env['ProgramFiles(x86)'], env.LOCALAPPDATA && join(env.LOCALAPPDATA, 'Programs')]
  return roots.filter((root): root is string => !!root).map(root => join(root, 'Git', 'bin', 'bash.exe'))
}

/**
 * Resolve the bash executable, failing loud when none exists.
 * @param configured - explicit path (`PLEXAR_BASH_PATH`), used when it exists.
 * @param env - the environment to probe.
 * @returns an existing bash executable path.
 * @throws Error naming the probed locations when Git Bash is not installed.
 */
export function resolveBashPath(configured?: string, env: NodeJS.ProcessEnv = process.env): string {
  const candidates = configured ? [configured] : candidateBashPaths(env)
  const found = candidates.find(candidate => existsSync(candidate))
  if (found === undefined) {
    throw new Error(`git-bash: no bash executable at ${candidates.join(', ')}; install Git for Windows or set PLEXAR_BASH_PATH`)
  }
  return found
}

/** Unconfined Git Bash executor registered as `ctx.shell`. */
export default class GitBashExecutor extends PwshLocalExecutor {
  /** The bash executable every command runs through. */
  readonly bashPath: string

  constructor(ctx: Context, config: Config) {
    super(ctx, config)
    this.bashPath = resolveBashPath(process.env.PLEXAR_BASH_PATH)
  }

  protected override argv(spec: ShellExecSpec): string[] {
    return [this.bashPath, '-c', spec.command]
  }
}
