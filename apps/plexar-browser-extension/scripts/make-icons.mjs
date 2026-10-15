// Copyright (c) Plexar contributors. Licensed under Apache-2.0.
//
// Resizes apps/plexar-desktop/ui/mark.png to the icon sizes MV3 requires
// (16/32/48/128) and writes them under icons/. Run via `pnpm icons`; the
// output is committed so `pnpm build` does not need to re-derive it.

import { readFile, mkdir } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import sharp from 'sharp';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const sourcePath = resolve(root, '../plexar-desktop/ui/mark.png');
const iconsDir = resolve(root, 'icons');
const sizes = [16, 32, 48, 128];

async function main() {
  const source = await readFile(sourcePath);
  await mkdir(iconsDir, { recursive: true });
  await Promise.all(sizes.map(async size => {
    const outPath = resolve(iconsDir, `icon-${size}.png`);
    await sharp(source).resize(size, size).png().toFile(outPath);
    console.log(`Wrote ${outPath}`);
  }));
}

await main();
