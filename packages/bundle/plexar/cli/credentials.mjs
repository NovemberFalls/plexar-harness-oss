/**
 * The Plexar key store: the OS credential store entry service "Plexar Harness", user "default",
 * shared with the desktop app's Rust keyring crate (same service/user pair), plus the developer
 * env override. Never logs or otherwise persists the raw key outside this entry.
 */
import { Entry } from '@napi-rs/keyring';

const SERVICE = 'Plexar Harness';
const USER = 'default';

/** The `Entry` constructor used to reach the OS credential store; overridable in tests. */
export let entryFactory = (service, user) => new Entry(service, user);

/** Test-only seam: replace the `Entry` constructor, returning a restore function. */
export function _withEntryFactory(factory) {
  const previous = entryFactory;
  entryFactory = factory;
  return () => { entryFactory = previous; };
}

function entry() {
  return entryFactory(SERVICE, USER);
}

/** Store `key` in the OS credential store, replacing any prior value. */
export function storeKey(key) {
  entry().setPassword(key);
}

/** @returns {string | undefined} the key in the OS credential store, or undefined when there is none. */
export function loadKey() {
  try {
    return entry().getPassword();
  } catch (error) {
    // No entry yet, or the platform store is unavailable: both read as signed-out.
    if (/no matching entry|no entry found/i.test(error.message ?? '')) return undefined;
    throw error;
  }
}

/** Remove the stored key. A missing entry is not an error. */
export function deleteKey() {
  try {
    entry().deletePassword();
  } catch (error) {
    if (/no matching entry|no entry found/i.test(error.message ?? '')) return;
    throw error;
  }
}

/**
 * The key to use: the OS credential store first, falling back to the `PLEXAR_HARNESS_KEY` env
 * override only when the store holds no key. A real sign-in through the OS store always wins, so
 * a stale shared `PLEXAR_HARNESS_KEY` (e.g. a revoked developer key) never shadows it.
 * @returns {{key: string, source: 'env' | 'keyring'} | undefined}
 */
export function resolveKey() {
  const key = loadKey();
  if (key) return { key, source: 'keyring' };
  return process.env.PLEXAR_HARNESS_KEY ? { key: process.env.PLEXAR_HARNESS_KEY, source: 'env' } : undefined;
}
