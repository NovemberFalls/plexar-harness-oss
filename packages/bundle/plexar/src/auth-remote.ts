/**
 * Host sign-in status and sign-out service backing the generated `ctx.remote.plexarAuth`
 * namespace, for the desktop app's Settings "Account" block (the Web client runs on the Host's
 * own origin and cannot invoke Tauri commands, so it reaches sign-out through this Remote
 * instead, the same pattern `update.ts`'s `plexarUpdate` uses for the sidebar update notice).
 *
 * Reads and deletes the same Windows Credential Manager entry (service "Plexar Harness", user
 * "default") that `cli/credentials.mjs` and the desktop Tauri shell's Rust keyring crate share.
 * The key-store and server-revoke logic is duplicated here in source, deliberately: `cli/credentials.mjs`
 * and `cli/auth.mjs` run as plain Node under the CLI's own launcher, while this module builds
 * through the package's `tsc`/typert pipeline, the same module-resolution split `update.ts`
 * documents for `cli/update.mjs`.
 * @module @plexar/dsh-plexar/auth-remote
 */

import { Context } from '@deepseek-ai/cordis'
import { Remote, TypertRemoteService } from '@deepseek-ai/dsh-typert-protocol'
import { Entry } from '@napi-rs/keyring'

/** Windows Credential Manager entry service/user pair, shared with `cli/credentials.mjs` and the desktop Rust keyring crate. */
const SERVICE = 'Plexar Harness'
const USER = 'default'

/** Rig base URL: `PLEXAR_RIG_URL`, else the shared rig (matching `cli/auth.mjs`'s `rigUrl()`). */
function rigUrl(): string {
  return process.env['PLEXAR_RIG_URL'] ?? 'https://llm.plexar.tech'
}

/** The `Entry` constructor used to reach the OS credential store; overridable in tests. */
export let entryFactory: (service: string, user: string) => Pick<Entry, 'getPassword' | 'deletePassword'> = (service, user) => new Entry(service, user)

/** Test-only seam: replace the `Entry` constructor, returning a restore function. */
export function _withEntryFactory(factory: typeof entryFactory): () => void {
  const previous = entryFactory
  entryFactory = factory
  return () => { entryFactory = previous }
}

/** The `fetch` used for `GET /api/harness/me` and `POST /api/harness/logout`; overridable in tests. */
export let fetchImpl: typeof fetch = fetch

/** Test-only seam: replace `fetchImpl`, returning a restore function. */
export function _withFetch(impl: typeof fetch): () => void {
  const previous = fetchImpl
  fetchImpl = impl
  return () => { fetchImpl = previous }
}

/** The key stored in the OS credential store, or undefined when there is none (a missing entry is not an error). */
function loadKeychainKey(): string | undefined {
  try {
    return entryFactory(SERVICE, USER).getPassword() ?? undefined
  } catch (error) {
    if (/no matching entry|no entry found/i.test(error instanceof Error ? error.message : String(error))) return undefined
    throw error
  }
}

/** Delete the stored key. A missing entry is not an error. */
function deleteKeychainKey(): void {
  try {
    entryFactory(SERVICE, USER).deletePassword()
  } catch (error) {
    if (/no matching entry|no entry found/i.test(error instanceof Error ? error.message : String(error))) return
    throw error
  }
}

/** Where the active key came from: the OS credential store, the `PLEXAR_HARNESS_KEY` developer override, or nowhere. */
export type KeySource = 'keychain' | 'env' | 'none'

/** The key to use and its source: the `PLEXAR_HARNESS_KEY` env override when set, else the OS credential store. */
function resolveKey(): { readonly key: string; readonly source: KeySource } {
  const envKey = process.env['PLEXAR_HARNESS_KEY']
  if (envKey !== undefined && envKey.length > 0) return { key: envKey, source: 'env' }
  const key = loadKeychainKey()
  return key !== undefined ? { key, source: 'keychain' } : { key: '', source: 'none' }
}

/** Sign-in status the Settings "Account" block renders. */
export interface AuthStatus {
  readonly signedIn: boolean
  readonly email?: string
  readonly source: KeySource
}

/** Result of a `signOut()` call. */
export type SignOutResult =
  | { readonly ok: true }
  | { readonly ok: false; readonly reason: 'env' }

/** `GET /api/harness/me`; returns the signed-in email, or undefined on any non-200 or network failure. */
async function fetchEmail(key: string): Promise<string | undefined> {
  try {
    const response = await fetchImpl(new URL('/api/harness/me', rigUrl()), { headers: { authorization: `Bearer ${key}` } })
    if (!response.ok) return undefined
    const body: unknown = await response.json()
    const email = typeof body === 'object' && body !== null ? (body as { email?: unknown }).email : undefined
    return typeof email === 'string' ? email : undefined
  } catch {
    return undefined
  }
}

/** `POST /api/harness/logout`; network errors are ignored, since the local key is deleted regardless. */
async function revokeKey(key: string): Promise<void> {
  try {
    await fetchImpl(new URL('/api/harness/logout', rigUrl()), { method: 'POST', headers: { authorization: `Bearer ${key}` } })
  } catch {
    // The rig may be unreachable; the key is still removed locally by the caller.
  }
}

/** Host exit code the desktop Tauri shell treats as "stop respawning, show the signed-out card" (`main.rs`, `SIGNOUT_EXIT_CODE`). */
const SIGNOUT_EXIT_CODE = 76

/**
 * Host service backing the generated `ctx.remote.plexarAuth` namespace: reports sign-in status
 * for the Settings "Account" block and signs the current computer out.
 */
export class PlexarAuth extends TypertRemoteService {
  static inject: string[] = []

  /** The key `email` was last resolved for, and its resolved value; avoids one `/me` call per `status()` poll. */
  private emailCache: { readonly key: string; readonly email: string | undefined } | undefined

  constructor(ctx: Context) {
    super(ctx, 'plexarAuth', { namespace: 'plexarAuth' })
  }

  /**
   * Read the current sign-in status: which key source is active and, when signed in, the
   * account email (cached for the process once resolved, since it never changes for a given key).
   * @returns signed-in state, source, and email when known.
   */
  @Remote
  async status(): Promise<AuthStatus> {
    const resolved = resolveKey()
    if (resolved.source === 'none') return { signedIn: false, source: 'none' }
    if (this.emailCache?.key !== resolved.key) {
      this.emailCache = { key: resolved.key, email: await fetchEmail(resolved.key) }
    }
    const email = this.emailCache.email
    return { signedIn: true, source: resolved.source, ...email === undefined ? {} : { email } }
  }

  /**
   * Sign out of Plexar on this computer: revoke the key server-side (best effort), then delete
   * it from the OS credential store. A key sourced from `PLEXAR_HARNESS_KEY` cannot be revoked
   * this way (the developer override is not stored anywhere this service can clear) and is left
   * untouched. When running under the desktop app, exits the Host shortly after replying so the
   * Tauri shell can stop respawning it and show the sign-in card.
   * @returns `{ok: true}` on success, or `{ok: false, reason: 'env'}` when the active key came
   *   from the env override and nothing was done.
   */
  @Remote
  async signOut(): Promise<SignOutResult> {
    const resolved = resolveKey()
    if (resolved.source === 'env') return { ok: false, reason: 'env' }
    if (resolved.source === 'keychain') await revokeKey(resolved.key)
    deleteKeychainKey()
    this.emailCache = undefined
    if (process.env['PLEXAR_DESKTOP'] === '1') {
      // Deferred so this reply reaches the client before the process exits.
      setTimeout(() => { process.exit(SIGNOUT_EXIT_CODE) }, 0)
    }
    return { ok: true }
  }
}

export default PlexarAuth
