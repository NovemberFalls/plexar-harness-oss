/**
 * The framed input box. Draws, in place below the conversation:
 *
 *   ╭──────────────────────────╮
 *   │ › Ask Plexar to do anything│
 *   ╰──────────────────────────╯
 *     ›› auto-edit on (shift+tab to cycle) · / for commands
 *     <slash-command menu while the line starts with "/">
 *
 * The terminal cursor is always left on the input row, so a redraw moves up to the block's
 * first row, clears downward, and repaints. Submitting erases the block and echoes the line.
 */
import { pushKeys } from './keys.mjs';
import { wrap } from '../render.mjs';
import { PALETTE, bold, columns, cursor, dim, fg, truncate } from './term.mjs';

const MENU_ROWS = 8;

/** The `?` panel: every key the composer and a running turn understand, in reading order. */
export const SHORTCUTS = [
  ['enter', 'send'],
  ['esc', 'clear the line · stop a running turn'],
  ['ctrl+c', 'clear the line · stop a turn · twice to quit'],
  ['ctrl+d', 'quit (on an empty line)'],
  ['shift+tab', 'cycle ask / auto-edit / full-access'],
  ['/', 'commands · tab completes'],
  ['/login  /logout', 'sign in or out of Plexar'],
  ['↑ ↓', 'history, or move in a menu'],
  ['← →  home end', 'move · ctrl+a / ctrl+e also'],
  ['ctrl+← ctrl+→', 'jump a word (alt+← alt+→ also)'],
  ['ctrl+w  ctrl+backspace', 'delete the word before the cursor'],
  ['ctrl+k  ctrl+u', 'delete to the end · clear the line'],
  ['ctrl+l', 'clear the screen'],
  ['ctrl+=  ctrl+-', 'expand · collapse diffs (alt+= alt+- if the terminal zooms)'],
  ['y  n  1-9', 'answer a prompt (yes · no · pick)'],
];

/** Key sequences for expand (ctrl/alt + `=` or `+`) and collapse (ctrl/alt + `-`); terminals differ. */
const EXPAND_KEYS = new Set(['\x1b=', '\x1b+', '\x1b[61;5u', '\x1b[43;5u', '\x1b[43;6u']);
const COLLAPSE_KEYS = new Set(['\x1b-', '\x1f', '\x1b[45;5u']);

/**
 * Whether a key asks to expand or collapse diffs.
 * @param {{sequence?: string}} key
 * @returns {'expand' | 'collapse' | undefined}
 */
export function diffKey(key) {
  if (EXPAND_KEYS.has(key.sequence)) return 'expand';
  if (COLLAPSE_KEYS.has(key.sequence)) return 'collapse';
  return undefined;
}

/** Index of the start of the word before `pos` (spaces skipped first). */
export function wordLeft(line, pos) {
  let i = pos;
  while (i > 0 && line[i - 1] === ' ') i -= 1;
  while (i > 0 && line[i - 1] !== ' ') i -= 1;
  return i;
}

/** Index just past the end of the word at or after `pos`. */
export function wordRight(line, pos) {
  let i = pos;
  while (i < line.length && line[i] === ' ') i += 1;
  while (i < line.length && line[i] !== ' ') i += 1;
  return i;
}
const PLACEHOLDER = 'Ask Plexar to do anything';

export class Composer {
  /**
   * @param {{
   *   commands: () => {name: string, description: string}[],
   *   status: () => string,
   *   onShiftTab: () => void,
   *   onInterrupt: () => void,
   *   onEof: () => void,
   *   onClear?: () => void,
   *   onDiffKey?: (action: 'expand' | 'collapse') => void,
   *   out?: NodeJS.WritableStream,
   * }} options
   */
  constructor({ commands, status, onShiftTab, onInterrupt, onEof, onClear = () => {}, onDiffKey = () => {}, out = process.stdout }) {
    Object.assign(this, { commands, status, onShiftTab, onInterrupt, onEof, onClear, onDiffKey, out });
    this.showKeys = false;
    this.history = [];
    this.historyIndex = 0;
    this.line = '';
    this.pos = 0;
    this.menuIndex = 0;
    this.drawnAbove = 0;
    this.active = false;
  }

  /** Slash commands matching the current line, or none when the menu is closed. */
  matches() {
    if (!this.line.startsWith('/') || /\s/.test(this.line)) return [];
    const typed = this.line.slice(1).toLowerCase();
    return this.commands().filter((c) => c.name.toLowerCase().startsWith(typed));
  }

  render() {
    const width = Math.max(columns() - 2, 20);
    const inner = width - 2;
    const border = (s) => fg(PALETTE.gunmetalLight, s);
    const prompt = `${fg(PALETTE.orange, '›')} `;
    const room = inner - 3;
    // The line wraps inside the box, which grows a row at a time; the caret row is where the cursor rests.
    const rows = [];
    for (let i = 0; i < this.line.length; i += room) rows.push(this.line.slice(i, i + room));
    const caretRow = Math.floor(this.pos / room);
    while (rows.length <= caretRow) rows.push('');
    const bodyRows = this.line
      ? rows.map((row, i) => `${i === 0 ? prompt : '  '}${row}${' '.repeat(room - row.length)}`)
      : [`${prompt}${dim(PLACEHOLDER)}${' '.repeat(Math.max(room - PLACEHOLDER.length, 0))}`];
    const lines = [
      border(`╭${'─'.repeat(inner)}╮`),
      ...bodyRows.map((row) => `${border('│')} ${row}${border('│')}`),
      border(`╰${'─'.repeat(inner)}╯`),
      `  ${this.status()}`,
    ];
    if (this.showKeys) {
      const keyWidth = Math.max(...SHORTCUTS.map(([k]) => k.length)) + 2;
      for (const [k, what] of SHORTCUTS) lines.push(`  ${fg(PALETTE.orange, k.padEnd(keyWidth))}${dim(what)}`);
    }
    const found = this.matches();
    if (found.length > 0) {
      this.menuIndex = Math.min(this.menuIndex, found.length - 1);
      const first = Math.max(0, Math.min(this.menuIndex - MENU_ROWS + 1, found.length - MENU_ROWS));
      const nameWidth = Math.min(Math.max(...found.map((c) => c.name.length)) + 3, 22);
      for (const [i, c] of found.slice(first, first + MENU_ROWS).entries()) {
        const selected = first + i === this.menuIndex;
        const name = `/${c.name}`.padEnd(nameWidth);
        const row = selected
          ? `  ${fg(PALETTE.orange, bold(name))} ${fg(PALETTE.orangeLight, c.description)}`
          : `  ${name} ${dim(c.description)}`;
        lines.push(truncate(row, width));
      }
    }
    // Every row must fit on one screen row: redraw moves the cursor by row count, and a row the
    // terminal wraps shifts every later move by one, leaving the old frame behind.
    return {
      lines: lines.map((line) => truncate(line, columns() - 1)),
      inputRow: 1 + caretRow,
      caretCol: 4 + this.pos - caretRow * room,
    };
  }

  draw() {
    if (!this.active) return;
    const { lines, inputRow, caretCol } = this.render();
    this.out.write(`${cursor.hide}${cursor.up(this.drawnAbove)}\r${cursor.clearDown}${lines.join('\n')}`);
    this.out.write(`${cursor.up(lines.length - 1 - inputRow)}${cursor.col(caretCol)}${cursor.show}`);
    this.drawnAbove = inputRow;
  }

  /** Remove the block, leaving the cursor where it began. */
  erase() {
    this.out.write(`${cursor.up(this.drawnAbove)}\r${cursor.clearDown}`);
    this.drawnAbove = 0;
  }

  /**
   * Show the box and resolve with the submitted line.
   * @returns {Promise<string>}
   */
  read() {
    this.line = '';
    this.pos = 0;
    this.menuIndex = 0;
    this.historyIndex = this.history.length;
    this.active = true;
    this.out.write('\n');
    this.draw();
    return new Promise((resolve) => {
      const submit = (text) => {
        release();
        this.erase();
        this.active = false;
        if (text.trim() && this.history[this.history.length - 1] !== text) this.history.push(text);
        const echo = wrap(text, Math.max(columns() - 3, 20)).map((row, i) => `${i === 0 ? fg(PALETTE.orange, '›') : ' '} ${bold(row)}`);
        this.out.write(`${echo.join('\n')}\n`);
        resolve(text);
      };
      const release = pushKeys((text, key) => this.key(text, key, submit));
    });
  }

  key(text, key, submit) {
    const found = this.matches();
    const set = (line, pos = line.length) => {
      this.line = line;
      this.pos = pos;
    };
    // `?` on an empty line toggles the shortcuts panel; any other key closes it and still acts.
    if (text === '?' && !this.line) {
      this.showKeys = !this.showKeys;
      this.draw();
      return undefined;
    }
    this.showKeys = false;
    const diffAction = diffKey(key);
    if (diffAction) {
      this.erase();
      this.onDiffKey(diffAction);
      this.drawnAbove = 0;
      this.draw();
      return undefined;
    }
    if (key.ctrl && key.name === 'c') {
      if (this.line) set('');
      else return this.onInterrupt();
    } else if (key.ctrl && key.name === 'd') {
      if (!this.line) return this.onEof();
    } else if (key.name === 'tab' && key.shift) {
      this.onShiftTab();
    } else if (key.name === 'return') {
      if (found.length > 0 && this.line !== `/${found[this.menuIndex].name}`) set(`/${found[this.menuIndex].name}`);
      return submit(this.line);
    } else if (key.name === 'tab' && found.length > 0) {
      set(`/${found[this.menuIndex].name} `);
    } else if (key.name === 'up') {
      if (found.length > 0) this.menuIndex = (this.menuIndex + found.length - 1) % found.length;
      else if (this.historyIndex > 0) set(this.history[--this.historyIndex]);
    } else if (key.name === 'down') {
      if (found.length > 0) this.menuIndex = (this.menuIndex + 1) % found.length;
      else if (this.historyIndex < this.history.length) {
        this.historyIndex += 1;
        set(this.history[this.historyIndex] ?? '');
      }
    } else if (key.name === 'escape') {
      set('');
    } else if ((key.ctrl && key.name === 'w') || ((key.ctrl || key.meta) && key.name === 'backspace')) {
      const start = wordLeft(this.line, this.pos);
      set(this.line.slice(0, start) + this.line.slice(this.pos), start);
    } else if (key.ctrl && key.name === 'k') {
      set(this.line.slice(0, this.pos), this.pos);
    } else if (key.ctrl && key.name === 'l') {
      this.onClear();
      this.drawnAbove = 0;
    } else if ((key.ctrl || key.meta) && key.name === 'left') {
      this.pos = wordLeft(this.line, this.pos);
    } else if ((key.ctrl || key.meta) && key.name === 'right') {
      this.pos = wordRight(this.line, this.pos);
    } else if (key.meta && (key.name === 'b' || key.name === 'f')) {
      this.pos = key.name === 'b' ? wordLeft(this.line, this.pos) : wordRight(this.line, this.pos);
    } else if (key.name === 'backspace') {
      if (this.pos > 0) set(this.line.slice(0, this.pos - 1) + this.line.slice(this.pos), this.pos - 1);
    } else if (key.name === 'delete') {
      set(this.line.slice(0, this.pos) + this.line.slice(this.pos + 1), this.pos);
    } else if (key.name === 'left') {
      this.pos = Math.max(0, this.pos - 1);
    } else if (key.name === 'right') {
      this.pos = Math.min(this.line.length, this.pos + 1);
    } else if (key.name === 'home' || (key.ctrl && key.name === 'a')) {
      this.pos = 0;
    } else if (key.name === 'end' || (key.ctrl && key.name === 'e')) {
      this.pos = this.line.length;
    } else if (key.ctrl && key.name === 'u') {
      set('');
    } else if (text && !key.ctrl && !key.meta && text >= ' ') {
      set(this.line.slice(0, this.pos) + text + this.line.slice(this.pos), this.pos + text.length);
      this.menuIndex = 0;
    } else {
      return undefined;
    }
    this.draw();
    return undefined;
  }
}
