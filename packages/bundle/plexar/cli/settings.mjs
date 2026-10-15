/**
 * Client settings: trusted folders, the last permission mode, and the last update check. Stored in `PLEXAR_HARNESS_SETTINGS`,
 * else `~/.dsh/plexar-harness.json`. A missing or unreadable file reads as defaults; the client never fails on it.
 */
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join, resolve } from 'node:path';

const FILE = process.env.PLEXAR_HARNESS_SETTINGS ?? join(homedir(), '.dsh', 'plexar-harness.json');

/** Permission modes in Shift+Tab order; `env` is the harness `DSH_PERMISSION_MODE` value. */
export const MODES = [
  { id: 'ask', env: 'read-only', label: 'ask mode', hint: 'asks before every edit and command' },
  { id: 'auto-edit', env: 'workspace-write', label: 'auto-edit', hint: 'edits this folder freely; asks before commands' },
  { id: 'full-access', env: 'danger-full-access', label: 'full access', hint: 'never asks' },
];

/** @returns {{trusted: string[], mode: string, update?: {checkedAt: number, branch: string, remote: string}}} */
export function load() {
  try {
    const data = JSON.parse(readFileSync(FILE, 'utf8'));
    const update = data.update && typeof data.update.remote === 'string' && typeof data.update.checkedAt === 'number' ? data.update : undefined;
    return { trusted: Array.isArray(data.trusted) ? data.trusted : [], mode: typeof data.mode === 'string' ? data.mode : 'auto-edit', ...update ? { update } : {} };
  } catch (error) {
    // Absent on first run, or hand-edited into invalid JSON: both mean defaults.
    if (error.code !== 'ENOENT') process.stderr.write(`plexar-harness: ignoring ${FILE}: ${error.message}\n`);
    return { trusted: [], mode: 'auto-edit' };
  }
}

/** Persist settings; a write failure is reported and otherwise ignored. */
export function save(settings) {
  try {
    mkdirSync(dirname(FILE), { recursive: true });
    writeFileSync(FILE, `${JSON.stringify(settings, null, 2)}\n`);
  } catch (error) {
    process.stderr.write(`plexar-harness: could not save ${FILE}: ${error.message}\n`);
  }
}

/** @returns {boolean} whether `folder` or one of its parents is trusted */
export function isTrusted(settings, folder) {
  const target = resolve(folder).toLowerCase();
  return settings.trusted.some((t) => {
    const root = resolve(t).toLowerCase();
    return target === root || target.startsWith(root.endsWith('\\') || root.endsWith('/') ? root : `${root}${process.platform === 'win32' ? '\\' : '/'}`);
  });
}
