"""A standalone `.html` document, charts drawn as inline SVG.

══ WHY SVG AND NOT THE VENDORED CHART.JS ═══════════════════════════════════
The file leaves the product. It is downloaded and opened from disk, so every
external reference in it is a reference that resolves on nobody's machine —
and C50's shelf resolves only on the artifact origin, which this file will
never be loaded from. **A blank rectangle the model then describes as the
answer is the defect the whole chart row exists to end**, so nothing here may
depend on anything arriving over a network. Inline SVG, an inline `<style>`,
and no third resource.

══ THE GEOMETRY IS NOT COMPUTED HERE ═══════════════════════════════════════
`.._chart` owns the axis, the ticks and the tick TEXT. Three renderers each
picking their own y-range is the defect that module exists to prevent, and the
label formatter in particular has already been got wrong once (see its
docstring on `900k` beside `1M`). So this file asks for `nice_axis`,
`tick_labels` and `fraction` and reformats none of them.

══ THE COORDINATE FLIP, DECIDED ONCE ═══════════════════════════════════════
`fraction()` is 0 at the plot's BOTTOM and 1 at its top, because that is what
the PDF's origin wants. SVG's y grows DOWNWARD from the top-left. **Those two
conventions are reconciled in exactly one function — `_y()` — and nowhere
else.** Every mark, gridline, tick and baseline in this file gets its vertical
position from that call. A second flip written inline is how a chart comes to
be drawn upside down in one place and the right way up in another.
"""

from __future__ import annotations

from .._chart import Chart, fraction, nice_axis, parse_chart, tick_labels
from .._colour import hex_of, readable_on_white
from .._runs import runs
from .._xml import escape

# ══ THE PAGE ════════════════════════════════════════════════════════════════
#: Defaults matching the PDF writer's, so one spec in two formats reads as the
#: same document. **Each falls back independently** (T72): a palette naming
#: only an accent leaves the ink and the rules alone.
ACCENT = (0.11, 0.34, 0.58)
INK = (0.13, 0.13, 0.15)
RULE = (0.80, 0.82, 0.85)

#: Font stacks. **Every family named here is a generic or a face the operating
#: system already has** — a webfont would be an external resource, which is the
#: one thing this format may not have.
FAMILIES = {
    "sans": "system-ui, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif",
    "serif": "Georgia, 'Times New Roman', Times, serif",
    "mono": "ui-monospace, 'Cascadia Mono', Consolas, 'Courier New', monospace",
}

#: A distinguishable series cycle for charts whose series named no colour.
#: The palette's accent takes position 0 when there is one, so a themed
#: document's first series matches its headings.
SERIES_COLOURS = (
    (0.11, 0.34, 0.58), (0.83, 0.37, 0.13), (0.16, 0.50, 0.33),
    (0.55, 0.24, 0.55), (0.72, 0.16, 0.26), (0.35, 0.42, 0.47),
    (0.85, 0.62, 0.13), (0.20, 0.55, 0.60),
)

# ══ THE PLOT BOX, IN SVG USER UNITS ═════════════════════════════════════════
SVG_W, SVG_H = 760.0, 420.0
PAD_L, PAD_R = 78.0, 22.0
PAD_T, PAD_B = 34.0, 74.0
PLOT_L = PAD_L
PLOT_R = SVG_W - PAD_R
PLOT_T = PAD_T
PLOT_B = SVG_H - PAD_B
PLOT_W = PLOT_R - PLOT_L
PLOT_H = PLOT_B - PLOT_T


def _y(f: float) -> float:
    """A `fraction()` (0 = plot BOTTOM, 1 = top) into an SVG y (grows DOWN).

    **THE ONLY PLACE THE TWO CONVENTIONS MEET.** See this module's header.
    """
    return PLOT_B - f * PLOT_H


def _hash(colour: tuple[float, float, float] | None) -> str:
    """An rgb triple -> a CSS/SVG colour. **`hex_of` returns OOXML's `RRGGBB`
    with NO HASH**, which is correct for a `.docx` and is not a colour at all in
    CSS or SVG — `fill="1C5794"` is an invalid value, so the browser falls back
    and every themed chart draws BLACK. Found by this row's own gate, which is
    the only reason it is not shipped: nothing about `hex_of(accent)` reads
    wrong. `None` becomes `inherit` rather than an empty declaration."""
    text = hex_of(colour)
    return f"#{text.lower()}" if text else "inherit"


def _n(value: float) -> str:
    """A coordinate, short. `-0` never reaches the markup — it is legal SVG and
    it reads as a bug in every diff that contains one."""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-", "-0") else text


# ══ BLOCKS ══════════════════════════════════════════════════════════════════

_HEADINGS = {"heading1": "h1", "heading2": "h2", "heading3": "h3"}


def _family(name: object, default: str) -> str:
    key = str(name or "").strip().lower()
    if key in FAMILIES:
        return key
    if key in ("helvetica", "arial", "sans-serif"):
        return "sans"
    if key in ("times", "times new roman", "georgia"):
        return "serif"
    if key in ("courier", "monospace", "code"):
        return "mono"
    return default


def _size_of(value: object) -> float | None:
    """A model-authored point size, clamped (R42). A document is laid out by the
    browser here rather than by arithmetic, but 4000pt still makes one glyph a
    whole page and there is no reading of that as intent."""
    try:
        size = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if size <= 0:
        return None
    return min(96.0, max(6.0, size))


def _style_attr(block: dict, *, body: str, heading: str,
                is_heading: bool) -> str:
    """A `style="…"` for one block, or `""`. **Read off the already-normalised
    fields** — `colour` is an rgb triple and `align` a vocabulary, both settled
    upstream by `_styled`, so nothing is parsed twice (T72)."""
    parts: list[str] = []
    colour = block.get("colour")
    # Refused when it cannot be read on paper, not darkened — the PDF writer's
    # rule, for its reason: a colour nobody chose is worse than the default.
    if isinstance(colour, tuple) and readable_on_white(colour):
        parts.append(f"color:{_hash(colour)}")
    align = block.get("align")
    if align in ("centre", "left", "right"):
        parts.append("text-align:" + ("center" if align == "centre" else align))
    size = _size_of(block.get("size"))
    if size is not None:
        parts.append(f"font-size:{_n(size)}pt")
    if isinstance(block.get("bold"), bool):
        parts.append("font-weight:" + ("700" if block["bold"] else "400"))
    if block.get("italic"):
        parts.append("font-style:italic")
    named = block.get("font")
    if named is not None:
        key = _family(named, heading if is_heading else body)
        parts.append(f"font-family:{FAMILIES[key]}")
    if not parts:
        return ""
    return f' style="{escape(";".join(parts))}"'


def _inline(text: object) -> str:
    """Model prose -> escaped HTML with `**bold**` and `*italic*` honoured.

    **The escape runs on the run's TEXT, and the tags are added around it** —
    escaping the assembled markup would show the tags, and assembling first and
    escaping never is how `</p><script>` gets into a document.
    """
    out = []
    for run in runs(str(text or "")):
        body = escape(run.text)
        if run.bold:
            body = f"<strong>{body}</strong>"
        if run.italic:
            body = f"<em>{body}</em>"
        out.append(body)
    return "".join(out)


def _table(block: dict) -> str:
    rows = [r for r in (block.get("rows") or []) if isinstance(r, (list, tuple))]
    if not rows:
        return ""
    out = ['<table class="px-table">']
    head, *rest = rows
    out.append("<thead><tr>"
               + "".join(f"<th>{escape(c)}</th>" for c in head)
               + "</tr></thead><tbody>")
    for row in rest:
        out.append("<tr>" + "".join(f"<td>{escape(c)}</td>" for c in row)
                   + "</tr>")
    out.append("</tbody></table>")
    return "".join(out)


# ══ THE CHART ═══════════════════════════════════════════════════════════════

def _series_colour(index: int, series, accent) -> str:
    if series.colour is not None:
        return _hash(series.colour)
    cycle = (accent,) + SERIES_COLOURS[1:] if accent else SERIES_COLOURS
    return _hash(cycle[index % len(cycle)])


def marks(chart: Chart, axis, accent) -> str:
    """The data marks and nothing else — **bars as `<rect>`, lines as
    `<polyline>`.**

    Broken out as a named function so the gate can replace it and watch the
    count assertion redden (R23) without a wrong file ever existing on disk.

    A `None` is a GAP: a bar is simply ABSENT, and a line is cut into one
    `<polyline>` per contiguous run of real values. **A gap interpolated across,
    or drawn at the baseline, is a measurement the document does not have** —
    and the reader cannot see that it is missing.
    """
    out: list[str] = []
    points = max(1, chart.points)
    if chart.shape == "bar":
        band = PLOT_W / points
        count = max(1, len(chart.series))
        inner = band * 0.76
        width = inner / count
        base = _y(fraction(0.0, axis))
        for si, series in enumerate(chart.series):
            fill = _series_colour(si, series, accent)
            for pi, value in enumerate(series.values):
                if value is None:
                    continue  # THE GAP. No rect, no baseline stub.
                top = _y(fraction(value, axis))
                x = PLOT_L + pi * band + (band - inner) / 2 + si * width
                y0, y1 = min(top, base), max(top, base)
                out.append(
                    f'<rect x="{_n(x)}" y="{_n(y0)}" width="{_n(width * 0.9)}"'
                    f' height="{_n(max(0.5, y1 - y0))}" fill="{fill}"'
                    f' class="px-bar">{_hover(chart, si, pi, value)}</rect>')
        return "".join(out)

    # A line's points sit on the band centres, so a bar chart and a line chart
    # of the same data put January in the same place.
    step = PLOT_W / max(1, points - 1) if points > 1 else PLOT_W
    for si, series in enumerate(chart.series):
        stroke = _series_colour(si, series, accent)
        run: list[str] = []

        # ══ ONE FLUSH, AND THE FIRST DRAFT HAD TWO — SO IT DROPPED DATA ══════
        # **Found in a screenshot, not by an assertion.** The gap branch tested
        # `len(run) > 1` and the end-of-series branch handled the single-point
        # case, so a value with a gap on BOTH sides was silently discarded:
        # Len's own fixture had January alone before a null February, and the
        # blue series simply began in March. Every arm was green — the polyline
        # counts were right — because a mark that is missing entirely reddens
        # nothing that counts marks. One function, two call sites, so the two
        # cases cannot be treated differently again.
        def flush() -> None:
            if len(run) > 1:
                out.append(_polyline(run, stroke))
            elif len(run) == 1:
                # A point with a gap on both sides has no line to be part of.
                # It is still a measurement, so it is drawn — as a dot, which
                # is what one measurement looks like. Dropping it would be the
                # gap defect in reverse: real data rendered as absent.
                x, y = run[0].split(",")
                out.append(f'<circle cx="{x}" cy="{y}" r="3.2"'
                           f' fill="{stroke}" class="px-point"/>')

        for pi, value in enumerate(series.values):
            if value is None:
                flush()
                run = []
                continue
            run.append(f"{_n(PLOT_L + pi * step)},"
                       f"{_n(_y(fraction(value, axis)))}")
        flush()

    # ══ THE HOVER TARGETS, AND WHY A LINE NEEDS THEM AND A BAR DOES NOT ══════
    # A `<rect>` is one mark for one value, so its `<title>` is unambiguous. A
    # `<polyline>` is ONE element carrying twelve values — a `<title>` on it
    # could only name the series, which is what the legend already says. So each
    # point gets an invisible target.
    #
    # `pointer-events="all"` is load-bearing: the default `visiblePainted` will
    # not hit-test an unpainted shape, so `fill="none"` alone gives a target
    # that exists in the DOM, passes any count, and cannot be hovered. **That is
    # the shape of every dead control this lane has already paid for** (T10).
    #
    # Emitted AFTER the lines so the targets sit on top; a target painted under
    # a 2.4px stroke loses the pixels that matter most.
    if chart.shape != "bar":
        for si, series in enumerate(chart.series):
            for pi, value in enumerate(series.values):
                if value is None:
                    continue
                out.append(
                    f'<circle cx="{_n(PLOT_L + pi * step)}"'
                    f' cy="{_n(_y(fraction(value, axis)))}" r="9"'
                    f' fill="none" pointer-events="all" class="px-hit">'
                    f'{_hover(chart, si, pi, value)}</circle>')
    return "".join(out)


def _hover(chart: Chart, si: int, pi: int, value: float) -> str:
    """One mark's native tooltip: `Jan · 2025 Actual · 936,205`.

    ══ THIS EXISTS BECAUSE THE MODEL KEPT PROMISING IT (T81d) ═══════════════════
    Len's chart came with *"You can interact with the chart by hovering over data
    points to see exact values"* — written while
    `Never describe a file you created as interactive` was in the prompt, and
    measurably false: no `<title>` on any mark, no `<desc>`, no script.

    **T81b answered that with a prohibition and the prohibition did not hold.**
    So this row makes the sentence TRUE instead of forbidden. An SVG `<title>`
    child is a browser-native tooltip: no JavaScript, nothing fetched, works in
    the downloaded file on a machine with no network, and survives the artifact
    sandbox — which is the entire reason it is the right mechanism here and
    Chart.js is not.

    Every field is model-authored, so every field is escaped (`escape`), for the
    same reason C57 bounded the blocked-URL report: this text is written into
    markup the browser then parses.
    """
    label = chart.labels[pi] if pi < len(chart.labels) else ""
    name = chart.series[si].name if si < len(chart.series) else ""
    parts = [p for p in (label, name, _human(value)) if p]
    return f"<title>{escape(' · '.join(parts))}</title>"


def _human(value: float) -> str:
    """A number as a person reads it — thousands separated, no unit invented.

    **Not `tick_labels`' abbreviation.** An axis says `0.9M` because it has
    30 points of room; a tooltip is the one place the reader came for the EXACT
    figure, so abbreviating it here would defeat the feature the tooltip is.
    """
    if value == int(value) and abs(value) < 1e15:
        return f"{int(value):,}"
    return f"{value:,.2f}"


def _polyline(points: list[str], stroke: str) -> str:
    return (f'<polyline points="{" ".join(points)}" fill="none"'
            f' stroke="{stroke}" stroke-width="2.4" stroke-linejoin="round"'
            f' stroke-linecap="round" class="px-line"/>')


def chart_svg(chart: Chart, palette: dict) -> str:
    """One `Chart` -> one `<svg>`. Every string in it goes through `escape`."""
    axis = nice_axis(chart)
    labels = tick_labels(axis)
    ink = _hash(palette.get("ink") or INK)
    rule = _hash(palette.get("rule") or RULE)
    accent = palette.get("accent") or ACCENT

    # Precomputed rather than inlined: nested same-quotes inside an f-string
    # expression is a 3.12-only grammar, and this package targets what runs.
    label = escape(chart.title or (chart.shape + " chart"))
    # ══ NO `xmlns`, AND THAT IS THE SELF-CONTAINED RULE BEING ENFORCEABLE ═══
    # The SVG namespace declaration is a URL, not a fetch — no parser has ever
    # retrieved it. But the gate's rule is "no `http` anywhere", because a rule
    # with an exception in it is a rule somebody widens. **Inline SVG inside an
    # HTML document needs no declaration**: the HTML parser puts `<svg>` and its
    # descendants in the SVG namespace itself. This file is `text/html`, always.
    out = [f'<svg viewBox="0 0 '
           f'{_n(SVG_W)} {_n(SVG_H)}" width="100%" role="img"'
           f' class="px-chart-svg" aria-label="{label}">']
    if chart.title:
        # An SVG `<title>` is the accessible name, and it is CHARACTER DATA —
        # so a model-authored `</svg><script>` is inert text here once escaped,
        # which the gate asserts rather than assumes.
        out.append(f"<title>{escape(chart.title)}</title>")

    # ── gridlines and y ticks. `<line>`/`<text>`, never a mark element, so the
    # gate can count marks without the chrome polluting the number.
    for tick, text in zip(axis.ticks, labels):
        y = _y(fraction(tick, axis))
        # ══ DECORATION NEVER INTERCEPTS A POINTER (T81d) ═════════════════════
        # **Found by hit-testing, and ten structural arms were green.** A line
        # chart's first point sits exactly at `x = PLOT_L`, and the y-axis frame
        # is drawn at `PLOT_L` AFTER the marks — so `elementFromPoint` at that
        # target's own centre returned the axis, and the first month of every
        # line chart had no reachable tooltip. Every count and every attribute
        # assertion passed while it was unhoverable, which is T10's dead control
        # in a paint order.
        out.append(f'<line x1="{_n(PLOT_L)}" y1="{_n(y)}" x2="{_n(PLOT_R)}"'
                   f' y2="{_n(y)}" stroke="{rule}" stroke-width="1"'
                   f' pointer-events="none"/>')
        out.append(f'<text x="{_n(PLOT_L - 10)}" y="{_n(y + 4)}"'
                   f' text-anchor="end" class="px-tick"'
                   f' fill="{ink}">{escape(text)}</text>')

    # The zero line, when zero is inside the range and is not already a tick's
    # gridline doing the job. Drawn darker: a bar chart without a visible
    # baseline invites the reader to take the bottom of the box as zero.
    if axis.lo < 0.0 < axis.hi:
        zero = _y(fraction(0.0, axis))
        out.append(f'<line x1="{_n(PLOT_L)}" y1="{_n(zero)}"'
                   f' x2="{_n(PLOT_R)}" y2="{_n(zero)}" stroke="{ink}"'
                   f' stroke-width="1.2" pointer-events="none"/>')

    out.append(marks(chart, axis, accent))

    # ── x labels. Thinned when they would collide rather than drawn on top of
    # each other: overlapping text is unreadable AND hides that it overlapped.
    points = max(1, chart.points)
    every = max(1, -(-points // 14))
    band = PLOT_W / points
    step = PLOT_W / max(1, points - 1) if points > 1 else PLOT_W
    for index, label in enumerate(chart.labels):
        if index % every:
            continue
        x = (PLOT_L + index * band + band / 2 if chart.shape == "bar"
             else PLOT_L + index * step)
        out.append(f'<text x="{_n(x)}" y="{_n(PLOT_B + 18)}"'
                   f' text-anchor="middle" class="px-tick"'
                   f' fill="{ink}">{escape(label)}</text>')

    # ── the axis frame
    out.append(f'<line x1="{_n(PLOT_L)}" y1="{_n(PLOT_B)}" x2="{_n(PLOT_R)}"'
               f' y2="{_n(PLOT_B)}" stroke="{ink}" stroke-width="1.2"'
               f' pointer-events="none"/>')
    out.append(f'<line x1="{_n(PLOT_L)}" y1="{_n(PLOT_T)}" x2="{_n(PLOT_L)}"'
               f' y2="{_n(PLOT_B)}" stroke="{ink}" stroke-width="1.2"'
               f' pointer-events="none"/>')

    if chart.x_title:
        out.append(f'<text x="{_n((PLOT_L + PLOT_R) / 2)}"'
                   f' y="{_n(SVG_H - 34)}" text-anchor="middle"'
                   f' class="px-axis-title" fill="{ink}">'
                   f"{escape(chart.x_title)}</text>")
    if chart.y_title:
        # Rotated about its own midpoint. `transform` carries no URL and no
        # reference, so it costs nothing this format cares about.
        cy = (PLOT_T + PLOT_B) / 2
        out.append(f'<text transform="rotate(-90 16 {_n(cy)})" x="16"'
                   f' y="{_n(cy)}" text-anchor="middle"'
                   f' class="px-axis-title" fill="{ink}">'
                   f"{escape(chart.y_title)}</text>")

    # ── the legend, when there is more than one series to tell apart. Swatches
    # are `<circle>`, deliberately: a `<rect>` here would be counted as a bar
    # by anything measuring the marks, including the gate.
    named = [s for s in chart.series if s.name]
    if len(chart.series) > 1 and named:
        x = PLOT_L
        for index, series in enumerate(chart.series):
            colour = _series_colour(index, series, accent)
            out.append(f'<circle cx="{_n(x + 5)}" cy="{_n(SVG_H - 12)}" r="5"'
                       f' fill="{colour}"/>')
            out.append(f'<text x="{_n(x + 15)}" y="{_n(SVG_H - 8)}"'
                       f' class="px-legend" fill="{ink}">'
                       f"{escape(series.name or f'Series {index + 1}')}</text>")
            x += 22 + 7.2 * len(series.name or "")
    out.append("</svg>")
    return "".join(out)


def _chart_block(block: dict, palette: dict) -> str:
    from .._chart import BadChart
    try:
        chart = parse_chart(block)
    except BadChart:
        # **A refusal upstream is the tool's answer, not this writer's.** By the
        # time bytes are being built the spec has been validated; reaching here
        # means a caller assembled blocks by hand, and a renderer must not be
        # the thing that raises. Nothing is drawn rather than a blank box being
        # drawn, so the document does not claim a picture it does not have.
        return ""
    caption = (f'<figcaption class="px-chart-title">{escape(chart.title)}'
               f"</figcaption>" if chart.title else "")
    return (f'<figure class="px-chart">{caption}'
            f"{chart_svg(chart, palette)}</figure>")


# ══ THE DOCUMENT ════════════════════════════════════════════════════════════

#: The mark that carries a callout's tone where colour cannot -- print,
#: forced-colours mode, a monochrome screen. **The same four the PDF and docx
#: writers use**: three tables that must agree is how one format learns a tone
#: the others have never heard of.
_CALLOUT_MARK = {"note": "i", "warning": "!", "caution": "!", "success": "*"}


def _css(palette: dict) -> str:
    ink = _hash(palette.get("ink") or INK)
    accent = _hash(palette.get("accent") or ACCENT)
    heading = _hash(palette.get("heading") or palette.get("accent") or ACCENT)
    # C77e: the second heading tier, falling back to the first.
    subheading = _hash(palette.get("subheading") or palette.get("heading")
                       or palette.get("accent") or ACCENT)
    rule = _hash(palette.get("rule") or RULE)
    body = FAMILIES[_family(palette.get("font"), "sans")]
    head = FAMILIES[_family(palette.get("heading_font"),
                            _family(palette.get("font"), "sans"))]
    try:
        weight = min(6.0, max(0.3, float(palette.get("rule_width"))))
    except (TypeError, ValueError):
        weight = 0.7
    return f"""
:root {{ color-scheme: light; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: #fff; color: {ink};
  font: 16px/1.55 {body}; }}
.px-doc {{ max-width: 46rem; margin: 0 auto; padding: 3rem 1.5rem 4rem; }}
h1, h2, h3 {{ font-family: {head}; color: {heading}; margin: 0 0 .4em; }}
h2, h3 {{ color: {subheading}; }}
h1 {{ font-size: 2.35rem; text-align: center; letter-spacing: -.01em;
  padding-bottom: .5rem; border-bottom: {weight}pt solid {rule}; }}
h2 {{ font-size: .95rem; text-transform: uppercase; letter-spacing: .12em;
  margin-top: 2.2em; padding-bottom: .35rem;
  border-bottom: {weight}pt solid {rule}; }}
h3 {{ font-size: 1.2rem; margin-top: 1.6em; }}
p {{ margin: 0 0 .85em; }}
ul {{ margin: 0 0 1em; padding-left: 1.35em; }}
li {{ margin: .2em 0; }}
.px-spacer {{ height: 1.4em; }}
/* C77 - the callout band. The wash is `color-mix` of the tone's own ink,
   so a band can never end up green with an orange bar; the fallback rule
   above it keeps a readable band on engines without color-mix. */
.px-callout {{ display: flex; gap: .6em; align-items: baseline;
  margin: 1.1em 0; padding: .7em .9em; font-weight: 600;
  border-left: 3px solid currentColor; background: #f2f4f7; }}
@supports (background: color-mix(in srgb, red 10%, white)) {{
  .px-callout {{ background: color-mix(in srgb, currentColor 12%, white); }} }}
.px-callout .px-mark {{ font-weight: 700; flex: none; }}
.px-note {{ color: #1c334f; }}
.px-warning, .px-caution {{ color: #b04a0f; }}
.px-success {{ color: #1a6640; }}
.px-table {{ width: 100%; border-collapse: collapse; margin: 1.2em 0;
  font-size: .95rem; }}
.px-table th, .px-table td {{ text-align: left; padding: .45em .6em;
  border-bottom: 1px solid {rule}; }}
.px-table th {{ color: {accent}; text-transform: uppercase;
  letter-spacing: .06em; font-size: .8rem; }}
.px-chart {{ margin: 1.6em 0; }}
.px-chart-title {{ font-family: {head}; color: {heading}; font-weight: 700;
  font-size: 1.05rem; margin-bottom: .4em; }}
.px-chart-svg {{ display: block; height: auto; }}
.px-tick {{ font: 11px {body}; }}
.px-axis-title {{ font: 12px {body}; opacity: .8; }}
.px-legend {{ font: 12px {body}; }}
@media print {{
  .px-doc {{ max-width: none; padding: 0; }}
  h1, h2, h3, figure, table {{ break-inside: avoid; }}
}}
"""


def build(blocks: list, palette: dict | None = None) -> bytes:
    """Blocks -> a complete standalone `.html` document, as UTF-8 bytes.

    Mirrors `pdf/_write.build` and `word/_write.build` so the orchestrator's
    dispatch line is uniform: `palette` is the same already-PARSED
    `{"accent"|"ink"|"rule"|"heading": (r, g, b), "font": …}` those take, and
    `None` keeps the defaults above.

    **Nothing in the output is fetched.** No `<script>`, no `<link>`, no
    `src=`, no `@import`, no absolute URL. That is the format's contract, not a
    preference, and `tests/test_chart_html.py` gates it.
    """
    palette = palette if isinstance(palette, dict) else {}
    body_font = _family(palette.get("font"), "sans")
    head_font = _family(palette.get("heading_font"), body_font)

    title = ""
    parts: list[str] = []
    open_list = False

    def close_list() -> None:
        nonlocal open_list
        if open_list:
            parts.append("</ul>")
            open_list = False

    for raw in list(blocks or []):
        block = raw if isinstance(raw, dict) else {"type": "paragraph",
                                                   "text": str(raw)}
        kind = str(block.get("type") or "paragraph").strip().lower()
        if kind in ("title", "heading"):
            kind = "heading1"

        if kind != "bullet":
            close_list()

        if kind in ("spacer", "break"):
            parts.append('<div class="px-spacer"></div>')
            continue
        if kind == "image":
            # **An image block cannot reach this writer** — the tool refuses
            # pictures outside docx/pdf. Skipped rather than crashed, because a
            # renderer must never be the thing that raises, and skipped in
            # SILENCE rather than as a broken-image placeholder there is no
            # `src` to give.
            continue
        if kind == "chart":
            parts.append(_chart_block(block, palette))
            continue
        if kind == "table":
            parts.append(_table(block))
            continue
        if kind == "callout":
            # ══ A `<p>` WITH A CLASS, NOT A `<div>` OF SPANS (C77) ═══════════
            # The band is one paragraph that happens to be set apart, and a
            # screen reader should hear it as one. The MARK is decorative — the
            # tone is already in the class and in the text — so it carries
            # `aria-hidden`, which is the difference between a reader hearing
            # *"warning: always use a drip tray"* and hearing *"exclamation
            # mark always use a drip tray"*.
            tone = str(block.get("tone") or "note").strip().lower()
            if tone not in _CALLOUT_MARK:
                tone = "note"
            parts.append(
                f'<p class="px-callout px-{tone}">'
                f'<span class="px-mark" aria-hidden="true">'
                f'{escape(_CALLOUT_MARK[tone])}</span>'
                f'{_inline(block.get("text"))}</p>')
            continue

        style = _style_attr(block, body=body_font, heading=head_font,
                            is_heading=kind.startswith("heading"))
        text = _inline(block.get("text"))
        if kind == "bullet":
            if not open_list:
                parts.append("<ul>")
                open_list = True
            parts.append(f"<li{style}>{text}</li>")
            continue
        tag = _HEADINGS.get(kind)
        if tag:
            if not title and kind == "heading1":
                title = str(block.get("text") or "")
            parts.append(f"<{tag}{style}>{text}</{tag}>")
            continue
        parts.append(f"<p{style}>{text}</p>")
    close_list()

    document = (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{escape(_inline_text(title) or 'Document')}</title>\n"
        f"<style>{_css(palette)}</style>\n</head>\n"
        f'<body>\n<main class="px-doc">{"".join(parts)}</main>\n</body>\n</html>\n'
    )
    return document.encode("utf-8")


def _inline_text(text: str) -> str:
    """A heading's text with its emphasis markers dropped, for `<title>` — a
    document called `**Q3 Report**` is a document whose tab says `**Q3
    Report**`."""
    return "".join(r.text for r in runs(str(text or ""))).strip()
