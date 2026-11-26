/**
 * Normal column geometry: the right column shrinks, then loses its track,
 * before the center drops below its minimum. The sidebar never concedes here;
 * AppFrame supplies its effective preference after responsive collapse.
 */

/** Resolved widths for one frame; `envbar` is present only while the rail takes a track. */
export interface Columns { sidebar: number; center: number; rightbar: number; envbar?: number }

/** Center width protected while the normal right column is open. */
export const CENTER_MIN = 400
/** Sidebar drag clamp floor. */
export const SIDEBAR_MIN = 264
/** Sidebar drag clamp ceiling. */
export const SIDEBAR_MAX = 420
/** Sidebar width before any user drag. */
export const SIDEBAR_DEFAULT = 280
/** Closed-sidebar rail: a 24px icon column between 16px horizontal paddings. */
export const SIDEBAR_COLLAPSED = 56
/** Viewport width below which the sidebar auto-collapses to the rail (deepsuite
 * LG breakpoint); a manual toggle below it re-expands over the squeezed center
 * (stores.ts narrowExpanded). */
export const SIDEBAR_AUTO_COLLAPSE = 1024
/** Right column drag clamp floor. */
export const RIGHTBAR_MIN = 300
/** Maximum normal right panel width as a fraction of the frame. */
export const RIGHTBAR_MAX_RATIO = 0.7
/** First-open right panel preference as a fraction of the frame. */
export const RIGHTBAR_DEFAULT_RATIO = 0.45
/** Fixed width of the environment rail right of the right column; it has no drag handle. */
export const ENVBAR_WIDTH = 280

/**
 * Clamp a panel width into its contract range.
 * @param px - requested width.
 * @param min - range lower bound.
 * @param max - range upper bound.
 * @returns the clamped width.
 */
export function clampWidth(px: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, Math.round(px)))
}

/**
 * Solve the column widths for one viewport frame. The environment rail is
 * reserved before the right column bids: it takes its fixed width or nothing,
 * and the right column then shrinks or loses its track in what remains.
 * @param viewport - available frame width in px.
 * @param sidebar - sidebar width preference in px (0 = closed).
 * @param rightbar - requested right panel width in px (0 = no track).
 * @param collapsedWidth - track width of the closed sidebar; the default keeps
 *   the icon rail, 0 hides the column entirely (macOS desktop).
 * @param envbar - requested environment rail width in px (0 = no track); it
 *   gets no track when the center could not keep its minimum beside it.
 * @returns actual widths after shrinking or removing the right tracks; only
 *   without them may the center fall below its minimum, down to zero.
 */
export function computeColumns(
  viewport: number, sidebar: number, rightbar: number, collapsedWidth = SIDEBAR_COLLAPSED, envbar = 0,
): Columns {
  const s = sidebar === 0 ? collapsedWidth : clampWidth(sidebar, SIDEBAR_MIN, SIDEBAR_MAX)
  const e = envbar === 0 || viewport - s - CENTER_MIN < envbar ? 0 : envbar
  const available = viewport - s - e - CENTER_MIN
  const r = rightbar === 0 || available < RIGHTBAR_MIN
    ? 0
    : Math.min(available, clampWidth(rightbar, RIGHTBAR_MIN, viewport * RIGHTBAR_MAX_RATIO))
  const columns: Columns = { sidebar: s, center: Math.max(0, viewport - s - r - e), rightbar: r }
  if (e > 0) columns.envbar = e
  return columns
}
