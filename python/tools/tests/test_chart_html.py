"""T81 — the `html` writer, and the two properties it exists for.

**1 · IT IS SELF-CONTAINED.** The file is downloaded and opened off disk with no
network. Every external reference in it is a blank box on the user's machine,
and C50's vendored Chart.js resolves only on the artifact origin — which is why
the charts are inline SVG and why the absence of `<script>`, `src=`, `@import`
and any absolute URL is asserted rather than assumed.

**2 · A GAP IS NOT A ZERO.** A missing month drawn at the baseline is a claim
the document does not have, and the reader cannot see that it is missing. So a
`None` costs a bar and BREAKS a line, measured against the same series with
`0.0` in the same slot.

The SVG is parsed, not substring-matched: a malformed `<svg>` renders nothing
and would pass every `in` check in this file.
"""

from __future__ import annotations

import re
import xml.dom.minidom as minidom

import pytest

from plexar_tools.office._chart import nice_axis, parse_chart, tick_labels
from plexar_tools.office.html import _write
from plexar_tools.office.html._write import build

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
FULL = [10.0, 14.0, 9.0, 22.0, 18.0, 25.0]


def chart(shape="line", values=None, **extra):
    block = {"type": "chart", "chart": shape, "labels": list(MONTHS),
             "series": [{"name": "Revenue",
                         "values": list(FULL if values is None else values)}]}
    block.update(extra)
    return block


def html(blocks, palette=None) -> str:
    body = build(blocks, palette)
    assert isinstance(body, bytes)
    return body.decode("utf-8")


def svg_of(text: str) -> minidom.Document:
    """The `<svg>` fragment, PARSED. Well-formedness is the assertion."""
    match = re.search(r"<svg\b.*?</svg>", text, re.S)
    assert match, "no <svg> in the output"
    return minidom.parseString(match.group(0))


def marks_in(text: str, tag: str) -> int:
    return len(svg_of(text).getElementsByTagName(tag))


# ══ WELL-FORMEDNESS ═════════════════════════════════════════════════════════

@pytest.mark.parametrize("shape", ["line", "bar"])
def test_the_svg_parses(shape):
    doc = svg_of(html([chart(shape)]))
    assert doc.documentElement.tagName == "svg"


def test_the_whole_document_is_walkable_xml():
    """The document body, parsed as XML. **Void elements are the reason this
    normalises rather than parsing the file as shipped** — `<meta>` is legal
    HTML and illegal XML, so the assertion is about OUR markup being balanced,
    which is where an escaping defect would show."""
    text = html([{"type": "heading1", "text": "Q3 & Co <Report>"},
                 {"type": "paragraph", "text": "One **bold** word."},
                 {"type": "bullet", "text": "first"},
                 {"type": "bullet", "text": "second"},
                 {"type": "table", "rows": [["a", "b"], ["1", "2"]]},
                 {"type": "spacer"},
                 chart("bar")])
    main = re.search(r"<main\b.*</main>", text, re.S)
    assert main
    minidom.parseString(main.group(0))


# ══ ZERO EXTERNAL REFERENCES — THE WHOLE REASON FOR SVG ═════════════════════

FORBIDDEN = ("http://", "https://", "//cdn", "<script", "src=", "@import",
             "<link", "url(", "xlink:href")


def test_nothing_is_fetched():
    text = html([{"type": "heading1", "text": "Report"},
                 {"type": "paragraph", "text": "prose"},
                 chart("line"), chart("bar"),
                 {"type": "table", "rows": [["a"], ["b"]]}],
                {"accent": (0.1, 0.4, 0.7), "font": "serif"})
    for token in FORBIDDEN:
        assert token not in text.lower(), f"{token!r} is in the output"


def test_a_model_authored_url_is_still_not_a_reference():
    """A URL the model TYPED is text, and it must stay text. This is the one
    case where the blanket rule needs a reading: the characters may appear, but
    only inside escaped character data — never in an attribute that fetches."""
    text = html([{"type": "paragraph",
                  "text": "see https://example.com/x"}])
    assert "https://example.com/x" in text
    assert "<script" not in text and "src=" not in text
    assert "<a " not in text  # nothing is turned INTO a link


# ══ THE MARKS SCALE WITH THE DATA ═══════════════════════════════════════════

def test_one_bar_per_value():
    assert marks_in(html([chart("bar")]), "rect") == len(FULL)


def test_two_series_double_the_bars():
    block = chart("bar")
    block["series"].append({"name": "Cost", "values": [1.0] * len(FULL)})
    assert marks_in(html([block]), "rect") == 2 * len(FULL)


def test_a_line_is_one_polyline():
    assert marks_in(html([chart("line")]), "polyline") == 1


# ══ A GAP IS NOT A ZERO ═════════════════════════════════════════════════════

def test_a_null_costs_a_bar():
    zeroed = list(FULL)
    zeroed[2] = 0.0
    gapped = list(FULL)
    gapped[2] = None
    with_zero = marks_in(html([chart("bar", zeroed)]), "rect")
    with_gap = marks_in(html([chart("bar", gapped)]), "rect")
    assert with_zero == len(FULL)
    assert with_gap == with_zero - 1


def test_a_null_breaks_the_line():
    zeroed = list(FULL)
    zeroed[2] = 0.0
    gapped = list(FULL)
    gapped[2] = None
    assert marks_in(html([chart("line", zeroed)]), "polyline") == 1
    assert marks_in(html([chart("line", gapped)]), "polyline") == 2


def test_a_point_with_gaps_on_both_sides_is_still_drawn():
    """**The defect a screenshot found and no count could.** The first draft
    flushed a run only when it held 2+ points, so a value fenced by nulls was
    discarded and the series appeared to start later than it does. Every
    polyline count was green: a mark that is absent entirely reddens nothing
    that counts marks. Real data rendered as absent is the gap defect inverted.
    """
    lonely = [10.0, None, 9.0, None, 18.0, 25.0]
    text = html([chart("line", lonely)])
    doc = svg_of(text)
    dots = [c for c in doc.getElementsByTagName("circle")
            if c.getAttribute("class") == "px-point"]
    # Jan and Mar are lone points; May-Jun is a real segment.
    assert len(dots) == 2
    assert marks_in(text, "polyline") == 1


def test_a_gapped_line_never_touches_the_baseline_at_the_gap():
    """The stronger form: not only two polylines, but no vertex AT the gap's x.
    A run that ended by plotting the gap at zero would still count as two."""
    gapped = list(FULL)
    gapped[2] = None
    doc = svg_of(html([chart("line", gapped)]))
    xs = set()
    for line in doc.getElementsByTagName("polyline"):
        for point in line.getAttribute("points").split():
            xs.add(round(float(point.split(",")[0]), 1))
    # index 2 of 6 points across the plot
    gap_x = round(_write.PLOT_L + 2 * (_write.PLOT_W / 5), 1)
    assert gap_x not in xs


# ══ THE SHARED GEOMETRY, NOT A SECOND ONE ═══════════════════════════════════

@pytest.mark.parametrize("shape", ["line", "bar"])
def test_the_tick_labels_are_the_shared_ones_verbatim(shape):
    block = chart(shape)
    parsed = parse_chart(block)
    wanted = tick_labels(nice_axis(parsed))
    assert wanted
    text = html([block])
    for label in wanted:
        assert f">{label}</text>" in text, f"{label!r} missing from the axis"


def test_big_numbers_keep_one_unit_down_the_axis():
    """`tick_labels` picks the divisor from the largest tick, once. Reformatting
    here would rebuild the `900k` beside `1M` defect its docstring describes."""
    values = [936204.81, 972929.0, 941000.0, 950000.0, 960000.0, 999000.0]
    block = chart("line", values)
    wanted = tick_labels(nice_axis(parse_chart(block)))
    suffixes = {label[-1] for label in wanted}
    assert len(suffixes) == 1
    text = html([block])
    for label in wanted:
        assert f">{label}</text>" in text


def test_the_flip_happens_once_and_bigger_means_higher():
    """`fraction()` is 0 at the plot BOTTOM; SVG y grows DOWN. So the tallest
    bar must have the SMALLEST y. A second, unflipped conversion anywhere would
    reverse this."""
    doc = svg_of(html([chart("bar")]))
    tops = [float(r.getAttribute("y")) for r in doc.getElementsByTagName("rect")]
    assert tops[FULL.index(max(FULL))] == min(tops)
    assert tops[FULL.index(min(FULL))] == max(tops)
    assert all(_write.PLOT_T - 1 <= y <= _write.PLOT_B + 1 for y in tops)


# ══ INJECTION ═══════════════════════════════════════════════════════════════

HOSTILE = "</svg><script>alert(1)</script>"


def test_a_hostile_chart_title_is_text():
    text = html([chart("bar", title=HOSTILE)])
    assert "<script" not in text.lower()
    assert "alert(1)" not in text or "&lt;script&gt;" in text
    # Exactly ONE `</svg>` — the real one. The title's must have been escaped.
    assert text.count("</svg>") == 1
    assert "&lt;/svg&gt;" in text
    svg_of(text)  # and it still parses


def test_hostile_series_names_and_axis_captions_are_text():
    block = {"type": "chart", "chart": "line", "labels": list(MONTHS),
             "x_title": HOSTILE, "y_title": '" onload="alert(1)',
             "series": [{"name": HOSTILE, "values": list(FULL)},
                        {"name": "b", "values": list(FULL)}]}
    text = html([block])
    assert "<script" not in text.lower()
    # **The characters may appear; an ATTRIBUTE may not.** `&quot; onload=&quot;`
    # is escaped character data and is the correct output — asserting the
    # substring alone would fail on a document that is exactly right.
    assert 'onload="' not in text.lower() and "onload='" not in text.lower()
    assert text.count("</svg>") == 1
    svg_of(text)


def test_hostile_prose_and_table_cells_are_text():
    text = html([{"type": "heading1", "text": "<script>x</script>"},
                 {"type": "paragraph", "text": "</main><script>y</script>"},
                 {"type": "table",
                  "rows": [["</td><script>z</script>"], ["&"]]}])
    assert "<script" not in text.lower()
    assert text.count("</main>") == 1
    assert "&amp;" in text


def test_a_hostile_style_field_cannot_close_the_attribute():
    text = html([{"type": "paragraph", "text": "x",
                  "font": '" onmouseover="alert(1)'}])
    assert "onmouseover" not in text.lower()


# ══ THE BLOCK VOCABULARY, AND NOT CRASHING ══════════════════════════════════

def test_every_block_kind_renders():
    text = html([{"type": "title", "text": "T"},
                 {"type": "heading2", "text": "H2"},
                 {"type": "heading3", "text": "H3"},
                 {"type": "paragraph", "text": "p"},
                 {"type": "bullet", "text": "b1"},
                 {"type": "bullet", "text": "b2"},
                 {"type": "spacer"},
                 {"type": "table", "rows": [["h"], ["c"]]},
                 chart("bar")])
    for tag in ("<h1", "<h2", "<h3", "<p", "<ul>", "<li", "<table", "<svg"):
        assert tag in text
    # `</li>`, not `<li` — **`<li` also matches the SVG's `<line>`**, which is
    # the kind of count that passes for the wrong reason.
    assert text.count("<ul>") == 1 and text.count("</li>") == 2


def test_an_image_block_does_not_crash():
    """It cannot arrive — the tool refuses pictures outside docx/pdf — and a
    renderer must never be the thing that raises."""
    text = html([{"type": "image", "image": None},
                 {"type": "paragraph", "text": "after"}])
    assert "after" in text
    assert "<img" not in text and "src=" not in text


def test_garbage_blocks_do_not_crash():
    text = html(["a bare string", None, 7, {"type": "wat", "text": "x"},
                 {"type": "chart"}, {"type": "table", "rows": "nope"}])
    assert "a bare string" in text
    svg = re.search(r"<svg\b", text)
    assert svg is None  # an unparseable chart draws nothing, not a blank box


def test_no_palette_still_builds():
    assert b"<!DOCTYPE html>" in build([chart("line")], None)


def test_the_palette_reaches_the_document():
    text = html([{"type": "heading1", "text": "T"}, chart("bar")],
                {"accent": (1.0, 0.0, 0.0), "ink": (0.0, 0.0, 0.0),
                 "font": "serif", "rule_width": 3.0})
    assert "#ff0000" in text.lower()
    assert "Georgia" in text
    assert "3pt solid" in text or "3.0pt solid" in text


def test_a_per_block_colour_and_alignment_render():
    text = html([{"type": "paragraph", "text": "x",
                  "colour": (0.1, 0.2, 0.3), "align": "centre",
                  "bold": True, "italic": True, "size": 18}])
    assert "text-align:center" in text
    assert "font-weight:700" in text and "font-style:italic" in text
    assert "font-size:18pt" in text


# ══ R23 — AN ASSERTION THAT CANNOT FAIL IS NOT AN ASSERTION ═════════════════

def test_watch_the_mark_count_fail(monkeypatch):
    """Replace the mark drawer with one that emits nothing and confirm the
    count assertions REDDEN, then confirm green is restored.

    **The patch is in memory. No file on disk is ever wrong** — this repo serves
    HEAD to the public internet (T5), and C54c's bill arrived from a
    watch-to-fail arm that sabotaged a real file.
    """
    assert marks_in(html([chart("bar")]), "rect") == len(FULL)

    monkeypatch.setattr(_write, "marks", lambda *a, **k: "")
    blank = html([chart("bar")])
    assert marks_in(blank, "rect") == 0
    assert marks_in(html([chart("line")]), "polyline") == 0
    # and the chrome is still there, so a zero cannot mean "no chart was drawn"
    wanted = tick_labels(nice_axis(parse_chart(chart("bar"))))
    for label in wanted:
        assert f">{label}</text>" in blank

    monkeypatch.undo()
    assert marks_in(html([chart("bar")]), "rect") == len(FULL)


def test_watch_the_escape_fail(monkeypatch):
    """With the escaper neutered, the injection arm must fail. Proves those
    assertions are load-bearing rather than true of any output."""
    monkeypatch.setattr(_write, "escape", lambda t: "" if t is None else str(t))
    text = html([chart("bar", title=HOSTILE)])
    assert "<script" in text.lower()
    # More than one, and the exact number is not the point: the title reaches
    # the figcaption, the SVG `<title>` and the `aria-label`, so the unescaped
    # form closes the element in three places rather than one.
    assert text.count("</svg>") > 1
    monkeypatch.undo()
    assert "<script" not in html([chart("bar", title=HOSTILE)]).lower()


def test_watch_the_gap_fail(monkeypatch):
    """A `None` plotted at the baseline instead of skipped: the bar count stops
    dropping and the line stops breaking. This is the false measurement the gap
    assertions exist to refuse."""
    real = _write.fraction

    def zero_gap(value, axis):
        return real(0.0 if value is None else value, axis)

    def flat_marks(chart_, axis, accent):
        patched = type(chart_)(
            shape=chart_.shape, title=chart_.title, labels=chart_.labels,
            series=tuple(type(s)(name=s.name,
                                 values=tuple(0.0 if v is None else v
                                              for v in s.values),
                                 colour=s.colour) for s in chart_.series),
            x_title=chart_.x_title, y_title=chart_.y_title)
        return real_marks(patched, axis, accent)

    real_marks = _write.marks
    monkeypatch.setattr(_write, "marks", flat_marks)
    gapped = list(FULL)
    gapped[2] = None
    assert marks_in(html([chart("bar", gapped)]), "rect") == len(FULL)
    assert marks_in(html([chart("line", gapped)]), "polyline") == 1
    monkeypatch.undo()
    assert marks_in(html([chart("bar", gapped)]), "rect") == len(FULL) - 1
    assert marks_in(html([chart("line", gapped)]), "polyline") == 2
    assert zero_gap  # named for the reader; the patch above is the mechanism
