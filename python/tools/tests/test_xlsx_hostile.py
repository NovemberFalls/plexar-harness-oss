"""T84 — THE XLSX READER'S BOUNDS, AND THE DATA-LOSS DEFECT THEY UNCOVERED.

**The finding that matters most in this file is not a denial of service.** A
two-sheet workbook returned sheet 1's cells TWICE under sheet 2's name and
silently dropped every later sheet, because `_REL` required `Id` before `Target`
and openpyxl — and Excel — write `Type`, `Target`, `Id`. That is verbatim the
trap `chat/office/excel/_read.py`'s own header opens with, and it means
essentially every real multi-sheet spreadsheet reached the model with one sheet
duplicated and the rest gone.

**None of it was findable with our own writer, which agrees with our own
reader** (C19: *the double certifies the bug*). So openpyxl 3.1.5 — already a
dependency of the T81 chart gate — is used here as an **INDEPENDENT PRODUCER**,
and three defects regress together against it: the attribute order, a
package-absolute `Target`, and a declared sheet whose part is missing.

Every hostile fixture is generated in code. A `.xlsx` is a zip, so a committed
blob would be doubly opaque — the hostile part is one string inside one member,
and a reader of this file has to be able to see which.

Wall clock **and** peak allocation, in separate passes: see `tests/_bounds.py`.
"""

from __future__ import annotations

import io
import re
import zipfile

import pytest

from plexar_tools.office.excel import _read as reader
from tests._bounds import elapsed, peak_mib

WORKBOOK = ('<workbook><sheets>'
            '<sheet name="{name}" r:id="rId1"/>'
            '</sheets></workbook>')
RELS = ('<Relationships><Relationship '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
        'relationships/worksheet" Target="{target}" Id="rId1"/>'
        '</Relationships>')


def _zip(parts: dict[str, str]) -> bytes:
    """A workbook as bytes. **Deflated**, because the exposure is the ratio.

    `MAX_FILE_BYTES` is 8 MiB and bounds only the COMPRESSED input; sheet XML
    compresses 10-20x, which is what let a 730-byte zip buy ten seconds.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in parts.items():
            archive.writestr(name, text)
    return buffer.getvalue()


def _sheet(body: str) -> str:
    return f"<worksheet><sheetData>{body}</sheetData></worksheet>"


def _one_sheet(body: str, name: str = "Sheet1") -> bytes:
    return _zip({
        "xl/workbook.xml": WORKBOOK.format(name=name),
        "xl/_rels/workbook.xml.rels": RELS.format(
            target="worksheets/sheet1.xml"),
        "xl/worksheets/sheet1.xml": _sheet(body),
    })


def _rows(count: int, ref: str = "A") -> str:
    """`count` rows, each holding ONE cell at column `ref`.

    `<c r="XFD1"/>` alone on a row is legal, sparse Excel — and `max(cells)`
    reads the FARTHEST column, so one cell makes one row 16,384 wide. That is
    the whole of Z5's second half: entirely legal refs, 81,920,000 pointers from
    a ~150 KB sheet.
    """
    return "".join(f'<row r="{i}"><c r="{ref}{i}"><v>1</v></c></row>'
                   for i in range(1, count + 1))


def _sheets(count: int, body: str) -> bytes:
    """`count` declared sheets, each pointing at its own part with `body`.

    The fixture for *"the budget is per WORKBOOK, not per sheet"* — the
    implementer's own first version wrote it per sheet, which is 50 x 2,000,000
    cells and ~285s per request: **the bound holding for every statement and not
    for the composition**, which is exactly what `_REF` did to `_column`.
    """
    declarations = "".join(
        f'<sheet name="S{i}" r:id="rId{i}"/>' for i in range(1, count + 1))
    relationships = "".join(
        f'<Relationship Type="worksheet" Target="worksheets/sheet{i}.xml" '
        f'Id="rId{i}"/>' for i in range(1, count + 1))
    parts = {
        "xl/workbook.xml": f"<workbook><sheets>{declarations}</sheets></workbook>",
        "xl/_rels/workbook.xml.rels": f"<Relationships>{relationships}</Relationships>",
    }
    for i in range(1, count + 1):
        parts[f"xl/worksheets/sheet{i}.xml"] = _sheet(body)
    return _zip(parts)


def _grid(document) -> list:  # type: ignore[no-untyped-def]
    return [b for b in document.blocks if b.kind == "sheet"]


def _notes(document) -> str:  # type: ignore[no-untyped-def]
    return " ".join(b.text for b in document.blocks if b.kind == "paragraph")


# ══════════════════════════════════════════════════════════════════════════════
# Z6 — QUADRATIC SCANNING, AND 730 BYTES ON THE WIRE BOUGHT TEN SECONDS
# ══════════════════════════════════════════════════════════════════════════════

def test_four_point_eight_million_unclosed_row_openers_cost_one_pass() -> None:
    """`<row .*?</row>` costs O(openers x length) — 4x per doubling, measured.

        2,000 openers (10 KB)     0.094s
        4,000 openers (20 KB)     0.414s
        8,000 openers (40 KB)     1.540s
       16,000 openers (80 KB)     6.424s

    `MAX_XML_BYTES` permits ~4.8 million of them, which is ~90,000x the last row
    — hours of one pinned core on the upload request thread. The anchored walk
    measured **0.003s** at that size, so the deadline here is a genuine
    discriminator with four orders of magnitude between the two states.

    The buffer is built OUTSIDE the measured passes on purpose: it is 24 MB of
    Python string, and including it would put the fixture's own cost inside the
    peak this arm is asserting — an instrument altering what it measures, which
    is C54b's stylesheet padding in another notation.
    """
    text = "<row " * 4_800_000
    assert len(text) <= reader.MAX_XML_BYTES

    seconds, raised, found = elapsed(
        lambda: reader._scan(text, "row", reader.MAX_ROWS + 1))
    assert raised is None, raised
    assert found == [], "an unclosed opener is not an element"
    assert seconds < 10.0, seconds
    assert peak_mib(
        lambda: reader._scan(text, "row", reader.MAX_ROWS + 1)) < 16.0


def test_a_tiny_zip_of_unclosed_openers_reads_end_to_end() -> None:
    """The same defect through the real entry point. **10.063s before T84**,
    from a workbook that is under a kilobyte on the wire — which is the number
    that makes this an upload-shaped attack rather than a curiosity.

    Asserted end to end rather than at `_scan`, because `read()` calls it five
    times over four different parts and a repair to one call site would leave
    the other four."""
    data = _one_sheet("<row " * 200_000)
    assert len(data) < 4 * 1024, len(data)

    seconds, raised, document = elapsed(lambda: reader.read(data))
    assert raised is None, raised
    assert seconds < 10.0, seconds                     # measured 0.003s
    assert peak_mib(lambda: reader.read(data)) < 32.0
    assert _grid(document), "the workbook must still produce its sheet block"


def test_a_real_row_is_still_found_by_the_anchored_walk() -> None:
    """**THE COMPANION, and it is the one that matters most in this file.**

    A scanner that found NOTHING would make every arm above pass while every
    real spreadsheet read as empty — T81f's direction, and `_scan`'s own
    docstring says a pattern that stops matching is *"strictly worse than the
    denial of service."* So: a self-closing cell is an element, a nested `<t>`
    is found, and `<rows>` is not `<row>`.
    """
    body = ('<row r="1"><c r="A1" t="inlineStr"><is><t>Dine In</t></is></c>'
            '<c r="B1"/><c r="C1"><v>42</v></c></row>'
            '<rows r="9"><c r="A9"><v>99</v></c></rows>')
    document = reader.read(_one_sheet(body))
    grid = _grid(document)
    assert len(grid) == 1
    assert grid[0].rows == [["Dine In", "", "42"]], grid[0].rows
    assert "99" not in str(grid[0].rows), "`<rows>` was read as `<row>`"


# ══════════════════════════════════════════════════════════════════════════════
# Z5 — THE BASE-26 BOMB, AND BOTH HALVES OF THE COLUMN BOUND
# ══════════════════════════════════════════════════════════════════════════════

def test_the_column_bound_refuses_zzzzzzz_and_still_accepts_xfd() -> None:
    """**BOTH HALVES. An arm on the refusal alone passes against a reader that
    refuses everything**, and a reader that refuses `XFD` cannot read the last
    column of a real spreadsheet.

    `r="ZZZZZZZ1"` names column 8,353,082,582, and `read` then built
    `[cells.get(i, "") for i in range(width)]` — eight billion pointers, ~64 GB,
    per row. `_column("A" * 200000)` measured **5.277s** of bignum
    multiplication with no allocation to notice, which is why the length check
    sits BEFORE the loop and not only the range check after it.
    """
    assert reader._column("XFD") == reader.EXCEL_MAX_COLUMN == 16_383
    assert reader._column("A") == 0
    assert reader._column("AA") == 26
    assert reader._column("ZZZZZZZ") == -1
    assert reader._column("XFE") == -1, "one past Excel's last column"

    seconds, raised, refused = elapsed(lambda: reader._column("A" * 200_000))
    assert raised is None, raised
    assert refused == -1
    assert seconds < 5.0, seconds                      # measured 0.0001s


def test_a_cell_beyond_excels_last_column_is_skipped_and_counted() -> None:
    """`-1` means REFUSED and the caller must not place it.

    **Neither of the two cheaper repairs would do**: bounding the regex makes the
    ref ABSENT, and the absent-ref fallback is `index = len(cells)`, which
    converts a hang into every later column shifting left — the single most
    likely silent-wrong bug in this format. Clamping to `EXCEL_MAX_COLUMN`
    collapses two refused refs onto one index and the last silently wins.

    So the row keeps its shape and the sheet SAYS how many cells it dropped.
    """
    body = ('<row r="1"><c r="A1"><v>1</v></c>'
            '<c r="ZZZZZZZ1"><v>2</v></c>'
            '<c r="B1"><v>3</v></c></row>')
    document = reader.read(_one_sheet(body))
    assert _grid(document)[0].rows == [["1", "3"]], (
        "the refused cell was placed positionally and shifted B1 left")
    assert "beyond Excel's last one (XFD)" in _notes(document)
    assert "1 cell(s)" in _notes(document)


def test_the_cell_budget_is_per_workbook_and_not_per_sheet(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """**THE IMPLEMENTER'S OWN FIRST VERSION GOT THIS WRONG.**

    A 2,000,000-cell budget on each of `MAX_SHEETS` sheets is 100,000,000 cells
    and ~285s per request. Ten sheets, each asking for 16,384 columns on every
    one of 200 rows, must share ONE allowance — so the total number of grid
    cells materialised across the whole document is bounded, and the sheets
    after the budget is gone say so.

    The constant is reduced in memory rather than paid in full: `read()` reads
    the module global at call time, the arm below pays the real 2,000,000 once,
    and the property here is the SHARING, which is the same at any size.
    """
    monkeypatch.setattr(reader, "MAX_WORKBOOK_CELLS", 50_000)
    data = _sheets(10, _rows(200, ref="XFD"))
    assert len(data) < 64 * 1024, len(data)

    seconds, raised, document = elapsed(lambda: reader.read(data))
    assert raised is None, raised
    total = sum(len(row) for sheet in _grid(document) for row in sheet.rows)
    assert total <= 50_000, total
    # **AND THE FIXTURE MUST ACTUALLY SPEND IT.** `total <= 50_000` is satisfied
    # by a reader that produced rows one cell wide, so the ceiling alone would
    # pass against a `max(cells)` that had stopped working — which is the
    # quantity Z5 is about.
    assert total > 16_384, total
    assert "more than Plexar reads from one workbook" in _notes(document)
    assert seconds < 15.0, seconds
    assert peak_mib(lambda: reader.read(data)) < 64.0


def test_two_hundred_sparse_xfd_rows_are_bounded_with_the_shipped_budget(
) -> None:
    """The real constant, paid once. **6.66s before the bound and 5.7s after**,
    which is the residual T84 asked to be argued about rather than the hangs it
    replaced: 2,000,000 cells is ~16 MB of pointers and 50x the 40,000-character
    attachment cut, so nothing a model can ever be shown is lost to it.

    5,000 such rows was ~170s and ~650 MB before. The deadline is 60s — ~10x the
    170s this used to cost at ten times the size.

    **AND THE RESIDUAL IS CHEAPER THAN THE ROW CLAIMED, MEASURED HERE: 0.08s and
    ~40 MiB for 1,998,848 cells, not 5.7s.** The difference is what the cells
    HOLD — `[cells.get(i, "") for i in range(width)]` over a sparse row is 16,384
    references to one interned empty string, and T84's 5.7s figure was taken on
    a shape that filled them. The bound is unaffected and the ceiling is left
    generous rather than tightened to this measurement, because a workbook whose
    cells are full is the one a real user uploads.
    """
    data = _sheets(3, _rows(200, ref="XFD"))
    assert len(data) < 32 * 1024, len(data)
    seconds, raised, document = elapsed(lambda: reader.read(data))
    assert raised is None, raised
    total = sum(len(row) for sheet in _grid(document) for row in sheet.rows)
    assert total <= reader.MAX_WORKBOOK_CELLS, total
    # 1,998,848 measured — one row's width short of the whole allowance, which
    # is what says the budget is the thing that stopped it rather than the
    # fixture running out of rows.
    assert total > reader.MAX_WORKBOOK_CELLS - 2 * 16_384, total
    assert seconds < 60.0, seconds
    assert peak_mib(lambda: reader.read(data)) < 256.0     # measured ~40 MiB


def test_a_hundred_row_sheet_reads_every_cell() -> None:
    """**THE COMPANION for the cell budget.** 100 rows x 10 columns is an
    ordinary spreadsheet and every cell must arrive; a budget that trimmed it
    would be T81f exactly — a file reading as smaller than it is, with a chart
    drawn from what survived."""
    body = "".join(
        f'<row r="{r}">'
        + "".join(f'<c r="{chr(65 + c)}{r}"><v>{r * 10 + c}</v></c>'
                  for c in range(10))
        + "</row>" for r in range(1, 101))
    grid = _grid(reader.read(_one_sheet(body)))[0]
    assert len(grid.rows) == 100
    assert all(len(row) == 10 for row in grid.rows)
    assert grid.rows[99][9] == "1009"
    assert "stopped after" not in _notes(reader.read(_one_sheet(body)))


# ══════════════════════════════════════════════════════════════════════════════
# THE LIVE DATA-LOSS DEFECT — openpyxl AS AN INDEPENDENT PRODUCER
# ══════════════════════════════════════════════════════════════════════════════

def _openpyxl_workbook() -> bytes:
    """Two sheets with DISTINCT data, written by a producer we did not write.

    **`'dine in'` and `'labour'` are chosen to be unmistakable**: the pre-T84
    reader returned the first twice and the second never, so an arm on cell
    COUNTS or on sheet NAMES would have passed — the names were right and the
    shapes were right, and the data was wrong.
    """
    import openpyxl

    workbook = openpyxl.Workbook()
    first = workbook.active
    first.title = "Dine In"
    first["A1"] = "dine in"
    first["B1"] = 936204.81
    second = workbook.create_sheet("Labour")
    second["A1"] = "labour"
    second["B1"] = 42
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_a_real_two_sheet_workbook_reads_both_sheets_once() -> None:
    """**THE MOST VALUABLE ARM IN THIS FILE, and it is not about a DoS.**

    Verified against HEAD in a clean worktree before T84: `'dine in'` twice,
    `'labour'` absent. `_REL` required `Id` first; openpyxl and Excel write
    `Type, Target, Id`; so `rels` was EMPTY, every
    `rels.get(rid, "worksheets/sheet1.xml")` took its default, and each declared
    sheet resolved to sheet1.

    Asserted on the DATA and on the count of occurrences, not on the sheet
    names — three separate facts, because the duplication and the loss are two
    different failures and a reader could have exactly one of them.
    """
    document = reader.read(_openpyxl_workbook())
    grid = _grid(document)
    assert [sheet.name for sheet in grid] == ["Dine In", "Labour"]
    flattened = str([sheet.rows for sheet in grid])
    assert flattened.count("dine in") == 1, (
        "sheet one's cells were emitted twice — attribute order in the "
        "relationship part, chat's oldest documented trap in this format")
    assert "labour" in flattened, "every sheet after the first was lost"
    assert "936204.81" in flattened


def test_watch_to_fail_requiring_id_before_target_loses_every_later_sheet(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """R23 — the pre-T84 pattern, put back through the LIVE code path.

    `_REL_ID` is replaced with one that only matches an `Id` followed by a
    `Target` in the same element, which is precisely what the old combined
    regex demanded. **The sabotage is confirmed before the result is read**: the
    replacement must genuinely fail to match openpyxl's own relationship
    element, or the arm would be reporting a bug in a fixture rather than
    re-creating the defect.

    Both halves of the defect are then required: `'dine in'` TWICE and
    `'labour'` gone. An arm asserting only the absence would pass equally
    against a reader that dropped both sheets, which is a different bug.
    """
    data = _openpyxl_workbook()
    old = re.compile(r'\bId="([^"]+)"(?=[^>]*Target=)')
    monkeypatch.setattr(reader, "_REL_ID", old)

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        rels = archive.read("xl/_rels/workbook.xml.rels").decode()
    assert 'Target=' in rels and 'Id="rId1"' in rels
    assert old.search(rels) is None, (
        "the sabotage did not take — this producer now writes Id before "
        "Target, so the arm is no longer re-creating the defect")

    document = reader.read(data)
    flattened = str([sheet.rows for sheet in _grid(document)])
    assert flattened.count("dine in") == 2, flattened
    assert "labour" not in flattened, flattened


def test_a_package_absolute_target_resolves() -> None:
    """openpyxl writes `/xl/worksheets/sheet2.xml`, leading slash and all.

    The old join tested `startswith("xl/")` BEFORE stripping the slash, so an
    absolute target became `xl/xl/worksheets/…` and the sheet vanished. **It was
    unreachable until the attribute-order fix landed** — one bug standing in
    front of another, which is why it had to be measured on a workbook this repo
    did not write. Asserted here on a hand-built part too, so the property
    survives a version of openpyxl that changes its mind.
    """
    data = _zip({
        "xl/workbook.xml": WORKBOOK.format(name="Absolute"),
        "xl/_rels/workbook.xml.rels": RELS.format(
            target="/xl/worksheets/sheet1.xml"),
        "xl/worksheets/sheet1.xml": _sheet(
            '<row r="1"><c r="A1" t="inlineStr"><is><t>reached</t></is></c></row>'),
    })
    grid = _grid(reader.read(data))
    assert grid and grid[0].rows == [["reached"]], grid


def test_a_declared_sheet_with_no_part_names_itself() -> None:
    """**SILENCE HERE IS HOW THE OTHER TWO DEFECTS STAYED INVISIBLE.**

    The sheet was simply not in the document and nothing said a sheet had been
    promised. Absence of a promise and a promise unkept are different facts
    (INVARIANT-ENVELOPE), and this is the note that would have made a
    duplicated-sheet workbook visible years earlier.
    """
    data = _zip({
        "xl/workbook.xml": ('<workbook><sheets>'
                            '<sheet name="Present" r:id="rId1"/>'
                            '<sheet name="Gone" r:id="rId2"/>'
                            '</sheets></workbook>'),
        "xl/_rels/workbook.xml.rels": (
            '<Relationships>'
            '<Relationship Type="worksheet" Target="worksheets/sheet1.xml" Id="rId1"/>'
            '<Relationship Type="worksheet" Target="worksheets/sheet9.xml" Id="rId2"/>'
            '</Relationships>'),
        "xl/worksheets/sheet1.xml": _sheet('<row r="1"><c r="A1"><v>1</v></c></row>'),
    })
    document = reader.read(data)
    assert [sheet.name for sheet in _grid(document)] == ["Present"]
    notes = _notes(document)
    assert "'Gone'" in notes and "missing from the workbook or empty" in notes
    assert "xl/worksheets/sheet9.xml" in notes, (
        "the note must name the part, or the reader cannot act on it")


# ══════════════════════════════════════════════════════════════════════════════
# FIVE REFUSALS, FIVE SENTENCES — AND THEY FAIL SEPARATELY
# ══════════════════════════════════════════════════════════════════════════════

def test_a_part_over_the_ceiling_is_refused_by_its_declared_size() -> None:
    """`_read_part`'s three-state return. Both refusals used to answer `""`,
    which the caller could not tell from a genuinely empty sheet — so an
    oversized part became a workbook that read as blank.

    Asserted on the DECLARED size path, which is the zip's own claim, and the
    fixture is stored uncompressed so the claim is true; the bounded `read` is
    the independent second check and has its own arm below.
    """
    data = _zip({
        "xl/workbook.xml": WORKBOOK.format(name="Sheet1"),
        "xl/_rels/workbook.xml.rels": RELS.format(
            target="worksheets/sheet1.xml"),
        "xl/worksheets/sheet1.xml": "x" * (reader.MAX_XML_BYTES + 64),
    })
    document = reader.read(data)
    assert not _grid(document)
    notes = _notes(document)
    assert "larger than 24 MiB" in notes, notes
    assert "'Sheet1'" in notes


def test_a_lying_size_header_gains_nothing() -> None:
    """The declared size and the bounded read are BOTH kept, because a lying
    header must gain nothing. `_read_part` asks for `MAX_XML_BYTES + 1` and
    refuses at more than the cap — the same `+ 1` trick the PDF reader uses,
    for the same reason: a cap-sized slice cannot be told from a part that
    happens to be exactly that size.

    **A real zip cannot lie**, so the liar is a duck-typed stand-in: it declares
    ten bytes and hands over one more than the ceiling. That is the only way to
    reach the second check with the first one satisfied, and it is what a
    hand-assembled archive with a forged central directory would do.
    """

    class _Liar:
        def getinfo(self, name: str) -> object:
            return type("Info", (), {"file_size": 10})()

        def open(self, info: object) -> io.BytesIO:
            return io.BytesIO(b"y" * (reader.MAX_XML_BYTES + 1))

    assert reader._read_part(_Liar(), "xl/worksheets/sheet1.xml") is None, (
        "the declared size was believed, so a forged central directory buys "
        "an unbounded read")


def test_more_rows_than_the_ceiling_says_the_sheet_has_more() -> None:
    """`MAX_ROWS` truncates rather than refusing, and the difference is
    announced — a silently short sheet is the T81f shape."""
    document = reader.read(_one_sheet(_rows(reader.MAX_ROWS + 10)))
    grid = _grid(document)[0]
    assert len(grid.rows) == reader.MAX_ROWS
    assert "only the first 5,000 rows were read" in _notes(document)


def test_each_refusal_sentence_is_its_own(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """**FIVE FACTS, FIVE SENTENCES, ASSERTED AS DISTINCT STRINGS.**

    Four are about OUR ceilings and the last is about the FILE, and they fail
    separately — a single *"this workbook could not be read"* is the generic the
    whole channel exists to replace. This arm is the one that would catch two of
    them being collapsed into one wording.
    """
    over_ceiling = _zip({
        "xl/workbook.xml": WORKBOOK.format(name="Big"),
        "xl/_rels/workbook.xml.rels": RELS.format(target="worksheets/sheet1.xml"),
        "xl/worksheets/sheet1.xml": "x" * (reader.MAX_XML_BYTES + 64),
    })
    missing = _zip({
        "xl/workbook.xml": WORKBOOK.format(name="Absent"),
        "xl/_rels/workbook.xml.rels": RELS.format(target="worksheets/sheet7.xml"),
    })
    produced = {
        "part over the ceiling": _notes(reader.read(over_ceiling)),
        "part missing": _notes(reader.read(missing)),
        "too many rows": _notes(reader.read(
            _one_sheet(_rows(reader.MAX_ROWS + 10)))),
        "ref beyond XFD": _notes(reader.read(_one_sheet(
            '<row r="1"><c r="ZZZZZZZ1"><v>2</v></c></row>'))),
    }
    monkeypatch.setattr(reader, "MAX_WORKBOOK_CELLS", 1)
    produced["cell budget spent"] = _notes(reader.read(
        _one_sheet(_rows(4, ref="XFD"))))

    for label, note in produced.items():
        assert note.strip(), f"{label} arrived as silence"
    # **PAIRWISE DISTINCT, which is the property.** Five facts collapsed into
    # one wording is the generic sentence this channel exists to replace, and it
    # is a change that no single-refusal arm can see.
    assert len(set(produced.values())) == 5, produced


# ══════════════════════════════════════════════════════════════════════════════
# T81f MUST SURVIVE ALL OF THIS
# ══════════════════════════════════════════════════════════════════════════════

def test_the_formula_marker_and_the_payload_rule_survive_the_bounds() -> None:
    """T81f, re-asserted here because this row rewrote every scan in the module.

    `tests/test_unevaluated_formula.py` owns these properties and was RUN, not
    edited. What this arm adds is that they hold on the SAME fixture shape the
    bounds above use, so a future bound cannot be green in one file and wrong in
    the other: a formula with no cached value reads `=?`, and a cell carrying
    text under a numeric `t` is text.
    """
    body = ('<row r="1">'
            '<c r="A1" t="n"><is><t>Feb 2025 -&gt; 2026</t></is></c>'
            '<c r="B1"><f>SUM(C1:D1)</f></c>'
            '<c r="C1"><f>1+1</f><v>2</v></c>'
            '</row>')
    grid = _grid(reader.read(_one_sheet(body)))[0]
    assert grid.rows == [["Feb 2025 -> 2026", reader.FORMULA_UNSET, "2"]], \
        grid.rows
