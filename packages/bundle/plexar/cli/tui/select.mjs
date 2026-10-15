/**
 * Arrow-key choice prompt drawn in place: ↑/↓ move, Enter confirms, a digit picks directly, y/n pick
 * the yes-like or no-like option, Esc cancels. The prompt collapses to one summary line when it resolves.
 */
import { pushKeys } from './keys.mjs';
import { PALETTE, bold, columns, cursor, dim, fg, truncate } from './term.mjs';

/**
 * The option a `y` or `n` key picks: the first option that reads as yes (Allow, Yes, Trust) or as
 * no (Reject, No, Deny, Don't), or -1 when none does.
 * @param {string[]} options
 * @param {'y' | 'n'} answer
 * @returns {number}
 */
export function answerIndex(options, answer) {
  const pattern = answer === 'y' ? /^(allow|yes|trust|approve)\b/i : /^(reject|no|deny|don'?t|cancel)\b/i;
  return options.findIndex((option) => pattern.test(option.trim()));
}

/**
 * @param {{title: string, options: string[], icon?: string, initial?: number, out?: NodeJS.WritableStream}} spec
 *   `icon` marks the prompt: `!` for permission requests, `?` (default) for everything else.
 * @returns {Promise<number>} chosen index, or -1 when cancelled
 */
export function select({ title, options, icon = '?', initial = 0, out = process.stdout }) {
  let index = initial;
  let drawn = 0;

  const draw = () => {
    const lines = [
      ` ${fg(PALETTE.orange, icon)} ${bold(title)}`,
      ...options.map((option, i) =>
        i === index ? `  ${fg(PALETTE.orange, '›')} ${fg(PALETTE.orange, `${i + 1}. ${option}`)}` : `    ${dim(`${i + 1}.`)} ${option}`,
      ),
      dim(`  ↑/↓ to choose · enter to confirm${answerIndex(options, 'y') >= 0 ? ' · y/n' : ''} · esc to cancel`),
    ];
    // One screen row per line, or the next redraw's upward move lands short (see composer).
    out.write(`${cursor.up(drawn)}\r${cursor.clearDown}${lines.map((l) => truncate(l, columns() - 1)).join('\n')}`);
    drawn = lines.length - 1;
  };

  return new Promise((resolve) => {
    out.write(cursor.hide);
    const finish = (choice) => {
      release();
      const summary = choice < 0 ? dim('cancelled') : fg(PALETTE.orange, options[choice]);
      out.write(`${cursor.up(drawn)}\r${cursor.clearDown} ${fg(PALETTE.orange, icon)} ${title} ${dim('›')} ${summary}\n${cursor.show}`);
      resolve(choice);
    };
    const release = pushKeys((text, key) => {
      if (key.name === 'up') index = (index + options.length - 1) % options.length;
      else if (key.name === 'down' || key.name === 'tab') index = (index + 1) % options.length;
      else if (key.name === 'return') return finish(index);
      else if (key.name === 'escape' || (key.ctrl && key.name === 'c')) return finish(-1);
      else if (/^[1-9]$/.test(text) && Number(text) <= options.length) return finish(Number(text) - 1);
      else if (/^[yn]$/i.test(text) && answerIndex(options, text.toLowerCase()) >= 0) return finish(answerIndex(options, text.toLowerCase()));
      else return;
      draw();
    });
    draw();
  });
}
