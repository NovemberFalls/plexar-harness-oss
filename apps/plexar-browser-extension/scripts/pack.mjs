// Copyright (c) Plexar contributors. Licensed under Apache-2.0.
//
// Packs the built dist/ directory into a .zip suitable for Chrome Web Store
// upload. Run `pnpm build` first; this script does not rebuild.
//
// The store rejects a manifest carrying "key" (it assigns its own), so the zip
// is built from a staging copy whose manifest omits it; dist/ keeps the key so
// load-unpacked installs keep the pinned development id.

import { cp, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { zipDirectory } from './zip.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const dist = resolve(root, 'dist');

async function main() {
  if (!existsSync(dist))
    throw new Error(`dist/ not found at ${dist}; run "pnpm build" first.`);
  const manifest = JSON.parse(await readFile(resolve(dist, 'manifest.json'), 'utf8'));
  const outPath = resolve(dist, `plexar-browser-bridge-${manifest.version}.zip`);
  const staging = await mkdtemp(join(tmpdir(), 'plexar-bridge-pack-'));
  try {
    await cp(dist, staging, { recursive: true, filter: source => !source.endsWith('.zip') });
    const { key: _key, ...storeManifest } = manifest;
    await writeFile(join(staging, 'manifest.json'), JSON.stringify(storeManifest, null, 2) + '\n', 'utf8');
    await zipDirectory(staging, outPath);
  } finally {
    await rm(staging, { recursive: true, force: true });
  }
  console.log(`Packed ${outPath}`);
}

await main();
