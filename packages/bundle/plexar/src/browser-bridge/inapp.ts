/**
 * The in-app browser route: the Plexar desktop shell hosts native browser panes and exposes their Chrome DevTools
 * Protocol endpoint on loopback. The Host asks the shell for a pane with one line on its stdout, waits until the
 * endpoint lists a page, and attaches Playwright to it.
 * @module @plexar/dsh-plexar/browser-bridge/inapp
 */

/** Environment variable the desktop shell sets on the Host child to the pane CDP endpoint. */
export const INAPP_CDP_ENV = 'PLEXAR_INAPP_BROWSER_CDP'

/** Prefix of every line the Host writes to the shell on its stdout. */
export const SHELL_LINE_PREFIX = 'plexar shell: '

/** Feature id in the `plexar-feature-toggles` `off` setting that turns the in-app route off. */
export const IN_APP_BROWSER_FEATURE = 'inAppBrowser'

/** Milliseconds between two readiness polls. */
const POLL_INTERVAL_MS = 250

/**
 * The endpoint from the environment.
 * @param env - the Host's environment.
 * @returns the value of `PLEXAR_INAPP_BROWSER_CDP` when it is exactly `http://127.0.0.1:<1-65535>`, else undefined.
 */
export function inAppEndpoint(env: NodeJS.ProcessEnv): string | undefined {
  const value = env[INAPP_CDP_ENV]
  if (value === undefined) return undefined
  const match = /^http:\/\/127\.0\.0\.1:([1-9]\d{0,4})$/u.exec(value)
  return match !== null && Number(match[1]) <= 65535 ? value : undefined
}

/** One shell line: the prefix, a single-line JSON object with `op` before `session`, and a newline. */
function shellLine(op: 'browser.ensure' | 'browser.release', session: string): string {
  return `${SHELL_LINE_PREFIX}${JSON.stringify({ op, session })}\n`
}

/** Whether a `/json/list` body is an array with at least one `page` target. */
function hasPage(body: unknown): boolean {
  return Array.isArray(body) && body.some(entry => typeof entry === 'object' && entry !== null && (entry as { type?: unknown }).type === 'page')
}

/** `fetch` of a JSON body; a non-2xx response is an error. */
async function defaultFetchJson(url: string, signal: AbortSignal): Promise<unknown> {
  const response = await fetch(url, { signal })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.json()
}

/**
 * Ask the shell for a pane and wait until it is ready.
 * @param options.endpoint - the shell's CDP endpoint, as returned by {@link inAppEndpoint}.
 * @param options.session - the id the shell keys the pane by; non-empty, at most 128 characters.
 * @param options.timeoutMs - how long to wait for a page.
 * @param options.signal - aborts the wait; the abort reason is rethrown after the pane is released.
 * @param options.write - writes one line to the shell.
 * @param options.fetchJson - reads a JSON body; replaced in tests.
 * @param options.intervalMs - milliseconds between polls; default 250.
 * @returns the endpoint and a `close` that releases the pane, or undefined after a timeout (already released).
 *   `browser.release` is written at most once across timeout, abort and `close()`.
 */
export async function attachInApp(options: {
  endpoint: string
  session: string
  timeoutMs: number
  signal: AbortSignal
  write: (line: string) => void
  fetchJson?: (url: string, signal: AbortSignal) => Promise<unknown>
  intervalMs?: number
}): Promise<{ endpoint: string; close: () => void } | undefined> {
  const { endpoint, session, signal, write } = options
  const fetchJson = options.fetchJson ?? defaultFetchJson
  const intervalMs = options.intervalMs ?? POLL_INTERVAL_MS
  signal.throwIfAborted()
  let released = false
  const release = (): void => {
    if (released) return
    released = true
    write(shellLine('browser.release', session))
  }
  write(shellLine('browser.ensure', session))

  const stop = new AbortController()
  const timer = setTimeout(() => { stop.abort() }, options.timeoutMs)
  const onAbort = (): void => { stop.abort() }
  signal.addEventListener('abort', onAbort, { once: true })
  let sleepTimer: ReturnType<typeof setTimeout> | undefined
  let wake: () => void = () => {}
  const stopped = new Promise<void>((resolve) => { stop.signal.addEventListener('abort', () => { resolve() }, { once: true }) })
  const sleep = (): Promise<void> => new Promise<void>((resolve) => {
    wake = resolve
    if (stop.signal.aborted) { resolve(); return }
    sleepTimer = setTimeout(resolve, intervalMs)
  })
  stop.signal.addEventListener('abort', () => { clearTimeout(sleepTimer); wake() }, { once: true })
  try {
    let ready = false
    while (!stop.signal.aborted && !ready) {
      try {
        ready = hasPage(await Promise.race([fetchJson(`${endpoint}/json/list`, stop.signal), stopped.then(() => undefined)]))
      } catch {
        // The shell has not opened the port yet, or the response was not JSON: poll again.
      }
      if (!ready) await sleep()
    }
    if (ready && !signal.aborted) return { endpoint, close: release }
  } finally {
    clearTimeout(timer)
    clearTimeout(sleepTimer)
    signal.removeEventListener('abort', onAbort)
  }
  release()
  if (signal.aborted) throw signal.reason
  return undefined
}
