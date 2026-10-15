/** parseAllModels: env parsing/validation, sorting, and the PlexarModels Remote's list(). */

import { Context } from '@deepseek-ai/cordis'
import { describe, expect, it } from 'vitest'
import { parseAllModels, PlexarModels } from '../src/models.ts'

describe('parseAllModels', () => {
  it('is unavailable with empty lists when the variable is absent', () => {
    expect(parseAllModels(undefined)).toEqual({ source: 'unavailable', chat: [], classifiers: [] })
  })

  it('is unavailable when the variable is not JSON', () => {
    expect(parseAllModels('not json')).toEqual({ source: 'unavailable', chat: [], classifiers: [] })
  })

  it('is unavailable when the parsed value is not an array', () => {
    expect(parseAllModels('{"id":"x"}')).toEqual({ source: 'unavailable', chat: [], classifiers: [] })
  })

  it('is unavailable when every entry is malformed', () => {
    expect(parseAllModels(JSON.stringify([{ id: 'x' }, 'not an object', 42]))).toEqual({ source: 'unavailable', chat: [], classifiers: [] })
  })

  it('drops a malformed entry but keeps the valid ones', () => {
    const raw = JSON.stringify([
      { id: 'qwen3.8-27b', kind: 'chat', serving: true, name: 'Qwen3.8 27B' },
      { id: 'missing-kind', serving: true },
      { id: 'missing-serving', kind: 'chat' },
      { kind: 'chat', serving: true },
    ])
    const view = parseAllModels(raw)
    expect(view.source).toBe('plexar')
    expect(view.chat).toEqual([{ id: 'qwen3.8-27b', name: 'Qwen3.8 27B', serving: true, contextWindow: null, input: null }])
  })

  it('falls back to the id as the name, and null for unknown fields', () => {
    const raw = JSON.stringify([{ id: 'gemma-4-26b-fp8', kind: 'chat', serving: false, name: null, context_window: null, input: null }])
    expect(parseAllModels(raw).chat).toEqual([{ id: 'gemma-4-26b-fp8', name: 'gemma-4-26b-fp8', serving: false, contextWindow: null, input: null }])
  })

  it('reads context_window and input when present', () => {
    const raw = JSON.stringify([{ id: 'qwen3.8-27b', kind: 'chat', serving: true, name: 'Qwen', context_window: 131072, input: ['text', 'image'] }])
    expect(parseAllModels(raw).chat).toEqual([{ id: 'qwen3.8-27b', name: 'Qwen', serving: true, contextWindow: 131072, input: ['text', 'image'] }])
  })

  it('drops a non-string entry inside input, falling back to null', () => {
    const raw = JSON.stringify([{ id: 'x', kind: 'chat', serving: true, name: 'X', input: ['text', 1] }])
    expect(parseAllModels(raw).chat[0]!.input).toBeNull()
  })

  it('splits chat and classifier entries into their own lists', () => {
    const raw = JSON.stringify([
      { id: 'qwen3.8-27b', kind: 'chat', serving: true, name: 'Qwen' },
      { id: 'guard-1', kind: 'classifier', serving: true, name: 'Guard' },
    ])
    const view = parseAllModels(raw)
    expect(view.chat.map(m => m.id)).toEqual(['qwen3.8-27b'])
    expect(view.classifiers.map(m => m.id)).toEqual(['guard-1'])
  })

  it('sorts chat models serving-first, then by name', () => {
    const raw = JSON.stringify([
      { id: 'b-down', kind: 'chat', serving: false, name: 'B down' },
      { id: 'a-up', kind: 'chat', serving: true, name: 'A up' },
      { id: 'a-down', kind: 'chat', serving: false, name: 'A down' },
      { id: 'b-up', kind: 'chat', serving: true, name: 'B up' },
    ])
    expect(parseAllModels(raw).chat.map(m => m.id)).toEqual(['a-up', 'b-up', 'a-down', 'b-down'])
  })

  it('sorts classifiers by name', () => {
    const raw = JSON.stringify([
      { id: 'z', kind: 'classifier', serving: true, name: 'Zeta' },
      { id: 'a', kind: 'classifier', serving: false, name: 'Alpha' },
    ])
    expect(parseAllModels(raw).classifiers.map(m => m.id)).toEqual(['a', 'z'])
  })
})

describe('PlexarModels', () => {
  it('list() returns the roster parsed at construction from PLEXAR_HARNESS_ALL_MODELS', async () => {
    const previous = process.env['PLEXAR_HARNESS_ALL_MODELS']
    process.env['PLEXAR_HARNESS_ALL_MODELS'] = JSON.stringify([{ id: 'qwen3.8-27b', kind: 'chat', serving: true, name: 'Qwen' }])
    const ctx = new Context()
    try {
      const service = new PlexarModels(ctx)
      await expect(service.list()).resolves.toEqual({ source: 'plexar', chat: [{ id: 'qwen3.8-27b', name: 'Qwen', serving: true, contextWindow: null, input: null }], classifiers: [] })
    } finally {
      if (previous === undefined) delete process.env['PLEXAR_HARNESS_ALL_MODELS']
      else process.env['PLEXAR_HARNESS_ALL_MODELS'] = previous
      await ctx.fiber.dispose()
    }
  })

  it('list() is unavailable when the variable is unset', async () => {
    const previous = process.env['PLEXAR_HARNESS_ALL_MODELS']
    delete process.env['PLEXAR_HARNESS_ALL_MODELS']
    const ctx = new Context()
    try {
      const service = new PlexarModels(ctx)
      await expect(service.list()).resolves.toEqual({ source: 'unavailable', chat: [], classifiers: [] })
    } finally {
      if (previous !== undefined) process.env['PLEXAR_HARNESS_ALL_MODELS'] = previous
      await ctx.fiber.dispose()
    }
  })
})
