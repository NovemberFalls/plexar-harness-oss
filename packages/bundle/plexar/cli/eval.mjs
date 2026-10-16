/**
 * `plexar-harness eval`: run the tasks in `packages/bundle/plexar/evals/<id>/task.json` against the harness
 * in a fresh temp workspace and score each with its check command.
 *
 * Task format: `{id, prompt, timeoutSec, check: {cmd: string[]}}` plus an optional `files/` directory copied
 * into the workspace. The check runs in the workspace after the agent exits; exit 0 is a pass.
 *
 * Flags: `--list`, `--task <id>` (repeatable), `--model`, `--effort`, `--repeat N`, `--json`.
 * Each run appends one JSON line `{model, results:[{id, pass, ms, exit, attempt}], passRate}` to
 * `<PLEXAR_EVAL_DIR or ~/.dsh/plexar-evals>/<YYYY-MM-DD>.jsonl`.
 * `PLEXAR_EVAL_HARNESS` overrides the spawned entry script (default: the sibling plexar-harness.mjs).
 */
import { spawn, spawnSync } from 'node:child_process';
import { appendFileSync, cpSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync } from 'node:fs';
import { homedir, tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const TASKS_DIR = join(HERE, '..', 'evals');

/**
 * Parse eval argv.
 * @param {string[]} argv arguments after the subcommand name.
 * @returns {{list: boolean, json: boolean, tasks: string[], model?: string, effort?: string, repeat: number}} parsed options.
 */
function parseArgs(argv) {
  const o = { list: false, json: false, tasks: [], repeat: 1 };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--list') o.list = true;
    else if (a === '--json') o.json = true;
    else if (a === '--task') o.tasks.push(argv[++i]);
    else if (a === '--model') o.model = argv[++i];
    else if (a === '--effort') o.effort = argv[++i];
    else if (a === '--repeat') o.repeat = Number(argv[++i]);
    else throw new Error(`unknown argument: ${a}`);
  }
  if (!Number.isInteger(o.repeat) || o.repeat < 1) throw new Error('--repeat needs a positive integer');
  return o;
}

/**
 * Load every task definition from the evals directory, sorted by id.
 * @returns {{id: string, prompt: string, timeoutSec: number, check: {cmd: string[]}, dir: string}[]} tasks.
 */
function loadTasks() {
  return readdirSync(TASKS_DIR, { withFileTypes: true })
    .filter((d) => d.isDirectory() && existsSync(join(TASKS_DIR, d.name, 'task.json')))
    .map((d) => {
      const dir = join(TASKS_DIR, d.name);
      return { ...JSON.parse(readFileSync(join(dir, 'task.json'), 'utf8')), dir };
    })
    .sort((a, b) => a.id.localeCompare(b.id));
}

/**
 * Kill a child and its descendants.
 * @param {import('node:child_process').ChildProcess} child process to kill.
 * @returns {void}
 */
function killTree(child) {
  if (process.platform === 'win32') {
    spawnSync('taskkill', ['/pid', String(child.pid), '/T', '/F'], { stdio: 'ignore' });
    return;
  }
  try {
    process.kill(-child.pid, 'SIGKILL');
  } catch (err) {
    // The process group is already gone or the child is not a group leader (${err.code}); kill the child alone.
    child.kill('SIGKILL');
  }
}

/**
 * Run the harness once on a task prompt, killing it on timeout.
 * @param {string[]} args argv for node.
 * @param {number} timeoutMs time limit.
 * @returns {Promise<number>} exit code, or -1 on timeout or spawn failure.
 */
function runAgent(args, timeoutMs) {
  return new Promise((resolve) => {
    const child = spawn(process.execPath, args, { stdio: 'ignore', detached: process.platform !== 'win32' });
    let done = false;
    let timer;
    const finish = (code) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      resolve(code);
    };
    timer = setTimeout(() => {
      killTree(child);
      finish(-1);
    }, timeoutMs);
    child.on('error', () => finish(-1));
    child.on('close', (code) => finish(code ?? -1));
  });
}

/**
 * Run the eval subcommand.
 * @param {string[]} argv arguments after `eval`.
 * @param {{timeoutScale?: number}} [hooks] test hook: multiplies every task timeout.
 * @returns {Promise<number>} process exit code: 0 iff every run passed.
 */
export async function runEval(argv, hooks = {}) {
  let opts;
  try {
    opts = parseArgs(argv);
  } catch (err) {
    process.stderr.write(`plexar-harness eval: ${err.message}\n`);
    return 2;
  }
  const all = loadTasks();
  if (opts.list) {
    for (const t of all) process.stdout.write(`${t.id}\t${t.timeoutSec}s\t${t.prompt.split('\n')[0].slice(0, 80)}\n`);
    return 0;
  }
  const selected = opts.tasks.length ? opts.tasks.map((id) => all.find((t) => t.id === id)) : all;
  const missing = opts.tasks.filter((_, i) => !selected[i]);
  if (missing.length) {
    process.stderr.write(`plexar-harness eval: unknown task: ${missing.join(', ')}\n`);
    return 2;
  }
  const entry = process.env.PLEXAR_EVAL_HARNESS || join(HERE, 'plexar-harness.mjs');
  const results = [];
  for (const task of selected) {
    for (let attempt = 1; attempt <= opts.repeat; attempt++) {
      const ws = mkdtempSync(join(tmpdir(), `plexar-eval-${task.id}-`));
      if (existsSync(join(task.dir, 'files'))) cpSync(join(task.dir, 'files'), ws, { recursive: true });
      const args = [entry, '-p', task.prompt, '--cwd', ws, '--mode', 'full-access'];
      if (opts.model) args.push('--model', opts.model);
      if (opts.effort) args.push('--effort', opts.effort);
      const start = Date.now();
      const exit = await runAgent(args, task.timeoutSec * 1000 * (hooks.timeoutScale ?? 1));
      const ms = Date.now() - start;
      const [cmd, ...cmdArgs] = task.check.cmd;
      const check = spawnSync(cmd === 'node' ? process.execPath : cmd, cmdArgs, { cwd: ws, stdio: 'ignore' });
      results.push({ id: task.id, pass: exit !== -1 && check.status === 0, ms, exit, attempt });
      rmSync(ws, { recursive: true, force: true });
    }
  }
  const passed = results.filter((r) => r.pass).length;
  const passRate = passed / results.length;
  const summary = { model: opts.model ?? null, results, passRate };
  const dir = process.env.PLEXAR_EVAL_DIR || join(homedir(), '.dsh', 'plexar-evals');
  mkdirSync(dir, { recursive: true });
  appendFileSync(join(dir, `${new Date().toISOString().slice(0, 10)}.jsonl`), `${JSON.stringify(summary)}\n`);
  if (opts.json) {
    process.stdout.write(`${JSON.stringify(summary)}\n`);
  } else {
    for (const r of results) {
      process.stdout.write(`${r.pass ? 'PASS' : 'FAIL'}  ${r.id.padEnd(18)} #${r.attempt}  ${(r.ms / 1000).toFixed(1)}s  exit ${r.exit}\n`);
    }
    process.stdout.write(`pass rate ${(passRate * 100).toFixed(0)}% (${passed}/${results.length})\n`);
  }
  return passed === results.length ? 0 : 1;
}
