/**
 * Line diffs for file edits, drawn the way reviewers read them: a line-number column, `-` rows on a red
 * background, `+` rows on a green one, unchanged rows plain, two lines of context around each change.
 * The CLI snapshots a file when an edit or write tool call starts and diffs it against the file when
 * the call completes, so the numbers are the file's real line numbers.
 */

const CONTEXT = 2;
/** Above this many line-pair comparisons the middle is shown as a block replace instead of an LCS. */
const MAX_LCS_CELLS = 4_000_000;

/**
 * Diff two texts by line.
 * @param {string} before
 * @param {string} after
 * @returns {{kind: ' ' | '-' | '+', text: string, oldNo?: number, newNo?: number}[]} every line, in order
 */
export function lineDiff(before, after) {
  // A final newline ends the last line; it does not start an empty one.
  const lines = (text) => (text === '' ? [] : text.replace(/\r\n/g, '\n').replace(/\n$/, '').split('\n'));
  const a = lines(before);
  const b = lines(after);
  let start = 0;
  while (start < a.length && start < b.length && a[start] === b[start]) start += 1;
  let endA = a.length;
  let endB = b.length;
  while (endA > start && endB > start && a[endA - 1] === b[endB - 1]) { endA -= 1; endB -= 1; }
  const rows = [];
  for (let i = 0; i < start; i += 1) rows.push({ kind: ' ', text: a[i], oldNo: i + 1, newNo: i + 1 });
  const midA = a.slice(start, endA);
  const midB = b.slice(start, endB);
  const push = (kind, ai, bi) => rows.push(kind === '-'
    ? { kind, text: midA[ai], oldNo: start + ai + 1 }
    : kind === '+' ? { kind, text: midB[bi], newNo: start + bi + 1 }
      : { kind, text: midA[ai], oldNo: start + ai + 1, newNo: start + bi + 1 });
  if (midA.length * midB.length > MAX_LCS_CELLS) {
    midA.forEach((_, i) => push('-', i));
    midB.forEach((_, j) => push('+', 0, j));
  } else {
    // Longest common subsequence table, filled from the end so the walk below goes forward.
    const n = midA.length;
    const m = midB.length;
    const lcs = Array.from({ length: n + 1 }, () => new Uint32Array(m + 1));
    for (let i = n - 1; i >= 0; i -= 1) {
      for (let j = m - 1; j >= 0; j -= 1) {
        lcs[i][j] = midA[i] === midB[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
      }
    }
    let i = 0;
    let j = 0;
    while (i < n || j < m) {
      if (i < n && j < m && midA[i] === midB[j]) { push(' ', i, j); i += 1; j += 1; }
      // Removals before additions when both keep the LCS, so a replaced line reads - then +.
      else if (i < n && (j === m || lcs[i + 1][j] >= lcs[i][j + 1])) { push('-', i, j); i += 1; }
      else { push('+', i, j); j += 1; }
    }
  }
  const tailOffset = b.length - a.length;
  for (let i = endA; i < a.length; i += 1) rows.push({ kind: ' ', text: a[i], oldNo: i + 1, newNo: i + 1 + tailOffset });
  return rows;
}

/**
 * Keep changed rows plus `CONTEXT` unchanged rows around them; gaps become `null` separators.
 * @param {ReturnType<typeof lineDiff>} rows
 * @returns {(ReturnType<typeof lineDiff>[number] | null)[]}
 */
export function hunks(rows) {
  const keep = new Array(rows.length).fill(false);
  rows.forEach((row, i) => {
    if (row.kind === ' ') return;
    for (let k = Math.max(0, i - CONTEXT); k <= Math.min(rows.length - 1, i + CONTEXT); k += 1) keep[k] = true;
  });
  const out = [];
  rows.forEach((row, i) => {
    if (keep[i]) out.push(row);
    else if (out.length > 0 && out[out.length - 1] !== null && keep.slice(i).some(Boolean)) out.push(null);
  });
  return out;
}

/**
 * Draw a diff as terminal rows.
 * @param {ReturnType<typeof lineDiff>} rows
 * @param {{width: number, maxRows: number, color: boolean, indent?: string}} options
 * @returns {{lines: string[], added: number, removed: number}}
 */
export function renderDiff(rows, { width, maxRows, color, indent = '    ' }) {
  const added = rows.filter((r) => r.kind === '+').length;
  const removed = rows.filter((r) => r.kind === '-').length;
  const shown = hunks(rows);
  const numWidth = String(Math.max(0, ...rows.map((r) => r.newNo ?? r.oldNo ?? 0))).length;
  const textWidth = Math.max(10, width - indent.length - numWidth - 3);
  const paint = (kind, s) => {
    if (!color) return s.trimEnd();
    if (kind === '-') return `\x1b[48;2;70;14;14m\x1b[38;2;255;170;170m${s}\x1b[0m`;
    if (kind === '+') return `\x1b[48;2;14;60;22m\x1b[38;2;170;255;180m${s}\x1b[0m`;
    return s;
  };
  const lines = [];
  for (const row of shown) {
    if (lines.length >= maxRows) break;
    if (row === null) { lines.push(`${indent}${color ? '\x1b[2m' : ''}${' '.repeat(numWidth)} ⋮${color ? '\x1b[0m' : ''}`); continue; }
    const no = String(row.kind === '-' ? row.oldNo : row.newNo).padStart(numWidth);
    const text = row.text.replace(/\t/g, '  ');
    const body = `${no} ${row.kind} ${text.length > textWidth ? `${text.slice(0, textWidth - 1)}…` : text.padEnd(textWidth)}`;
    lines.push(`${indent}${row.kind === ' ' ? (color ? `\x1b[2m${no}\x1b[0m ${row.kind} ${text.slice(0, textWidth)}` : body.trimEnd()) : paint(row.kind, body)}`);
  }
  const hidden = shown.length - Math.min(shown.length, maxRows);
  if (hidden > 0) lines.push(`${indent}${color ? '\x1b[2m' : ''}… ${hidden} more lines${color ? '\x1b[0m' : ''}`);
  return { lines, added, removed };
}
