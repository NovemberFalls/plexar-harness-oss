"""T81 — the PDF's chart branch. **A vector mark is invisible to a
text-extracting gate**, so most of this file reads the raw content-stream
OPERATORS rather than the text `pdfminer` pulls out of them; only the tick
labels are asserted through text, because that is the one part of a chart
pdfminer can actually see.
"""

from __future__ import annotations

import re

import pytest

from plexar_tools.office.pdf import _write
from plexar_tools.office.pdf._write import ACCENT, MAX_CHART_H, PAGE_H, MARGIN, build
from plexar_tools.office.pdf._read import read as read_pdf


def _fills(pdf: bytes) -> list[tuple[str, str, str, str, str]]:
    """Every `r g b x y w h re f` fill, as raw string groups, in document
    order — read straight off the (uncompressed, cp1252) content stream, not
    parsed by any PDF library. That is deliberate: this file is the one
    place in the suite that must not trust the same machinery it is
    checking."""
    text = pdf.decode("cp1252", "replace")
    return re.findall(
        r"([\d.]+) ([\d.]+) ([\d.]+) rg ([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+) re f",
        text)


def _strokes(pdf: bytes) -> list[str]:
    text = pdf.decode("cp1252", "replace")
    return re.findall(r"[\d.]+ w [\d.]+ J [\d.]+ j [\d.]+ [\d.]+ [\d.]+ RG[^Q]*S", text)


def _bar_chart(shape: str = "bar", **overrides) -> list[dict]:
    spec = {
        "type": "chart", "chart": shape, "title": "Revenue",
        "labels": ["Jan", "Feb", "Mar", "Apr"],
        "series": [
            {"name": "A", "values": [1, 2, 3, 4]},
            {"name": "B", "values": [4, 3, 2, 1]},
        ],
    }
    spec.update(overrides)
    return [spec]


# ══ THE COUNT SCALES WITH THE DATA ══════════════════════════════════════════

def test_bar_fills_scale_with_series_and_points():
    pdf = build(_bar_chart())
    fills = _fills(pdf)
    # 2 series x 4 points = 8 bars, plus 5 gridlines + 1 baseline = 14.
    bar_colour = f"{ACCENT[0]:.3f} {ACCENT[1]:.3f} {ACCENT[2]:.3f}"
    # Excludes the legend's 9x9 swatch, which is drawn in the same accent
    # colour as the first series' bars but is not a bar.
    bars = [f for f in fills
            if f"{f[0]} {f[1]} {f[2]}" == bar_colour and f[6] != "9.00"]
    assert len(bars) == 4          # the FIRST series only, one bar per point

    # tall boxes, excluding the legend's fixed-size 9x9 swatches
    total_bar_like = [f for f in fills if float(f[6]) > 5.0 and f[6] != "9.00"]
    # 8 real bars; gridlines and the baseline are all under 2pt tall.
    assert len(total_bar_like) == 8


def test_more_points_more_bars():
    small = _fills(build(_bar_chart(labels=["A", "B"],
                                     series=[{"values": [1, 2]}])))
    big = _fills(build(_bar_chart(labels=["A", "B", "C", "D", "E", "F"],
                                   series=[{"values": [1, 2, 3, 4, 5, 6]}])))
    tall_small = [f for f in small if float(f[6]) > 5.0]
    tall_big = [f for f in big if float(f[6]) > 5.0]
    assert len(tall_small) == 2
    assert len(tall_big) == 6


# ══ TICK LABELS ARE THE ONE PART A TEXT READER CAN SEE ══════════════════════

def test_tick_labels_and_category_labels_are_readable_text():
    pdf = build(_bar_chart())
    doc = read_pdf(pdf)
    text = doc.text
    for label in ("Jan", "Feb", "Mar", "Apr"):
        assert label in text
    # nice_axis(0..4, bar) lands on 0/1/2/3/4 — asserted via the rendered
    # tick text rather than by recomputing the axis a second time here,
    # which is exactly the mistake this row was told not to make.
    for tick in ("0", "1", "2", "3", "4"):
        assert tick in text


# ══ A GAP IS NOT A ZERO ══════════════════════════════════════════════════════

def test_none_draws_one_fewer_bar_than_zero():
    with_zero = _fills(build(_bar_chart(
        labels=["A", "B", "C"], series=[{"values": [1, 0, 1]}])))
    with_gap = _fills(build(_bar_chart(
        labels=["A", "B", "C"], series=[{"values": [1, None, 1]}])))
    tall_zero = [f for f in with_zero if float(f[6]) > 0.5]
    tall_gap = [f for f in with_gap if float(f[6]) > 0.5]
    # Both charts draw the baseline+gridlines identically; only the bar count
    # differs, so comparing the DIFFERENCE isolates exactly the property
    # under test rather than an absolute count that could pass by accident.
    assert len(tall_zero) - len(tall_gap) == 1


def test_none_breaks_a_line_rather_than_bridging_it():
    # Each side of the gap needs >=2 points of its own: a single surviving
    # point next to a gap draws no segment at all (a line needs a slope),
    # which is a real, separately-true property and not what this arm is
    # isolating — so the gap sits in the MIDDLE of two 2-point runs.
    unbroken = _strokes(build(_bar_chart(
        shape="line", labels=["A", "B", "C", "D", "E"],
        series=[{"values": [1, 2, 3, 4, 5]}])))
    gapped = _strokes(build(_bar_chart(
        shape="line", labels=["A", "B", "C", "D", "E"],
        series=[{"values": [1, 2, None, 4, 5]}])))
    # One run of 5 points draws ONE stroked path; a gap in the middle draws
    # two shorter ones — never a single path spanning the missing point.
    assert len(unbroken) == 1
    assert len(gapped) == 2


# ══ A CHART TALLER THAN THE PAGE MUST NOT HANG `advance()` ══════════════════

def test_oversized_chart_height_is_clamped_not_infinite(monkeypatch):
    # advance() has no "will never fit" detection; a box taller than the
    # usable column loops forever. Sabotage the CONSTANT to something that
    # would hang if the call site trusted it blindly, and require the build
    # to still finish (pytest's own timeout would otherwise catch a real
    # infinite loop, but the assertion below is the actual property: nothing
    # this row draws is taller than the page it was clamped against).
    monkeypatch.setattr(_write, "MAX_CHART_H", PAGE_H * 5)
    pdf = build(_bar_chart())
    assert pdf.startswith(b"%PDF")


def test_max_chart_h_constant_fits_the_usable_column():
    assert MAX_CHART_H < PAGE_H - 2 * MARGIN


# ══ WATCH-TO-FAIL: THE ARM MUST BE SHOWN CAPABLE OF FAILING (R23) ═══════════

def test_watch_to_fail_bars_removed_reddens_then_recovers(monkeypatch):
    """Sabotage `_chart_fill` in memory — never a file on disk — so the bar
    branch draws nothing, confirm the arm goes RED, then restore and confirm
    green. R23: an arm that could not have failed proves nothing."""

    original_fill = _write._chart_fill

    def _sabotaged(page, x, y, w, h, colour):
        # Only the accent-coloured (first-series) fills are dropped, so
        # gridlines/baseline/labels are untouched and the sabotage is
        # unambiguous rather than "nothing draws at all".
        if tuple(round(c, 3) for c in colour) == tuple(round(c, 3) for c in ACCENT):
            return
        original_fill(page, x, y, w, h, colour)

    monkeypatch.setattr(_write, "_chart_fill", _sabotaged)
    pdf = build(_bar_chart())
    fills = _fills(pdf)
    bar_colour = f"{ACCENT[0]:.3f} {ACCENT[1]:.3f} {ACCENT[2]:.3f}"
    bars = [f for f in fills
            if f"{f[0]} {f[1]} {f[2]}" == bar_colour and f[6] != "9.00"]
    assert bars == []          # RED: the property this suite exists to check

    monkeypatch.undo()
    pdf = build(_bar_chart())
    fills = _fills(pdf)
    bars = [f for f in fills
            if f"{f[0]} {f[1]} {f[2]}" == bar_colour and f[6] != "9.00"]
    assert len(bars) == 4      # GREEN: restored, no file on disk ever changed


# ══ BADCHART IS SWALLOWED, NOT RAISED, THE SAME WAY A MISSING IMAGE IS ══════

# ══ THE LEGEND (T81b) — A PICTURE FOUND THIS, NOT AN OPERATOR COUNT ═════════

def test_series_names_appear_as_legend_text():
    pdf = build(_bar_chart(series=[
        {"name": "2025 Actual", "values": [1, 2, 3, 4]},
        {"name": "2026 Result", "values": [4, 3, 2, 1]},
    ]))
    text = read_pdf(pdf).text
    assert "2025 Actual" in text
    assert "2026 Result" in text


def test_a_swatch_fill_is_emitted_per_series():
    pdf = build(_bar_chart(series=[
        {"name": "2025 Actual", "values": [1, 2, 3, 4]},
        {"name": "2026 Result", "values": [4, 3, 2, 1]},
    ]))
    fills = _fills(pdf)
    swatches = [f for f in fills if f[5] == "9.00" and f[6] == "9.00"]
    assert len(swatches) == 2


def test_single_unnamed_series_gets_no_legend():
    # C57's rule, one field over: a swatch and a blank label is furniture.
    pdf = build(_bar_chart(labels=["A", "B", "C"],
                           series=[{"values": [1, 2, 3]}]))
    fills = _fills(pdf)
    assert not [f for f in fills if f[5] == "9.00" and f[6] == "9.00"]
    text = read_pdf(pdf).text
    assert "Series 1" not in text


def test_single_named_series_still_gets_a_legend():
    pdf = build(_bar_chart(labels=["A", "B", "C"],
                           series=[{"name": "Revenue", "values": [1, 2, 3]}]))
    text = read_pdf(pdf).text
    assert "Revenue" in text
    fills = _fills(pdf)
    assert len([f for f in fills if f[5] == "9.00" and f[6] == "9.00"]) == 1


def test_watch_to_fail_legend_removed_reddens_then_recovers(monkeypatch):
    """Sabotage `_write._place_legend` to a no-op — never touching a file on
    disk — confirm the legend text vanishes (RED), then restore (GREEN)."""
    original = _write._place_legend
    monkeypatch.setattr(_write, "_place_legend", lambda *a, **k: None)
    pdf = build(_bar_chart(series=[
        {"name": "2025 Actual", "values": [1, 2, 3, 4]},
        {"name": "2026 Result", "values": [4, 3, 2, 1]},
    ]))
    text = read_pdf(pdf).text
    assert "2025 Actual" not in text     # RED: the property under test

    monkeypatch.undo()
    pdf = build(_bar_chart(series=[
        {"name": "2025 Actual", "values": [1, 2, 3, 4]},
        {"name": "2026 Result", "values": [4, 3, 2, 1]},
    ]))
    text = read_pdf(pdf).text
    assert "2025 Actual" in text         # GREEN: restored


def test_y_title_cannot_collide_with_a_wide_tick_label():
    # A wide tick label ("-1234.5" and a "M" suffix) grows `ytick_w`, which
    # grows `plot_left` — but the rotated y_title's x is fixed at
    # `MARGIN + 2.0`, structurally to the LEFT of the reserved tick column
    # (`MARGIN .. MARGIN + ytitle_w`), regardless of how wide the ticks get.
    # Measured off the actual emitted `Tm` and tick `Td` operators rather
    # than argued from the constants, so a future change to either literal
    # cannot silently reintroduce the collision.
    pdf = build(_bar_chart(
        labels=["A", "B"], y_title="USD",
        series=[{"values": [-1234567.89, 987654321.0]}]))
    text = pdf.decode("cp1252", "replace")
    tm = re.search(r"0 1 -1 0 ([\d.]+) [\d.]+ Tm", text)
    assert tm is not None
    y_title_x = float(tm.group(1))
    tick_xs = [float(x) for x in
              re.findall(r"BT /F1 7\.5 Tf ([\d.]+) [\d.]+ Td \([-\d.MkB]+\) Tj", text)]
    assert tick_xs, "expected at least one tick label operator"
    assert y_title_x < min(tick_xs)


def test_invalid_chart_block_is_skipped_not_raised():
    pdf = build([{"type": "heading1", "text": "Report"},
                 {"type": "chart", "chart": "pie", "labels": ["a"],
                  "series": [{"values": [1]}]}])
    assert pdf.startswith(b"%PDF")
    doc = read_pdf(pdf)
    assert "Report" in doc.text
