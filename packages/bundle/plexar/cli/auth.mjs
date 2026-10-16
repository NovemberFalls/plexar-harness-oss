/**
 * Plexar Harness sign-in: PKCE authorization-code flow against the Plexar rig
 * (`docs/plexar/07-studio-api-contract.md` §10p), the entitlement gate the launcher runs before
 * starting any Host, and `plexar-harness login` / `logout`.
 */
import { createHash, randomBytes } from 'node:crypto';
import { createServer } from 'node:http';
import { createInterface } from 'node:readline';
import { spawn } from 'node:child_process';
import { byoConfig, deleteKey, resolveKey, storeKey } from './credentials.mjs';

/** Rig base URL: `PLEXAR_RIG_URL`, else the shared rig. */
export function rigUrl() {
  return process.env.PLEXAR_RIG_URL ?? 'https://llm.plexar.tech';
}

/** Plain-language copy for a `me` `reason`, a 401, or a mid-session 403 revocation. */
export const REASON_COPY = {
  paused: 'Your Plexar access is paused.',
  grant_disabled: 'Your Plexar access has been turned off. Ask the Plexar owner.',
  product_not_granted: "Your account doesn't have Plexar Harness access yet. Ask the Plexar owner to enable it.",
  default: "Your account doesn't have Plexar Harness access yet. Ask the Plexar owner to enable it.",
};
/** Copy for a 401 from the rig (revoked or unknown key). */
export const UNAUTHORIZED_COPY = 'Please sign in again: plexar-harness login';
/** Copy for a mid-session `403 {error:{code:"product_not_granted"}}` on a `/v1/*` call. */
export const REVOKED_COPY = 'Plexar Harness access was revoked. Ask the Plexar owner.';

/** @returns {string} the user-facing copy for a `me` response's `reason` field. */
export function reasonCopy(reason) {
  return REASON_COPY[reason] ?? REASON_COPY.default;
}

/** @returns {{verifier: string, challenge: string}} an RFC 7636 S256 PKCE pair from 32 random bytes. */
export function pkcePair() {
  const verifier = base64url(randomBytes(32));
  const challenge = base64url(createHash('sha256').update(verifier).digest());
  return { verifier, challenge };
}

function base64url(buffer) {
  return buffer.toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

/** @returns {string} a random opaque state value for the authorize request. */
export function randomState() {
  return base64url(randomBytes(16));
}

/** The `authorize` URL for a redirect URI (a loopback callback or the literal `"oob"`). */
export function authorizeUrl({ redirectUri, state, challenge }) {
  const url = new URL('/api/harness/authorize', rigUrl());
  url.searchParams.set('redirect_uri', redirectUri);
  url.searchParams.set('state', state);
  url.searchParams.set('code_challenge', challenge);
  url.searchParams.set('code_challenge_method', 'S256');
  return url.href;
}

/** Exchange an authorization code for a key. @returns {Promise<{key: string, key_id: string, email: string, sub: string}>} */
export async function exchangeToken({ code, verifier, redirectUri }) {
  const response = await fetch(new URL('/api/harness/token', rigUrl()), {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ code, code_verifier: verifier, redirect_uri: redirectUri }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(tokenErrorMessage(response.status, body?.error?.code));
  }
  return response.json();
}

/**
 * The message for a failed token exchange.
 * @param {number} status HTTP status of `/api/harness/token`.
 * @param {string | undefined} code The body's `error.code`, when present.
 * @returns {string} what to tell the person, including the action to take.
 */
export function tokenErrorMessage(status, code) {
  if (status === 400) return 'Sign-in expired or was already used. Run plexar-harness login again.';
  if (status === 403 && code === 'paused') return 'Your Plexar Harness access is paused. Ask the Plexar owner.';
  if (status === 403) return "Your account doesn't have Plexar Harness access yet. Ask the Plexar owner to enable it.";
  if (status === 409) {
    return "You're signed in on 5 computers already. Run plexar-harness logout on one of them, or remove a key in the Plexar portal, then try again.";
  }
  if (status === 429) return 'Plexar is busy. Try again shortly.';
  return `Can't reach Plexar (HTTP ${status}). Try again shortly.`;
}

/** `GET /api/harness/me`. @returns {Promise<{status: number, body: object}>} the status and parsed body. */
export async function fetchMe(key) {
  const response = await fetch(new URL('/api/harness/me', rigUrl()), { headers: { authorization: `Bearer ${key}` } });
  const body = await response.json().catch(() => ({}));
  return { status: response.status, body };
}

/** `POST /api/harness/logout`; network errors are ignored, since the local key is deleted regardless. */
export async function revokeKey(key) {
  try {
    await fetch(new URL('/api/harness/logout', rigUrl()), { method: 'POST', headers: { authorization: `Bearer ${key}` } });
  } catch {
    // The rig may be unreachable; the key is still removed locally below.
  }
}

/** @returns {boolean} whether a parsed callback's `state` matches the state sent with the authorize request. */
export function stateMatches(callback, expectedState) {
  return callback.state === expectedState;
}

/** Parse a loopback callback request's query string into `{code, state}` or `{error, state}`. */
export function parseCallback(requestUrl) {
  const url = new URL(requestUrl, 'http://127.0.0.1');
  const error = url.searchParams.get('error');
  const state = url.searchParams.get('state');
  if (error) return { error, state };
  const code = url.searchParams.get('code');
  if (!code) return { error: 'missing_code', state };
  return { code, state };
}

const CALLBACK_PAGE = (ok, message) => `<!doctype html><html><head><meta charset="utf-8"><title>Plexar Harness</title>
<style>body{background:#1a1410;color:#f2e8dc;font-family:system-ui,sans-serif;display:flex;align-items:center;
justify-content:center;height:100vh;margin:0}main{text-align:center}h1{color:${ok ? '#ff8c3a' : '#e05a4e'};
font-size:1.4rem}p{color:#b8a99a}</style></head><body><main><h1>${ok ? 'Signed in' : 'Sign-in failed'}</h1>
<p>${message}</p><p>You can close this tab and return to the terminal.</p></main></body></html>`;

/**
 * A one-shot loopback listener on `127.0.0.1:0` for `/callback`: resolves with the first matching
 * request's query, answers the browser with a small HTML page, and times out after 5 minutes.
 * @returns {Promise<{port: number, result: Promise<{code: string, state: string} | {error: string, state: string}>, close: () => void}>}
 */
export function listenForCallback() {
  let resolveResult;
  let rejectResult;
  const result = new Promise((res, rej) => { resolveResult = res; rejectResult = rej; });
  const server = createServer((req, res) => {
    const url = new URL(req.url, 'http://127.0.0.1');
    if (url.pathname !== '/callback') {
      res.writeHead(404).end();
      return;
    }
    const parsed = parseCallback(req.url);
    const ok = !parsed.error;
    res.writeHead(200, { 'content-type': 'text/html' }).end(CALLBACK_PAGE(ok, ok ? 'Signing you in…' : parsed.error));
    clearTimeout(timer);
    server.close();
    resolveResult(parsed);
  });
  const timer = setTimeout(() => {
    server.close();
    rejectResult(new Error('sign-in timed out after 5 minutes'));
  }, 5 * 60 * 1000);
  timer.unref();
  const close = () => {
    clearTimeout(timer);
    server.close();
  };
  return new Promise((res) => {
    server.listen(0, '127.0.0.1', () => res({ port: server.address().port, result, close }));
  });
}

/**
 * The command that opens `url` in the default browser. Windows uses `rundll32
 * url.dll,FileProtocolHandler` with no shell: `cmd /c start` would split the URL at its first `&`.
 * @param {string} url
 * @param {string} [platform]
 * @returns {[string, string[]]}
 */
export function browserCommand(url, platform = process.platform) {
  return platform === 'win32'
    ? ['rundll32', ['url.dll,FileProtocolHandler', url]]
    : platform === 'darwin'
      ? ['open', [url]]
      : ['xdg-open', [url]];
}

/** Open `url` in the default browser (see `browserCommand`). */
export function openBrowser(url) {
  const [cmd, args] = browserCommand(url);
  spawn(cmd, args, { stdio: 'ignore', detached: true }).unref();
}

/** Resolve with `promise`, or reject with a `cancelled` error and close the listener if `signal` fires first. */
function raceAbort(promise, signal, close) {
  if (signal.aborted) {
    close();
    return Promise.reject(new Error('cancelled'));
  }
  return new Promise((resolve, reject) => {
    const onAbort = () => {
      close();
      reject(new Error('cancelled'));
    };
    signal.addEventListener('abort', onAbort, { once: true });
    promise.then(
      (value) => { signal.removeEventListener('abort', onAbort); resolve(value); },
      (error) => { signal.removeEventListener('abort', onAbort); reject(error); },
    );
  });
}

async function promptLine(question) {
  const rl = createInterface({ input: process.stdin, output: process.stdout });
  try {
    return await new Promise((resolve) => rl.question(question, resolve));
  } finally {
    rl.close();
  }
}

/**
 * `plexar-harness login`: PKCE sign-in, then `GET me` and a signed-in line.
 * @param {{noBrowser?: boolean, signal?: AbortSignal}} [options] `signal`, when given, cancels an
 *   in-progress loopback wait (browser flow only) and rejects with a `cancelled` error; the caller
 *   (the TUI's Esc-to-cancel) tells it apart from other failures by that message.
 * @returns {Promise<number>} process exit code.
 */
export async function login({ noBrowser = false, signal } = {}) {
  const { verifier, challenge } = pkcePair();
  const state = randomState();
  let code;
  let redirectUri;
  if (noBrowser) {
    redirectUri = 'oob';
    const url = authorizeUrl({ redirectUri, state, challenge });
    process.stdout.write(`Open this URL and sign in:\n\n  ${url}\n\n`);
    code = (await promptLine('Paste the code: ')).trim();
  } else {
    const { port, result, close } = await listenForCallback();
    redirectUri = `http://127.0.0.1:${port}/callback`;
    openBrowser(authorizeUrl({ redirectUri, state, challenge }));
    process.stdout.write('Opening your browser to sign in…\n');
    let callback;
    try {
      callback = signal ? await raceAbort(result, signal, close) : await result;
    } catch (error) {
      if (error.message === 'cancelled') {
        process.stderr.write('plexar-harness login: sign-in cancelled.\n');
        return 1;
      }
      throw error;
    }
    if (callback.error) {
      // access_denied: the person chose Deny on Plexar's consent page.
      const reason = callback.error === 'access_denied' ? 'sign-in was cancelled.' : callback.error;
      process.stderr.write(`plexar-harness login: ${reason}\n`);
      return 1;
    }
    if (!stateMatches(callback, state)) {
      process.stderr.write('plexar-harness login: state mismatch; aborting.\n');
      return 1;
    }
    code = callback.code;
  }
  let token;
  try {
    token = await exchangeToken({ code, verifier, redirectUri });
  } catch (error) {
    process.stderr.write(`plexar-harness login: ${error.message}\n`);
    return 1;
  }
  storeKey(token.key);
  const me = await fetchMe(token.key);
  const entitled = me.status === 200 && me.body.entitled;
  process.stdout.write(`Signed in as ${token.email}${entitled ? '' : `\n${reasonCopy(me.body.reason)}`}\n`);
  return 0;
}

/**
 * `plexar-harness logout`: revoke the stored key server-side (best effort) and delete it locally.
 * @returns {Promise<number>} process exit code.
 */
export async function logout() {
  const resolved = resolveKey();
  if (!resolved) {
    process.stdout.write('Signed out.\n');
    return 0;
  }
  if (resolved.source === 'env') {
    // Reached only when the credential store held no key, so PLEXAR_HARNESS_KEY was the fallback
    // that resolveKey() used; there is nothing stored to delete.
    process.stdout.write('Signed in via PLEXAR_HARNESS_KEY (no stored key); unset that variable to sign out.\n');
    return 0;
  }
  await revokeKey(resolved.key);
  deleteKey();
  process.stdout.write('Signed out.\n');
  return 0;
}

/**
 * The entitlement gate the launcher runs before starting any Host. With `PLEXAR_BYO_BASE_URL` set
 * it passes with the BYO key and makes no keyring lookup or `/me` call; it also sets
 * `PLEXAR_BYO_API_KEY` to the key it returns, so the `byo` provider's `apiKeyEnv` always resolves.
 * @param {{fetchMeFn?: typeof fetchMe, resolveKeyFn?: typeof resolveKey}} [deps] - injected for tests.
 * @returns {Promise<{ok: true, key: string, models?: object[], allModels?: object[]} | {ok: false, message: string, exitCode: number}>}
 *   `models` is the serving chat models only (for the provider's model list); `allModels` is the
 *   full, unfiltered `/me` models array (chat and classifier, serving and not), for the Models
 *   settings page. Both are present only when `/me` answered 200 with a `models` array.
 */
export async function checkGate({ fetchMeFn = fetchMe, resolveKeyFn = resolveKey } = {}) {
  let byo;
  try {
    byo = byoConfig();
  } catch (error) {
    return { ok: false, message: error.message, exitCode: 1 };
  }
  if (byo) {
    process.env.PLEXAR_BYO_API_KEY = byo.key;
    return { ok: true, key: byo.key };
  }
  const resolved = resolveKeyFn();
  if (!resolved) return { ok: false, message: 'Not signed in. Run: plexar-harness login', exitCode: 1 };
  let me;
  try {
    me = await fetchMeFn(resolved.key);
  } catch {
    return { ok: true, key: resolved.key, warning: "Can't reach Plexar; starting offline." };
  }
  if (me.status === 401) return { ok: false, message: UNAUTHORIZED_COPY, exitCode: 1 };
  // Only a definite answer blocks: any other status (a gateway without these routes, a 5xx) is
  // treated like being offline, so an outage on plexar-llm never locks people out.
  if (me.status !== 200) return { ok: true, key: resolved.key, warning: "Can't check Plexar access right now; starting anyway." };
  if (!me.body.entitled) return { ok: false, message: reasonCopy(me.body.reason), exitCode: 1 };
  // Serving chat models only; classifiers are not chat models and stay out of the pickers.
  const models = Array.isArray(me.body.models) ? me.body.models.filter(m => m.kind === 'chat' && m.serving === true) : undefined;
  // The full, unfiltered /me models array (chat and classifier, serving and not), for the Models
  // settings page; distinct from `models` above, which is the chat-picker's narrower slice.
  const allModels = Array.isArray(me.body.models) ? me.body.models : undefined;
  return {
    ok: true,
    key: resolved.key,
    ...models === undefined ? {} : { models },
    ...allModels === undefined ? {} : { allModels },
  };
}

/** Commands that skip the entitlement gate. */
export const GATE_EXEMPT_COMMANDS = new Set(['login', 'logout', 'update']);
