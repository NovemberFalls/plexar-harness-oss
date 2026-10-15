/**
 * Installed-copy setup, the equivalent of `profiles/install.ps1` for a runtime with no pnpm and no
 * sources: creates or refreshes every Plexar profile under `$DSH_HOME/profiles` (default
 * `~/.dsh/profiles`) and manages the `plexar-harness` directory on the user `PATH`.
 *
 *   node setup.mjs profiles                  create/refresh the profiles
 *   node setup.mjs install --path-dir <dir>  the profiles, then add <dir> to the user PATH
 *   node setup.mjs uninstall --path-dir <dir> remove <dir> from the user PATH (profiles and sessions stay)
 *
 * Idempotent like `install.ps1`: an existing profile keeps its sessions; its `link:` plugins are
 * re-pointed at this runtime (a directory junction replaces pnpm's link); the shipped patch is
 * re-copied, except plexar-web's after its first install, since the Web UI saves settings there.
 * The Plexar desktop app runs `profiles` at every launch of an installed copy; the NSIS installer
 * hooks run `install` and `uninstall`.
 */
import { spawnSync } from 'node:child_process';
import { copyFileSync, existsSync, lstatSync, mkdirSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { dshEntry, harnessRoot } from './acp.mjs';

/** Profile name -> the `--from-default-profile` template it is created from (as in install.ps1). */
export const PROFILES = { plexar: 'headless', 'plexar-web': 'web', 'plexar-sdk': 'sdk', 'plexar-acp': 'acp' };

/**
 * Repo-relative package directories linked into a profile, in install.ps1's order.
 * @param {string} profile - a {@link PROFILES} key.
 * @returns {string[]}
 */
export function linkedPackages(profile) {
  const common = ['packages/bundle/plexar'];
  if (profile !== 'plexar-web') return common;
  return [...common, 'packages/client/ui-brand-plexar', 'packages/client/ui-settings-plexar', 'packages/experimental/voice-input-bundle'];
}

function readJson(path) {
  return JSON.parse(readFileSync(path, 'utf8'));
}

/** Replace `link` (a pnpm symlink, a junction, or nothing) with a junction to `target`. */
function junction(link, target) {
  let stat;
  try {
    stat = lstatSync(link);
  } catch (error) {
    // ENOENT: no previous link to replace.
    if (error.code !== 'ENOENT') throw error;
  }
  if (stat) rmSync(link, { recursive: !stat.isSymbolicLink(), force: true });
  mkdirSync(dirname(link), { recursive: true });
  symlinkSync(target, link, 'junction');
}

/**
 * Create or refresh every Plexar profile against the runtime at `root`.
 * @param {{root?: string, home?: string, log?: (line: string) => void}} [options]
 */
export function setupProfiles({ root = harnessRoot(), home = process.env.DSH_HOME ?? join(homedir(), '.dsh'), log = () => {} } = {}) {
  const entry = dshEntry(root);
  for (const [profile, template] of Object.entries(PROFILES)) {
    const dir = join(home, 'profiles', profile);
    const fresh = !existsSync(dir);
    if (fresh) {
      const r = spawnSync(process.execPath, [...entry.args, '--profile', profile, '--from-default-profile', template, '--dump-default-config'], {
        env: { ...process.env, ...entry.env, DSH_HOME: home },
        encoding: 'utf8',
        windowsHide: true,
      });
      if (r.status !== 0) throw new Error(`could not create profile ${profile} (exit ${r.status}): ${(r.stderr || '').trim().split('\n').pop()}`);
    }
    const manifestPath = join(dir, 'package.json');
    const manifest = readJson(manifestPath);
    manifest.dependencies ??= {};
    manifest.dsh ??= {};
    manifest.dsh.profile ??= {};
    manifest.dsh.profile.bundles ??= [];
    for (const rel of linkedPackages(profile)) {
      const target = join(root, rel);
      const pkg = readJson(join(target, 'package.json'));
      manifest.dependencies[pkg.name] = `link:${target.replaceAll('\\', '/')}`;
      junction(join(dir, 'node_modules', ...pkg.name.split('/')), target);
      if (pkg.dsh?.bundle?.patch !== undefined && !manifest.dsh.profile.bundles.includes(pkg.name)) manifest.dsh.profile.bundles.push(pkg.name);
    }
    writeFileSync(manifestPath, JSON.stringify(manifest, undefined, 2) + '\n');
    const patch = join(root, 'packages/bundle/plexar/profiles', `${profile}.patch.yml`);
    const appOwned = profile === 'plexar-web';
    if ((fresh || !appOwned) && existsSync(patch)) copyFileSync(patch, join(dir, 'cordis.patch.yml'));
    log(`profile ${profile} ready`);
  }
}

/**
 * Add or remove `dir` in the user `PATH` (HKCU Environment), through .NET so Windows broadcasts the change.
 * @param {'add' | 'remove'} action
 * @param {string} dir
 */
export function updateUserPath(action, dir) {
  const script = action === 'add'
    ? "$p=[Environment]::GetEnvironmentVariable('Path','User'); if(-not $p){$p=''}; if(-not (($p -split ';') -contains $env:PLEXAR_PATH_DIR)){[Environment]::SetEnvironmentVariable('Path', ($p.TrimEnd(';') + ';' + $env:PLEXAR_PATH_DIR).TrimStart(';'), 'User')}"
    : "$p=[Environment]::GetEnvironmentVariable('Path','User'); if($p){[Environment]::SetEnvironmentVariable('Path', ((($p -split ';') | Where-Object { $_ -and $_ -ne $env:PLEXAR_PATH_DIR }) -join ';'), 'User')}";
  const r = spawnSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', script], {
    env: { ...process.env, PLEXAR_PATH_DIR: dir },
    encoding: 'utf8',
    windowsHide: true,
  });
  if (r.status !== 0) throw new Error(`could not ${action} ${dir} in the user PATH: ${(r.stderr || '').trim()}`);
}

const isMain = process.argv[1] !== undefined && fileURLToPath(import.meta.url) === resolve(process.argv[1]);
if (isMain) {
  const [command, ...rest] = process.argv.slice(2);
  const pathDirIndex = rest.indexOf('--path-dir');
  const pathDir = pathDirIndex >= 0 ? rest[pathDirIndex + 1] : undefined;
  try {
    if (command === 'profiles') setupProfiles({ log: (line) => process.stdout.write(`${line}\n`) });
    else if (command === 'install' && pathDir) {
      setupProfiles({ log: (line) => process.stdout.write(`${line}\n`) });
      updateUserPath('add', pathDir);
    } else if (command === 'uninstall' && pathDir) updateUserPath('remove', pathDir);
    else {
      process.stderr.write('usage: setup.mjs profiles | install --path-dir <dir> | uninstall --path-dir <dir>\n');
      process.exitCode = 2;
    }
  } catch (error) {
    process.stderr.write(`plexar-harness setup: ${error.message}\n`);
    process.exitCode = 1;
  }
}
