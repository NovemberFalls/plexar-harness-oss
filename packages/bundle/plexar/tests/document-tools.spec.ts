/**
 * The `plexar-document-tools` MCP row (cordis.patch.yml, N90): a real spawn of
 * `python -m plexar_tools.harness_mcp` against a temp workspace, using the same
 * interpreter-resolution rule the row's `command` uses, checked end to end
 * (initialize, tools/list, one path-argument call). No network.
 */

import { spawn } from 'node:child_process'
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { afterEach, describe, expect, it } from 'vitest'

const HERE = fileURLToPath(new URL('.', import.meta.url))
const REPO_ROOT = join(HERE, '..', '..', '..', '..')
const TOOLS_SRC = join(REPO_ROOT, 'python', 'tools', 'src')

// Mirrors cordis.patch.yml's `plexar-document-tools` row: PLEXAR_PYTHON, else
// `python` on Windows, `python3` elsewhere.
const PYTHON = process.env.PLEXAR_PYTHON ?? (process.platform === 'win32' ? 'python' : 'python3')

const TOOL_NAMES = ['read_file', 'find_in_file', 'query_sheet', 'convert_document', 'extract_document', 'create_document']

/** The JSON-RPC reply fields these tests read; a reply carries either `result` or `error`. */
interface RpcReply {
  result: {
    serverInfo: { name: string }
    tools: { name: string; inputSchema: { required: string[]; properties: Record<string, unknown> } }[]
    isError: boolean
    content: { text: string }[]
  }
  error: { code: number; message: string }
}

class JsonRpcClient {
  private readonly child: ReturnType<typeof spawn>
  private buffer = ''
  private nextId = 0
  private readonly pending = new Map<number, (value: RpcReply) => void>()
  private readonly stderrChunks: Buffer[] = []

  constructor(workspace: string) {
    this.child = spawn(PYTHON, ['-m', 'plexar_tools.harness_mcp'], {
      cwd: workspace,
      env: { ...process.env, PYTHONPATH: TOOLS_SRC, PLEXAR_TOOLS_ROOT: workspace },
      stdio: ['pipe', 'pipe', 'pipe'],
    })
    this.child.stdout!.on('data', (chunk: Buffer) => this.onData(chunk))
    this.child.stderr!.on('data', (chunk: Buffer) => this.stderrChunks.push(chunk))
  }

  private onData(chunk: Buffer): void {
    this.buffer += chunk.toString('utf8')
    let newline = this.buffer.indexOf('\n')
    while (newline !== -1) {
      const line = this.buffer.slice(0, newline)
      this.buffer = this.buffer.slice(newline + 1)
      newline = this.buffer.indexOf('\n')
      if (!line.trim()) continue
      const message = JSON.parse(line) as RpcReply & { id: number }
      this.pending.get(message.id)?.(message)
      this.pending.delete(message.id)
    }
  }

  request(method: string, params?: unknown): Promise<RpcReply> {
    const id = ++this.nextId
    const body = JSON.stringify({ jsonrpc: '2.0', id, method, ...(params !== undefined ? { params } : {}) })
    return new Promise((resolve) => {
      this.pending.set(id, resolve)
      this.child.stdin!.write(`${body}\n`)
    })
  }

  notify(method: string): void {
    this.child.stdin!.write(`${JSON.stringify({ jsonrpc: '2.0', method })}\n`)
  }

  stderrText(): string {
    return Buffer.concat(this.stderrChunks).toString('utf8')
  }

  async close(): Promise<void> {
    this.child.stdin!.end()
    await new Promise<void>(resolve => this.child.once('exit', () => resolve()))
  }
}

describe('plexar-document-tools MCP row', () => {
  let workspace: string | undefined
  let client: JsonRpcClient | undefined

  afterEach(async () => {
    await client?.close()
    client = undefined
    if (workspace) await rm(workspace, { recursive: true, force: true })
    workspace = undefined
  })

  it('lists the six pinned tools and reads a file by path', async () => {
    workspace = await mkdtemp(join(tmpdir(), 'plexar-doc-tools-'))
    await writeFile(join(workspace, 'a.txt'), 'alpha beta', 'utf8')
    client = new JsonRpcClient(workspace)

    const initReply = await client.request('initialize', { protocolVersion: '2025-06-18' })
    expect(initReply.result.serverInfo.name).toBe('plexar-tools')
    client.notify('notifications/initialized')

    const listReply = await client.request('tools/list')
    expect(listReply.result.tools.map((tool: { name: string }) => tool.name)).toEqual(TOOL_NAMES)
    for (const tool of listReply.result.tools) {
      if (tool.name === 'create_document') continue
      expect(tool.inputSchema.required).toContain('path')
      expect(tool.inputSchema.properties).not.toHaveProperty('document')
      expect(tool.inputSchema.properties).not.toHaveProperty('file')
    }

    const readReply = await client.request('tools/call', {
      name: 'read_file',
      arguments: { source: 'a.txt', start: 0, path: 'a.txt' },
    })
    expect(readReply.result.isError).toBe(false)
    expect(readReply.result.content[0]?.text).toContain('alpha beta')
  }, 30_000)

  it('refuses a path outside the workspace root', async () => {
    workspace = await mkdtemp(join(tmpdir(), 'plexar-doc-tools-'))
    client = new JsonRpcClient(workspace)
    await client.request('initialize', { protocolVersion: '2025-06-18' })
    client.notify('notifications/initialized')

    const reply = await client.request('tools/call', {
      name: 'read_file',
      arguments: { source: 'x', start: 0, path: '../outside.txt' },
    })
    expect(reply.error.code).toBe(-32602)
    expect(reply.error.message).toContain('outside the workspace root')
  }, 30_000)
})
