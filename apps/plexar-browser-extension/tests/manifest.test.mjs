// Copyright (c) Plexar contributors. Licensed under Apache-2.0.
//
// Verifies dist/manifest.json (built via `pnpm build`): identity fields, the
// pinned developer key, and that the extension id Chrome derives from that
// key (sha256 of the DER-decoded key, first 32 hex nibbles mapped 0-f to
// a-p) is the pinned id cnfgenfphpnhddlefhminclbbjdgkbbd.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const manifestPath = resolve(here, '../dist/manifest.json');

const PINNED_EXTENSION_ID = 'cnfgenfphpnhddlefhminclbbjdgkbbd';

function extensionIdFromKey(base64Key) {
  const der = Buffer.from(base64Key, 'base64');
  const hash = createHash('sha256').update(der).digest('hex');
  const first32 = hash.slice(0, 32);
  return first32
      .split('')
      .map(c => String.fromCharCode(97 + parseInt(c, 16)))
      .join('');
}

test('dist/manifest.json has the expected identity fields', async () => {
  const manifest = JSON.parse(await readFile(manifestPath, 'utf8'));

  assert.equal(manifest.name, 'Plexar Browser Bridge');
  assert.equal(manifest.version, '0.2.0');
  assert.deepEqual(
      [...manifest.permissions].sort(),
      ['activeTab', 'debugger', 'tabGroups', 'tabs'].sort(),
  );
  assert.equal(typeof manifest.key, 'string');
  assert.ok(manifest.key.length > 0);
});

test('the manifest key derives the pinned extension id', async () => {
  const manifest = JSON.parse(await readFile(manifestPath, 'utf8'));
  assert.equal(extensionIdFromKey(manifest.key), PINNED_EXTENSION_ID);
});

// The relay opens chrome-extension://<id>/connect.html and the service worker opens status.html,
// so both pages must sit at the extension root with their scripts and styles resolvable from there.
test('dist pages sit at the extension root with resolvable assets', async () => {
  const { access } = await import('node:fs/promises');
  for (const name of ['connect', 'status']) {
    const html = await readFile(resolve(here, `../dist/${name}.html`), 'utf8');
    const refs = [...html.matchAll(/(?:src|href)="([^"]+)"/g)].map(m => m[1]);
    assert.ok(refs.includes(`lib/ui/${name}.bundle.js`), `${name}.html loads its bundle`);
    for (const ref of refs) await access(resolve(here, '../dist', ref));
  }
});
