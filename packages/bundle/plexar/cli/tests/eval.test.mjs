import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';

const STUB = `
import { writeFileSync } from 'node:fs';
import { join } from 'node:path';
const ws = process.argv[process.argv.indexOf('--cwd') + 1];
const mode = process.env.STUB_MODE;
if (mode === 'sleep') setInterval(() => {}, 1000);
else writeFileSync(join(ws, 'hello.txt'), mode === 'pass' ? 'hello plexar\\n' : 'wrong\\n');
`;

/** Run runEval in a child process with a stub harness; hooks.timeoutScale shortens task timeouts. */
async function run(args, mode, hooks = {}) {
  const dir = mkdtempSync(join(tmpdir(), 'eval-test-'));
  const stub = join(dir, 'stub.mjs');
  writeFileSync(stub, STUB);
  const evalUrl = pathToFileURL(join(import.meta.dirname, '..', 'eval.mjs')).href;
  const script = `import(${JSON.stringify(evalUrl)}).then((m) => m.runEval(JSON.parse(process.argv[1]), JSON.parse(process.argv[2]))).then((c) => process.exit(c))`;
  const r = spawnSync(process.execPath, ['-e', script, JSON.stringify(args), JSON.stringify(hooks)], {
    encoding: 'utf8',
    env: { ...process.env, PLEXAR_EVAL_HARNESS: stub, PLEXAR_EVAL_DIR: join(dir, 'out'), STUB_MODE: mode },
  });
  return { code: r.status, out: r.stdout, dir: join(dir, 'out') };
}

test('--list shows the six tasks', async () => {
  const { code, out } = await run(['--list'], 'pass');
  assert.equal(code, 0);
  assert.equal(out.trim().split('\n').length, 6);
});

test('passing task exits 0 with json fields and appends jsonl', async () => {
  const { code, out, dir } = await run(['--task', 'create-file', '--json', '--model', 'm1'], 'pass');
  assert.equal(code, 0);
  const obj = JSON.parse(out);
  assert.equal(obj.model, 'm1');
  assert.equal(obj.passRate, 1);
  assert.deepEqual(Object.keys(obj.results[0]).sort(), ['attempt', 'exit', 'id', 'ms', 'pass']);
  const files = readdirSync(dir);
  assert.equal(files.length, 1);
  assert.match(files[0], /^\d{4}-\d{2}-\d{2}\.jsonl$/);
  assert.deepEqual(JSON.parse(readFileSync(join(dir, files[0]), 'utf8').trim()), obj);
});

test('failing check exits 1', async () => {
  const { code, out } = await run(['--task', 'create-file', '--json'], 'fail');
  assert.equal(code, 1);
  assert.equal(JSON.parse(out).results[0].pass, false);
});

test('repeat runs numbered attempts', async () => {
  const { out } = await run(['--task', 'create-file', '--json', '--repeat', '2'], 'pass');
  assert.deepEqual(JSON.parse(out).results.map((r) => r.attempt), [1, 2]);
});

test('timeout kills the agent and fails', async () => {
  const { code, out } = await run(['--task', 'create-file', '--json'], 'sleep', { timeoutScale: 0.005 });
  assert.equal(code, 1);
  const res = JSON.parse(out).results[0];
  assert.equal(res.pass, false);
  assert.equal(res.exit, -1);
});
