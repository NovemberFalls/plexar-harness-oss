// Regression for the live-check failure of 2026-09-25: with no key, the signed-out start path was
// still calling `session/new` on the ACP host (which has no key, so it answered "Internal error")
// before the sign-in notice ever showed. Drives `App` directly with a fake ACP client (no real
// subprocess) and asserts `session/new` is not called while blocked, and is called once `/login`
// (faked) succeeds.
// Usage: node --test packages/bundle/plexar/cli/tests/tui-session-gate.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { App } from '../plexar-harness.mjs';

/** A fake `HarnessRuntime`: same events/methods `App` calls, no child process. */
class FakeRuntime extends EventEmitter {
  constructor({ workspace }) {
    super();
    this.workspace = workspace;
    this.calls = [];
  }
  async start() { return { configOptions: [] }; }
  async newSession() {
    this.calls.push('newSession');
    return { sessionId: 'sess-1', configOptions: [] };
  }
  async resumeSession(id) {
    this.calls.push(`resumeSession:${id}`);
    return { configOptions: [] };
  }
  async listSessions() { return { sessions: [] }; }
  async setOption() { return { configOptions: [] }; }
  async prompt() { return { stopReason: 'end_turn' }; }
  cancel() {}
  async stop() {}
}

function makeApp({ checkGateResults, loginResult = { ok: true } }) {
  const created = [];
  let checkGateCall = 0;
  const app = new App(
    { print: false },
    {
      runtimeFactory: (opts) => {
        const runtime = new FakeRuntime(opts);
        created.push(runtime);
        return runtime;
      },
      checkGateFn: async () => checkGateResults[Math.min(checkGateCall++, checkGateResults.length - 1)],
      loginFn: async () => loginResult,
    },
  );
  return { app, created };
}

test('signed-out start: session/new is not called before login, and is called once login succeeds', async () => {
  const notSignedIn = { ok: false, message: 'Not signed in. Run: plexar-harness login', exitCode: 1 };
  const signedIn = { ok: true, key: 'k1' };
  const { app, created } = makeApp({ checkGateResults: [notSignedIn, signedIn] });

  await app.startRuntime();
  await app.ensureSignedIn();
  await app.startSession();

  assert.equal(app.signIn.blocked, true);
  assert.equal(app.sessionId, null);
  assert.deepEqual(created[0].calls, [], 'session/new must not run while signed out');

  const result = await app.signIn.login();

  assert.deepEqual(result, { ok: true });
  assert.equal(app.signIn.blocked, false);
  assert.equal(app.sessionId, 'sess-1');
  // `login()`'s `restartHostFn` (`App#onSignedIn`) stops the old runtime and starts a fresh one,
  // which is the one that should have created the session.
  const latest = created.at(-1);
  assert.ok(latest.calls.includes('newSession'), `expected newSession on the restarted runtime; calls: ${JSON.stringify(latest.calls)}`);
});

test('login cancelled: session/new is still never called', async () => {
  const notSignedIn = { ok: false, message: 'Not signed in. Run: plexar-harness login', exitCode: 1 };
  const { app, created } = makeApp({ checkGateResults: [notSignedIn], loginResult: { ok: false } });

  await app.startRuntime();
  await app.ensureSignedIn();
  await app.startSession();
  const result = await app.signIn.login();

  assert.deepEqual(result, { ok: false });
  assert.equal(app.signIn.blocked, true);
  assert.equal(app.sessionId, null);
  for (const runtime of created) assert.deepEqual(runtime.calls, []);
});

test('already signed in: session/new runs immediately, no login needed', async () => {
  const signedIn = { ok: true, key: 'k1' };
  const { app, created } = makeApp({ checkGateResults: [signedIn] });

  await app.startRuntime();
  await app.ensureSignedIn();
  await app.startSession();

  assert.equal(app.signIn.blocked, false);
  assert.equal(app.sessionId, 'sess-1');
  assert.ok(created[0].calls.includes('newSession'));
});
