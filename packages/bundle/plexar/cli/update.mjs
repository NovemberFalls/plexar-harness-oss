/**
 * Update checks and `plexar-harness update` for a git-checkout install or an installed copy.
 *
 * Every interactive launch checks in the background and never waits for it. In a git checkout, it
 * compares HEAD with the tip of the same branch on `origin` (`git ls-remote`, 5 s timeout). In an
 * installed copy (the Windows installer's runtime: no `.git`), it instead fetches the release
 * manifest (`PLEXAR_RELEASE_MANIFEST`, default `https://downloads.plexar.tech/harness/latest.json`)
 * and compares its `version` against the local `packages/bundle/plexar/package.json` version,
 * bounded by the same 5 s timeout. A notice appears under the header at once when the last stored
 * answer already names a newer commit or version, and as soon as the check finds one otherwise. The
 * answer is stored in the settings file. Every failure on either path (offline, non-200, invalid
 * JSON, timeout) means no notice, never an error. `PLEXAR_HARNESS_UPDATE_CHECK=0` turns the check off.
 *
 * `update` on a checkout refuses uncommitted changes to tracked files, then runs
 * `git pull --ff-only`, `pnpm install` and the Plexar bundle build, and prints the old and new
 * commit. On an installed copy it does not touch git or pnpm: it prints where updates come from
 * (the desktop app installs them on launch, or the installer download page) and exits 0.
 */
import { spawn, spawnSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { harnessRoot } from './acp.mjs';

/** Timeout for the background check, on either path. */
const CHECK_TIMEOUT_MS = 5000;

/** Default release manifest URL, matching the desktop app's Tauri updater feed. */
const DEFAULT_RELEASE_MANIFEST_URL = 'https://downloads.plexar.tech/harness/latest.json';

/** Path of the manifest whose `version` is the Plexar version, relative to the harness root. */
const VERSION_MANIFEST = 'packages/bundle/plexar/package.json';

function git(root, args) {
  const r = spawnSync('git', args, { cwd: root, encoding: 'utf8', windowsHide: true });
  return r.status === 0 ? r.stdout.trim() : undefined;
}

/** Whether `root` is a git checkout (has the git plumbing the checkout path needs). */
function isCheckout(root) {
  return existsSync(join(root, '.git'));
}

/** The `version` field of a manifest's JSON text, or undefined when it is not a manifest with one. */
function versionOf(text) {
  if (text === undefined) return undefined;
  try {
    const parsed = JSON.parse(text);
    return typeof parsed?.version === 'string' ? parsed.version : undefined;
  } catch (error) {
    // A manifest that is not JSON has no readable version; the notice then shows none.
    void error;
    return undefined;
  }
}

/** The local Plexar version of an installed copy, read directly from disk (no git needed). */
function localManifestVersion(root) {
  try {
    return versionOf(readFileSync(join(root, VERSION_MANIFEST), 'utf8'));
  } catch (error) {
    // A runtime missing its own manifest has no readable version; the notice then shows none.
    void error;
    return undefined;
  }
}

/**
 * Compares two `major.minor.patch` semver strings.
 * @returns {number | undefined} negative when `a` < `b`, positive when `a` > `b`, zero when equal,
 * or undefined when either string does not start with a parseable `major.minor.patch` prefix.
 */
export function compareSemver(a, b) {
  const pattern = /^(\d+)\.(\d+)\.(\d+)/;
  const left = pattern.exec(a);
  const right = pattern.exec(b);
  if (left === null || right === null) return undefined;
  for (let i = 1; i <= 3; i++) {
    const diff = Number(left[i]) - Number(right[i]);
    if (diff !== 0) return diff;
  }
  return 0;
}

/** Fetches the release manifest's `version`, bounded by {@link CHECK_TIMEOUT_MS}; undefined on any failure. */
async function fetchManifestVersion(url) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), CHECK_TIMEOUT_MS);
  try {
    const response = await fetch(url, { signal: controller.signal });
    if (!response.ok) return undefined;
    const parsed = await response.json();
    return typeof parsed?.version === 'string' ? parsed.version : undefined;
  } catch (error) {
    void error;
    return undefined;
  } finally {
    clearTimeout(timer);
  }
}

/** The notice for a stored checkout answer, or undefined when the checkout already has that commit. */
function noticeForCheckout(root, known) {
  const head = git(root, ['rev-parse', 'HEAD']);
  if (!known?.remote || !head || known.remote === head) return undefined;
  // A remote commit the checkout already contains is not an update (local is ahead or equal).
  if (git(root, ['merge-base', '--is-ancestor', known.remote, 'HEAD']) !== undefined) return undefined;
  return `Update available (${known.remote.slice(0, 10)} on ${known.branch}). Run: plexar-harness update`;
}

/** The notice for a stored installed-copy answer, or undefined when there is nothing newer. */
function noticeForManifest(root, known) {
  if (!known?.version) return undefined;
  const local = localManifestVersion(root);
  if (local === undefined) return undefined;
  const cmp = compareSemver(known.version, local);
  if (cmp === undefined || cmp <= 0) return undefined;
  return `Update available (v${known.version}). Open Plexar Harness to install it, or download the installer: https://harness.plexar.tech`;
}

/** The notice for a stored answer, whichever shape it has, or undefined when there is nothing newer. */
function noticeFor(root, known) {
  return isCheckout(root) ? noticeForCheckout(root, known) : noticeForManifest(root, known);
}

/**
 * The stored update notice now, and a background check that reports a newer commit or version when
 * it lands.
 * @param {object} settings - loaded settings; `update` is read and, after the check, rewritten.
 * @param {(settings: object) => void} save - persists settings after the check.
 * @param {(notice: string) => void} [onNotice] - called when the check finds a newer commit or version.
 * @returns {string | undefined} the notice line when the stored answer names something newer.
 */
export function updateNotice(settings, save, onNotice = () => {}) {
  if (process.env.PLEXAR_HARNESS_UPDATE_CHECK === '0') return undefined;
  const root = harnessRoot();
  refresh(root, settings, save, (known) => {
    const notice = noticeFor(root, known);
    if (notice) onNotice(notice);
  });
  return noticeFor(root, settings.update);
}

function refresh(root, settings, save, onDone) {
  if (!isCheckout(root)) {
    const manifestUrl = process.env.PLEXAR_RELEASE_MANIFEST ?? DEFAULT_RELEASE_MANIFEST_URL;
    fetchManifestVersion(manifestUrl).then((version) => {
      if (!version) return;
      settings.update = { checkedAt: Date.now(), version };
      save(settings);
      onDone(settings.update);
    });
    return;
  }
  const branch = git(root, ['rev-parse', '--abbrev-ref', 'HEAD']);
  if (!branch || branch === 'HEAD') return;
  const child = spawn('git', ['ls-remote', 'origin', `refs/heads/${branch}`], { cwd: root, windowsHide: true, stdio: ['ignore', 'pipe', 'ignore'] });
  let out = '';
  child.stdout.on('data', (d) => { out += d; });
  const timer = setTimeout(() => child.kill(), CHECK_TIMEOUT_MS);
  timer.unref();
  child.unref();
  child.stdout.unref?.();
  child.on('close', (code) => {
    clearTimeout(timer);
    const remote = code === 0 ? out.split(/\s/)[0] : undefined;
    if (!remote) return;
    settings.update = { checkedAt: Date.now(), branch, remote };
    save(settings);
    onDone(settings.update);
  });
}

/**
 * `plexar-harness update`: on a checkout, fast-forward it, reinstall, rebuild the bundle. On an
 * installed copy, print where updates come from instead of touching git or pnpm.
 * @returns {number} process exit code.
 */
export function runUpdate() {
  const root = harnessRoot();
  if (!isCheckout(root)) {
    process.stdout.write(
      'This is an installed copy; plexar-harness update does not apply.\n'
      + 'The desktop app installs updates itself on launch, or download the latest installer from '
      + 'https://harness.plexar.tech\n',
    );
    return 0;
  }
  const step = (label, cmd, args) => {
    process.stdout.write(`› ${label}\n`);
    const r = spawnSync(cmd, args, { cwd: root, stdio: 'inherit', shell: process.platform === 'win32', windowsHide: true });
    if (r.status !== 0) throw new Error(`${label} failed (exit ${r.status})`);
  };
  try {
    if (git(root, ['status', '--porcelain', '--untracked-files=no'])) {
      throw new Error(`${root} has uncommitted changes; commit or stash them, then run plexar-harness update again`);
    }
    const before = git(root, ['rev-parse', '--short=10', 'HEAD']);
    step('git pull --ff-only', 'git', ['pull', '--ff-only']);
    const after = git(root, ['rev-parse', '--short=10', 'HEAD']);
    if (before === after) {
      process.stdout.write(`Already up to date (${after}).\n`);
      return 0;
    }
    step('pnpm install', 'pnpm', ['install']);
    step('build the Plexar bundle', 'npx', ['tsc', '-b', 'packages/bundle/plexar']);
    process.stdout.write(`Updated ${before} → ${after}.\n`);
    return 0;
  } catch (error) {
    process.stderr.write(`plexar-harness update: ${error.message}\n`);
    return 1;
  }
}
