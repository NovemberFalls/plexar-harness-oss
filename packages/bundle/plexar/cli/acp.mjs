/**
 * ACP client for the `plexar-acp` profile: JSON-RPC 2.0, one frame per line, over the child's stdio.
 * The wire matches `studio/plexar_harness_client.py` (contract v2, docs/plexar/07-studio-api-contract.md).
 */
import { spawn } from 'node:child_process';
import { EventEmitter } from 'node:events';
import { existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

export const PROTOCOL_VERSION = 1;

/** Harness checkout that runs the profile: `PLEXAR_HARNESS_ROOT`, else the checkout this file lives in. */
export function harnessRoot() {
  return process.env.PLEXAR_HARNESS_ROOT ?? resolve(dirname(fileURLToPath(import.meta.url)), '../../../..');
}

/**
 * Node arguments and env that start the `dsh` CLI of `root`: the built `apps/cli/lib/bin.js` under
 * plain Node when it exists (the installed runtime, or a checkout after `pnpm run build`, which
 * `plexar-harness update` runs), else the source entry under the checkout's tsx loader, which
 * compiles every loaded package on each start. `PLEXAR_HARNESS_SOURCE=1` forces the source entry.
 * @param {string} root - harness checkout or installed runtime, from {@link harnessRoot}.
 * @returns {{args: string[], env: Record<string, string>}} arguments before the dsh arguments, and env additions.
 */
export function dshEntry(root) {
  const source = join(root, 'apps/cli/src/bin.ts');
  const built = join(root, 'apps/cli/lib/bin.js');
  if (!existsSync(source) || (existsSync(built) && process.env.PLEXAR_HARNESS_SOURCE !== '1')) {
    return { args: [built], env: {} };
  }
  const loader = pathToFileURL(join(root, 'node_modules/tsx/dist/esm/index.mjs')).href;
  return { args: ['--import', loader, source], env: { TSX_TSCONFIG_PATH: join(root, 'tsconfig.json') } };
}

/**
 * One harness process for one workspace.
 * Events: `update` (sessionId, update), `permission` (params, reply(optionId|null)), `exit` (code).
 */
/**
 * One line for a JSON-RPC error. The ACP SDK answers a plain thrown error with the bare message
 * "Internal error" and puts the cause in `data.details`, so the details are appended.
 * @param {string} method - the request's method, prefixed to the line.
 * @param {{message?: string, data?: {details?: unknown}}} error - the response's `error` member.
 * @returns {string}
 */
export function rpcErrorMessage(method, error) {
  const message = error.message ?? JSON.stringify(error);
  const details = typeof error.data?.details === 'string' ? error.data.details : undefined;
  return details && !message.includes(details) ? `${method}: ${message}: ${details}` : `${method}: ${message}`;
}

export class HarnessRuntime extends EventEmitter {
  /**
   * @param {{workspace: string, profile?: string, env?: Record<string,string>}} options
   */
  constructor({ workspace, profile = 'plexar-acp', env = {} }) {
    super();
    this.workspace = resolve(workspace);
    this.profile = profile;
    this.env = env;
    this.nextId = 1;
    this.pending = new Map();
    this.stderrTail = [];
    this.child = null;
  }

  /** Spawn the profile and run `initialize`. @returns {Promise<object>} the agent's initialize result */
  async start() {
    const entry = dshEntry(harnessRoot());
    this.child = spawn(process.execPath, [...entry.args, '--profile', this.profile], {
      cwd: this.workspace,
      env: { ...process.env, ...entry.env, ...this.env },
      stdio: ['pipe', 'pipe', 'pipe'],
      windowsHide: true,
    });
    let buffer = '';
    this.child.stdout.setEncoding('utf8');
    this.child.stdout.on('data', (chunk) => {
      buffer += chunk;
      let nl;
      while ((nl = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, nl).trim();
        buffer = buffer.slice(nl + 1);
        if (line) this.#onLine(line);
      }
    });
    this.child.stderr.setEncoding('utf8');
    this.child.stderr.on('data', (chunk) => {
      this.stderrTail = [...this.stderrTail, ...chunk.split(/\r?\n/).filter(Boolean)].slice(-50);
    });
    this.child.on('exit', (code) => {
      for (const { reject } of this.pending.values()) reject(new Error(`harness exited (${code}): ${this.stderrTail.slice(-5).join(' | ')}`));
      this.pending.clear();
      this.emit('exit', code);
    });
    return this.request('initialize', {
      protocolVersion: PROTOCOL_VERSION,
      clientCapabilities: { fs: { readTextFile: false, writeTextFile: false }, terminal: false },
    });
  }

  /** Close stdin and wait for the child to exit; sessions stay on disk. */
  async stop() {
    if (!this.child || this.child.exitCode !== null) return;
    const exited = new Promise((r) => this.child.once('exit', r));
    this.child.stdin.end();
    const timer = setTimeout(() => this.child.kill(), 15000);
    await exited;
    clearTimeout(timer);
  }

  /** @returns {Promise<{sessionId: string, configOptions: object[]}>} */
  newSession() {
    return this.request('session/new', { cwd: this.workspace, mcpServers: [] });
  }

  /** @returns {Promise<{sessions: {sessionId: string, cwd: string}[], nextCursor?: string}>} newest first */
  listSessions() {
    return this.request('session/list', { cwd: this.workspace });
  }

  /** @returns {Promise<{configOptions?: object[]}>} */
  resumeSession(sessionId) {
    return this.request('session/resume', { sessionId, cwd: this.workspace, mcpServers: [] });
  }

  /** @returns {Promise<{configOptions?: object[]}>} the updated options */
  setOption(sessionId, configId, value) {
    return this.request('session/set_config_option', { sessionId, configId, value });
  }

  /** Run one turn to completion. @returns {Promise<{stopReason: string}>} */
  prompt(sessionId, text) {
    return this.request('session/prompt', { sessionId, prompt: [{ type: 'text', text }] });
  }

  /** Stop the turn in flight; its `prompt()` resolves with stopReason `cancelled`. */
  cancel(sessionId) {
    this.#send({ jsonrpc: '2.0', method: 'session/cancel', params: { sessionId } });
  }

  /** @returns {Promise<object>} */
  closeSession(sessionId) {
    return this.request('session/close', { sessionId });
  }

  /** Send one request and resolve with its result; a JSON-RPC error rejects. */
  request(method, params) {
    const id = this.nextId++;
    return new Promise((resolvePromise, reject) => {
      this.pending.set(id, { resolve: resolvePromise, reject, method });
      this.#send({ jsonrpc: '2.0', id, method, params });
    });
  }

  #send(frame) {
    this.child.stdin.write(`${JSON.stringify(frame)}\n`);
  }

  #onLine(line) {
    let msg;
    try {
      msg = JSON.parse(line);
    } catch (error) {
      // A non-JSON stdout line is harness log noise, never a frame; keep it for diagnostics.
      this.stderrTail.push(`[stdout] ${line.slice(0, 200)} (${error.message})`);
      return;
    }
    if (msg.id !== undefined && !msg.method) {
      const waiter = this.pending.get(msg.id);
      if (!waiter) return;
      this.pending.delete(msg.id);
      if (msg.error) waiter.reject(new Error(rpcErrorMessage(waiter.method, msg.error)));
      else waiter.resolve(msg.result);
    } else if (msg.method === 'session/update') {
      this.emit('update', msg.params?.sessionId, msg.params?.update ?? {});
    } else if (msg.method === 'session/request_permission') {
      let answered = false;
      const reply = (optionId) => {
        if (answered) return;
        answered = true;
        const outcome = optionId ? { outcome: 'selected', optionId } : { outcome: 'cancelled' };
        this.#send({ jsonrpc: '2.0', id: msg.id, result: { outcome } });
      };
      if (this.listenerCount('permission') === 0) reply(null);
      else this.emit('permission', msg.params ?? {}, reply);
    } else if (msg.id !== undefined && msg.method) {
      this.#send({ jsonrpc: '2.0', id: msg.id, error: { code: -32601, message: `unsupported: ${msg.method}` } });
    }
  }
}
