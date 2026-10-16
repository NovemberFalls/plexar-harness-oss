/**
 * The workspace fence decides file-tool paths against the session workspace root.
 */
import { mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, parse } from 'node:path'
import { afterAll, describe, expect, it, vi } from 'vitest'
import { Config, DOCUMENT_TOOLS, fenceDecision, pathArguments } from '../src/workspace-fence.ts'

const fsCalls = vi.hoisted(() => [] as string[])
vi.mock('node:fs/promises', async (importOriginal) => {
  const actual = await importOriginal<typeof import('node:fs/promises')>()
  return { ...actual, realpath: async (path: string) => { fsCalls.push(path); return await actual.realpath(path) } }
})

const base = mkdtempSync(join(tmpdir(), 'plexar-fence-'))
const root = join(base, 'ws')
const extra = join(base, 'extra')
const outside = join(base, 'outside')
mkdirSync(join(root, 'src'), { recursive: true })
mkdirSync(extra)
mkdirSync(outside)
writeFileSync(join(root, 'src', 'a.ts'), '')
writeFileSync(join(outside, 'secret.txt'), '')
afterAll(() => { rmSync(base, { recursive: true, force: true }) })

const config = (over: Partial<Config> = {}): Config => ({
  enabled: true,
  tools: ['read', 'read_image', 'write', 'edit', 'glob', 'grep'],
  extraRoots: [],
  outside: 'ask',
  ...over,
})

describe('workspace fence', () => {
  it('passes paths inside the workspace, existing or not', async () => {
    expect(await fenceDecision('read', { file_path: 'src/a.ts' }, root, config())).toBeUndefined()
    expect(await fenceDecision('write', { file_path: join(root, 'new', 'b.ts'), content: '' }, root, config())).toBeUndefined()
    expect(await fenceDecision('grep', { pattern: 'x' }, root, config())).toBeUndefined()
    expect(await fenceDecision('glob', { pattern: '**/*.ts' }, root, config())).toBeUndefined()
  })

  it('asks for a ../ escape by default and denies it naming the root when configured', async () => {
    expect(await fenceDecision('read', { file_path: '../outside/secret.txt' }, root, config())).toMatchObject({ kind: 'ask' })
    const denied = await fenceDecision('edit', { file_path: '../outside/secret.txt', old_string: 'a', new_string: 'b' }, root, config({ outside: 'deny' }))
    expect(denied).toMatchObject({ kind: 'deny' })
    expect(denied?.kind === 'deny' && denied.reason).toContain(root)
  })

  it('fences an absolute path on another drive or root', async () => {
    const { root: drive } = parse(root)
    const other = process.platform === 'win32'
      ? `${drive.toUpperCase().startsWith('Z') ? 'Y' : 'Z'}:\\data\\x.txt`
      : '/etc/hosts'
    expect(await fenceDecision('read', { file_path: other }, root, config())).toMatchObject({ kind: 'ask' })
  })

  it('allows extraRoots', async () => {
    expect(await fenceDecision('read', { file_path: join(extra, 'x.txt') }, root, config({ extraRoots: [extra] }))).toBeUndefined()
  })

  it('denies a symlink inside the workspace that points outside', async (test) => {
    const link = join(root, 'link')
    try {
      symlinkSync(outside, link, 'junction')
    } catch (error) {
      test.skip(`the OS refused to create a link: ${String(error)}`)
    }
    expect(await fenceDecision('read', { file_path: 'link/secret.txt' }, root, config({ outside: 'deny' }))).toMatchObject({ kind: 'deny' })
  })

  it('fences glob and grep rooted outside', async () => {
    expect(await fenceDecision('glob', { pattern: '*.txt', path: outside }, root, config())).toMatchObject({ kind: 'ask' })
    expect(await fenceDecision('glob', { pattern: `${outside.replace(/\\/g, '/')}/**/*.txt` }, root, config())).toMatchObject({ kind: 'ask' })
    expect(await fenceDecision('glob', { pattern: '../outside/*.txt' }, root, config())).toMatchObject({ kind: 'ask' })
    expect(await fenceDecision('grep', { pattern: 'x', path: '..' }, root, config())).toMatchObject({ kind: 'ask' })
  })

  it('decides UNC and device paths outside without touching the filesystem', async () => {
    for (const raw of [String.raw`\\host\share\x.txt`, '//host/share/x.txt', String.raw`  \\?\UNC\host\share\x.txt`, String.raw`\\.\pipe\p`]) {
      fsCalls.length = 0
      expect(await fenceDecision('read', { file_path: raw }, root, config())).toMatchObject({ kind: 'ask' })
      expect(fsCalls.filter(path => /host|pipe/.test(path))).toEqual([])
    }
  })

  it('fences lsp file_path and every present files[].path by default', async () => {
    // `tools` omitted, so the schema supplies its default.
    const { tools: _omitted, ...rest } = config()
    const defaults = Config(rest as Config)
    expect(defaults.tools).toEqual(expect.arrayContaining(['lsp', 'present']))
    expect(pathArguments('present', { files: [{ path: 'a.md' }, { path: '../b.md', description: 'd' }] })).toEqual(['a.md', '../b.md'])
    expect(await fenceDecision('lsp', { operation: 'hover', file_path: '../outside/secret.txt', line: 1, character: 1 }, root, defaults)).toMatchObject({ kind: 'ask' })
    expect(await fenceDecision('lsp', { operation: 'hover', file_path: 'src/a.ts', line: 1, character: 1 }, root, defaults)).toBeUndefined()
    expect(await fenceDecision('present', { files: [{ path: 'src/a.ts' }, { path: '../outside/secret.txt' }] }, root, defaults)).toMatchObject({ kind: 'ask' })
    expect(await fenceDecision('present', { files: [{ path: 'src/a.ts' }] }, root, defaults)).toBeUndefined()
  })

  it('fences the plexar-doc document tools by default, including each sources value', async () => {
    const defaults = Config({})
    expect(defaults.tools).toEqual(expect.arrayContaining(DOCUMENT_TOOLS))
    const read = 'mcp__plexar-doc__read_file'
    expect(await fenceDecision(read, { path: 'src/a.ts' }, root, defaults)).toBeUndefined()
    expect(await fenceDecision(read, { path: join(outside, 'secret.txt') }, root, defaults)).toMatchObject({ kind: 'ask' })
    const create = 'mcp__plexar-doc__create_document'
    expect(pathArguments(create, { sources: { logo: 'src/a.ts', chart: join(outside, 'secret.txt') } }))
      .toEqual(['src/a.ts', join(outside, 'secret.txt')])
    expect(await fenceDecision(create, { sources: { chart: join(outside, 'secret.txt') } }, root, defaults))
      .toMatchObject({ kind: 'ask' })
  })
})
