/**
 * Host plugin `plexar-revocation`: stops a turn without retry when a /v1 call
 * fails because the rig revoked harness access mid-session, and surfaces the
 * pinned user-facing copy through the agent loop's existing terminal-error
 * path (contract §10p) instead of the raw provider failure text.
 *
 * @module @plexar/dsh-plexar/revocation
 */

import type { Context, Events } from '@deepseek-ai/cordis'
import { LlmError } from '@deepseek-ai/dsh-llm'
import type { LlmFailure } from '@deepseek-ai/dsh-llm'
import type { RequestErrorAction } from '@deepseek-ai/dsh-agent'

export const name = 'plexar-revocation'
export const inject = ['agents']

/** Pinned user-facing copy (contract §10p) for a key the rig revoked mid-session. */
export const REVOKED_MID_SESSION_COPY = 'Plexar Harness access was revoked. Ask the Plexar owner.'

/** Machine-routing code stamped on the terminal `LlmError` this plugin raises. */
export const REVOKED_MID_SESSION_CODE = 'PLEXAR_REVOKED_MID_SESSION'

/**
 * The `error.code` field of a /v1 failure body naming harness revocation
 * (contract §10p). Any other body, or none the message discloses, is left to
 * ordinary retry/error handling.
 */
const PRODUCT_NOT_GRANTED_BODY_CODE = 'product_not_granted'

/**
 * Extract the `error.code` field of a failed request's raw JSON body.
 *
 * `LlmFailure` carries no separate body field; the installed
 * `@earendil-works/pi-ai` package's `openai-completions` adapter folds the raw
 * provider body into `LlmFailure.message` as `"<status>: <raw JSON body>"`
 * (its shared `error-body.ts` normalization), so a composed message is the
 * only channel through which a listener can read the wire error code.
 * @param message - the failure's composed display message.
 * @returns the body's `error.code`, or `undefined` when the message carries
 *   no parseable JSON object, or that object names no such field.
 */
function bodyErrorCode(message: string): string | undefined {
  const start = message.indexOf('{')
  if (start === -1) return undefined
  let body: unknown
  try {
    body = JSON.parse(message.slice(start))
  } catch {
    return undefined
  }
  const code = (body as { error?: { code?: unknown } } | null)?.error?.code
  return typeof code === 'string' ? code : undefined
}

/**
 * Whether one failed request attempt is the rig's mid-session revocation
 * signal: a 403 whose body names `error.code == "product_not_granted"`
 * (contract §10p). A 403 for a different reason (for example
 * `model_not_permitted`), a different status, or a body this build cannot
 * parse, is not.
 * @param failure - serializable facts normalized at the final adapter boundary.
 * @returns whether the failure means the rig revoked harness access mid-session.
 */
export function isMidSessionRevocation(failure: LlmFailure): boolean {
  return failure.status === 403 && bodyErrorCode(failure.message) === PRODUCT_NOT_GRANTED_BODY_CODE
}

/**
 * The `agent/request-error` waterfall listener. A mid-session revocation
 * throws its own `LlmError` carrying the pinned copy instead of calling
 * `next()`: the throw escapes the waterfall dispatch directly, so the agent
 * loop's terminal error (`packages/core/agent-loop/src/agent.ts`) never
 * reconstructs from the raw provider failure message, and no retry is
 * attempted. Every other failure delegates unchanged.
 * @param payload - the failed attempt's provider-neutral facts.
 * @param next - delegates to the rest of the waterfall (retry policy, etc.).
 * @returns the delegated decision for a non-revocation failure.
 * @throws LlmError with the pinned "revoked mid-session" copy on revocation.
 */
export async function handleRequestError(
  payload: Parameters<Events['agent/request-error']>[0],
  next: () => Promise<RequestErrorAction>,
): Promise<RequestErrorAction> {
  if (!isMidSessionRevocation(payload.failure)) return next()
  // isMidSessionRevocation only returns true when failure.status === 403.
  throw new LlmError(REVOKED_MID_SESSION_COPY, REVOKED_MID_SESSION_CODE, { status: 403 })
}

/**
 * Install the mid-session revocation listener.
 * @param ctx - plugin context that owns the listener; disposed with the fiber.
 */
export function apply(ctx: Context): void {
  ctx.on('agent/request-error', handleRequestError)
}
