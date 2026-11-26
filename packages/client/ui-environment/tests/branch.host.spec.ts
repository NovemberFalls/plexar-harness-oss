/** The Host half: the folder comes from the registry, git comes from PATH, runs without a shell, and every failure is null. */
import { Context } from '@deepseek-ai/cordis'
import { delimiter, join, resolve } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, onTestFinished, vi } from 'vitest'
import type { SessionId } from '@deepseek-ai/dsh-session'

type Callback = (error: Error | null, stdout: string) => void
const execFile = vi.hoisted(() => vi.fn())
const files = vi.hoisted(() => new Set<string>())
vi.mock('node:child_process', () => ({ execFile }))
vi.mock('node:fs/promises', () => ({
  stat: vi.fn((path: string) => files.has(path)
    ? Promise.resolve({ isFile: () => true })
    : Promise.reject(Object.assign(new Error('ENOENT'), { code: 'ENOENT' }))),
}))

const { default: EnvironmentRail, resolveGit } = await import('../src/index.ts')

const SESSION = 's-1' as SessionId
const GIT_NAME = process.platform === 'win32' ? 'git.exe' : 'git'
const BIN = resolve('/usr-tools/bin')
const GIT = join(BIN, GIT_NAME)

beforeEach(() => {
  execFile.mockReset()
  files.clear()
  files.add(GIT)
  vi.stubEnv('PATH', BIN)
})

afterEach(() => { vi.unstubAllEnvs() })

function answer(error: Error | null, stdout = ''): void {
  execFile.mockImplementation((_file: string, _args: string[], _options: object, callback: Callback) => { callback(error, stdout) })
}

async function mount(list: () => readonly { path: string; sessionIds: readonly SessionId[] }[]) {
  const ctx = new Context()
  onTestFinished(() => ctx.fiber.dispose())
  ctx.provide('workspaceRegistry', { list } as never)
  await ctx.plugin(EnvironmentRail).await()
  return ctx.environmentRail
}

describe('resolveGit', () => {
  it('returns the first absolute PATH entry holding git', async () => {
    const other = resolve('/other/bin')
    vi.stubEnv('PATH', [other, BIN].join(delimiter))
    await expect(resolveGit()).resolves.toBe(GIT)
  })

  it('never searches relative PATH entries, so a git in the working folder is not found', async () => {
    files.clear()
    files.add(join('.', GIT_NAME))
    vi.stubEnv('PATH', ['', '.', 'tools'].join(delimiter))
    await expect(resolveGit()).resolves.toBeNull()
  })
})

describe('EnvironmentRail.branch', () => {
  it('runs PATH git by absolute path in the Session workspace the registry names, without a shell, 2 s, hidden', async () => {
    answer(null, 'feat/in-app-browser\n')
    const rail = await mount(() => [{ path: '/other', sessionIds: [] }, { path: '/repo', sessionIds: [SESSION] }])
    await expect(rail.branch(SESSION)).resolves.toEqual({ branch: 'feat/in-app-browser' })
    expect(execFile).toHaveBeenCalledOnce()
    const [file, args, options] = execFile.mock.calls[0]! as [string, string[], Record<string, unknown>]
    expect(file).toBe(GIT)
    expect(args).toEqual(['rev-parse', '--abbrev-ref', 'HEAD'])
    expect(options).toMatchObject({ cwd: '/repo', timeout: 2000, windowsHide: true })
    expect(options.shell).toBeUndefined()
  })

  it('returns null without spawning when git is not on PATH, even if the workspace holds one', async () => {
    files.clear()
    files.add(join('/repo', GIT_NAME))
    const rail = await mount(() => [{ path: '/repo', sessionIds: [SESSION] }])
    await expect(rail.branch(SESSION)).resolves.toEqual({ branch: null })
    expect(execFile).not.toHaveBeenCalled()
  })

  it('takes the Session id only, never a path from the caller', async () => {
    answer(null, 'main\n')
    const rail = await mount(() => [{ path: '/repo', sessionIds: [SESSION] }])
    expect(EnvironmentRail.prototype.branch.length).toBe(1)
    // A path-shaped id is just an unknown Session: no workspace, no git.
    await expect(rail.branch('/etc' as SessionId)).resolves.toEqual({ branch: null })
    expect(execFile).not.toHaveBeenCalled()
  })

  it.each([
    ['git fails (not a repository)', new Error('fatal: not a git repository'), ''],
    ['HEAD is detached', null, 'HEAD\n'],
    ['git prints nothing', null, ''],
  ])('returns null when %s', async (_case, error, stdout) => {
    answer(error, stdout)
    const rail = await mount(() => [{ path: '/repo', sessionIds: [SESSION] }])
    await expect(rail.branch(SESSION)).resolves.toEqual({ branch: null })
  })

  it('returns null when the registry fails', async () => {
    const rail = await mount(() => { throw new Error('registry not ready') })
    await expect(rail.branch(SESSION)).resolves.toEqual({ branch: null })
    expect(execFile).not.toHaveBeenCalled()
  })
})
