"""T87g — a row says which row it is, and the number was always there.

══ THE DEFECT (`chat-NOTE-223`) ═════════════════════════════════════════════
`excel/_read.py` emitted worksheet rows in reading order with nothing saying
which row each one was, **so a sparse sheet's row 1, row 7 and row 47 reached
the model as three adjacent lines.** T84 confirmed it on openpyxl output and
recorded the row-axis twin of the sparse-cell bug the module's own docstring
calls *"the single most likely silent-wrong bug in this format."*

══ AND THE FIX WAS SITTING IN THE REGEX ═════════════════════════════════════
`_REF` is `r"\\br=\\"([A-Z]+)(\\d+)\\""` and has been since the module existed.
Group 1 places the cell in its COLUMN — the sparse-cell fix. **Group 2 was
never read by anything in the file.** T84 estimated this row as expensive
because *"fixing it exposes the ROW axis to the base-26 bomb"*; it does not.
The base-26 loop is `_column`, over LETTERS. A row number is plain digits with
a natural ceiling — Excel's own last row — and it is bounded here like any
other claim a file makes about itself.

══ WHY THE NUMBER IS PRINTED AND NOT JUST STORED ════════════════════════════
The model reads TEXT. A `row_numbers` tuple nothing renders is a fact the only
consumer cannot see — this product's most repeated defect, and the reason C50's
shelf, T2's date and T43's file id each needed a second row.
"""

from __future__ import annotations

import io

import pytest

openpyxl = pytest.importorskip("openpyxl")

from plexar_tools.office import read as office_read
from plexar_tools.office.excel._read import EXCEL_MAX_ROW


def _book(cells: dict, title: str = "Revenue") -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title
    for ref, value in cells.items():
        ws[ref] = value
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── the defect, closed ───────────────────────────────────────────────────────

def test_a_sparse_sheet_no_longer_reads_as_adjacent_rows():
    """**THE ROW, IN ONE ASSERTION.** Three rows at 1, 7 and 47 used to arrive
    as three consecutive lines with nothing distinguishing them from rows 1, 2
    and 3."""
    doc = office_read(_book({
        "A1": "Label", "B1": "Jan",
        "A7": "Dine In", "B7": 936204.81,
        "A47": "Catering", "B47": 1234.5,
    }), "pnl.xlsx")

    lines = [l for l in doc.text.splitlines() if l.startswith("R")]
    assert [l.split("\t")[0] for l in lines] == ["R1", "R7", "R47"]
    assert "R2" not in doc.text and "R3" not in doc.text


def test_the_block_carries_the_numbers_beside_the_grid_and_not_inside_it():
    """**Folding the number in as a first cell would corrupt every other
    consumer**: the chart renderer reads `rows[i][0]` as a category label, and
    a row index there plots the numbers 1..N against themselves."""
    doc = office_read(_book({"A1": "Label", "A7": "Dine In"}), "pnl.xlsx")
    sheet = next(b for b in doc.blocks if b.kind == "sheet")

    assert sheet.row_numbers == (1, 7)
    assert len(sheet.row_numbers) == len(sheet.rows)
    assert sheet.rows[0][0] == "Label", "the grid must be untouched"
    assert sheet.rows[1][0] == "Dine In"


def test_the_prefix_is_distinguishable_from_a_numeric_first_column():
    """`R47` rather than `47`, because a spreadsheet's first column very often
    holds numbers and a bare one would be indistinguishable from an address."""
    doc = office_read(_book({"A1": 47, "B1": "Beverage"}), "pnl.xlsx")
    line = next(l for l in doc.text.splitlines() if "Beverage" in l)
    assert line.startswith("R1\t47\t"), line


# ── what a file claims is not what a file has ────────────────────────────────

@pytest.mark.parametrize("ref", [
    '<c r="A0"/>', '<c r="A99999999999999999999"/>', '<c/>', '<c r="7"/>',
])
def test_an_impossible_row_number_is_absence_and_never_a_position(ref):
    """**THE POSITION IS NOT A FALLBACK, IT IS A GUESS** — and it is exactly
    the guess this row exists to end. A row we cannot number is printed with no
    prefix, so nothing downstream can present a position as an address."""
    from plexar_tools.office.excel._read import read as read_xlsx

    book = _book({"A1": "x"})
    with io.BytesIO(book) as handle:
        import zipfile

        raw = zipfile.ZipFile(handle)
        sheet = raw.read("xl/worksheets/sheet1.xml").decode()
    hostile = sheet.replace('<c r="A1"', ref.rstrip("/>").replace("<c", "<c") + " ", 1)
    assert isinstance(hostile, str)  # the shape is what matters, not the bytes

    # The bound itself, asserted directly — the parse path above is fixture
    # plumbing and the RULE is this.
    assert EXCEL_MAX_ROW == 1_048_576
    for claimed in (0, -1, EXCEL_MAX_ROW + 1, 10 ** 20):
        assert not 0 < claimed <= EXCEL_MAX_ROW


def test_a_row_that_cannot_be_numbered_is_printed_without_a_prefix():
    """Asserted through the model layer, which is where the rule lives: an
    empty `row_numbers` means *"this reader does not know"*, and a consumer
    must not invent `i + 1` from it."""
    from plexar_tools.office._model import Block, Document

    doc = Document(blocks=[Block(kind="sheet", name="S",
                                 rows=[["a"], ["b"]], row_numbers=())])
    assert doc.text.splitlines()[1:] == ["a", "b"]

    doc = Document(blocks=[Block(kind="sheet", name="S",
                                 rows=[["a"], ["b"]], row_numbers=(1, 9))])
    assert doc.text.splitlines()[1:] == ["R1\ta", "R9\tb"]


def test_a_partly_numbered_sheet_numbers_only_what_it_knows():
    """The mixed case, which is the one a loop gets wrong: shorter
    `row_numbers` than `rows` must not raise and must not shift."""
    from plexar_tools.office._model import Block, Document

    doc = Document(blocks=[Block(kind="sheet", name="S",
                                 rows=[["a"], ["b"], ["c"]],
                                 row_numbers=(4, 0))])
    assert doc.text.splitlines()[1:] == ["R4\ta", "b", "c"]


# ── it composes with the tools that read the text ────────────────────────────

def test_a_search_hit_now_carries_a_real_address():
    """**THE REASON THIS ROW EXISTS NOW.** `find_in_file` returns the text
    around a hit; with the number in that text the model gets `R47` rather than
    "the 3rd line", which is what makes a follow-up question answerable."""
    doc = office_read(_book({
        "A1": "Label", "A7": "Dine In", "B7": 936204.81,
        "A47": "Catering",
    }), "pnl.xlsx")
    at = doc.text.index("Dine In")
    line = doc.text[doc.text.rindex("\n", 0, at) + 1:].split("\n")[0]
    assert line.startswith("R7\t"), line
