/**
 * `plexar-harness acp`: start the `plexar-acp` profile over stdio for an ACP client (Plexar Studio), from any
 * working directory. Before ACP starts it checks, in order, and fails with a distinct exit code and one
 * stderr line `plexar-harness: error <code>: <sentence>`:
 *
 *   10 node_too_old          Node is older than 22.19 (the harness would otherwise exit 0 silently)
 *   11 key_missing           PLEXAR_HARNESS_KEY is not set
 *   12 profile_install_failed the plexar-acp profile was absent and could not be created
 *   13 key_rejected          the rig answered 401/403 to the key
 *   14 rig_unreachable       the rig did not answer within 8 s
 *
 * After the checks it runs the profile with inherited stdio and exits with the profile's own exit code.
 * With `PLEXAR_BYO_BASE_URL` set, the BYO key satisfies the key check and the probe targets
 * `${PLEXAR_BYO_BASE_URL}/models` instead of the rig. The check is skipped with `--no-preflight` or `PLEXAR_HARNESS_PREFLIGHT=0`.
 * Reference: docs/plexar/07-studio-api-contract.md, "Launch".
 */
import { spawn, spawnSync } from 'node:child_process';
import { copyFileSync, existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { dshEntry, harnessRoot } from './acp.mjs';
import { byoConfig } from './credentials.mjs';
import { setupProfiles } from './setup.mjs';

export const EXIT = {
  node_too_old: 10,
  key_missing: 11,
  profile_install_failed: 12,
  key_rejected: 13,
  rig_unreachable: 14,
};
const PROFILE = 'plexar-acp';
const MIN_NODE = [22, 19];

function fail(code, sentence) {
  process.stderr.write(`plexar-harness: error ${code}: ${sentence}\n`);
  process.exit(EXIT[code]);
}

/** Argv and env that run the harness CLI (source in a checkout, built when installed), whatever the caller's cwd. */
export function dshCommand(args) {
  const entry = dshEntry(harnessRoot());
  return { argv: [process.execPath, ...entry.args, ...args], env: { ...process.env, ...entry.env } };
}

/** Create the plexar-acp profile the way `profiles/install.ps1` does, when it does not exist yet. */
function ensureProfile() {
  const home = process.env.DSH_HOME ?? join(homedir(), '.dsh');
  const dir = join(home, 'profiles', PROFILE);
  if (existsSync(join(dir, 'cordis.patch.yml'))) return;
  const root = harnessRoot();
  if (!existsSync(join(root, 'apps/cli/src/bin.ts'))) return installedProfiles();
  const run = (args) => {
    const { argv, env } = dshCommand(args);
    const r = spawnSync(argv[0], argv.slice(1), { env, encoding: 'utf8', windowsHide: true });
    if (r.status !== 0) fail('profile_install_failed', `could not create profile ${PROFILE} (${args.join(' ')} exited ${r.status}): ${(r.stderr || '').trim().split('\n').pop()}`);
  };
  if (!existsSync(dir)) run(['--profile', PROFILE, '--from-default-profile', 'acp', '--dump-default-config']);
  run(['plugin', '--profile', PROFILE, 'add', `link:${join(root, 'packages/bundle/plexar').replaceAll('\\', '/')}`]);
  copyFileSync(join(root, 'packages/bundle/plexar/profiles', `${PROFILE}.patch.yml`), join(dir, 'cordis.patch.yml'));
}

/** An installed runtime has no pnpm: create every Plexar profile with `setup.mjs` instead. */
function installedProfiles() {
  try {
    setupProfiles();
  } catch (error) {
    fail('profile_install_failed', error.message);
  }
}

/**
 * The endpoint the ACP preflight probes.
 * @param {NodeJS.ProcessEnv} [env] - the environment to read.
 * @returns {{base: string, url: string}} the base named in errors and the `/models` URL fetched.
 */
export function preflightTarget(env = process.env) {
  const byo = byoConfig(env);
  if (byo) {
    const base = byo.baseURL.replace(/\/$/, '');
    return { base, url: `${base}/models` };
  }
  const base = (env.PLEXAR_RIG_URL ?? 'https://llm.plexar.tech').replace(/\/$/, '');
  return { base, url: `${base}/v1/models` };
}

/**
 * The key the launch checks accept and the preflight sends: the BYO key (or its placeholder) when BYO
 * is active, never `PLEXAR_HARNESS_KEY`, since the preflight then targets the BYO host; otherwise
 * `PLEXAR_HARNESS_KEY`. Exits with `key_missing` when BYO is misconfigured.
 * @param {NodeJS.ProcessEnv} [env] - the environment to read; the BYO key is exported into it.
 * @returns {string | undefined} the key, or undefined when none is set.
 */
export function launchKey(env = process.env) {
  let byo;
  try {
    byo = byoConfig(env);
  } catch (error) {
    fail('key_missing', error.message);
  }
  if (byo) {
    env.PLEXAR_BYO_API_KEY = byo.key;
    return byo.key;
  }
  return env.PLEXAR_HARNESS_KEY;
}

/**
 * Probe the preflight target with `key`; exits with `rig_unreachable` or `key_rejected` on failure.
 * @param {string} key - the bearer key from {@link launchKey}.
 * @param {NodeJS.ProcessEnv} [env] - the environment naming the target.
 * @returns {Promise<void>} resolves when the target accepted the key.
 */
export async function preflight(key, env = process.env) {
  const { base, url } = preflightTarget(env);
  let response;
  try {
    response = await fetch(url, { headers: { authorization: `Bearer ${key}` }, signal: AbortSignal.timeout(8000) });
  } catch (error) {
    const cause = error.cause?.code ?? error.cause?.errors?.[0]?.code ?? (error.name === 'TimeoutError' ? 'timeout' : error.message);
    fail('rig_unreachable', `the Plexar rig at ${base} did not answer (${cause}); check the network, or point PLEXAR_RIG_URL at a rig you can reach`);
  }
  if (response.status === 401 || response.status === 403) {
    fail('key_rejected', `the Plexar rig refused PLEXAR_HARNESS_KEY (HTTP ${response.status}); request a new key from your Plexar admin`);
  }
}

/**
 * Run the ACP profile after the checks above.
 * @param {string[]} argv - arguments after `acp` (`--no-preflight` is the only one recognized)
 */
export async function launchAcp(argv) {
  const [major, minor] = process.versions.node.split('.').map(Number);
  if (major < MIN_NODE[0] || (major === MIN_NODE[0] && minor < MIN_NODE[1])) {
    fail('node_too_old', `Node ${process.versions.node} is too old; install Node 22.19+ or 24`);
  }
  const key = launchKey();
  if (!key) fail('key_missing', 'PLEXAR_HARNESS_KEY is not set; request a Plexar Harness key from your Plexar admin');
  ensureProfile();
  if (!argv.includes('--no-preflight') && process.env.PLEXAR_HARNESS_PREFLIGHT !== '0') await preflight(key);
  const { argv: command, env } = dshCommand(['--profile', PROFILE]);
  const child = spawn(command[0], command.slice(1), { env, stdio: 'inherit', windowsHide: true });
  child.on('exit', (code, signal) => process.exit(code ?? (signal ? 1 : 0)));
}

/**
 * `plexar-harness web [--port N] [--no-open]`: run the `plexar-web` profile (the browser UI, and the
 * Host the desktop app loads). Node and key checks match `acp`; the rig is not pre-checked, so the
 * UI opens and reports rig errors itself. The Host prints `dsh web: <url with one-time token>`.
 * @param {string[]} argv - flags after `web`, passed through to the Web Host (`--port`, `--no-open`, `--host`)
 */
export function launchWeb(argv) {
  const [major, minor] = process.versions.node.split('.').map(Number);
  if (major < MIN_NODE[0] || (major === MIN_NODE[0] && minor < MIN_NODE[1])) {
    fail('node_too_old', `Node ${process.versions.node} is too old; install Node 22.19+ or 24`);
  }
  if (!launchKey()) fail('key_missing', 'PLEXAR_HARNESS_KEY is not set; request a Plexar Harness key from your Plexar admin');
  const home = process.env.DSH_HOME ?? join(homedir(), '.dsh');
  if (!existsSync(join(home, 'profiles', 'plexar-web', 'cordis.patch.yml')) && !existsSync(join(harnessRoot(), 'apps/cli/src/bin.ts'))) installedProfiles();
  if (!existsSync(join(home, 'profiles', 'plexar-web', 'cordis.patch.yml'))) {
    fail('profile_install_failed', 'the plexar-web profile is not installed; run packages/bundle/plexar/profiles/install.ps1');
  }
  const { argv: command, env } = dshCommand(['--profile', 'plexar-web', ...argv]);
  const child = spawn(command[0], command.slice(1), { env, stdio: 'inherit', windowsHide: true });
  for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => child.kill(signal));
  child.on('exit', (code, signal) => process.exit(code ?? (signal ? 1 : 0)));
}
