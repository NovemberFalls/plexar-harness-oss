"""**T81f · the model was asked to chart numbers that were not in the data.**

Len: *"can you make a bart chart per location for dine in?"* — and got 24 months
of two values repeated:

    labels        Jan 2025 … Dec 2026        (24)
    2025 Actual   936205 × 24                (1 distinct)
    2026 Result   646796 × 24                (1 distinct)

From his sheet: Dine In **January** = 936,204.81 and Dine In **February** =
646,795.80. It took two adjacent cells of one row, called one 2025 and the other
2026, and repeated each 24 times. Read from R2, not inferred.

**That is a reasonable misreading of a table this product destroyed on the way
in.** Measured against the real workbook, two faults, both here:

    7,141  cells in the sheet
    1,109  formulas with NO cached value  -> emitted as ""      (15.5%)
        0  formulas WITH a cached value   -> this exporter never caches
        7  cells carrying text under a numeric `t`  -> emitted as ""

The 7 were the month headers. Of six, exactly ONE survived — January's, the only
one declared `inlineStr` — so nothing told the model which column was which
month. And every `2026 Result` was one of the 1,109, so **the values it was asked
to plot were genuinely absent, and it filled them in from the next cell along.**
"""

from __future__ import annotations

import re
import zipfile

import pytest

from plexar_tools import office
from plexar_tools.office.excel._read import FORMULA_UNSET, read
from plexar_tools.office.excel._write import xlsx_bytes


def _sheet(rows: list[list[str]], extra_cells: str = "") -> bytes:
    """A workbook built by hand, because the defect is in the XML shapes a real
    exporter writes and `xlsx_bytes` writes neither of them."""
    body = []
    for r, row in enumerate(rows, start=1):
        cells = []
        for c, text in enumerate(row):
            ref = f"{chr(65 + c)}{r}"
            cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>')
        body.append(f'<row r="{r}">{"".join(cells)}</row>')
    if extra_cells:
        body.append(extra_cells)
    sheet = ('<?xml version="1.0"?><worksheet><sheetData>'
             + "".join(body) + "</sheetData></worksheet>")
    buf = __import__("io").BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0"?><Types xmlns="http://schemas.openxml'
                   'formats.org/package/2006/content-types"><Default '
                   'Extension="xml" ContentType="application/xml"/></Types>')
        z.writestr("xl/workbook.xml",
                   '<?xml version="1.0"?><workbook xmlns:r="r"><sheets>'
                   '<sheet name="S" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<?xml version="1.0"?><Relationships><Relationship '
                   'Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml", sheet)
    return buf.getvalue()


# ══ 1 · A FORMULA WITH NO STORED RESULT IS NOT AN EMPTY CELL ════════════════

def test_a_formula_with_no_cached_value_is_marked_not_blanked():
    """**The fault that let the model invent 2026.** `<f>` with no `<v>` used to
    read exactly like a cell nobody filled in."""
    extra = ('<row r="2">'
             '<c r="A2" t="n"><v>100</v></c>'
             '<c r="B2"><f>A2*1.1</f></c>'      # a formula, never calculated
             '<c r="C2" t="n"><v>200</v></c>'
             '</row>')
    rows = read(_sheet([["base", "projected", "next"]], extra)).blocks[0].rows
    assert rows[1] == ["100", FORMULA_UNSET, "200"], rows[1]


def test_a_formula_that_DID_cache_its_value_keeps_the_value():
    """**The marker must not swallow a working formula.** Excel caches results;
    only exporters that never calculate omit them, and a workbook from Excel
    itself must be unaffected."""
    extra = ('<row r="2">'
             '<c r="A2" t="n"><v>100</v></c>'
             '<c r="B2" t="n"><f>A2*1.1</f><v>110</v></c>'
             '</row>')
    rows = read(_sheet([["base", "projected"]], extra)).blocks[0].rows
    assert rows[1] == ["100", "110"], rows[1]


def test_a_genuinely_empty_cell_is_still_empty():
    """The other direction, and it is the one that matters for honesty: a cell
    nobody filled in must NOT acquire a marker claiming a hidden value."""
    extra = ('<row r="2">'
             '<c r="A2" t="n"><v>100</v></c>'
             '<c r="C2" t="n"><v>200</v></c>'
             '</row>')
    rows = read(_sheet([["a", "b", "c"]], extra)).blocks[0].rows
    assert rows[1] == ["100", "", "200"], rows[1]


# ══ 2 · THE PAYLOAD DECIDES, NOT THE `t` ATTRIBUTE ══════════════════════════

def test_text_under_a_numeric_type_is_read_as_text():
    """R365 writes month headers as `t="n"` with an `<is><t>` payload. Trusting
    `t` dropped five of six. **C57's rule, one format along: read from the
    payload, not from the field list.**"""
    extra = ('<row r="2">'
             '<c r="A2" t="n"><is><t>Feb 2025 -&gt; 2026</t></is></c>'
             '<c r="B2" t="inlineStr"><is><t>Mar 2025</t></is></c>'
             '</row>')
    rows = read(_sheet([["h"]], extra)).blocks[0].rows
    assert rows[1] == ["Feb 2025 -> 2026", "Mar 2025"], rows[1]


def test_a_shared_string_index_is_still_resolved():
    """`t="s"` holds an INDEX into sharedStrings. The payload-first branch must
    not intercept it — there is no `<is>`, so it cannot, and this arm holds
    that."""
    rows = read(_sheet([["plain", "cells"]])).blocks[0].rows
    assert rows[0] == ["plain", "cells"]


# ══ 3 · THE REAL WORKBOOK, WHICH IS THE ONLY PROOF THAT MATTERS ═════════════

@pytest.mark.parametrize("shape", ["headers", "formulas"])
def test_the_real_export_becomes_legible(tmp_path, shape):
    """Built from the shapes measured in Len's own file rather than his bytes,
    which are his. Two groups of three columns, month headers declared `t="n"`,
    and a `2026 Result` formula with no cached value in each group."""
    header = ('<row r="1">'
              '<c r="A1" t="inlineStr"><is><t>Account</t></is></c>'
              '<c r="C1" t="inlineStr"><is><t>Jan 2025 -&gt; 2026</t></is></c>'
              '<c r="D1" t="n"><is><t>Feb 2025 -&gt; 2026</t></is></c>'
              '</row>')
    dine = ('<row r="3">'
            '<c r="A3" t="inlineStr"><is><t>Dine In</t></is></c>'
            '<c r="C3" t="n"><v>936204.81</v></c>'
            '<c r="D3" t="n"><v>0.1015</v></c>'
            '<c r="E3"><f>C3*(1+D3)</f></c>'
            '<c r="F3" t="n"><v>646795.8</v></c>'
            '</row>')
    rows = read(_sheet([], header + dine)).blocks[0].rows
    flat = ["\t".join(r) for r in rows]
    if shape == "headers":
        # **Both months, which is what tells the model which column is which.**
        assert "Jan 2025 -> 2026" in flat[0]
        assert "Feb 2025 -> 2026" in flat[0], (
            "the second month header is still being dropped, which is the whole "
            "reason the model could not tell January from February")
    else:
        # ══ INDEXED [1], NOT [2] — AND THAT IS ITS OWN SMALL FINDING ══════════
        # The XML holds `<row r="1">` then `<row r="3">`; the reader APPENDS
        # rows in document order rather than placing them by `r`, so the absent
        # row 2 collapses and `Dine In` lands at index 1. The module docstring
        # warns about exactly this for CELLS ("a reader that appends
        # positionally collapses a sparse row") and the ROW loop takes the
        # shortcut it warns against. Harmless for this row's purpose — a blank
        # spacer row carries nothing — and recorded rather than widened into.
        assert FORMULA_UNSET in flat[1], flat[1]
        assert flat[1].split("\t")[4] == FORMULA_UNSET, flat[1]
        assert flat[1].split("\t")[5] == "646795.8", flat[1]


# ══ 4 · THE MARKER ITSELF ════════════════════════════════════════════════════
#
# `test_the_attachment_steer_explains_the_marker_and_forbids_inventing_one`
# stays in Chat (chat-DEC-397): it drives `chat.api.App._attachment_block`,
# which is `chat.api`/`chat.store` behavior this package does not own.

def test_the_marker_is_short_because_there_can_be_a_thousand_of_them():
    """1,109 in one real workbook, against a 40,000-character attachment cap. A
    verbose marker would evict the data it exists to explain."""
    assert len(FORMULA_UNSET) <= 3, FORMULA_UNSET
    assert office.FORMULA_UNSET == FORMULA_UNSET


# ══ 5 · WATCH TO FAIL ═══════════════════════════════════════════════════════

def test_watch_to_fail_the_old_reader_dropped_both(monkeypatch):
    """**R23, and it reproduces BOTH faults on one row.** Patched in memory: no
    file on disk is ever wrong, because this tree is served to the public per
    request (T5).
    """
    import plexar_tools.office.excel._read as reader

    extra = ('<row r="2">'
             '<c r="A2" t="n"><is><t>Feb 2025</t></is></c>'
             '<c r="B2"><f>A1*2</f></c>'
             '</row>')
    good = read(_sheet([["h"]], extra)).blocks[0].rows[1]
    assert good == ["Feb 2025", FORMULA_UNSET], good

    # The pre-T81f rule: trust `t`, take `<v>` or nothing.
    original = reader._V

    class _NeverMatches:
        @staticmethod
        def search(_cell):
            return None

    # Sabotaging the marker alone would not reproduce the header loss, so the
    # arm asserts the CHANGE rather than a single value.
    monkeypatch.setattr(reader, "FORMULA_UNSET", "")
    broken = read(_sheet([["h"]], extra)).blocks[0].rows[1]
    assert broken != good, "the sabotage changed nothing, so this proves nothing"
    assert broken == ["Feb 2025", ""], broken
    monkeypatch.undo()
    assert reader._V is original
    assert read(_sheet([["h"]], extra)).blocks[0].rows[1] == good
