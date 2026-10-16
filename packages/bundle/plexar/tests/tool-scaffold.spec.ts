/** Lean tool restriction and invalid-argument hints, composed on the real tool registry. */

import { describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import { createScope } from '@deepseek-ai/dsh-scope'
import type { Scope } from '@deepseek-ai/dsh-scope'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import ToolRuntime, { defineTool } from '@deepseek-ai/dsh-tools'
import type { ToolExecutionResult } from '@deepseek-ai/dsh-tools'
import type { Agent } from '@deepseek-ai/dsh-agent'
import { ToolCallId } from '@deepseek-ai/dsh-llm'
import type { SessionId } from '@deepseek-ai/dsh-session'
import * as ToolScaffold from '../src/tool-scaffold.ts'

const signal = new AbortController().signal

function makeTool(toolName: string) {
  return defineTool({
    name: toolName,
    description: toolName,
    parameters: { text: { type: 'string', required: true } },
    output: { schema: { type: 'string' }, render: (_args, value) => [{ type: 'text', text: value }] },
    async execute(args) { return args.text },
  })
}

async function mount(config: Partial<ToolScaffold.Config>): Promise<{ ctx: Context; key: Agent }> {
  const ctx = new Context()
  await ctx.plugin(SystemPrompt, {})
  await ctx.plugin(ToolRuntime)
  ctx.tools.register(makeTool('read'))
  ctx.tools.register(makeTool('job_list'))
  await ctx.plugin(ToolScaffold, config)
  const key = { id: 'a' as SessionId } as Agent
  let scope!: Scope
  await ctx.plugin(Object.assign((inner: Context) => { scope = createScope(inner, key) }, { inject: ['tools', 'systemPrompt'] }))
  Object.assign(key, { ctx: scope.ctx })
  return { ctx, key }
}

function text(result: ToolExecutionResult): string {
  return result.content.map(block => (block.type === 'text' ? block.text : '')).join('\n')
}

function call(ctx: Context, key: Agent, args: unknown): Promise<ToolExecutionResult> {
  return ctx.tools.execute({ signal, callId: ToolCallId('c'), name: 'read', arguments: args, agent: key })
}

describe('plexar-tool-scaffold', () => {
  it('lean denies the configured tools on a new agent', async () => {
    const { ctx, key } = await mount({ toolProfile: 'lean' })
    await ctx.parallel('agent/created', { agent: key } as never)
    expect(ctx.tools.schemas(key).map(t => t.name)).toEqual(['read'])
  })

  it('full leaves the tools untouched', async () => {
    const { ctx, key } = await mount({})
    await ctx.parallel('agent/created', { agent: key } as never)
    expect(ctx.tools.schemas(key).map(t => t.name).sort()).toEqual(['job_list', 'read'])
  })

  it('appends the schema and retry line to invalid arguments', async () => {
    const { ctx, key } = await mount({})
    const result = await call(ctx, key, {})
    expect(result.isError).toBe(true)
    expect(text(result)).toContain('invalid arguments')
    expect(text(result)).toContain('Parameter schema for read: {')
    expect(text(result)).toContain('Call read again with arguments matching this schema.')
  })

  it('caps the schema text', async () => {
    const { ctx, key } = await mount({ schemaHintMaxChars: 10 })
    const out = text(await call(ctx, key, {}))
    expect(out).toContain('Parameter schema for read: {')
    expect(out).toMatch(/\.\.\.\nCall read again/)
    expect(out).not.toContain('"required"')
  })

  it('leaves valid calls and disabled hints alone', async () => {
    const valid = await mount({})
    expect(text(await call(valid.ctx, valid.key, { text: 'ok' }))).toBe('ok')
    const off = await mount({ repairHints: false })
    expect(text(await call(off.ctx, off.key, {}))).not.toContain('Parameter schema')
  })
})
