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

  it('deny removes its tools in every profile', async () => {
    const full = await mount({ deny: ['job_list', 'not_mounted'] })
    await full.ctx.parallel('agent/created', { agent: full.key } as never)
    expect(full.ctx.tools.schemas(full.key).map(t => t.name)).toEqual(['read'])
    const lean = await mount({ toolProfile: 'lean', leanDeny: [], deny: ['read'] })
    await lean.ctx.parallel('agent/created', { agent: lean.key } as never)
    expect(lean.ctx.tools.schemas(lean.key).map(t => t.name)).toEqual(['job_list'])
  })

  it('hides tools a preset registers in the standing scope and in the agent\'s own scope (Web profile)', async () => {
    const ctx = new Context()
    await ctx.plugin(SystemPrompt, {})
    await ctx.plugin(ToolRuntime)
    await ctx.plugin(ToolScaffold, { toolProfile: 'lean', deny: ['web_search'] })
    // The preset's standing composition: its tool rows register here, not globally.
    const standing = { id: 'preset' } as never
    let standingScope!: Scope
    await ctx.plugin(Object.assign((inner: Context) => { standingScope = createScope(inner, standing) }, { inject: ['tools', 'systemPrompt'] }))
    for (const tool of ['read', 'web_fetch', 'web_search', 'job_list', 'browse']) standingScope.ctx.tools.register(makeTool(tool))
    const key = { id: 'a' as SessionId } as Agent
    let scope!: Scope
    await ctx.plugin(Object.assign((inner: Context) => { scope = createScope(inner, key, { parent: standing }) }, { inject: ['tools', 'systemPrompt'] }))
    Object.assign(key, { ctx: scope.ctx })
    expect(ctx.tools.get('web_search')).toBeUndefined()
    await ctx.parallel('agent/created', { agent: key } as never)
    expect(ctx.tools.schemas(key).map(t => t.name).sort()).toEqual(['browse', 'read', 'web_fetch'])
    // The preset installs `subagent` in the agent's own scope after creation; restrict() cannot mask it.
    scope.ctx.tools.register(makeTool('subagent'))
    const assembled = await ctx.systemPrompt.assemble({ scope: key })
    expect(assembled.tools.map(t => t.name).sort()).toEqual(['browse', 'read', 'web_fetch'])
    const refused = await ctx.tools.execute({ signal, callId: ToolCallId('c'), name: 'subagent', arguments: { text: 'x' }, agent: key })
    expect(refused.isError).toBe(true)
    expect(text(refused)).toContain('not available to this agent')
    // Another agent of the same preset that the scaffold never saw keeps every tool.
    const other = { id: 'b' as SessionId } as Agent
    await ctx.plugin(Object.assign((inner: Context) => { createScope(inner, other, { parent: standing }) }, { inject: ['tools', 'systemPrompt'] }))
    expect(ctx.tools.schemas(other).map(t => t.name)).toContain('job_list')
  })

  it('denyForAgent hides a standing-scope tool registered after the agent was created', async () => {
    const ctx = new Context()
    await ctx.plugin(SystemPrompt, {})
    await ctx.plugin(ToolRuntime)
    const standing = { id: 'preset' } as never
    let standingScope!: Scope
    await ctx.plugin(Object.assign((inner: Context) => { standingScope = createScope(inner, standing) }, { inject: ['tools', 'systemPrompt'] }))
    const key = { id: 'a' as SessionId } as Agent
    let scope!: Scope
    await ctx.plugin(Object.assign((inner: Context) => { scope = createScope(inner, key, { parent: standing }) }, { inject: ['tools', 'systemPrompt'] }))
    expect(ToolScaffold.denyForAgent(scope.ctx, ['workflow'])).toEqual([])
    standingScope.ctx.tools.register(makeTool('workflow'))
    standingScope.ctx.tools.register(makeTool('read'))
    expect(ctx.tools.schemas(key).map(t => t.name)).toEqual(['read'])
  })

  it('a browser agent under a preset keeps only its own browser tools', async () => {
    const { BROWSER_AGENT_DENY } = await import('../src/browser-agent.ts')
    const ctx = new Context()
    await ctx.plugin(SystemPrompt, {})
    await ctx.plugin(ToolRuntime)
    const standing = { id: 'preset' } as never
    let standingScope!: Scope
    await ctx.plugin(Object.assign((inner: Context) => { standingScope = createScope(inner, standing) }, { inject: ['tools', 'systemPrompt'] }))
    for (const tool of ['bash', 'pwsh', 'read', 'write', 'web_fetch', 'subagent_fork']) standingScope.ctx.tools.register(makeTool(tool))
    ctx.tools.register(makeTool('browse'))
    const parent = { id: 'p' as SessionId } as Agent
    await ctx.plugin(Object.assign((inner: Context) => { createScope(inner, parent, { parent: standing }) }, { inject: ['tools', 'systemPrompt'] }))
    const child = { id: 'c' as SessionId } as Agent
    let childScope!: Scope
    await ctx.plugin(Object.assign((inner: Context) => { childScope = createScope(inner, child, { parent }) }, { inject: ['tools', 'systemPrompt'] }))
    // The `browse` row's toolFilter, then the bridge's denial, then the preset's own-scope `subagent` and the browser tools.
    childScope.ctx.tools.restrict({ allow: [] })
    ToolScaffold.denyForAgent(childScope.ctx, BROWSER_AGENT_DENY)
    childScope.ctx.tools.register(makeTool('subagent'))
    childScope.ctx.tools.register(makeTool('mcp__playwright-mcp__browser_click'))
    const assembled = await ctx.systemPrompt.assemble({ scope: child })
    expect(assembled.tools.map(t => t.name)).toEqual(['mcp__playwright-mcp__browser_click'])
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
