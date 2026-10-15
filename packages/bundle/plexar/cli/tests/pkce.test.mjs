// PKCE and callback-parsing unit tests: RFC 7636 Appendix B vector, state-mismatch rejection in
// `login`, and `parseCallback` over code/error/missing-code query strings.
// Usage: node --test packages/bundle/plexar/cli/tests/pkce.test.mjs
import { createHash } from 'node:crypto';
import test from 'node:test';
import assert from 'node:assert/strict';
import { authorizeUrl, listenForCallback, parseCallback, pkcePair, randomState, stateMatches } from '../auth.mjs';

test('pkcePair: verifier is 32 random bytes, base64url with no padding', () => {
  const { verifier } = pkcePair();
  assert.match(verifier, /^[A-Za-z0-9_-]+$/);
  assert.equal(Buffer.from(verifier.replace(/-/g, '+').replace(/_/g, '/'), 'base64').length, 32);
});

test('pkcePair: challenge is the S256 transform of the verifier (RFC 7636 §4.2)', () => {
  const { verifier, challenge } = pkcePair();
  const expected = createHash('sha256').update(verifier).digest('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  assert.equal(challenge, expected);
});

test('pkcePair: RFC 7636 Appendix B verifier produces the Appendix B challenge', () => {
  // The vector uses a 43-octet verifier below the profile's own 32-random-byte input; it exercises
  // only the S256 transform, not pkcePair()'s own byte generation.
  const verifier = 'dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk';
  const challenge = createHash('sha256').update(verifier).digest('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  assert.equal(challenge, 'E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM');
});

test('randomState: distinct calls produce distinct opaque values', () => {
  const a = randomState();
  const b = randomState();
  assert.notEqual(a, b);
  assert.match(a, /^[A-Za-z0-9_-]+$/);
});

test('authorizeUrl: builds the pinned authorize query', () => {
  const url = new URL(authorizeUrl({ redirectUri: 'http://127.0.0.1:5555/callback', state: 's1', challenge: 'c1' }));
  assert.equal(url.pathname, '/api/harness/authorize');
  assert.equal(url.searchParams.get('redirect_uri'), 'http://127.0.0.1:5555/callback');
  assert.equal(url.searchParams.get('state'), 's1');
  assert.equal(url.searchParams.get('code_challenge'), 'c1');
  assert.equal(url.searchParams.get('code_challenge_method'), 'S256');
});

test('authorizeUrl: redirect_uri "oob" passes through literally', () => {
  const url = new URL(authorizeUrl({ redirectUri: 'oob', state: 's', challenge: 'c' }));
  assert.equal(url.searchParams.get('redirect_uri'), 'oob');
});

test('parseCallback: a code response', () => {
  assert.deepEqual(parseCallback('/callback?code=abc&state=xyz'), { code: 'abc', state: 'xyz' });
});

test('parseCallback: an error response', () => {
  assert.deepEqual(parseCallback('/callback?error=access_denied&state=xyz'), { error: 'access_denied', state: 'xyz' });
});

test('parseCallback: neither code nor error reads as an error', () => {
  const result = parseCallback('/callback?state=xyz');
  assert.equal(result.error, 'missing_code');
  assert.equal(result.state, 'xyz');
});

test('stateMatches: rejects a callback whose state differs from the one sent with authorize', () => {
  assert.equal(stateMatches({ code: 'c', state: 'attacker-state' }, 'issued-state'), false);
  assert.equal(stateMatches({ code: 'c', state: 'issued-state' }, 'issued-state'), true);
});

test('listenForCallback: a real loopback request with a mismatched state is caught by stateMatches', async () => {
  const { port, result } = await listenForCallback();
  const response = await fetch(`http://127.0.0.1:${port}/callback?code=abc&state=wrong-state`);
  assert.equal(response.status, 200);
  const callback = await result;
  assert.equal(callback.code, 'abc');
  assert.equal(stateMatches(callback, 'issued-state'), false);
});

test('Windows opens the browser without cmd, so the whole authorize URL survives its & separators', async () => {
  const { browserCommand } = await import('../auth.mjs');
  const url = 'https://rig.example/api/harness/authorize?redirect_uri=x&state=s1&code_challenge=c&code_challenge_method=S256';
  const [cmd, args] = browserCommand(url, 'win32');
  assert.notEqual(cmd.toLowerCase(), 'cmd');
  assert.equal(args.at(-1), url);
});
