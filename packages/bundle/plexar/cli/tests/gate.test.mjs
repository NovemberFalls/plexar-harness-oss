// Entitlement-gate decisions against a local mock HTTP server standing in for the rig's `/me`
// endpoint: 401, entitled=false per `reason`, entitled, and a network failure.
// Usage: node --test packages/bundle/plexar/cli/tests/gate.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { checkGate, fetchMe, reasonCopy, REASON_COPY, tokenErrorMessage, UNAUTHORIZED_COPY } from '../auth.mjs';
import { createServer } from 'node:http';

/** A local HTTP server answering `GET /api/harness/me` with a fixed status/body; closed by the caller. */
function meServer(status, body) {
  return new Promise((resolve) => {
    const server = createServer((req, res) => {
      res.writeHead(status, { 'content-type': 'application/json' }).end(JSON.stringify(body));
    });
    server.listen(0, '127.0.0.1', () => resolve(server));
  });
}

async function withServer(status, body, fn) {
  const server = await meServer(status, body);
  const port = server.address().port;
  const previous = process.env.PLEXAR_RIG_URL;
  process.env.PLEXAR_RIG_URL = `http://127.0.0.1:${port}`;
  try {
    await fn();
  } finally {
    if (previous === undefined) delete process.env.PLEXAR_RIG_URL;
    else process.env.PLEXAR_RIG_URL = previous;
    await new Promise((resolve) => server.close(resolve));
  }
}

test('fetchMe: reads status and JSON body from the pinned /api/harness/me route', async () => {
  await withServer(200, { email: 'a@b.com', entitled: true }, async () => {
    const me = await fetchMe('some-key');
    assert.equal(me.status, 200);
    assert.equal(me.body.email, 'a@b.com');
  });
});

test('checkGate: no key resolves -> not-signed-in message, exit 1', async () => {
  const result = await checkGate({ resolveKeyFn: () => undefined });
  assert.deepEqual(result, { ok: false, message: 'Not signed in. Run: plexar-harness login', exitCode: 1 });
});

test('checkGate: 401 -> the pinned unauthorized copy, exit 1', async () => {
  const result = await checkGate({
    resolveKeyFn: () => ({ key: 'k', source: 'keyring' }),
    fetchMeFn: async () => ({ status: 401, body: {} }),
  });
  assert.deepEqual(result, { ok: false, message: UNAUTHORIZED_COPY, exitCode: 1 });
});

for (const [reason, message] of Object.entries(REASON_COPY)) {
  test(`checkGate: entitled=false reason=${reason} -> its copy, exit 1`, async () => {
    const result = await checkGate({
      resolveKeyFn: () => ({ key: 'k', source: 'keyring' }),
      fetchMeFn: async () => ({ status: 200, body: { entitled: false, reason: reason === 'default' ? 'something_unlisted' : reason } }),
    });
    assert.deepEqual(result, { ok: false, message, exitCode: 1 });
  });
}

test('checkGate: entitled -> ok with the resolved key, set in the child env by the caller', async () => {
  const result = await checkGate({
    resolveKeyFn: () => ({ key: 'the-key', source: 'keyring' }),
    fetchMeFn: async () => ({ status: 200, body: { entitled: true, email: 'a@b.com' } }),
  });
  assert.deepEqual(result, { ok: true, key: 'the-key' });
});

test('checkGate: network failure -> warns and continues offline rather than blocking', async () => {
  const result = await checkGate({
    resolveKeyFn: () => ({ key: 'the-key', source: 'keyring' }),
    fetchMeFn: async () => { throw new Error('ECONNREFUSED'); },
  });
  assert.equal(result.ok, true);
  assert.equal(result.key, 'the-key');
  assert.equal(result.warning, "Can't reach Plexar; starting offline.");
});

test('checkGate: a status other than 200/401 (e.g. 404 before deployment) starts with a warning', async () => {
  const result = await checkGate({
    resolveKeyFn: () => ({ key: 'the-key', source: 'keyring' }),
    fetchMeFn: async () => ({ status: 404, body: {} }),
  });
  assert.deepEqual(result, { ok: true, key: 'the-key', warning: "Can't check Plexar access right now; starting anyway." });
});

test('checkGate: entitled passes on only serving chat models', async () => {
  const models = [
    { id: 'chat-up', kind: 'chat', serving: true },
    { id: 'chat-down', kind: 'chat', serving: false },
    { id: 'signal', kind: 'classifier', serving: true },
  ]
  const result = await checkGate({
    resolveKeyFn: () => ({ key: 'the-key', source: 'keyring' }),
    fetchMeFn: async () => ({ status: 200, body: { entitled: true, reason: null, models } }),
  });
  assert.deepEqual(result.models, [models[0]]);
});

test('checkGate: entitled also passes the full, unfiltered models array as allModels', async () => {
  const models = [
    { id: 'chat-up', kind: 'chat', serving: true },
    { id: 'chat-down', kind: 'chat', serving: false },
    { id: 'signal', kind: 'classifier', serving: true },
  ]
  const result = await checkGate({
    resolveKeyFn: () => ({ key: 'the-key', source: 'keyring' }),
    fetchMeFn: async () => ({ status: 200, body: { entitled: true, reason: null, models } }),
  });
  assert.deepEqual(result.allModels, models);
});

test('checkGate: entitled with no models field on the body sets neither models nor allModels', async () => {
  const result = await checkGate({
    resolveKeyFn: () => ({ key: 'the-key', source: 'keyring' }),
    fetchMeFn: async () => ({ status: 200, body: { entitled: true, email: 'a@b.com' } }),
  });
  assert.deepEqual(result, { ok: true, key: 'the-key' });
});

test('tokenErrorMessage: paused, key cap, rate limit and expired codes get their own messages', () => {
  assert.match(tokenErrorMessage(403, 'paused'), /paused/);
  assert.match(tokenErrorMessage(409, 'too_many_harness_keys'), /5 computers/);
  assert.match(tokenErrorMessage(429, undefined), /busy/);
  assert.match(tokenErrorMessage(400, 'invalid_grant'), /expired/);
  assert.match(tokenErrorMessage(502, undefined), /Can't reach Plexar/);
});

test('reasonCopy: an unlisted reason falls back to the product_not_granted copy', () => {
  assert.equal(reasonCopy('some_future_reason'), REASON_COPY.product_not_granted);
  assert.equal(reasonCopy(null), REASON_COPY.product_not_granted);
});
