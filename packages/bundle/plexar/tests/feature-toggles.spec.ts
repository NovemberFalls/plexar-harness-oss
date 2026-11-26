/** Which tools the Features `off` setting hides. */

import { describe, expect, it, vi } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import { createScope } from '@deepseek-ai/dsh-scope'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import ToolRuntime, { defineTool } from '@deepseek-ai/dsh-tools'
import type { Agent } from '@deepseek-ai/dsh-agent'
import type { SessionId } from '@deepseek-ai/dsh-session'
import { apply, hiddenTools } from '../src/feature-toggles.ts'

const FEATURES = { shell: ['bash', 'pwsh'], files: ['read', 'write'], jobs: ['job_output', 'bash'] }

describe('hiddenTools', () => {
  it('hides nothing when every feature is on', () => {
    expect(hiddenTools(FEATURES, [])).toEqual({ tools: [], unknown: [] })
  })

  it('hides every tool of each off feature once', () => {
    expect(hiddenTools(FEATURES, ['shell', 'jobs']).tools).toEqual(['bash', 'pwsh', 'job_output'])
  })

  it('reports an off feature the configuration does not define', () => {
    expect(hiddenTools(FEATURES, ['voice', 'shell'])).toEqual({ tools: ['bash', 'pwsh'], unknown: ['voice'] })
  })
})

describe('apply', () => {
  it('loads a saved setting whose `features` table predates the browser switches', () => {
    // A failed load would drop the `off` setting the browser bridge reads and turn "Use my Chrome" back on.
    const error = vi.fn()
    const ctx = { logger: { error }, inject: () => {}, on: () => {} }
    expect(() => { apply(ctx as never, { features: FEATURES, off: { get: () => ['useMyChrome', 'inAppBrowser'] } } as never) }).not.toThrow()
    expect(error).not.toHaveBeenCalled()
  })

  it('reports an unknown off id instead of failing the load', () => {
    const error = vi.fn()
    const ctx = { logger: { error }, inject: () => {}, on: () => {} }
    expect(() => { apply(ctx as never, { features: FEATURES, off: { get: () => ['voice'] } } as never) }).not.toThrow()
    expect(error).toHaveBeenCalledWith(expect.stringContaining('voice'))
  })
})

describe('apply on the real tool registry', () => {
  it('hides an off feature tools that the agent inherits from its preset (Web profile)', async () => {
    const tool = (name: string) => defineTool({
      name,
      description: name,
      parameters: {},
      output: { schema: { type: 'string' }, render: () => [] },
      async execute() { return '' },
    })
    const ctx = new Context()
    await ctx.plugin(SystemPrompt, {})
    await ctx.plugin(ToolRuntime)
    apply(Object.assign(ctx.extend(), { inject: () => {} }) as never, { features: FEATURES, off: { get: () => ['shell'] } } as never)
    const standing = { id: 'preset' } as never
    let standingCtx!: Context
    await ctx.plugin(Object.assign((inner: Context) => { standingCtx = createScope(inner, standing).ctx }, { inject: ['tools', 'systemPrompt'] }))
    for (const name of ['bash', 'pwsh', 'read']) standingCtx.tools.register(tool(name))
    const agent = { id: 'a' as SessionId } as Agent
    await ctx.plugin(Object.assign((inner: Context) => { Object.assign(agent, { ctx: createScope(inner, agent, { parent: standing }).ctx }) }, { inject: ['tools', 'systemPrompt'] }))
    await ctx.parallel('agent/created', { agent } as never)
    expect(ctx.tools.schemas(agent).map(t => t.name)).toEqual(['read'])
  })
})
