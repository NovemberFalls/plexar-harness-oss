// Update checks and `plexar-harness update` for an installed copy (no .git): manifest-based
// notice via a loopback HTTP server standing in for the release manifest, and `runUpdate`'s
// guidance instead of git/pnpm. The checkout path is exercised against this repo's own checkout
// (unchanged git behavior) and covered separately by tests/update.spec.ts's mocked git.
// Usage: node --test packages/bundle/plexar/cli/tests/update.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { compareSemver, runUpdate, updateNotice } from '../update.mjs';

/** A local HTTP server answering `GET /latest.json` with a fixed status/body; closed by the caller. */
function manifestServer(status, body) {
  return new Promise((resolve) => {
    const server = createServer((req, res) => {
      if (body === undefined) { res.destroy(); return; }
      res.writeHead(status, { 'content-type': 'application/json' }).end(typeof body === 'string' ? body : JSON.stringify(body));
    });
    server.listen(0, '127.0.0.1', () => resolve(server));
  });
}

/** A fresh installed-copy root: no .git, with the given local Plexar version on disk. */
function installedRoot(localVersion) {
  const root = mkdtempSync(join(tmpdir(), 'plexar-cli-update-'));
  mkdirSync(join(root, 'packages', 'bundle', 'plexar'), { recursive: true });
  writeFileSync(join(root, 'packages', 'bundle', 'plexar', 'package.json'), JSON.stringify({ version: localVersion }));
  return root;
}

async function withManifest(status, body, fn) {
  const server = await manifestServer(status, body);
  const { port } = server.address();
  const previousRoot = process.env.PLEXAR_HARNESS_ROOT;
  const previousManifest = process.env.PLEXAR_RELEASE_MANIFEST;
  const root = installedRoot('0.1.0');
  process.env.PLEXAR_HARNESS_ROOT = root;
  process.env.PLEXAR_RELEASE_MANIFEST = `http://127.0.0.1:${port}/latest.json`;
  try {
    await fn(root);
  } finally {
    if (previousRoot === undefined) delete process.env.PLEXAR_HARNESS_ROOT; else process.env.PLEXAR_HARNESS_ROOT = previousRoot;
    if (previousManifest === undefined) delete process.env.PLEXAR_RELEASE_MANIFEST; else process.env.PLEXAR_RELEASE_MANIFEST = previousManifest;
    rmSync(root, { recursive: true, force: true });
    await new Promise((resolvePromise) => { server.close(resolvePromise); });
  }
}

/** Waits for `updateNotice`'s background check to save settings, then returns the stored answer. */
async function afterBackgroundCheck(settings) {
  let saved;
  await new Promise((resolvePromise) => {
    updateNotice(settings, (next) => { saved = next; resolvePromise(); }, () => {});
    setTimeout(resolvePromise, 2000);
  });
  return saved;
}

test('compareSemver orders major.minor.patch and rejects unparseable input', () => {
  assert.equal(compareSemver('0.2.0', '0.1.0') > 0, true);
  assert.equal(compareSemver('0.1.0', '0.2.0') < 0, true);
  assert.equal(compareSemver('0.1.0', '0.1.0'), 0);
  assert.equal(compareSemver('not-a-version', '0.1.0'), undefined);
});

test('updateNotice: newer manifest version yields a notice naming it', async () => {
  await withManifest(200, { version: '0.2.0' }, async () => {
    const saved = await afterBackgroundCheck({});
    assert.equal(saved?.update?.version, '0.2.0');
  });
});

test('updateNotice: same manifest version yields no stored notice', async () => {
  await withManifest(200, { version: '0.1.0' }, async () => {
    const settings = {};
    await afterBackgroundCheck(settings);
    const notice = updateNotice(settings, () => {}, () => {});
    assert.equal(notice, undefined);
  });
});

test('updateNotice: older manifest version yields no notice', async () => {
  await withManifest(200, { version: '0.0.9' }, async () => {
    const settings = {};
    await afterBackgroundCheck(settings);
    const notice = updateNotice(settings, () => {}, () => {});
    assert.equal(notice, undefined);
  });
});

test('updateNotice: 404 from the manifest server yields no notice', async () => {
  await withManifest(404, {}, async () => {
    const settings = {};
    await afterBackgroundCheck(settings);
    const notice = updateNotice(settings, () => {}, () => {});
    assert.equal(notice, undefined);
    assert.equal(settings.update, undefined);
  });
});

test('updateNotice: invalid JSON from the manifest server yields no notice', async () => {
  await withManifest(200, 'not json', async () => {
    const settings = {};
    await afterBackgroundCheck(settings);
    const notice = updateNotice(settings, () => {}, () => {});
    assert.equal(notice, undefined);
    assert.equal(settings.update, undefined);
  });
});

test('updateNotice: an already-known newer version reports the notice immediately, before the check', () => {
  const root = installedRoot('0.1.0');
  const previousRoot = process.env.PLEXAR_HARNESS_ROOT;
  process.env.PLEXAR_HARNESS_ROOT = root;
  process.env.PLEXAR_RELEASE_MANIFEST = 'http://127.0.0.1:1/unreachable.json';
  try {
    const settings = { update: { checkedAt: Date.now(), version: '0.2.0' } };
    const notice = updateNotice(settings, () => {}, () => {});
    assert.match(notice, /0\.2\.0/);
    assert.match(notice, /Open Plexar Harness to install it/);
  } finally {
    if (previousRoot === undefined) delete process.env.PLEXAR_HARNESS_ROOT; else process.env.PLEXAR_HARNESS_ROOT = previousRoot;
    delete process.env.PLEXAR_RELEASE_MANIFEST;
    rmSync(root, { recursive: true, force: true });
  }
});

test('runUpdate on an installed copy prints guidance and exits 0 without touching git/pnpm', () => {
  const root = installedRoot('0.1.0');
  const previousRoot = process.env.PLEXAR_HARNESS_ROOT;
  process.env.PLEXAR_HARNESS_ROOT = root;
  const originalWrite = process.stdout.write;
  let printed = '';
  process.stdout.write = (chunk) => { printed += chunk; return true; };
  try {
    const code = runUpdate();
    assert.equal(code, 0);
    assert.match(printed, /desktop app installs updates itself/);
    assert.match(printed, /https:\/\/harness\.plexar\.tech/);
  } finally {
    process.stdout.write = originalWrite;
    if (previousRoot === undefined) delete process.env.PLEXAR_HARNESS_ROOT; else process.env.PLEXAR_HARNESS_ROOT = previousRoot;
    rmSync(root, { recursive: true, force: true });
  }
});
