// Bring-your-own endpoint: the gate passes without the keyring or /me, a missing model fails
// naming PLEXAR_BYO_MODEL, and the ACP preflight probes the BYO /models URL.
// Usage: node --test packages/bundle/plexar/cli/tests/byo.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { checkGate } from '../auth.mjs';
import { readFileSync } from 'node:fs';
import { launchKey, preflight, preflightTarget } from '../acp-launch.mjs';
import { BYO_PLACEHOLDER_KEY, byoConfig } from '../credentials.mjs';

const VARS = ['PLEXAR_BYO_BASE_URL', 'PLEXAR_BYO_API_KEY', 'PLEXAR_BYO_MODEL'];

async function withEnv(values, fn) {
  const previous = Object.fromEntries(VARS.map(name => [name, process.env[name]]));
  for (const name of VARS) {
    if (values[name] === undefined) delete process.env[name];
    else process.env[name] = values[name];
  }
  try {
    await fn();
  } finally {
    for (const name of VARS) {
      if (previous[name] === undefined) delete process.env[name];
      else process.env[name] = previous[name];
    }
  }
}

const fail = () => { throw new Error('must not be called with BYO active'); };

test('checkGate: BYO passes with no keyring lookup and no /me call', async () => {
  await withEnv({ PLEXAR_BYO_BASE_URL: 'http://localhost:11434/v1', PLEXAR_BYO_API_KEY: 'k1', PLEXAR_BYO_MODEL: 'llama3' }, async () => {
    assert.deepEqual(await checkGate({ fetchMeFn: fail, resolveKeyFn: fail }), { ok: true, key: 'k1' });
  });
});

test('checkGate: BYO without a key supplies the placeholder and exports it', async () => {
  await withEnv({ PLEXAR_BYO_BASE_URL: 'http://localhost:11434/v1', PLEXAR_BYO_MODEL: 'llama3' }, async () => {
    const gate = await checkGate({ fetchMeFn: fail, resolveKeyFn: fail });
    assert.equal(gate.key, BYO_PLACEHOLDER_KEY);
    assert.equal(process.env.PLEXAR_BYO_API_KEY, BYO_PLACEHOLDER_KEY);
  });
});

test('checkGate: BYO without PLEXAR_BYO_MODEL fails naming the variable', async () => {
  await withEnv({ PLEXAR_BYO_BASE_URL: 'http://localhost:11434/v1' }, async () => {
    const gate = await checkGate({ fetchMeFn: fail, resolveKeyFn: fail });
    assert.equal(gate.ok, false);
    assert.match(gate.message, /PLEXAR_BYO_MODEL/);
    assert.throws(() => byoConfig(), /PLEXAR_BYO_MODEL/);
  });
});

test('byoConfig: off when PLEXAR_BYO_BASE_URL is unset', () => {
  assert.equal(byoConfig({ PLEXAR_BYO_MODEL: 'x' }), undefined);
});

test('preflightTarget: probes the BYO base /models, else the rig /v1/models', () => {
  assert.equal(preflightTarget({ PLEXAR_BYO_BASE_URL: 'http://localhost:11434/v1/', PLEXAR_BYO_MODEL: 'm' }).url, 'http://localhost:11434/v1/models');
  assert.equal(preflightTarget({ PLEXAR_RIG_URL: 'https://rig.example' }).url, 'https://rig.example/v1/models');
});

test('preflight: with BYO active and PLEXAR_HARNESS_KEY set, the BYO host receives only the BYO key', async () => {
  const realFetch = globalThis.fetch;
  const sent = [];
  globalThis.fetch = async (url, init) => { sent.push({ url, auth: init.headers.authorization }); return new Response('{}', { status: 200 }); };
  try {
    for (const [byoKey, expected] of [['byo-secret', 'byo-secret'], [undefined, BYO_PLACEHOLDER_KEY]]) {
      const env = { PLEXAR_HARNESS_KEY: 'plx_secret', PLEXAR_BYO_BASE_URL: 'http://byo.example/v1', PLEXAR_BYO_MODEL: 'm' };
      if (byoKey) env.PLEXAR_BYO_API_KEY = byoKey;
      const key = launchKey(env);
      assert.equal(key, expected);
      await preflight(key, env);
    }
  } finally {
    globalThis.fetch = realFetch;
  }
  assert.deepEqual(sent.map(s => s.auth), ['Bearer byo-secret', `Bearer ${BYO_PLACEHOLDER_KEY}`]);
  assert.ok(sent.every(s => s.url === 'http://byo.example/v1/models' && !s.auth.includes('plx_secret')));
  assert.equal(launchKey({ PLEXAR_HARNESS_KEY: 'plx_secret' }), 'plx_secret');
});

/** Evaluate the llm-pi-ai row's `providers: !!js` block from cordis.patch.yml against `env`. */
function patchProviders(env) {
  const lines = readFileSync(new URL('../../cordis.patch.yml', import.meta.url), 'utf8').split(/\r?\n/);
  const start = lines.findIndex(line => line.trim() === 'providers: !!js |-');
  assert.notEqual(start, -1, 'llm-pi-ai providers is a !!js block');
  const indent = lines[start].search(/\S/);
  const body = [];
  for (const line of lines.slice(start + 1)) {
    if (line.trim() !== '' && line.search(/\S/) <= indent) break;
    body.push(line);
  }
  return new Function('process', `return ${body.join('\n')}`)({ env, platform: process.platform });
}

test('cordis.patch.yml: the plexar provider exists only without a BYO endpoint', () => {
  assert.deepEqual(Object.keys(patchProviders({ PLEXAR_BYO_BASE_URL: 'http://byo.example/v1', PLEXAR_BYO_MODEL: 'm' })), ['byo']);
  const rig = patchProviders({ PLEXAR_RIG_URL: 'https://rig.example' });
  assert.deepEqual(Object.keys(rig), ['plexar', 'byo']);
  assert.equal(rig.plexar.baseURL, 'https://rig.example/v1');
  assert.equal(rig.plexar.apiKeyEnv, 'PLEXAR_HARNESS_KEY');
  assert.deepEqual(rig.plexar.models.map(m => m.id), ['Qwen/Qwen3.6-35B-A3B', 'prism-ml/Ternary-Bonsai-2-27B']);
});
