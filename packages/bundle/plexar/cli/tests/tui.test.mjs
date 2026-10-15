// Keyless terminal-UI regression: a VT emulator replays the composer and select output at 60 columns.
// Usage: node packages/bundle/plexar/cli/tests/tui.test.mjs   (exit 0 = pass)
// Regression for the owner FAIL of 2026-09-23: in a narrow window the composer's status line
// wrapped, every redraw landed one row short, and old top borders stacked up.
// A tiny VT emulator applies the composer's output to a grid and counts frames left on screen.
process.stdout.columns = 60;
const cli = new URL('../', import.meta.url).href;
const { Composer } = await import(`${cli}tui/composer.mjs`);
const { select } = await import(`${cli}tui/select.mjs`);
const { dispatchKey } = await import(`${cli}tui/keys.mjs`);

function emulate(stream, cols) {
  const grid = [[]];
  let row = 0;
  let col = 0;
  const put = (ch) => {
    if (col >= cols) { row += 1; col = 0; }
    while (grid.length <= row) grid.push([]);
    grid[row][col] = ch;
    col += 1;
  };
  const re = /\x1b\[([0-9;?]*)([A-Za-z])|([\s\S])/g;
  let m;
  while ((m = re.exec(stream))) {
    if (m[3] !== undefined) {
      if (m[3] === '\n') { row += 1; col = 0; while (grid.length <= row) grid.push([]); }
      else if (m[3] === '\r') col = 0;
      else put(m[3]);
      continue;
    }
    const n = Number(m[1] || 1);
    if (m[2] === 'A') row = Math.max(0, row - n);
    else if (m[2] === 'B') row += n;
    else if (m[2] === 'G') col = n - 1;
    else if (m[2] === 'K') grid[row] = [];
    else if (m[2] === 'J') { grid[row] = grid[row].slice(0, col); grid.length = row + 1; }
  }
  return grid.map((r) => Array.from(r, (c) => c ?? ' ').join(''));
}

const fails = [];
const check = (name, ok, detail = '') => { console.log(`${ok ? 'PASS' : 'FAIL'} ${name}`); if (!ok) fails.push(`${name} ${detail}`); };

let out = '';
const sink = { write: (s) => { out += s; return true; } };
const longStatus = '›› auto-edit on (shift+tab to cycle) · / for commands · ctrl-c to cancel a turn';
const composer = new Composer({
  commands: () => [{ name: 'mode', description: 'show or set permissions' }, { name: 'model', description: 'show or set the model' }],
  status: () => longStatus,
  onShiftTab() {}, onInterrupt() {}, onEof() {},
  out: sink,
});
const done = composer.read();
for (const ch of 'exi') dispatchKey(ch, { name: ch });
for (const ch of '/mo') dispatchKey(ch, { name: ch });
dispatchKey('', { name: 'down' });
for (let i = 0; i < 3; i += 1) dispatchKey('', { name: 'backspace' });
for (const ch of 't') dispatchKey(ch, { name: ch });
const screen = emulate(out, 60);
const tops = screen.filter((l) => l.includes('╭')).length;
check('one frame on screen after 12 redraws at 60 columns', tops === 1, `found ${tops}:\n${screen.join('\n')}`);
check('no row wider than the window', out.split(/\r|\n/).every((l) => l.replace(/\x1b\[[0-9;?]*[A-Za-z]/g, '').length <= 60));
dispatchKey('', { name: 'return' });
const line = await done;
check('submitted text', line === 'exit', JSON.stringify(line));

out = '';
const choice = select({ title: 'Allow a very long tool name that would certainly wrap past sixty columns?', icon: '!', options: ['Allow once', 'Reject'], out: sink });
dispatchKey('', { name: 'down' });
dispatchKey('', { name: 'up' });
dispatchKey('', { name: 'return' });
check('select resolves', (await choice) === 0);
const sel = emulate(out, 60).join('\n');
check('select leaves one summary line', (sel.match(/Allow a very long/g) ?? []).length === 1, sel);
check('permission select uses !', sel.includes(' ! Allow'));
out = '';
const trust = select({ title: 'Trust this folder?', options: ['Yes', 'No'], out: sink });
dispatchKey('', { name: 'return' });
await trust;
check('non-permission select uses ?', emulate(out, 60).join('\n').includes(' ? Trust this folder?'));

// Long input wraps inside a growing box instead of scrolling sideways.
out = '';
const long = 'This is a test to see where the formatting is going for a second line to see how this is managed ok';
const grow = composer.read();
for (const ch of long) dispatchKey(ch, { name: ch });
const grown = emulate(out, 60);
const boxRows = grown.filter((l) => l.startsWith('│'));
check('box grows to fit long input', boxRows.length >= 2 && grown.filter((l) => l.includes('╭')).length === 1, grown.join('\n'));
check('box shows every character', boxRows.map((l) => l.slice(4, -1).trimEnd()).join('') === long, boxRows.join('\n'));
dispatchKey('', { name: 'return' });
await grow;
const echoed = emulate(out, 60).filter((l) => l.startsWith('›') || l.startsWith('  '));
check('echo wraps indented under the chevron', echoed.length >= 2 && echoed.every((l) => l.length <= 60) && echoed[1].startsWith('  '), emulate(out, 60).join('\n'));

// Keyboard shortcuts: ? panel, word editing, y/n answers.
out = '';
const keysRead = composer.read();
dispatchKey('?', { name: '?' });
const panel = emulate(out, 60);
check('? on an empty line opens the shortcuts panel', panel.some((l) => l.includes('ctrl+w')) && panel.every((l) => l.length <= 60), panel.join('\n'));
for (const ch of 'fix the build now') dispatchKey(ch, { name: ch === ' ' ? 'space' : ch });
check('typing closes the panel and keeps the text', !emulate(out, 60).some((l) => l.includes('ctrl+w')) && composer.line === 'fix the build now', composer.line);
dispatchKey('\x17', { name: 'w', ctrl: true });
check('ctrl+w deletes the previous word', composer.line === 'fix the build ', JSON.stringify(composer.line));
dispatchKey('', { name: 'left', ctrl: true });
dispatchKey('', { name: 'left', ctrl: true });
check('ctrl+left jumps words', composer.pos === 4, String(composer.pos));
dispatchKey('\x0b', { name: 'k', ctrl: true });
check('ctrl+k deletes to the end', composer.line === 'fix ', JSON.stringify(composer.line));
dispatchKey('', { name: 'return' });
await keysRead;
out = '';
const yes = select({ title: 'Allow bash?', icon: '!', options: ['Allow once', 'Reject'], out: sink });
dispatchKey('n', { name: 'n' });
check('n picks the reject option', (await yes) === 1);
check('y/n hint shown for yes/no prompts', emulate(out, 60).join('\n').includes('y/n') || out.includes('y/n'));
const trust2 = select({ title: 'Trust this folder?', options: ['Yes, trust it', 'No, exit'], out: sink });
dispatchKey('y', { name: 'y' });
check('y picks the yes option', (await trust2) === 0);

// Edit/write diffs: real line numbers, -/+ rows, context, capped with "more lines".
const { lineDiff, renderDiff } = await import(`${cli}diff.mjs`);
const d = lineDiff('a\nb\nc\nd\n', 'a\nB\nc\nd\ne\n');
check('lineDiff marks a replaced and an appended line', JSON.stringify(d.filter((r) => r.kind !== ' ').map((r) => r.kind + (r.oldNo ?? r.newNo) + r.text)) === JSON.stringify(['-2b', '+2B', '+5e']), JSON.stringify(d));
const big = renderDiff(lineDiff('', Array.from({ length: 40 }, (_, i) => `line ${i}`).join('\n')), { width: 60, maxRows: 16, color: false });
check('long diffs cap with a more-lines row', big.lines.length === 17 && big.lines[16].includes('24 more lines') && big.added === 40, big.lines.join('\n'));
{
  const { mkdtempSync, writeFileSync: wf } = await import('node:fs');
  const { tmpdir } = await import('node:os');
  const { join: pj } = await import('node:path');
  const dir = mkdtempSync(pj(tmpdir(), 'plexar-diff-'));
  wf(pj(dir, 'app.py'), 'def add(a, b):\n    return a + b\n');
  let drawn = '';
  const { Renderer: DiffRenderer } = await import(`${cli}render.mjs`);
  const r = new DiffRenderer({ out: { write: (x) => { drawn += x; } }, columns: () => 60, cwd: dir });
  r.update({ sessionUpdate: 'tool_call', toolCallId: 't1', title: 'edit', rawInput: { file_path: 'app.py', old_string: 'return a + b', new_string: 'return a - b' } });
  wf(pj(dir, 'app.py'), 'def add(a, b):\n    return a - b\n');
  r.update({ sessionUpdate: 'tool_call_update', toolCallId: 't1', status: 'completed', content: [] });
  const shown = drawn.split('\n');
  check('edit shows Updated with counts', shown.some((l) => l.includes('Updated') && l.includes('app.py') && l.includes('+1') && l.includes('-1')), drawn);
  check('edit shows numbered - and + rows', shown.some((l) => /2 - {5}return a \+ b/.test(l)) && shown.some((l) => /2 \+ {5}return a - b/.test(l)), drawn);
  drawn = '';
  r.update({ sessionUpdate: 'tool_call', toolCallId: 't2', title: 'write', rawInput: { file_path: 'new.txt', content: 'hello' } });
  wf(pj(dir, 'new.txt'), 'hello\n');
  r.update({ sessionUpdate: 'tool_call_update', toolCallId: 't2', status: 'completed', content: [] });
  check('write of a new file shows Created', drawn.includes('Created') && drawn.includes('1 + hello'), drawn);
}

// Expand / collapse diffs: ctrl or alt with = / + / -, whatever sequence the terminal sends.
const { diffKey } = await import(`${cli}tui/composer.mjs`);
check('ctrl/alt + = + map to expand', ['\x1b=', '\x1b+', '\x1b[61;5u'].every((seq) => diffKey({ sequence: seq }) === 'expand'));
check('ctrl/alt + - map to collapse', ['\x1b-', '\x1f', '\x1b[45;5u'].every((seq) => diffKey({ sequence: seq }) === 'collapse'));
check('plain = and - are just text', diffKey({ sequence: '=' }) === undefined && diffKey({ sequence: '-' }) === undefined);
{
  const { mkdtempSync, writeFileSync: wf } = await import('node:fs');
  const { tmpdir } = await import('node:os');
  const { join: pj } = await import('node:path');
  const dir = mkdtempSync(pj(tmpdir(), 'plexar-expand-'));
  const { Renderer: R3 } = await import(`${cli}render.mjs`);
  let drawn = '';
  const r = new R3({ out: { write: (x) => { drawn += x; } }, columns: () => 60, cwd: dir });
  r.update({ sessionUpdate: 'tool_call', toolCallId: 'e1', title: 'write', rawInput: { file_path: 'big.txt', content: 'x' } });
  wf(pj(dir, 'big.txt'), Array.from({ length: 40 }, (_, i) => 'row ' + i).join('\n'));
  r.update({ sessionUpdate: 'tool_call_update', toolCallId: 'e1', status: 'completed', content: [] });
  check('diff is capped by default', drawn.includes('more lines') && !drawn.includes('row 39'), drawn);
  drawn = '';
  check('expand redraws the last diff in full', r.expandDiffs() && drawn.includes('row 39') && !drawn.includes('more lines'), drawn);
  r.collapseDiffs();
  r.update({ sessionUpdate: 'tool_call', toolCallId: 'e2', title: 'write', rawInput: { file_path: 'big2.txt', content: 'x' } });
  wf(pj(dir, 'big2.txt'), Array.from({ length: 40 }, (_, i) => 'row ' + i).join('\n'));
  drawn = '';
  r.update({ sessionUpdate: 'tool_call_update', toolCallId: 'e2', status: 'completed', content: [] });
  check('collapse caps later diffs again', drawn.includes('more lines'), drawn);
}

const { Renderer } = await import(`${cli}render.mjs`);
let rendered = '';
const renderer = new Renderer({ out: { write: (s) => { rendered += s; } }, columns: () => 50 });
renderer.update({ sessionUpdate: 'agent_message_chunk', content: { type: 'text', text: 'I cannot rename the current session because there is no rename operation among the tools available here.\n\nSecond paragraph.' } });
renderer.endTurn('end_turn', 1000);
const plain = rendered.replace(/\x1b\[[0-9;]*m/g, '').split('\n');
check('answer rows fit 50 columns', plain.every((l) => l.length <= 50), plain.join('\n'));
check('answer starts under a bullet and continues indented', plain[0].startsWith('● ') && plain[1].startsWith('  ') && !plain[1].startsWith('   '), plain.join('\n'));

const { explain } = await import(`${cli}errors.mjs`);
check('rig loading error reads as a sentence', explain(new Error('turn failed: 503: {"message":"Model x is not ready: loading model weights (55%).","type":"engine_unavailable"}')) === 'The Plexar rig is still loading the model (55%). Try again in a moment.');
check('unknown errors pass through', explain(new Error('boom')) === 'boom');
check('a revoked key mid-turn reads as the revocation copy', explain(new Error('session/prompt: Internal error: turn failed: 403 {"error":{"code":"product_not_granted"}}')) === 'Plexar Harness access was revoked. Ask the Plexar owner.');
check('a 401 asks the person to sign in again', explain(new Error('turn failed: 401 Unauthorized')) === 'Please sign in again: plexar-harness login');
const { rpcErrorMessage } = await import(`${cli}acp.mjs`);
check('a bare Internal error carries the SDK details', rpcErrorMessage('session/new', { message: 'Internal error', data: { details: 'model x is not served' } }) === 'session/new: Internal error: model x is not served');
check('details already in the message are not repeated', rpcErrorMessage('session/prompt', { message: 'Internal error: turn failed: boom', data: { details: 'boom' } }) === 'session/prompt: Internal error: turn failed: boom');

const { spawnSync } = await import('node:child_process');
const { fileURLToPath } = await import('node:url');
const env = { ...process.env };
delete env.PLEXAR_HARNESS_KEY;
// Signed-out case only: once this computer holds a signed-in key, the gate would ask plexar-llm instead.
const { loadKey } = await import(`${cli}credentials.mjs`);
if (!loadKey()) {
  const noKey = spawnSync(process.execPath, [fileURLToPath(`${cli}plexar-harness.mjs`), '-p', 'hi'], { env, encoding: 'utf8' });
  check('no key: exits 1 and says to sign in', noKey.status === 1 && noKey.stderr.includes('Not signed in. Run: plexar-harness login'),
    `${noKey.status} ${noKey.stderr}`);
} else {
  console.log('SKIP no key: this computer is signed in');
}

console.log(fails.length ? `GATE FAIL ${fails.length}` : 'GATE PASS');
process.exit(fails.length ? 1 : 0);
