/**
 * Terminal primitives for the interactive client: Plexar palette (gunmetal and an orange gradient),
 * truecolor gradients and shimmer, cursor control, and visible-width helpers.
 * Colors are off when stdout is not a terminal or `NO_COLOR` is set.
 */

export const colorOn = Boolean(process.stdout.isTTY) && !process.env.NO_COLOR;

/** Plexar palette as RGB triples. */
export const PALETTE = {
  orangeDeep: [255, 94, 26],
  orange: [255, 140, 40],
  orangeLight: [255, 190, 90],
  gunmetal: [74, 84, 92],
  gunmetalLight: [128, 138, 146],
  text: [222, 226, 230],
  ink: [34, 38, 42],
};

const ESC = '\x1b[';

/**
 * @param {number[]} rgb
 * @param {string} text
 * @returns {string} text in that truecolor foreground
 */
export function fg(rgb, text) {
  return colorOn ? `${ESC}38;2;${rgb[0]};${rgb[1]};${rgb[2]}m${text}${ESC}39m` : text;
}

/**
 * Reversed badge: `text` on a colored background, for values that should stand out (the model).
 * @param {number[]} back - background RGB
 * @param {number[]} front - text RGB
 * @param {string} text
 * @returns {string}
 */
export function badge(back, front, text) {
  return colorOn
    ? `${ESC}48;2;${back[0]};${back[1]};${back[2]}m${ESC}38;2;${front[0]};${front[1]};${front[2]}m ${text} ${ESC}39m${ESC}49m`
    : text;
}

/** @returns {string} text in bold */
export function bold(text) {
  return colorOn ? `${ESC}1m${text}${ESC}22m` : text;
}

/** @returns {string} text dimmed */
export function dim(text) {
  return colorOn ? `${ESC}2m${text}${ESC}22m` : text;
}

function mix(a, b, t) {
  return a.map((v, i) => Math.round(v + (b[i] - v) * t));
}

/**
 * Color each character along a gradient between two colors.
 * @param {string} text - plain text (no escapes)
 * @param {number[]} from
 * @param {number[]} to
 * @returns {string}
 */
export function gradient(text, from = PALETTE.orangeDeep, to = PALETTE.orangeLight) {
  if (!colorOn) return text;
  const chars = [...text];
  const n = Math.max(chars.length - 1, 1);
  return chars.map((c, i) => (c === ' ' ? c : fg(mix(from, to, i / n), c))).join('');
}

/**
 * A bright band sweeping across dimmer text, one frame of the "working" shimmer.
 * @param {string} text - plain text
 * @param {number} frame - animation frame counter
 * @returns {string}
 */
export function shimmer(text, frame) {
  if (!colorOn) return text;
  const chars = [...text];
  const span = chars.length + 12;
  const center = (frame % span) - 6;
  return chars
    .map((c, i) => {
      const d = Math.abs(i - center);
      const t = d >= 6 ? 0 : 1 - d / 6;
      return fg(mix(PALETTE.orangeDeep, [255, 236, 200], t), c);
    })
    .join('');
}

// eslint-disable-next-line no-control-regex -- matching ANSI escape sequences is the point
const ANSI = /\x1b\[[0-9;?]*[A-Za-z]/g;

/** @returns {number} printed width of a string with escapes removed (one column per code point) */
export function visibleWidth(text) {
  return [...text.replace(ANSI, '')].length;
}

/** @returns {string} text cut to at most `width` visible columns, escapes kept */
export function truncate(text, width) {
  let out = '';
  let seen = 0;
  for (const part of text.split(/(\x1b\[[0-9;?]*[A-Za-z])/)) {
    if (part.startsWith('\x1b[')) {
      out += part;
      continue;
    }
    for (const ch of part) {
      if (seen >= width) return `${out}${colorOn ? `${ESC}0m` : ''}`;
      out += ch;
      seen += 1;
    }
  }
  return out;
}

/** Cursor and screen control sequences. */
export const cursor = {
  up: (n) => (n > 0 ? `${ESC}${n}A` : ''),
  down: (n) => (n > 0 ? `${ESC}${n}B` : ''),
  col: (n) => `${ESC}${n + 1}G`,
  clearLine: `\r${ESC}2K`,
  clearDown: `${ESC}J`,
  hide: `${ESC}?25l`,
  show: `${ESC}?25h`,
};

/** @returns {number} terminal width, with a fallback for non-terminals */
export function columns() {
  return process.stdout.columns || 100;
}
