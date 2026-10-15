// SignInState transitions (N74: sign-in happens inside the harness), with login, checkGate and the
// ACP host restart injected as fakes -- no browser, rig, or real host child.
// Usage: node --test packages/bundle/plexar/cli/tests/signin.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { NOTICE, SignInState } from '../tui/signin.mjs';

test('not-signed-in -> login ok -> signed-in, and the host is restarted with the new gate', async () => {
  const restarted = [];
  const state = new SignInState({
    loginFn: async () => ({ ok: true }),
    checkGateFn: async () => ({ ok: true, key: 'k1', models: [{ id: 'm' }] }),
    restartHostFn: async (gate) => { restarted.push(gate); },
  });
  await state.applyGate({ ok: false, message: 'Not signed in. Run: plexar-harness login' });
  assert.equal(state.status, 'signed-out');
  assert.equal(state.blocked, true);
  assert.equal(state.notice, NOTICE.signedOut);

  const result = await state.login();
  assert.deepEqual(result, { ok: true });
  assert.equal(state.status, 'signed-in');
  assert.equal(state.blocked, false);
  assert.deepEqual(restarted, [{ ok: true, key: 'k1', models: [{ id: 'm' }] }]);
});

test('login cancelled -> still signed-out, host never restarted', async () => {
  const restarted = [];
  const state = new SignInState({
    loginFn: async () => ({ ok: false }),
    checkGateFn: async () => ({ ok: true, key: 'k1' }),
    restartHostFn: async (gate) => { restarted.push(gate); },
  });
  await state.applyGate({ ok: false, message: 'Not signed in. Run: plexar-harness login' });
  const result = await state.login();
  assert.deepEqual(result, { ok: false });
  assert.equal(state.status, 'signed-out');
  assert.equal(state.blocked, true);
  assert.deepEqual(restarted, []);
});

test('entitled=false -> reason shown, prompts blocked, host never restarted', async () => {
  const restarted = [];
  const state = new SignInState({
    loginFn: async () => ({ ok: true }),
    checkGateFn: async () => ({ ok: false, message: 'Your Plexar access is paused.' }),
    restartHostFn: async (gate) => { restarted.push(gate); },
  });
  await state.applyGate({ ok: false, message: 'Not signed in. Run: plexar-harness login' });
  const result = await state.login();
  assert.deepEqual(result, { ok: false });
  assert.equal(state.status, 'entitled-false');
  assert.equal(state.blocked, true);
  assert.equal(state.notice, 'Your Plexar access is paused.');
  assert.deepEqual(restarted, []);
});

test('applyGate: a 401 reads as signed-out, not entitled-false', () => {
  const state = new SignInState({ loginFn: async () => ({ ok: true }), checkGateFn: async () => ({}), restartHostFn: async () => {} });
  state.applyGate({ ok: false, message: 'Please sign in again: plexar-harness login' });
  assert.equal(state.status, 'signed-out');
});

test('applyGate: ok clears a prior reason', () => {
  const state = new SignInState({ loginFn: async () => ({ ok: true }), checkGateFn: async () => ({}), restartHostFn: async () => {} });
  state.applyGate({ ok: false, message: 'Your Plexar access is paused.' });
  assert.equal(state.status, 'entitled-false');
  state.applyGate({ ok: true, key: 'k' });
  assert.equal(state.status, 'signed-in');
  assert.equal(state.reason, undefined);
  assert.equal(state.blocked, false);
});
