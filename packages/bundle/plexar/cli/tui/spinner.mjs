/**
 * Animated working line: a spinner glyph, a shimmering fantasy status phrase, and elapsed time.
 * Occupies the terminal's current line only while the cursor sits at a line start, so streamed
 * text is never overwritten; `Screen.write` hides it before output and restores it after.
 */
import { PHRASES } from './phrases.mjs';
import { PALETTE, colorOn, cursor, dim, fg, shimmer, truncate, columns } from './term.mjs';

const FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];
const TICK_MS = 80;
const PHRASE_MS = 3200;

function shuffled(list) {
  const out = [...list];
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

/** One stdout writer that keeps the spinner out of the way of streamed text. */
export class Screen {
  constructor(out = process.stdout) {
    this.out = out;
    this.atLineStart = true;
    this.spinner = null;
  }

  /** Write text, hiding the spinner first and redrawing it if the cursor ends at a line start. */
  write(text) {
    if (!text) return;
    this.spinner?.erase();
    this.out.write(text);
    this.atLineStart = text.endsWith('\n');
    this.spinner?.draw();
  }
}

export class Spinner {
  /** @param {Screen} screen */
  constructor(screen) {
    this.screen = screen;
    this.timer = null;
    this.frame = 0;
    this.visible = false;
    this.label = '';
  }

  /** Start animating; `label` overrides the phrases (used at startup). */
  start(label = '') {
    this.stop();
    this.label = label;
    this.phrases = shuffled(PHRASES);
    this.started = Date.now();
    this.frame = 0;
    this.screen.spinner = this;
    if (!colorOn) return;
    this.screen.out.write(cursor.hide);
    this.timer = setInterval(() => {
      this.frame += 1;
      this.draw();
    }, TICK_MS);
    this.draw();
  }

  line() {
    const elapsed = Math.floor((Date.now() - this.started) / 1000);
    const phrase = this.label || `${this.phrases[Math.floor((Date.now() - this.started) / PHRASE_MS) % this.phrases.length]}…`;
    const glyph = fg(PALETTE.orange, FRAMES[this.frame % FRAMES.length]);
    const tail = dim(` (${elapsed}s · ctrl-c to interrupt)`);
    return truncate(`${glyph} ${shimmer(phrase, this.frame)}${tail}`, columns() - 1);
  }

  draw() {
    if (!this.timer || !this.screen.atLineStart) return;
    this.screen.out.write(`${cursor.clearLine}${this.line()}`);
    this.visible = true;
  }

  erase() {
    if (!this.visible) return;
    this.screen.out.write(cursor.clearLine);
    this.visible = false;
  }

  stop() {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    this.erase();
    if (this.screen.spinner === this) this.screen.spinner = null;
    if (colorOn) this.screen.out.write(cursor.show);
  }
}
