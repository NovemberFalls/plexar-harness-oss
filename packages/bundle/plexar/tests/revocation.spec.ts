/** Mid-session revocation detection and the `agent/request-error` listener decision. */

import { describe, expect, it, vi } from 'vitest'
import { LlmError } from '@deepseek-ai/dsh-llm'
import type { LlmFailure } from '@deepseek-ai/dsh-llm'
import {
  handleRequestError,
  isMidSessionRevocation,
  REVOKED_MID_SESSION_CODE,
  REVOKED_MID_SESSION_COPY,
} from '../src/revocation.ts'

/**
 * Build a failure whose message matches how pi-ai's `openai-completions` adapter composes a non-2xx
 * failure: `"<status>: <raw JSON body>"`.
 */
function bodyFailure(status: number, body: unknown, code = 'FORBIDDEN'): LlmFailure {
  return { message: `${status}: ${JSON.stringify(body)}`, code, status }
}

describe('isMidSessionRevocation', () => {
  it('is true for a 403 whose body names error.code product_not_granted', () => {
    expect(isMidSessionRevocation(bodyFailure(403, { error: { code: 'product_not_granted' } }))).toBe(true)
  })

  it('is false for a 403 whose body names a different error.code (model_not_permitted)', () => {
    expect(isMidSessionRevocation(bodyFailure(403, { error: { code: 'model_not_permitted' } }))).toBe(false)
  })

  it('is false for a non-403 status carrying the same body', () => {
    expect(isMidSessionRevocation(bodyFailure(401, { error: { code: 'product_not_granted' } }))).toBe(false)
  })

  it('is false for a 403 whose message carries no parseable JSON body', () => {
    expect(isMidSessionRevocation({ message: '403 status code (no body)', code: 'FORBIDDEN', status: 403 })).toBe(false)
  })

  it('is false for a 403 whose body is JSON but has no error.code field', () => {
    expect(isMidSessionRevocation(bodyFailure(403, { detail: 'forbidden' }))).toBe(false)
  })

  it('is false when status is absent (transport failure with no HTTP status)', () => {
    expect(isMidSessionRevocation({ message: 'socket hang up', code: 'TRANSPORT' })).toBe(false)
  })
})

describe('handleRequestError', () => {
  it('throws the pinned mid-session copy on revocation, without calling next', async () => {
    const next = vi.fn(() => Promise.resolve(undefined))
    const payload = {
      agent: {} as never,
      turn: 1,
      step: 1,
      provider: 'plexar',
      failure: bodyFailure(403, { error: { code: 'product_not_granted' } }),
      retryPolicy: undefined,
      signal: new AbortController().signal,
    }
    await expect(handleRequestError(payload, next)).rejects.toMatchObject({
      message: REVOKED_MID_SESSION_COPY,
      code: REVOKED_MID_SESSION_CODE,
    })
    expect(next).not.toHaveBeenCalled()
  })

  it('throws an LlmError instance carrying the failed request status', async () => {
    const next = vi.fn(() => Promise.resolve(undefined))
    const payload = {
      agent: {} as never,
      turn: 1,
      step: 1,
      provider: 'plexar',
      failure: bodyFailure(403, { error: { code: 'product_not_granted' } }),
      retryPolicy: undefined,
      signal: new AbortController().signal,
    }
    try {
      await handleRequestError(payload, next)
      expect.unreachable('handleRequestError must throw on revocation')
    } catch (error) {
      expect(error).toBeInstanceOf(LlmError)
      expect((error as LlmError).failure.status).toBe(403)
    }
  })

  it('delegates to next for a 403 that is not product_not_granted (model_not_permitted)', async () => {
    const decision = { kind: 'retry' as const }
    const next = vi.fn(() => Promise.resolve(decision))
    const payload = {
      agent: {} as never,
      turn: 1,
      step: 1,
      provider: 'plexar',
      failure: bodyFailure(403, { error: { code: 'model_not_permitted' } }),
      retryPolicy: undefined,
      signal: new AbortController().signal,
    }
    await expect(handleRequestError(payload, next)).resolves.toBe(decision)
    expect(next).toHaveBeenCalledTimes(1)
  })

  it('delegates to next for an unrelated failure (network/other)', async () => {
    const next = vi.fn(() => Promise.resolve(undefined))
    const payload = {
      agent: {} as never,
      turn: 1,
      step: 1,
      provider: 'plexar',
      failure: { message: 'socket hang up', code: 'TRANSPORT' },
      retryPolicy: undefined,
      signal: new AbortController().signal,
    }
    await expect(handleRequestError(payload, next)).resolves.toBeUndefined()
    expect(next).toHaveBeenCalledTimes(1)
  })
})
