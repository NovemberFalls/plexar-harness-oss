"""T87i — a cell arrives with its column heading, so it cannot be mis-attributed.

MIXED source (chat-DEC-397): trimmed from `plexar-chat/tests/test_query_sheet.py`.
Only the two arms that drive `office/` directly (the sheet-text parser) are
kept. Every other arm in the source file drives `chat.api.App._query_attached`
or `chat.api._app`'s `_header_row`/`_looks_numeric` helpers, which are
`chat.api` internals this package does not own, and stays in Chat.
"""

from __future__ import annotations

from plexar_tools.office._model import parse_sheets


def _pnl() -> bytes:
    import io

    openpyxl = __import__("pytest").importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "PNL Projection"
    ws["A1"] = "R365 P&L Projection"
    for col, title in zip("ABCDEF", [
            "Line Item", "Jan 2025 Result", "Feb 2025 Result",
            "Mar 2025 Result", "Jan 2026 Result", "Total"]):
        ws[f"{col}2"] = title
    for col, value in zip("ABCDEF", [
            "Dine In", 936204.81, 700529.00, 972929.04, 1031105.48, 5342971.91]):
        ws[f"{col}3"] = value
    ws["A4"] = "Beverage"
    ws["B4"] = 1000
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_the_parser_reads_exactly_what_the_writer_wrote():
    """`parse_sheets` lives beside `Document.text` in `_model.py` **because a
    format has two halves and a third copy of this grammar in `api/` would
    drift the first time somebody adjusts the header line.** Asserted as a
    round trip through the real reader."""
    from plexar_tools.office import read as office_read

    doc = office_read(_pnl(), "pnl.xlsx")
    sheets = parse_sheets(doc.text)
    assert [s["name"] for s in sheets] == ["PNL Projection"]
    assert [n for n, _ in sheets[0]["rows"]] == [1, 2, 3, 4]
    assert sheets[0]["rows"][2][1][0] == "Dine In"


def test_an_unnumbered_row_is_skipped_and_never_renumbered():
    """`Document.text` prints a row it could not number WITHOUT a prefix,
    precisely so nothing presents a position as an address (T87g). Inventing
    one here would undo that in the consumer."""
    text = ("--- sheet 'S' (3 rows)\n"
            "R1\tLabel\tJan\n"
            "no prefix\tx\n"
            "R9\tDine In\t5\n")
    rows = parse_sheets(text)[0]["rows"]
    assert [n for n, _ in rows] == [1, 9]
