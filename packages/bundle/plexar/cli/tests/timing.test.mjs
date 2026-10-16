// Startup phase line and per-turn status line (first token, output rate).
// Usage: node --test packages/bundle/plexar/cli/tests/timing.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { Renderer, formatStartup, formatTurnLine, outputRate } from '../render.mjs';

const plain = (s) => s.replace(/\x1b\[[0-9;]*m/g, '');

test('startup line names each phase in order', () => {
  assert.equal(
    formatStartup([{ name: 'sign-in', ms: 400 }, { name: 'harness', ms: 3100 }, { name: 'session', ms: 600 }]),
    'startup: sign-in 0.4s · harness 3.1s · session 0.6s',
  );
  assert.equal(formatStartup([]), '');
});

test('turn line carries ctx, elapsed, first token and rate', () => {
  const line = formatTurnLine({ used: 12300, size: 32000, elapsedMs: 8200, firstTokenMs: 1400, rate: 41.2 });
  assert.equal(line, '12.3k/32k ctx (38%) · 8.2s · first token 1.4s · 41 tok/s');
});

test('missing usage omits ctx and rate, never inventing one', () => {
  assert.equal(formatTurnLine({ used: 0, size: 0, elapsedMs: 2000, firstTokenMs: 500 }), '2.0s · first token 0.5s');
  assert.equal(outputRate(undefined, 1000), undefined);
  assert.equal(outputRate(0, 1000), undefined);
  assert.equal(outputRate(100, undefined), undefined);
  assert.equal(outputRate(100, 2000), 50);
});

test('renderer measures first token and rate from usage deltas', () => {
  let out = '';
  const r = new Renderer({ out: { write: (s) => { out += s; } } });
  r.update({ sessionUpdate: 'usage_update', used: 1000, size: 32000 });
  r.reset();
  r.promptAt = Date.now() - 5000;
  r.firstTokenAt = undefined;
  r.update({ sessionUpdate: 'agent_thought_chunk', content: { type: 'text', text: 'hm' } });
  r.firstTokenAt = r.promptAt + 1000;
  r.update({ sessionUpdate: 'usage_update', used: 1400, size: 32000 });
  out = '';
  r.endTurn('end_turn', 5000);
  assert.match(plain(out), /1\.0k\/32k ctx|1\.4k\/32k ctx/);
  assert.match(plain(out), /first token 1\.0s · 100 tok\/s/);
});

test('no usage update leaves the rate out; null statusOut drops the line', () => {
  let out = '';
  const r = new Renderer({ out: { write: (s) => { out += s; } } });
  r.update({ sessionUpdate: 'agent_message_chunk', content: { type: 'text', text: 'hi' } });
  out = '';
  r.endTurn('end_turn', 1000);
  assert.doesNotMatch(plain(out), /tok\/s/);
  assert.match(plain(out), /first token/);
  let err = '';
  const q = new Renderer({ out: { write: () => {} }, statusOut: null });
  q.endTurn('end_turn', 1);
  const s = new Renderer({ out: { write: () => {} }, statusOut: { write: (t) => { err += t; } } });
  s.endTurn('end_turn', 1000);
  assert.match(plain(err), /1\.0s/);
});
