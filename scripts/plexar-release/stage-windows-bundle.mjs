/**
 * Stages a built Plexar Harness runtime into `apps/plexar-desktop/src-tauri/plexar-runtime/` so
 * `tauri build` packages it as an NSIS installer resource. See `apps/plexar-desktop/INSTALLER.md`
 * for the design (no source checkout, no system Node or pnpm required after install).
 *
 * Stages, at repo-relative paths matching a checkout (so `harnessRoot()` in the CLI and
 * `harness_root()` in `main.rs` resolve the same files as in a checkout):
 *
 *   plexar-runtime/harness/apps/cli/{lib,package.json}          the built `dsh` CLI (plain Node, no tsx)
 *   plexar-runtime/harness/node_modules/...                     flat production dependencies, real files
 *   plexar-runtime/harness/packages/bundle/plexar/{lib,cli,profiles,skills,cordis.patch.yml,package.json}
 *   plexar-runtime/harness/packages/client/ui-brand-plexar, ui-settings-plexar,
 *     packages/experimental/voice-input-bundle                  the other `link:` plugins of plexar-web
 *   plexar-runtime/harness/python/tools/src                     the document-tools server source
 *   plexar-runtime/node/node.exe                                a pinned win-x64 Node (`--node-exe`)
 *   plexar-runtime/bin/plexar-harness.cmd                       the PATH shim
 *
 * `node_modules` comes from `pnpm deploy --legacy --prod` with the hoisted linker, one deploy per
 * package that the profiles load, merged first-wins; peers that a deploy does not install are
 * deployed in further rounds until every staged package's dependencies and required peers resolve.
 * The result holds no symlinks or junctions, because an NSIS installer cannot carry them.
 *
 * Requires `pnpm run build` already run (reads `lib/` output; does not build). The Node binary is
 * downloaded and checked against nodejs.org's SHASUMS256.txt by `apps/plexar-desktop/build.ps1`,
 * which also pins its version.
 *
 * Usage:
 *   node scripts/plexar-release/stage-windows-bundle.mjs --node-exe <path to a verified node.exe>
 */
import { spawnSync } from 'node:child_process';
import { cpSync, existsSync, lstatSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(fileURLToPath(import.meta.url), '../../..');
const runtimeRoot = join(repoRoot, 'apps/plexar-desktop/src-tauri/plexar-runtime');
const harnessRoot = join(runtimeRoot, 'harness');

/** Packages whose production closure the runtime loads: the CLI (install anchor) and every `link:` plugin. */
const DEPLOY_ROOTS = [
  '@deepseek-ai/dsh',
  '@plexar/dsh-plexar',
  '@plexar/dsh-client-ui-brand',
  '@plexar/dsh-client-ui-settings-plexar',
  '@deepseek-ai/dsh-experimental-voice-input-bundle',
];

/** Workspace directories copied verbatim (minus sources and tests) to their repo-relative paths. */
const LINKED_PACKAGES = {
  'packages/bundle/plexar': ['lib', 'cli', 'profiles', 'skills', 'cordis.patch.yml', 'package.json'],
  'packages/client/ui-brand-plexar': ['lib', 'package.json'],
  'packages/client/ui-settings-plexar': ['lib', 'package.json'],
  'packages/experimental/voice-input-bundle': ['lib', 'locale', 'icon.svg', 'cordis.patch.yml', 'package.json'],
  'python/tools': ['src', 'pyproject.toml'],
};

/** File suffixes removed from the staged tree: build metadata and type declarations, never loaded at runtime. */
const PRUNED_SUFFIXES = ['.map', '.tsbuildinfo', '.d.ts', '.d.mts', '.d.cts'];

const SHIM = '@echo off\r\n"%~dp0..\\node\\node.exe" "%~dp0..\\harness\\packages\\bundle\\plexar\\cli\\plexar-harness.mjs" %*\r\n';

function readJson(path) {
  return JSON.parse(readFileSync(path, 'utf8'));
}

/** Workspace package name -> repo-relative directory, from `pnpm ls -r`. */
function workspacePackages() {
  // `shell`: pnpm is a .cmd shim on Windows; every argument here is a fixed literal.
  const r = spawnSync('pnpm', ['ls', '-r', '--depth', '-1', '--json'], { cwd: repoRoot, encoding: 'utf8', shell: true, maxBuffer: 64 << 20 });
  if (r.status !== 0) throw new Error(`pnpm ls failed: ${r.stderr}`);
  return new Map(JSON.parse(r.stdout).filter((p) => p.name).map((p) => [p.name, p.path]));
}

function deploy(name, out) {
  rmSync(out, { recursive: true, force: true });
  const r = spawnSync('pnpm', [
    '--filter', name, 'deploy', '--legacy', '--prod',
    '--config.node-linker=hoisted', '--config.allow-unused-patches=true', out,
  ], { cwd: repoRoot, encoding: 'utf8', shell: true, maxBuffer: 64 << 20 });
  if (r.status !== 0) throw new Error(`pnpm deploy ${name} failed:\n${r.stdout}\n${r.stderr}`);
}

/** Top-level package directories of a `node_modules` tree (scoped names expanded). */
function topLevel(nodeModules) {
  const names = [];
  for (const entry of existsSync(nodeModules) ? readdirSync(nodeModules) : []) {
    if (entry.startsWith('.')) continue;
    if (entry.startsWith('@')) for (const sub of readdirSync(join(nodeModules, entry))) names.push(`${entry}/${sub}`);
    else names.push(entry);
  }
  return names;
}

/** Copy every top-level package of `from` absent from `into`, dereferencing links. */
function mergeNodeModules(from, into) {
  let added = 0;
  for (const name of topLevel(from)) {
    const dest = join(into, name);
    if (existsSync(dest)) {
      const a = readJsonSafe(join(from, name, 'package.json'))?.version;
      const b = readJsonSafe(join(dest, 'package.json'))?.version;
      if (a !== b) process.stderr.write(`stage-windows-bundle: keeping ${name}@${b}, skipping ${a}\n`);
      continue;
    }
    mkdirSync(dirname(dest), { recursive: true });
    cpSync(join(from, name), dest, { recursive: true, dereference: true });
    added += 1;
  }
  return added;
}

function readJsonSafe(path) {
  try {
    return readJson(path);
  } catch (error) {
    // A package directory without a readable manifest has no version to compare; report it as unknown.
    if (error.code === 'ENOENT') return undefined;
    throw error;
  }
}

/** Resolve `name` the way Node does from package directory `fromDir`: nearest `node_modules` upwards. */
function resolvesFrom(fromDir, name) {
  for (let dir = fromDir; ; dir = dirname(dir)) {
    if (existsSync(join(dir, 'node_modules', name, 'package.json'))) return true;
    if (dirname(dir) === dir || !dir.startsWith(harnessRoot)) return false;
  }
}

/** Every package directory under the staged harness (node_modules packages, nested ones, and linked workspace dirs). */
function stagedPackageDirs() {
  const dirs = Object.keys(LINKED_PACKAGES).filter((rel) => existsSync(join(harnessRoot, rel, 'package.json'))).map((rel) => join(harnessRoot, rel));
  dirs.push(join(harnessRoot, 'apps/cli'));
  const walk = (nodeModules) => {
    for (const name of topLevel(nodeModules)) {
      const dir = join(nodeModules, name);
      if (!existsSync(join(dir, 'package.json'))) continue;
      dirs.push(dir);
      walk(join(dir, 'node_modules'));
    }
  };
  walk(join(harnessRoot, 'node_modules'));
  return dirs;
}

/** Dependency and required-peer names that do not resolve from the package that declares them. */
function unresolved() {
  const missing = new Map();
  for (const dir of stagedPackageDirs()) {
    const manifest = readJson(join(dir, 'package.json'));
    const optionalPeers = new Set(Object.entries(manifest.peerDependenciesMeta ?? {}).filter(([, m]) => m.optional).map(([n]) => n));
    const required = [...Object.keys(manifest.dependencies ?? {}), ...Object.keys(manifest.peerDependencies ?? {}).filter((n) => !optionalPeers.has(n))];
    for (const name of required) {
      if (!resolvesFrom(dir, name)) missing.set(name, [...(missing.get(name) ?? []), manifest.name]);
    }
  }
  return missing;
}

function prune(dir) {
  let removed = 0;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) removed += prune(path);
    else if (PRUNED_SUFFIXES.some((suffix) => entry.name.endsWith(suffix))) {
      rmSync(path);
      removed += 1;
    }
  }
  return removed;
}

/**
 * Remove every link left inside copied packages (a dereferenced `link:` package keeps its own
 * workspace links); `unresolved()` then reports any dependency that only such a link supplied.
 */
function removeLinks(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (lstatSync(path).isSymbolicLink()) rmSync(path, { recursive: false, force: true });
    else if (entry.isDirectory()) removeLinks(path);
  }
}

function sizeOf(dir) {
  let bytes = 0;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    bytes += entry.isDirectory() ? sizeOf(path) : statSync(path).size;
  }
  return bytes;
}

/**
 * Deploy every package in DEPLOY_ROOTS, then every workspace package that is still unresolved,
 * merging each result into the staged `node_modules`.
 * @returns {Set<string>} the deployed package names.
 */
function stageModules(packages, work) {
  let queue = [...DEPLOY_ROOTS];
  const deployed = new Set();
  for (let round = 1; queue.length > 0; round += 1) {
    for (const name of queue) {
      const out = join(work, name.replace('/', '__'));
      process.stdout.write(`deploy (round ${round}): ${name}\n`);
      deploy(name, out);
      deployed.add(name);
      if (name === '@deepseek-ai/dsh') {
        for (const entry of ['lib', 'package.json']) cpSync(join(out, entry), join(harnessRoot, 'apps/cli', entry), { recursive: true, dereference: true });
      } else if (!existsSync(join(harnessRoot, 'node_modules', name))) {
        // The deployed package itself is the deploy root, not an entry of its own node_modules.
        cpSync(out, join(harnessRoot, 'node_modules', name), { recursive: true, dereference: true, filter: (p) => p !== join(out, 'node_modules') });
      }
      mergeNodeModules(join(out, 'node_modules'), join(harnessRoot, 'node_modules'));
    }
    for (const [rel, entries] of Object.entries(LINKED_PACKAGES)) {
      for (const entry of entries) {
        const src = join(repoRoot, rel, entry);
        if (existsSync(src)) cpSync(src, join(harnessRoot, rel, entry), { recursive: true, dereference: true, filter: (p) => !/[\\/](tests|__pycache__)([\\/]|$)/.test(p) });
      }
    }
    removeLinks(harnessRoot);
    const missing = unresolved();
    queue = [...missing.keys()].filter((name) => packages.has(name) && !deployed.has(name));
    const external = [...missing].filter(([name]) => !packages.has(name));
    if (external.length > 0) {
      throw new Error('unresolved third-party dependencies:\n' + external.map(([n, by]) => `  ${n} (needed by ${by.join(', ')})`).join('\n'));
    }
    const stuck = [...missing.keys()].filter((name) => packages.has(name) && deployed.has(name));
    if (queue.length === 0 && stuck.length > 0) throw new Error(`workspace packages still unresolved after deploy: ${stuck.join(', ')}`);
  }
  return deployed;
}

function main() {
  const args = process.argv.slice(2);
  const nodeExeIndex = args.indexOf('--node-exe');
  const nodeExe = nodeExeIndex >= 0 ? args[nodeExeIndex + 1] : undefined;
  if (!nodeExe || !existsSync(nodeExe)) throw new Error('--node-exe <path> is required: the verified win-x64 node.exe to ship (build.ps1 downloads and checks it)');
  if (!existsSync(join(repoRoot, 'apps/cli/lib/bin.js'))) throw new Error('apps/cli/lib/bin.js is missing: run "pnpm run build" first');

  const packages = workspacePackages();
  const work = join(tmpdir(), 'plexar-harness-stage');
  // Only the staged entries: the directory itself keeps its committed .gitkeep.
  for (const entry of ['harness', 'node', 'bin']) rmSync(join(runtimeRoot, entry), { recursive: true, force: true });
  mkdirSync(join(harnessRoot, 'node_modules'), { recursive: true });

  // `pnpm deploy --prod` rewrites the checkout's workspace state as production-only, after which
  // every `pnpm run` in the checkout asks to reinstall; the state file is restored afterwards.
  const statePath = join(repoRoot, 'node_modules/.pnpm-workspace-state-v1.json');
  const savedState = existsSync(statePath) ? readFileSync(statePath) : undefined;
  let deployed;
  try {
    deployed = stageModules(packages, work);
  } finally {
    if (savedState !== undefined) writeFileSync(statePath, savedState);
  }
  const pruned = prune(harnessRoot);

  mkdirSync(join(runtimeRoot, 'node'), { recursive: true });
  cpSync(nodeExe, join(runtimeRoot, 'node/node.exe'));
  mkdirSync(join(runtimeRoot, 'bin'), { recursive: true });
  writeFileSync(join(runtimeRoot, 'bin/plexar-harness.cmd'), SHIM);

  const mb = (sizeOf(runtimeRoot) / (1 << 20)).toFixed(0);
  process.stdout.write(`Staged ${deployed.size} deploys (${pruned} build/type files pruned) into ${runtimeRoot}: ${mb} MB.\n`);
}

try {
  main();
} catch (error) {
  process.stderr.write(`stage-windows-bundle: ${error.message}\n`);
  process.exitCode = 1;
}
