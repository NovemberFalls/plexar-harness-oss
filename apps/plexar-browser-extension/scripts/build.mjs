// Copyright (c) Plexar contributors. Licensed under Apache-2.0.
//
// Bundles the background service worker and the connect/status UI pages
// into dist/, then copies the manifest, icons, and hand-authored page CSS
// alongside them so dist/ is directly `chrome://extensions` "Load unpacked"
// ready.
//
// Two CSS layers exist for the UI pages: the hand-authored page stylesheet
// (connect.css, linked directly from the HTML, shared by both pages) and the
// component stylesheets imported from TSX (authToken.css, icons.css, ...),
// which esbuild bundles into a `[name].bundle.css` file per entry. Both are
// linked from the rewritten HTML below.

import { readFile, writeFile, mkdir, cp, rm } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import esbuild from 'esbuild';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const dist = resolve(root, 'dist');

async function main() {
  await rm(dist, { recursive: true, force: true });
  await mkdir(dist, { recursive: true });

  await esbuild.build({
    entryPoints: [resolve(root, 'src/background.ts')],
    bundle: true,
    format: 'esm',
    target: 'chrome120',
    outfile: resolve(dist, 'lib/background.mjs'),
    logLevel: 'info',
  });

  await esbuild.build({
    entryPoints: {
      connect: resolve(root, 'src/ui/connect.tsx'),
      status: resolve(root, 'src/ui/status.tsx'),
    },
    bundle: true,
    format: 'esm',
    target: 'chrome120',
    jsx: 'automatic',
    outdir: resolve(dist, 'lib/ui'),
    entryNames: '[name].bundle',
    loader: { '.css': 'css' },
    logLevel: 'info',
  });

  await rewriteHtml('connect');
  await rewriteHtml('status');
  await cp(resolve(root, 'src/ui/connect.css'), resolve(dist, 'lib/ui/connect.css'));

  await cp(resolve(root, 'icons'), resolve(dist, 'icons'), { recursive: true });
  await cp(resolve(root, 'manifest.json'), resolve(dist, 'manifest.json'));

  console.log(`Build complete: ${dist}`);
}

// The source HTML loads its page as a .tsx module script and links the
// hand-authored connect.css. The built page also needs the esbuild-bundled
// component CSS (`[name].bundle.css`) and the compiled script
// (`[name].bundle.js`) in place of the .tsx source.
async function rewriteHtml(name) {
  const srcPath = resolve(root, 'src/ui', `${name}.html`);
  // Pages sit at the extension root, as upstream's Vite build (root: src/ui) emits them: the relay
  // opens chrome-extension://<id>/connect.html and the service worker opens /status.html.
  const destPath = resolve(dist, `${name}.html`);
  let html = await readFile(srcPath, 'utf8');
  html = html
      .replace(`src="${name}.tsx" type="module"`, `src="lib/ui/${name}.bundle.js" type="module"`)
      .replace(`type="module" src="${name}.tsx"`, `type="module" src="lib/ui/${name}.bundle.js"`)
      .replaceAll('href="../../icons/', 'href="icons/')
      .replace(/href="([a-zA-Z]+\.css)"/g, 'href="lib/ui/$1"')
      .replace('</head>', existsSync(resolve(dist, 'lib/ui', `${name}.bundle.css`))
        ? `  <link rel="stylesheet" href="lib/ui/${name}.bundle.css">\n</head>`
        : '</head>');
  await mkdir(dirname(destPath), { recursive: true });
  await writeFile(destPath, html, 'utf8');
}

await main();
