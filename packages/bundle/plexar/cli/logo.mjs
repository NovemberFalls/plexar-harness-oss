/**
 * Launch header (three text lines) and the Plexar attention mark, an exclamation mark in a hexagon.
 * The mark appears only where a permission is being asked: the folder-trust screen.
 */
import { PALETTE, badge, bold, dim, gradient } from './tui/term.mjs';

// Half-block art, one row per line; each row is colored from deep to light orange, rows get lighter downward.
const MARK = [' ▄▀█▀▄ ', '█  █  █', '█  ▄  █', ' ▀▄▄▄▀ '];
const ROW_COLORS = [
  [PALETTE.orangeDeep, PALETTE.orange],
  [PALETTE.orangeDeep, PALETTE.orange],
  [PALETTE.orange, PALETTE.orangeLight],
  [PALETTE.orange, PALETTE.orangeLight],
];

/**
 * The permission mode is not repeated here; the status line under the composer shows it.
 * @param {{version: string, model: string, effort: string, cwd: string}} facts
 * @returns {string} the header, newline-terminated
 */
export function header({ version, model, effort, cwd }) {
  const lines = [
    `${bold(gradient('Plexar Harness'))} ${dim(`v${version}`)}`,
    `${badge(PALETTE.orangeLight, PALETTE.ink, model)} ${dim('·')} effort ${effort}`,
    dim(cwd),
  ];
  return `\n${lines.map((line) => ` ${line}`).join('\n')}\n\n`;
}

/**
 * The attention mark beside up to four lines of text.
 * @param {string[]} lines - text for the rows beside the mark
 * @returns {string} the block, newline-terminated
 */
export function attention(lines) {
  return `${MARK.map((art, i) => ` ${gradient(art, ...ROW_COLORS[i])}  ${lines[i] ?? ''}`).join('\n')}\n`;
}
