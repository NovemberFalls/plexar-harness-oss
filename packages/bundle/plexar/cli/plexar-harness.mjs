#!/usr/bin/env node
/**
 * `plexar-harness`: interactive terminal client for Plexar Harness.
 * Runs the `plexar-acp` profile in the current folder and speaks ACP to it, so sessions are the same
 * ones Studio and the Web UI list. Reference: docs/plexar/08-cli.md.
 */
import { spawnSync } from 'node:child_process';
import { readFileSync, readdirSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { createInterface } from 'node:readline';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import { HarnessRuntime, harnessRoot } from './acp.mjs';
import { GATE_EXEMPT_COMMANDS, checkGate, login, logout } from './auth.mjs';
import { explain } from './errors.mjs';
import { attention, header } from './logo.mjs';
import { Renderer, style } from './render.mjs';
import { MODES, isTrusted, load, save } from './settings.mjs';
import { runUpdate, updateNotice } from './update.mjs';
import { Composer, diffKey } from './tui/composer.mjs';
import { pushKeys, startKeys, stopKeys } from './tui/keys.mjs';
import { select } from './tui/select.mjs';
import { NOTICE as SIGNIN_NOTICE, SIGNED_OUT_MESSAGES, SignInState } from './tui/signin.mjs';
import { Screen, Spinner } from './tui/spinner.mjs';
import { PALETTE, dim as tdim, fg } from './tui/term.mjs';

const VERSION = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8')).version;
const EFFORTS = { off: 'off', high: 'high', default: '' };
const CLEAR = '\x1b[2J\x1b[3J\x1b[H';
const MODE_COLOR = {
  ask: (t) => fg(PALETTE.orangeLight, t),
  'auto-edit': (t) => fg(PALETTE.orange, t),
  'full-access': (t) => fg([235, 70, 60], t),
};

/** Slash commands the client runs itself, for the `/` menu. */
const LOCAL_COMMANDS = [
  { name: 'help', description: 'list commands' },
  { name: 'mode', description: 'show or set permissions (ask, auto-edit, full-access)' },
  { name: 'model', description: 'show or set the model' },
  { name: 'effort', description: 'reasoning effort: off, high or default' },
  { name: 'new', description: 'start a fresh session' },
  { name: 'sessions', description: 'list resumable sessions in this folder' },
  { name: 'resume', description: 'resume a listed session' },
  { name: 'thinking', description: 'show or collapse thinking' },
  { name: 'clear', description: 'clear the screen' },
  { name: 'exit', description: 'quit' },
  { name: 'login', description: 'sign in to Plexar in your browser' },
  { name: 'logout', description: 'sign out and remove the stored key' },
];

/** Commands registered in the harness itself (run over ACP), for the `/` menu. */
const HARNESS_COMMANDS = [
  { name: 'rename', description: 'rename this session: /rename <title>' },
  { name: 'compact', description: 'condense older history into a summary' },
  { name: 'goal', description: 'set or show the session goal' },
  { name: 'permission', description: 'harness permission preset (same as /mode)' },
  { name: 'feedback', description: 'send feedback on this session' },
];

/** Plexar skills from the bundle's skills folder; typing one asks the model to load it. */
function skillCommands() {
  const dir = new URL('../skills/', import.meta.url);
  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true }).filter((entry) => entry.isDirectory());
  } catch (error) {
    // No skills folder in this checkout: the menu lists commands only.
    if (error.code === 'ENOENT') return [];
    throw error;
  }
  return entries.map((entry) => {
    let description = 'Plexar skill';
    try {
      const head = readFileSync(new URL(`${entry.name}/SKILL.md`, dir), 'utf8').slice(0, 2000);
      description = /^description:\s*(.+)$/m.exec(head)?.[1]?.replace(/^['"]|['"]$/g, '') ?? description;
    } catch (error) {
      // A skill folder without a readable SKILL.md still lists by name.
      description = `Plexar skill (${error.code ?? 'unreadable'})`;
    }
    return { name: entry.name, description };
  });
}

const HELP = `Usage: plexar-harness [options] [prompt]

  plexar-harness                interactive session in the current folder
  plexar-harness "task"         interactive, starting with this prompt
  plexar-harness -p "task"      one turn, print the answer, exit
  plexar-harness -c             resume the newest session in this folder
  plexar-harness --resume <id>  resume a session by id
  plexar-harness export <id>    print a session as text
  plexar-harness acp            run the ACP profile on stdio (for Plexar Studio)
  plexar-harness update         pull the latest harness, reinstall, rebuild
  plexar-harness web            open the browser UI (--port N, --no-open)
  plexar-harness login          sign in to Plexar (--no-browser for a pasted code)
  plexar-harness logout         sign out and remove the stored key

Options:
  -p, --print         run one turn non-interactively and exit
  -c, --continue      resume the newest session in this folder
  -r, --resume <id>   resume the given session
  -e, --effort <lvl>  reasoning effort: off | high | default
      --model <id>    model for this session (value, name, or id after provider/)
  -m, --mode <mode>   permissions: ask | auto-edit | full-access
      --read-only     same as --mode ask
      --no-thinking   collapse thinking to one line
      --cwd <dir>     workspace folder (default: current folder)
  -v, --version       print the version
  -h, --help          print this help
`;

const COMMANDS = `Commands:
  /help                 this list
  /new                  start a fresh session
  /sessions             list resumable sessions in this folder
  /resume <n|id>        resume a listed session
  /mode [ask|auto-edit|full-access]  show or set permissions (Shift+Tab cycles)
  /compact, /goal, ...  other slash commands run in the harness itself
  /model [value]        show or set the model
  /effort [off|high|default]  show or set reasoning effort
  /thinking [on|off]    show or collapse thinking
  /clear                clear the screen
  /exit                 quit (Ctrl-D also quits)
  /login                sign in to Plexar in your browser
  /logout               sign out and remove the stored key
`;

/** The model id inside an option value, which ACP encodes as a JSON `[provider, model]` pair. */
function modelId(value) {
  try {
    const pair = JSON.parse(value);
    return Array.isArray(pair) ? String(pair.at(-1)) : value;
  } catch {
    // Not JSON: the value is already a bare id.
    return value;
  }
}

/** A model option matching its value, display name, or bare model id. */
function findModel(configOptions, arg) {
  const lower = arg.toLowerCase();
  return optionValues(configOptions, 'model').find((v) => v.value === arg || v.name.toLowerCase() === lower || modelId(v.value) === arg);
}

function parseCli() {
  const { values, positionals } = parseArgs({
    allowPositionals: true,
    options: {
      print: { type: 'boolean', short: 'p' },
      continue: { type: 'boolean', short: 'c' },
      resume: { type: 'string', short: 'r' },
      effort: { type: 'string', short: 'e' },
      model: { type: 'string' },
      mode: { type: 'string', short: 'm' },
      'read-only': { type: 'boolean' },
      'no-thinking': { type: 'boolean' },
      cwd: { type: 'string' },
      version: { type: 'boolean', short: 'v' },
      help: { type: 'boolean', short: 'h' },
    },
  });
  if (values.effort !== undefined && !(values.effort in EFFORTS)) {
    throw new Error(`--effort must be one of ${Object.keys(EFFORTS).join(', ')}`);
  }
  if (values['read-only']) values.mode = 'ask';
  // One unattended turn (a framework worker, a script): nobody is at the person's Chrome to
  // see its connect tab, so the browser bridge launches its own headless browser instead.
  if (values.print) process.env.PLEXAR_UNATTENDED = '1';
  if (values.mode !== undefined && !MODES.some((m) => m.id === values.mode)) {
    throw new Error(`--mode must be one of ${MODES.map((m) => m.id).join(', ')}`);
  }
  return { ...values, prompt: positionals.join(' ').trim() };
}

function optionLabel(configOptions, id) {
  const option = configOptions?.find((o) => o.id === id);
  if (!option) return '?';
  const flat = option.options.flatMap((o) => o.options ?? [o]);
  return flat.find((o) => o.value === option.currentValue)?.name ?? (option.currentValue || 'default');
}

function optionValues(configOptions, id) {
  const option = configOptions?.find((o) => o.id === id);
  return option ? option.options.flatMap((o) => o.options ?? [o]) : [];
}

const modeById = (id) => MODES.find((m) => m.id === id) ?? MODES[1];

export class App {
  /**
   * @param {object} args - parsed CLI flags (`parseCli()`'s shape).
   * @param {{runtimeFactory?: (opts: {workspace: string}) => object, checkGateFn?: typeof checkGate, loginFn?: () => Promise<{ok: boolean}>}} [deps]
   *   Test seams: `runtimeFactory` replaces `HarnessRuntime` with a fake ACP client; `checkGateFn`
   *   replaces the real entitlement check; `loginFn` replaces the real browser PKCE flow inside `/login`.
   */
  constructor(args, { runtimeFactory = (opts) => new HarnessRuntime(opts), checkGateFn = checkGate, loginFn } = {}) {
    this.args = args;
    this.runtimeFactory = runtimeFactory;
    this.checkGateFn = checkGateFn;
    this.loginFnOverride = loginFn;
    this.interactive = !args.print;
    this.tty = this.interactive && process.stdin.isTTY && process.stdout.isTTY;
    this.settings = load();
    this.updateNotice = this.interactive ? updateNotice(this.settings, save, (notice) => this.showUpdate(notice)) : undefined;
    this.workspace = args.cwd ?? process.cwd();
    // The preset last applied to the open session (none yet), and the one the user has selected.
    this.mode = undefined;
    this.pendingMode = modeById(args.mode ?? (this.interactive ? this.settings.mode : 'auto-edit'));
    this.quiet = false;
    this.screen = new Screen();
    this.spinner = new Spinner(this.screen);
    this.renderer = new Renderer({ out: this.tty ? this.screen : process.stdout, showThinking: this.interactive && !args['no-thinking'], cwd: this.workspace });
    this.menu = [...LOCAL_COMMANDS, ...HARNESS_COMMANDS, ...skillCommands()];
    this.lastInterrupt = 0;
    this.runtime = null;
    this.sessionId = null;
    this.configOptions = [];
    this.effortValue = undefined;
    this.busy = false;
    this.queue = [];
    this.listed = [];
    this.rl = null;
    this.closing = false;
    // Set only for an interactive launch: the entitlement gate is checked in place (never blocks
    // launch) and this drives the in-TUI/REPL sign-in notice and `/login` · `/logout`.
    this.signIn = null;
    this.loginAbort = null;
  }

  async run() {
    if (this.tty) startKeys();
    if (this.tty && !isTrusted(this.settings, this.workspace) && !(await this.askTrust())) {
      process.stdout.write(style.dim('Not trusted; nothing was started.\n'));
      stopKeys();
      return;
    }
    if (this.tty) {
      process.stdout.write(CLEAR);
      this.spinner.start('Waking the harness…');
    }
    // The access check runs before the host starts: the host reads PLEXAR_HARNESS_KEY and the model
    // lists from its env once, at spawn, so the saved sign-in must be applied first.
    if (this.interactive) await this.ensureSignedIn();
    await this.startRuntime();
    if (this.interactive) {
      // Signed out or unentitled: the host has no key, so `session/new` would fail; the notice
      // below is shown instead, and `startSession()` runs again once `/login` succeeds.
      await this.startSession();
    } else {
      await this.openSession();
      await this.applyMode();
      if (this.args.model !== undefined) {
        const match = findModel(this.configOptions, this.args.model);
        if (!match) throw new Error(`unknown model ${this.args.model}; available: ${optionValues(this.configOptions, 'model').map((v) => modelId(v.value)).join(', ')}`);
        await this.setOption('model', match.value, false);
      }
      if (this.args.effort !== undefined) await this.setEffort(this.args.effort, false);
    }
    if (this.tty) this.spinner.stop();

    if (!this.interactive) {
      const text = this.args.prompt || (await readStdin());
      if (!text) throw new Error('-p needs a prompt argument or stdin');
      const result = await this.turn(text);
      await this.shutdown();
      if (result.stopReason === 'max_tokens') process.stderr.write('plexar-harness: the model reply hit its output-token limit (reasoning counts toward it); the turn stopped unfinished\n');
      process.exitCode = result.stopReason === 'end_turn' ? 0 : 1;
      return;
    }

    this.drawHeader();
    if (this.tty) return this.tuiLoop();
    this.startRepl();
    if (this.signIn?.blocked) this.printNotice(this.signIn.notice);
    if (this.args.prompt) this.enqueue(this.args.prompt);
    else this.rl.prompt();
    return undefined;
  }

  /** Terminal UI: framed composer, `/` menu, animated turns, arrow-key prompts. */
  async tuiLoop() {
    this.composer = new Composer({
      commands: () => this.menu,
      status: () => this.statusLine(),
      onShiftTab: () => this.cycleModeTui(),
      onInterrupt: () => this.interruptIdle(),
      onEof: () => this.exit(),
      onClear: () => this.drawHeader(),
      onDiffKey: (action) => this.diffKey(action),
    });
    // While a turn runs the composer is closed; this handler keeps Ctrl-C and Shift+Tab live.
    pushKeys((_text, key) => {
      if (diffKey(key)) {
        this.diffKey(diffKey(key));
      } else if (this.loginAbort && key.name === 'escape') {
        this.loginAbort.abort();
      } else if ((key.ctrl && key.name === 'c') || key.name === 'escape') {
        this.runtime?.cancel(this.sessionId);
        this.screen.write(fg(PALETTE.orangeLight, '\n  cancelling…\n'));
      } else if (key.name === 'tab' && key.shift) {
        this.cycleModeTui();
      }
    });
    if (this.signIn?.blocked) this.printNotice(this.signIn.notice);
    if (this.args.prompt) await this.handleLine(this.args.prompt);
    for (;;) await this.handleLine(await this.composer.read());
  }

  /** Expand or collapse edit diffs from a keypress (idle or during a turn). */
  diffKey(action) {
    if (action === 'expand') {
      if (!this.renderer.expandDiffs()) process.stdout.write(tdim('  diffs will show in full · ctrl+- (alt+-) to collapse\n'));
    } else {
      this.renderer.collapseDiffs();
      process.stdout.write(tdim('  diffs collapsed to 16 rows · ctrl+= (alt+=) to expand\n'));
    }
  }

  /** Show an update notice the background check found after the header was drawn. */
  showUpdate(notice) {
    if (notice === this.updateNotice) return;
    this.updateNotice = notice;
    if (this.composer?.active) {
      this.composer.erase();
      process.stdout.write(`  ${fg(PALETTE.orange, notice)}\n`);
      this.composer.draw();
    } else if (!this.busy) {
      process.stdout.write(`  ${fg(PALETTE.orange, notice)}\n`);
    }
  }

  statusLine() {
    if (Date.now() - this.lastInterrupt < 2000) return tdim('press ctrl-c again to exit');
    const color = MODE_COLOR[this.pendingMode.id];
    return `${color('››')} ${color(this.pendingMode.label)} on ${tdim('· shift+tab to cycle · / for commands · ? for shortcuts')}`;
  }

  cycleModeTui() {
    const index = MODES.indexOf(this.pendingMode);
    this.pendingMode = MODES[(index + 1) % MODES.length];
    this.settings.mode = this.pendingMode.id;
    save(this.settings);
    this.composer?.draw();
  }

  interruptIdle() {
    if (Date.now() - this.lastInterrupt < 2000) return this.exit();
    this.lastInterrupt = Date.now();
    this.composer.draw();
    setTimeout(() => this.composer?.draw(), 2100);
    return undefined;
  }

  /** Slash commands runnable while `this.signIn` is blocked; anything else refuses with the notice. */
  static SIGNED_OUT_ALLOWED = new Set(['login', 'logout', 'help', '?', 'clear']);

  async handleLine(raw) {
    const line = raw.trim();
    if (!line) {
      if (this.signIn?.blocked && !this.signIn.busy) await this.command('/login');
      else if (!this.sessionId) await this.startSession();
      return;
    }
    if (/^(exit|quit)$/i.test(line)) {
      await this.exit();
      return;
    }
    if (this.signIn?.blocked) {
      const name = line.startsWith('/') ? line.slice(1).split(/\s+/)[0].toLowerCase() : undefined;
      if (!name || !App.SIGNED_OUT_ALLOWED.has(name)) {
        this.printNotice(this.signIn.notice);
        return;
      }
    } else if (!this.sessionId) {
      const name = line.startsWith('/') ? line.slice(1).split(/\s+/)[0].toLowerCase() : undefined;
      if (!name || !App.SIGNED_OUT_ALLOWED.has(name)) {
        await this.startSession();
        if (!this.sessionId) return;
      }
    }
    this.busy = true;
    try {
      if (line.startsWith('/')) await this.command(line);
      else await this.turn(line);
    } catch (error) {
      this.spinner.stop();
      process.stdout.write(style.red(`  ${explain(error)}\n\n`));
    } finally {
      this.busy = false;
    }
  }

  drawHeader() {
    const out = header({
      version: VERSION,
      model: optionLabel(this.configOptions, 'model'),
      effort: optionLabel(this.configOptions, 'reasoning_effort').toLowerCase().replace('provider default', 'default'),
      cwd: this.runtime.workspace,
    });
    const hint = this.tty ? '' : style.dim('  /help for commands · shift+tab cycles permissions · ctrl-c cancels a turn\n\n');
    const notice = this.updateNotice ? `  ${fg(PALETTE.orange, this.updateNotice)}

` : '';
    process.stdout.write(`${this.tty ? CLEAR : ''}${out}${notice}${hint}`);
  }

  /** Folder-trust gate, asked once per folder (or parent) and remembered in the settings file. */
  async askTrust() {
    process.stdout.write(
      `${CLEAR}\n${attention([
        style.bold('Do you trust the files in this folder?'),
        this.workspace,
        style.dim('Plexar Harness can read, edit and run files here.'),
        style.dim('Only trust folders whose contents you know.'),
      ])}\n`,
    );
    const choice = await select({ title: 'Trust this folder?', icon: '!', options: ['Yes, trust this folder', 'No, exit'] });
    if (choice !== 0) return false;
    this.settings.trusted.push(this.workspace);
    save(this.settings);
    return true;
  }

  async startRuntime() {
    const runtime = this.runtimeFactory({ workspace: this.workspace });
    runtime.on('update', (sessionId, update) => {
      if (runtime === this.runtime && sessionId === this.sessionId && !this.quiet) this.renderer.update(update);
    });
    runtime.on('permission', (params, reply) => this.askPermission(params, reply));
    runtime.on('exit', (code) => {
      if (runtime === this.runtime && !this.closing) {
        process.stderr.write(style.red(`\nharness exited (${code}): ${runtime.stderrTail.slice(-5).join('\n')}\n`));
        process.exit(1);
      }
    });
    this.runtime = runtime;
    await runtime.start();
  }

  /**
   * Put the open session under the selected permission preset with the harness `/permission` command.
   * The switch is recorded in that session's log and takes effect on its next tool call; no restart.
   */
  async applyMode() {
    if (this.pendingMode === this.mode) return;
    const next = this.pendingMode;
    this.quiet = true;
    try {
      await this.runtime.prompt(this.sessionId, `/permission ${next.env}`);
    } finally {
      this.quiet = false;
    }
    this.mode = next;
    this.settings.mode = next.id;
    save(this.settings);
  }

  /**
   * The entitlement gate, checked in place for an interactive launch: it never exits the process.
   * Ok sets the env vars the ACP host and its children read; not ok or offline leaves `this.signIn`
   * blocked (or warns and continues), and `tuiLoop`/`startRepl` show the notice.
   */
  async ensureSignedIn() {
    this.signIn = new SignInState({
      loginFn: () => this.runLogin(),
      checkGateFn: () => this.checkGateFn(),
      restartHostFn: (gate) => this.onSignedIn(gate),
    });
    const gate = this.signIn.applyGate(await this.checkGateFn());
    if (gate.warning) process.stderr.write(style.yellow(`${gate.warning}\n`));
    if (gate.ok) this.applyGateEnv(gate);
  }

  /**
   * Create the session (once), skipped entirely while signed out or unentitled: the host has no key
   * in that state, so `session/new` would fail with an internal error rather than a clean 401. A
   * `session/new` failure while signed in is shown as a notice instead of crashing the client;
   * `handleLine`/`drain` retry it on the next submitted line.
   */
  async startSession() {
    if (this.sessionId || this.signIn?.blocked) return;
    try {
      await this.openSession();
      await this.applyMode();
      if (this.args.model !== undefined) {
        const match = findModel(this.configOptions, this.args.model);
        if (match) await this.setOption('model', match.value, false);
      }
      if (this.args.effort !== undefined) await this.setEffort(this.args.effort, false);
    } catch (error) {
      this.sessionId = null;
      this.printNotice(`Could not start a session: ${explain(error)}. Press Enter to retry.`);
    }
  }

  /**
   * Apply an `-e`/`/effort` name. `default` sends the provider-default value only when the current
   * model lists one; models whose efforts come from Plexar list only their levels, so `default`
   * keeps the model's preselected effort instead of sending a value the host rejects. A model with
   * no effort option (no reasoning levels) ignores every name.
   * @param {'off'|'high'|'default'} name
   * @param {boolean} announce - passed through to `setOption`.
   */
  async setEffort(name, announce) {
    const value = EFFORTS[name];
    const levels = optionValues(this.configOptions, 'reasoning_effort');
    if (levels.length === 0 || (name === 'default' && !levels.some((o) => o.value === value))) {
      if (announce) process.stdout.write(style.dim(`  effort: ${optionLabel(this.configOptions, 'reasoning_effort')} (this model's default)\n`));
      return undefined;
    }
    return this.setOption('reasoning_effort', value, announce);
  }

  /** Set the env vars the ACP host (and the `plexar` provider inside it) read for the signed-in key and model lists. */
  applyGateEnv(gate) {
    process.env.PLEXAR_HARNESS_KEY = gate.key;
    if (gate.models !== undefined) process.env.PLEXAR_HARNESS_MODELS = JSON.stringify(gate.models);
    if (gate.allModels !== undefined) process.env.PLEXAR_HARNESS_ALL_MODELS = JSON.stringify(gate.allModels);
  }

  /** `SignInState`'s `loginFn`: the loopback PKCE flow, Esc-cancellable while it waits on the browser. */
  async runLogin() {
    if (this.loginFnOverride) return this.loginFnOverride();
    this.loginAbort = new AbortController();
    this.printNotice(SIGNIN_NOTICE.waiting);
    try {
      const code = await login({ signal: this.loginAbort.signal });
      return { ok: code === 0 };
    } finally {
      this.loginAbort = null;
    }
  }

  /**
   * `SignInState`'s `restartHostFn`: apply the new gate's env vars, then restart the ACP host child
   * so it inherits the key, resuming the session that was open.
   */
  async onSignedIn(gate) {
    this.applyGateEnv(gate);
    const resumeId = this.sessionId;
    // `runtime`'s own `exit` handler treats an unexpected child exit as fatal unless `closing` is
    // set, same as `shutdown()`; this restart is intentional, so it borrows that flag too.
    this.closing = true;
    await this.runtime.stop();
    this.closing = false;
    await this.startRuntime();
    this.mode = undefined;
    if (resumeId) {
      const result = await this.runtime.resumeSession(resumeId);
      this.sessionId = resumeId;
      this.configOptions = result?.configOptions ?? this.configOptions;
      await this.applyMode();
    } else {
      // No session existed yet (the signed-out start skipped `session/new`): create the first one
      // now that the host has a key, applying any `--model`/`--effort` launch flags too.
      this.sessionId = null;
      await this.startSession();
    }
  }

  /** Print a styled notice, working around an open composer frame the way `showUpdate` does. */
  printNotice(text) {
    if (this.composer?.active) {
      this.composer.erase();
      process.stdout.write(`  ${fg(PALETTE.orange, text)}\n`);
      this.composer.draw();
    } else {
      process.stdout.write(`  ${fg(PALETTE.orange, text)}\n`);
    }
  }

  async openSession() {
    let id = this.args.resume;
    if (!id && this.args.continue) {
      id = (await this.runtime.listSessions()).sessions?.[0]?.sessionId;
      if (!id) process.stderr.write(style.yellow('no earlier session in this folder; starting a new one\n'));
    }
    if (id) {
      const result = await this.runtime.resumeSession(id);
      this.sessionId = id;
      this.configOptions = result?.configOptions ?? this.configOptions;
      return;
    }
    const created = await this.runtime.newSession();
    this.sessionId = created.sessionId;
    this.configOptions = created.configOptions ?? [];
  }

  promptText() {
    return `${MODE_COLOR[this.pendingMode.id](this.pendingMode.id)} ${style.accent('›')} `;
  }

  cycleMode() {
    const index = MODES.indexOf(this.pendingMode);
    this.pendingMode = MODES[(index + 1) % MODES.length];
    this.settings.mode = this.pendingMode.id;
    save(this.settings);
    // Readline inserted the Shift+Tab sequence before this listener ran; drop it from the edit line.
    this.rl.line = this.rl.line.replace(/\x1b\[Z|\t/g, '');
    this.rl.cursor = Math.min(this.rl.cursor, this.rl.line.length);
    this.rl.setPrompt(this.promptText());
    process.stdout.write(`\r\x1b[2K${style.dim(`  ${this.pendingMode.label}: ${this.pendingMode.hint}`)}\n`);
    this.rl.prompt(true);
  }

  startRepl() {
    this.rl = createInterface({ input: process.stdin, output: process.stdout, prompt: this.promptText(), historySize: 500 });
    let lastInterrupt = 0;
    this.rl.on('line', (line) => this.enqueue(line));
    if (this.tty) {
      process.stdin.on('keypress', (_text, key) => {
        if (key?.name === 'tab' && key.shift && !this.busy) setImmediate(() => this.cycleMode());
      });
    }
    this.rl.on('SIGINT', () => {
      if (this.busy) {
        this.runtime?.cancel(this.sessionId);
        process.stdout.write(style.yellow('\n  cancelling…\n'));
        return;
      }
      if (Date.now() - lastInterrupt < 2000) return this.exit();
      lastInterrupt = Date.now();
      this.rl.write(null, { ctrl: true, name: 'u' });
      process.stdout.write(style.dim('\n(press Ctrl-C again to exit)\n'));
      this.rl.prompt();
    });
    this.rl.on('close', () => {
      this.stdinClosed = true;
      if (!this.busy && this.queue.length === 0) this.exit();
    });
  }

  enqueue(line) {
    this.queue.push(line);
    if (!this.busy) void this.drain();
  }

  async drain() {
    this.busy = true;
    while (this.queue.length > 0) {
      const line = this.queue.shift().trim();
      if (!line) {
        if (this.signIn?.blocked && !this.signIn.busy) await this.command('/login');
        else if (!this.sessionId) await this.startSession();
        continue;
      }
      // A bare `exit` or `quit` means the user wants out, as in `claude` and `codex`; it never reaches the model.
      if (/^(exit|quit)$/i.test(line)) return this.exit();
      if (this.signIn?.blocked) {
        const name = line.startsWith('/') ? line.slice(1).split(/\s+/)[0].toLowerCase() : undefined;
        if (!name || !App.SIGNED_OUT_ALLOWED.has(name)) {
          this.printNotice(this.signIn.notice);
          continue;
        }
      } else if (!this.sessionId) {
        const name = line.startsWith('/') ? line.slice(1).split(/\s+/)[0].toLowerCase() : undefined;
        if (!name || !App.SIGNED_OUT_ALLOWED.has(name)) {
          await this.startSession();
          if (!this.sessionId) continue;
        }
      }
      try {
        if (line.startsWith('/')) await this.command(line);
        else await this.turn(line);
      } catch (error) {
        process.stdout.write(style.red(`  ${explain(error)}\n\n`));
      }
    }
    this.busy = false;
    if (this.stdinClosed) return this.exit();
    this.rl.setPrompt(this.promptText());
    this.rl.prompt();
  }

  async turn(text) {
    await this.applyMode();
    const started = Date.now();
    this.renderer.reset();
    if (this.interactive) process.stdout.write('\n');
    if (this.tty) {
      this.screen.atLineStart = true;
      this.spinner.start();
    }
    let result;
    try {
      result = await this.runtime.prompt(this.sessionId, text);
    } finally {
      if (this.tty) this.spinner.stop();
    }
    this.renderer.endTurn(result?.stopReason, Date.now() - started);
    return result ?? {};
  }

  async command(line) {
    const [name, ...rest] = line.slice(1).split(/\s+/);
    const arg = rest.join(' ');
    const say = (text) => process.stdout.write(`${text}\n`);
    switch (name) {
      case 'help':
      case '?':
        return say(COMMANDS);
      case 'exit':
      case 'quit':
        return this.exit();
      case 'clear':
        return this.drawHeader();
      case 'new': {
        const created = await this.runtime.newSession();
        this.sessionId = created.sessionId;
        this.configOptions = created.configOptions ?? this.configOptions;
        this.mode = undefined;
        await this.applyMode();
        return say(style.dim(`  new session ${this.sessionId}\n`));
      }
      case 'sessions': {
        this.listed = ((await this.runtime.listSessions()).sessions ?? []).slice(0, 15);
        if (this.listed.length === 0) return say(style.dim('  no resumable sessions in this folder\n'));
        this.listed.forEach((s, i) => say(`  ${style.bold(String(i + 1).padStart(2))}  ${s.sessionId}${s.title ? `  ${s.title}` : ''}`));
        return say(style.dim('\n  /resume <n> to open one; the open session is not listed\n'));
      }
      case 'resume': {
        if (!arg) return say(style.yellow('  /resume <n|id>; see /sessions\n'));
        const id = /^\d+$/.test(arg) ? this.listed[Number(arg) - 1]?.sessionId : arg;
        if (!id) return say(style.yellow('  no such entry; run /sessions first\n'));
        const result = await this.runtime.resumeSession(id);
        this.sessionId = id;
        this.configOptions = result?.configOptions ?? this.configOptions;
        this.mode = undefined;
        await this.applyMode();
        return say(style.dim(`  resumed ${id}\n`));
      }
      case 'mode': {
        if (!arg) {
          MODES.forEach((m) => say(`  ${m === this.pendingMode ? style.bold('●') : ' '} ${MODE_COLOR[m.id](m.id.padEnd(12))} ${style.dim(m.hint)}`));
          return say('');
        }
        const next = MODES.find((m) => m.id === arg);
        if (!next) return say(style.yellow(`  /mode ${MODES.map((m) => m.id).join(' | ')}\n`));
        this.pendingMode = next;
        await this.applyMode();
        return say(style.dim(`  permissions → ${next.label}\n`));
      }
      case 'model': {
        const values = optionValues(this.configOptions, 'model');
        if (!arg) {
          say(`  model: ${style.bold(optionLabel(this.configOptions, 'model'))}`);
          values.forEach((v) => say(style.dim(`    ${v.name}  ${v.value}`)));
          return say('');
        }
        const match = findModel(this.configOptions, arg);
        if (!match) return say(style.yellow(`  unknown model ${arg}\n`));
        return this.setOption('model', match.value, true);
      }
      case 'effort': {
        if (!arg) return say(`  effort: ${style.bold(optionLabel(this.configOptions, 'reasoning_effort'))}  ${style.dim('(off | high | default)')}\n`);
        if (!(arg in EFFORTS)) return say(style.yellow('  /effort off | high | default\n'));
        return this.setEffort(arg, true);
      }
      case 'thinking':
        this.renderer.showThinking = arg ? arg === 'on' : !this.renderer.showThinking;
        return say(style.dim(`  thinking ${this.renderer.showThinking ? 'shown' : 'collapsed'}\n`));
      case 'login': {
        if (!this.signIn || !this.signIn.blocked) return say(style.dim('  already signed in\n'));
        const result = await this.signIn.login();
        if (!result.ok) say(style.yellow(`  ${this.signIn.notice}\n`));
        return undefined;
      }
      case 'logout': {
        await logout();
        if (this.signIn) {
          this.signIn.status = 'signed-out';
          this.signIn.reason = undefined;
        }
        delete process.env.PLEXAR_HARNESS_KEY;
        delete process.env.PLEXAR_HARNESS_MODELS;
        delete process.env.PLEXAR_HARNESS_ALL_MODELS;
        return undefined;
      }
      default:
        // Harness commands (`/compact`, `/goal`, `/permission`, ...) run in the harness; unknown ones reach the model.
        return this.turn(line);
    }
  }

  async setOption(id, value, announce) {
    const result = await this.runtime.setOption(this.sessionId, id, value);
    this.configOptions = result?.configOptions ?? this.configOptions;
    if (id === 'reasoning_effort') this.effortValue = value;
    if (announce) process.stdout.write(style.dim(`  ${id === 'model' ? 'model' : 'effort'} → ${optionLabel(this.configOptions, id)}\n\n`));
  }

  askPermission(params, reply) {
    const options = params.options ?? [];
    // The request names the call by id; the renderer saw its `tool_call` and knows the tool.
    const title = params.toolCall?.title ?? this.renderer.tools.get(params.toolCall?.toolCallId) ?? 'a tool';
    const reject = () => reply(options.find((o) => o.kind === 'reject_once')?.optionId ?? null);
    const choose = (answer) => {
      const index = answer.trim() === '' ? 0 : Number(answer.trim()) - 1;
      reply(options[index]?.optionId ?? null);
    };
    if (this.tty) {
      this.spinner.stop();
      if (!this.screen.atLineStart) process.stdout.write('\n');
      void select({ title: `Allow ${title}?`, icon: '!', options: options.map((o) => o.name) }).then((i) => {
        reply(i < 0 ? (options.find((o) => o.kind === 'reject_once')?.optionId ?? null) : options[i].optionId);
        this.screen.atLineStart = true;
        if (this.busy) this.spinner.start();
      });
      return undefined;
    }
    // `-p` has no one to ask: refuse, so a one-shot run never writes past the sandbox unattended.
    if (!this.rl) return reject();
    process.stdout.write(`\n${style.yellow('!')} ${style.bold(`Allow ${title}?`)}\n`);
    options.forEach((o, i) => process.stdout.write(`  ${style.bold(String(i + 1))}. ${o.name}\n`));
    // A line typed ahead of the prompt answers it; closed input can no longer answer, so it refuses.
    if (this.queue.length > 0) {
      const answer = this.queue.shift();
      process.stdout.write(style.dim(`  choice: ${answer.trim() || '1'}\n`));
      return choose(answer);
    }
    if (this.stdinClosed) return reject();
    this.rl.question(style.yellow(`  choose 1-${options.length} (Enter = ${options[0]?.name ?? 'cancel'}): `), choose);
  }

  async shutdown() {
    this.closing = true;
    await this.runtime?.stop();
  }

  async exit() {
    if (this.closing) return;
    this.rl?.close();
    this.spinner.stop();
    if (this.tty) stopKeys();
    if (this.sessionId) process.stdout.write(style.dim(`\nresume with: plexar-harness --resume ${this.sessionId}\n`));
    await this.shutdown();
    process.exit(0);
  }
}

async function readStdin() {
  if (process.stdin.isTTY) return '';
  let text = '';
  for await (const chunk of process.stdin) text += chunk;
  return text.trim();
}

/** `plexar-harness export ...`: run `export.ts` under the harness's tsx loader and pass its output and exit code through. */
function runExport(argv) {
  const root = harnessRoot();
  const loader = pathToFileURL(join(root, 'node_modules/tsx/dist/esm/index.mjs')).href;
  const child = spawnSync(process.execPath, ['--import', loader, fileURLToPath(new URL('./export.ts', import.meta.url)), ...argv], {
    stdio: 'inherit',
    env: { ...process.env, TSX_TSCONFIG_PATH: join(root, 'tsconfig.json') },
  });
  process.exit(child.status ?? 1);
}

// Runs only when this file is the process's entry point, not when a test imports `App` from it.
const isMain = process.argv[1] !== undefined && fileURLToPath(import.meta.url) === resolve(process.argv[1]);

if (isMain && process.argv[2] === 'export') runExport(process.argv.slice(3));
if (isMain && process.argv[2] === 'login') process.exit(await login({ noBrowser: process.argv.includes('--no-browser') }));
if (isMain && process.argv[2] === 'logout') process.exit(await logout());
if (isMain && process.argv[2] === 'update') process.exit(runUpdate());

/**
 * Entitlement gate run before starting any Host (`login`, `logout`, `update`, `--help`, `--version`
 * skip it). On success it sets `PLEXAR_HARNESS_KEY` in this process's env, which every launcher and
 * child below inherits.
 * @returns {Promise<boolean>} whether the caller may proceed.
 */
async function passGate() {
  const gate = await checkGate();
  if (!gate.ok) {
    process.stderr.write(style.red(`${gate.message}\n`));
    process.exitCode = gate.exitCode;
    return false;
  }
  if (gate.warning) process.stderr.write(style.yellow(`${gate.warning}\n`));
  process.env.PLEXAR_HARNESS_KEY = gate.key;
  // Read by the plexar provider's model list in cordis.patch.yml.
  if (gate.models !== undefined) process.env.PLEXAR_HARNESS_MODELS = JSON.stringify(gate.models);
  // Read by the plexarModels Host Remote (src/models.ts) for the Models settings page.
  if (gate.allModels !== undefined) process.env.PLEXAR_HARNESS_ALL_MODELS = JSON.stringify(gate.allModels);
  return true;
}

if (isMain) {
  // Hosts and their tool servers (python/tools) locate the harness checkout or install through this.
  process.env.PLEXAR_HARNESS_ROOT ??= harnessRoot();
  const subcommand = process.argv[2];
  if (subcommand === 'web') {
    // Not signed in on a real terminal: sign in here first, then launch, instead of just printing
    // the message (there is no in-app surface for `web` to show it in). A piped/non-TTY caller keeps
    // the plain message, since there is no one to sign in.
    let gate = await checkGate();
    if (!gate.ok && SIGNED_OUT_MESSAGES.has(gate.message) && process.stdin.isTTY) {
      if (await login() === 0) gate = await checkGate();
    }
    if (!gate.ok) {
      process.stderr.write(style.red(`${gate.message}\n`));
      process.exitCode = gate.exitCode;
    } else {
      if (gate.warning) process.stderr.write(style.yellow(`${gate.warning}\n`));
      process.env.PLEXAR_HARNESS_KEY = gate.key;
      if (gate.models !== undefined) process.env.PLEXAR_HARNESS_MODELS = JSON.stringify(gate.models);
      if (gate.allModels !== undefined) process.env.PLEXAR_HARNESS_ALL_MODELS = JSON.stringify(gate.allModels);
      const { launchWeb } = await import('./acp-launch.mjs');
      launchWeb(process.argv.slice(3));
    }
  }
  if (subcommand === 'acp') {
    if (await passGate()) {
      const { launchAcp } = await import('./acp-launch.mjs');
      await launchAcp(process.argv.slice(3));
    }
  }

  // `acp` and `web` hand the process to their own launcher above; everything below is the interactive client.
  if (!GATE_EXEMPT_COMMANDS.has(subcommand) && subcommand !== 'acp' && subcommand !== 'web' && subcommand !== 'export') try {
    const args = parseCli();
    if (args.help) process.stdout.write(HELP);
    else if (args.version) process.stdout.write(`${VERSION}\n`);
    // `-p` cannot prompt for sign-in, so it keeps the old blocking gate; the interactive client checks
    // it in place instead (`App#ensureSignedIn`), so it never exits before the composer opens.
    else if (args.print) {
      if (await passGate()) await new App(args).run();
    } else {
      await new App(args).run();
    }
  } catch (error) {
    process.stderr.write(style.red(`plexar-harness: ${explain(error)}\n`));
    process.exit(1);
  }
}
