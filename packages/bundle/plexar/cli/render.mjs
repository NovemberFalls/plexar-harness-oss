/** Terminal rendering of ACP `session/update` events: thought, answer, tool calls, usage. */
import { readFileSync } from 'node:fs';
import { isAbsolute, resolve } from 'node:path';
import { lineDiff, renderDiff } from './diff.mjs';

const color = process.stdout.isTTY && !process.env.NO_COLOR;
const sgr = (open, close) => (text) => (color ? `\x1b[${open}m${text}\x1b[${close}m` : String(text));

/** ANSI styles; plain text when stdout is not a TTY or `NO_COLOR` is set. */
export const style = {
  bold: sgr('1', '22'),
  dim: sgr('2', '22'),
  italic: sgr('3', '23'),
  red: sgr('31', '39'),
  green: sgr('32', '39'),
  yellow: sgr('33', '39'),
  accent: sgr('38;2;255;140;40', '39'),
  code: sgr('38;5;180', '39'),
};

const TOOL_OUTPUT_LINES = 4;
/** Diff rows shown under an edit or write before `… N more lines`. */
const DIFF_ROWS = 16;

/** The file an edit or write tool call changes, or undefined for any other call. */
function editedFile(rawInput) {
  if (!rawInput || typeof rawInput.file_path !== 'string') return undefined;
  const edits = typeof rawInput.old_string === 'string' || typeof rawInput.content === 'string';
  return edits ? rawInput.file_path : undefined;
}

function readOrEmpty(path) {
  try {
    return readFileSync(path, 'utf8');
  } catch {
    // A file the call is about to create does not exist yet: its before-state is empty.
    return '';
  }
}
const GUTTER = 2;

/**
 * Word-wrap one plain line to `width` columns; words longer than a row are split.
 * @param {string} line - text without escapes
 * @param {number} width - columns available after the gutter
 * @returns {string[]} one or more rows
 */
export function wrap(line, width) {
  if (line.length <= width) return [line];
  const rows = [];
  let row = '';
  for (const word of line.split(/(\s+)/)) {
    if (row.length + word.length <= width) {
      row += word;
      continue;
    }
    if (row.trim()) rows.push(row.trimEnd());
    row = word.trimStart();
    while (row.length > width) {
      rows.push(row.slice(0, width));
      row = row.slice(width);
    }
  }
  if (row.trim() || rows.length === 0) rows.push(row.trimEnd());
  return rows;
}
const ARG_KEYS = ['file_path', 'path', 'command', 'pattern', 'query', 'url', 'name', 'skill'];

/** Inline markdown: `code`, **bold**. */
function inline(line) {
  return line
    .replace(/`([^`]+)`/g, (_, c) => style.code(c))
    .replace(/\*\*([^*]+)\*\*/g, (_, b) => style.bold(b));
}

function compact(n) {
  if (n >= 100000) return `${Math.round(n / 1000)}k`;
  return n >= 1000 ? `${(n / 1000).toFixed(1).replace(/\.0$/, '')}k` : String(n);
}

const seconds = (ms) => `${(ms / 1000).toFixed(1)}s`;

/**
 * The startup timing line text, e.g. `startup: sign-in 0.4s · harness 3.1s · session 0.6s`.
 * @param {{name: string, ms: number}[]} phases measured startup phases, in order
 * @returns {string} the plain line, or '' when no phase was measured
 */
export function formatStartup(phases) {
  if (!phases.length) return '';
  return `startup: ${phases.map((p) => `${p.name} ${seconds(p.ms)}`).join(' · ')}`;
}

/**
 * Output rate from a context-usage delta over the generation time.
 * @param {number|undefined} tokens `used` growth during the turn; undefined without a usage update
 * @param {number|undefined} generationMs time from first token to turn end; undefined without a first token
 * @returns {number|undefined} tokens per second, or undefined when it cannot be computed
 */
export function outputRate(tokens, generationMs) {
  if (tokens === undefined || generationMs === undefined || tokens <= 0 || generationMs <= 0) return undefined;
  return tokens / (generationMs / 1000);
}

/**
 * The end-of-turn status line text, e.g. `12.3k/32k ctx (38%) · 8.2s · first token 1.4s · 41 tok/s`.
 * @param {{used: number, size: number, elapsedMs: number, firstTokenMs?: number, rate?: number, stopReason?: string}} turn
 * @returns {string} the plain line; context, first token and rate parts are omitted when unknown
 */
export function formatTurnLine({ used, size, elapsedMs, firstTokenMs, rate, stopReason }) {
  const parts = [];
  if (size) parts.push(`${compact(used)}/${compact(size)} ctx (${Math.round((used / size) * 100)}%)`);
  parts.push(seconds(elapsedMs));
  if (firstTokenMs !== undefined) parts.push(`first token ${seconds(firstTokenMs)}`);
  if (rate !== undefined) parts.push(`${Math.round(rate)} tok/s`);
  if (stopReason && stopReason !== 'end_turn') parts.push(stopReason);
  return parts.join(' · ');
}

function toolArgs(rawInput) {
  if (!rawInput || typeof rawInput !== 'object') return '';
  const key = ARG_KEYS.find((k) => typeof rawInput[k] === 'string');
  const value = key ? rawInput[key] : JSON.stringify(rawInput);
  const oneLine = value.replace(/\s+/g, ' ');
  return oneLine.length > 90 ? `${oneLine.slice(0, 87)}...` : oneLine;
}

function toolText(content) {
  if (!Array.isArray(content)) return '';
  return content
    .map((item) => (item?.content?.type === 'text' ? item.content.text : item?.type === 'diff' ? `edited ${item.path}` : ''))
    .filter(Boolean)
    .join('\n')
    .replace(/<\/?(path|type|content)>/g, '')
    .trim();
}

/** Streams one session's updates to a writable stream, one turn at a time. */
export class Renderer {
  /**
   * @param {{out?: NodeJS.WritableStream, showThinking?: boolean}} [options]
   */
  constructor({ out = process.stdout, statusOut = out, showThinking = true, columns = () => process.stdout.columns || 100, cwd = process.cwd() } = {}) {
    this.cwd = cwd;
    /** Diff rows drawn per edit: `DIFF_ROWS`, or every row after `expandDiffs()`. */
    this.diffRows = DIFF_ROWS;
    /** The most recent edit's diff, kept so `expandDiffs()` can redraw it in full. */
    this.lastDiff = undefined;
    /** Before-snapshots of files that edit/write calls in flight will change, by tool call id. */
    this.snapshots = new Map();
    this.out = out;
    /** Where the end-of-turn status line goes; null drops it. */
    this.statusOut = statusOut;
    this.columns = columns;
    this.showThinking = showThinking;
    this.used = 0;
    this.size = 0;
    this.reset();
  }

  /** Clear per-turn state. */
  reset() {
    this.promptAt = Date.now();
    this.firstTokenAt = undefined;
    this.usedAtStart = this.used;
    this.usageSeen = false;
    this.block = null;
    this.pendingLine = '';
    this.inFence = false;
    this.fresh = false;
    this.tools = new Map();
  }

  /** Drop leading whitespace until a block's first visible character. */
  #trimStart(text) {
    if (!this.fresh) return text;
    const trimmed = text.replace(/^\s+/, '');
    if (trimmed) this.fresh = false;
    return trimmed;
  }

  #write(text) {
    this.out.write(text);
  }

  #enter(block) {
    if (this.block === block) return;
    this.#flushLine();
    if (this.block !== null) this.#write('\n');
    this.block = block;
  }

  #flushLine() {
    if (!this.pendingLine) return;
    if (this.block === 'thought') this.#emitThoughtLine(this.pendingLine);
    else this.#emitAnswerLine(this.pendingLine);
    this.pendingLine = '';
  }

  /** Rows of one logical line under a gutter: `mark` on the block's first row, spaces after. */
  #gutterRows(line, mark) {
    return wrap(line, Math.max(this.columns() - GUTTER - 1, 20)).map((row) => {
      const prefix = this.firstRow ? mark : ' '.repeat(GUTTER);
      this.firstRow = false;
      return { prefix, row };
    });
  }

  #emitAnswerLine(line) {
    let paint;
    let text = line;
    if (/^\s*```/.test(text)) {
      this.inFence = !this.inFence;
      paint = style.dim;
    } else if (this.inFence) {
      paint = style.code;
    } else if (/^#{1,6}\s/.test(text)) {
      text = text.replace(/^#{1,6}\s/, '');
      paint = style.bold;
    } else {
      paint = inline;
    }
    for (const { prefix, row } of this.#gutterRows(text, `${style.accent('●')} `)) this.#write(`${prefix}${paint(row)}\n`);
  }

  #emitThoughtLine(line) {
    for (const { prefix, row } of this.#gutterRows(line, style.dim('✻ '))) this.#write(`${prefix}${style.dim(style.italic(row))}\n`);
  }

  /** Render one `session/update` payload. */
  update(update) {
    switch (update.sessionUpdate) {
      case 'agent_thought_chunk': {
        this.firstTokenAt ??= Date.now();
        const text = update.content?.type === 'text' ? update.content.text : '';
        if (this.block !== 'thought') {
          this.#enter('thought');
          this.pendingLine = '';
          this.fresh = true;
          this.firstRow = true;
          if (!this.showThinking) this.#write(style.dim('✻ thinking…\n'));
        }
        if (!this.showThinking) break;
        const lines = (this.pendingLine + this.#trimStart(text)).replace(/\n{3,}/g, '\n\n').split('\n');
        this.pendingLine = lines.pop();
        for (const line of lines) this.#emitThoughtLine(line);
        break;
      }
      case 'agent_message_chunk': {
        this.firstTokenAt ??= Date.now();
        const text = update.content?.type === 'text' ? update.content.text : '';
        if (this.block !== 'answer') {
          this.#enter('answer');
          this.pendingLine = '';
          this.fresh = true;
          this.firstRow = true;
        }
        const lines = (this.pendingLine + this.#trimStart(text)).split('\n');
        this.pendingLine = lines.pop();
        for (const line of lines) this.#emitAnswerLine(line);
        break;
      }
      case 'tool_call': {
        this.#enter(`tool:${update.toolCallId}`);
        this.tools.set(update.toolCallId, update.title);
        const file = editedFile(update.rawInput);
        if (file) {
          const path = isAbsolute(file) ? file : resolve(this.cwd, file);
          this.snapshots.set(update.toolCallId, { path, file, before: readOrEmpty(path) });
        }
        this.#write(`${style.accent('●')} ${style.bold(update.title ?? 'tool')}${style.dim(`(${toolArgs(update.rawInput)})`)}\n`);
        break;
      }
      case 'tool_call_update': {
        if (update.status !== 'completed' && update.status !== 'failed') break;
        const snap = this.snapshots.get(update.toolCallId);
        this.snapshots.delete(update.toolCallId);
        if (snap && update.status === 'completed' && this.#drawDiff(snap)) {
          this.block = 'tool-done';
          break;
        }
        const text = toolText(update.content);
        const lines = text ? text.split('\n').map((l) => l.trimEnd()).filter(Boolean) : [update.status];
        const shown = lines.slice(0, TOOL_OUTPUT_LINES);
        const paint = update.status === 'failed' ? style.red : style.dim;
        shown.forEach((line, i) => this.#write(paint(`${i === 0 ? '  ⎿ ' : '    '}${line}`) + '\n'));
        if (lines.length > shown.length) this.#write(style.dim(`    … +${lines.length - shown.length} lines\n`));
        this.block = 'tool-done';
        break;
      }
      case 'usage_update':
        if (update.used !== undefined) this.usageSeen = true;
        this.used = update.used ?? this.used;
        this.size = update.size ?? this.size;
        break;
      default:
        // Plans, mode and option changes, and future kinds carry nothing this terminal view shows.
        break;
    }
  }

  /** Draw the change a completed edit/write made; false when the file did not change. */
  #drawDiff({ path, file, before }) {
    const after = readOrEmpty(path);
    if (after === before) return false;
    this.lastDiff = { file, before, after };
    this.#writeDiff(this.lastDiff, this.diffRows);
    return true;
  }

  #writeDiff({ file, before, after }, maxRows) {
    const { lines, added, removed } = renderDiff(lineDiff(before, after), {
      width: this.columns() - 1, maxRows, color,
    });
    const verb = before === '' ? 'Created' : 'Updated';
    const counts = [added ? style.green(`+${added}`) : '', removed ? style.red(`-${removed}`) : ''].filter(Boolean).join(' ');
    this.#write(`  ⎿ ${verb} ${style.bold(file)} ${counts}\n`);
    for (const line of lines) this.#write(`${line}\n`);
  }

  /**
   * Show later edits in full and redraw the most recent one in full.
   * @returns {boolean} whether there was a diff to redraw
   */
  expandDiffs() {
    this.diffRows = Infinity;
    if (!this.lastDiff) return false;
    this.#write(style.dim(`  full diff of ${this.lastDiff.file}:\n`));
    this.#writeDiff(this.lastDiff, Infinity);
    return true;
  }

  /** Show later edits capped at `DIFF_ROWS` rows again. */
  collapseDiffs() {
    this.diffRows = DIFF_ROWS;
  }

  /** Finish the turn: flush the answer and print the usage line. */
  endTurn(stopReason, elapsedMs) {
    this.#flushLine();
    const firstTokenMs = this.firstTokenAt === undefined ? undefined : this.firstTokenAt - this.promptAt;
    const rate = outputRate(this.usageSeen ? this.used - this.usedAtStart : undefined, firstTokenMs === undefined ? undefined : elapsedMs - firstTokenMs);
    const line = formatTurnLine({ used: this.used, size: this.size, elapsedMs, firstTokenMs, rate, stopReason });
    const text = style.dim(`  ${line}`) + '\n';
    if (this.statusOut === this.out) this.#write(text);
    else this.statusOut?.write(text);
    this.reset();
  }
}
