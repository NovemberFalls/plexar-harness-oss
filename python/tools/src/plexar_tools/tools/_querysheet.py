"""`query_sheet` — a cell arrives with its column heading attached (T87i).

══ WHAT WAS MEASURED, AND IT IS THE SAME DEFECT TWICE ═══════════════════════
`c_ff219befea4c88721f6d1bcf`, with T87g's row addresses live. The model said:

    "The Dine In data is in row 3 of the 'PNL Projection' sheet"

— **a correct address, which it could not have produced the day before** — and
then reported March 2025 as `$5,961.65` (it is 972,929.04), May and June 2025 as
the same figure, Total 2025 identical to Total 2026, and January 2026 as
646,795.80, which is February 2025's value.

So it found the right ROW and mis-read ACROSS it. `chat-R-221` has not closed;
it moved from *"read the wrong row"* to *"read the right row wrongly"*, **which
is harder to catch because the citation is now correct.**

══ WHY: A FLAT ROW IS A SEQUENCE OF NUMBERS WITH NO NAMES ═══════════════════
    R3	Dine In	936204.81	700529.00	5961.65	…

Nothing in that line says which figure is which month, or where 2025 stops and
2026 starts. The model has to count columns in its head across a line that may
carry blanks, a total, and two year-blocks — and it counts wrong, silently.
**T87g addressed one axis of a two-axis problem.** This is the other axis.

══ THE VERB PAIRS EVERY CELL WITH ITS HEADING, AND THAT IS THE WHOLE DESIGN ══
    Jan 2025 Result | 936204.81
    Feb 2025 Result | 700529.00
    Mar 2025 Result | 972929.04

There is no counting left to do. A pairing cannot be off by one the way a
position can, which is the same argument `find_in_file` makes against paging and
`read_file`'s own docstring makes against embeddings: **addressing beats
scanning, and a name beats an index.**

══ WHAT THIS MODULE DOES NOT DO ═════════════════════════════════════════════
It reads no bytes and knows no bucket. It names WHICH file, WHICH sheet and
WHICH row; `App._query_attached` performs the ownership-scoped read behind the
two barriers T82's review traced. **INVARIANT-OWNSCOPE gains no new way to name
a file here** — the candidate set is the caller's own conversation, exactly as
it is for the two tools this joins.
"""

from __future__ import annotations

from typing import Any

from ._contract import ToolResult
from ._registry import Tool

#: How many rows one call may return. A query that matches half a sheet is a
#: query that has not been narrowed, and returning it would rebuild the delivery
#: channel T87d removed — the count is still stated in full (T87f's rule).
MAX_ROWS = 6

#: How many `heading | value` pairs per row. A workbook two years wide is ~30
#: columns; past this the model is reading a sheet rather than asking it a
#: question, and the reply says how many were left out.
MAX_PAIRS = 40

PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "source": {
            "type": "string",
            "description": (
                "Which file — its NAME as shown in the attached-files list, or "
                "its file id. The name is easier to get right."
            ),
        },
        "row": {
            "type": "string",
            "description": (
                "Which row you want, as either its LABEL (the text in its "
                "first column, such as 'Dine In') or its row NUMBER (such as "
                "'3' or 'R3'). A label is safer — the numbers shown in the "
                "file text are the worksheet's own, and a label cannot be off "
                "by one."
            ),
        },
        "headings": {
            "type": "integer",
            "minimum": 1,
            "description": (
                "Only if the headings in a previous reply were wrong. The row "
                "number to read column names from — useful when a sheet has a "
                "merged title row above the real headings. Leave it out the "
                "first time; the reply tells you which row it used and shows "
                "them, so you can judge."
            ),
        },
        "sheet": {
            "type": "string",
            "description": (
                "Which sheet, when the workbook has more than one. Leave it "
                "out to search every sheet."
            ),
        },
    },
    "required": ["source", "row"],
}

#: ══ THE ROUTING RULE IS A QUESTION SHAPE (T87f's rule, inherited) ═══════════
#: Three tools now read a file and a model reaching for the wrong one wastes a
#: round. None of them states a preference; each states a question the model can
#: answer about itself. *Do you want a row's values?* → here. *Do you know what
#: you are looking for but not where?* → `find_in_file`. *Do you need a stretch
#: you have already located?* → `read_file`.
DESCRIPTION = (
    "Get one row of a spreadsheet with every value PAIRED TO ITS COLUMN "
    "HEADING. "
    "**Use this for any question about a spreadsheet's numbers** — a line "
    "item by month, a total, one product's figures. It returns "
    "'Jan 2025 Result | 936204.81' rather than a bare sequence of numbers, so "
    "you never have to count columns to work out which figure is which. "
    "**Counting columns across a raw row is how a value gets attributed to the "
    "wrong month or the wrong year**, and reading the row as text does not "
    "protect you from it. "
    "Name the row by its label — 'Dine In', 'Total Revenue' — or by its "
    "number. Use find_in_file first if you do not know what the rows are "
    "called. "
    "It returns TEXT for you to read; it creates, converts and attaches "
    "nothing."
)


def _run(args: dict) -> ToolResult:
    """Validate, and hand the intent back. **No bytes are read here.**"""
    if not isinstance(args, dict):
        return ToolResult(
            name="", ok=False,
            content="The arguments for query_sheet were incomplete, so nothing "
                    "was read. Send the call again with a source and a row.",
            detail="nothing read — incomplete arguments")

    source = str(args.get("source") or "").strip()
    if not source:
        return ToolResult(
            name="", ok=False,
            content="No source was given, so nothing was read. Name the file "
                    "as it appears in the attached-files list.",
            detail="nothing read — no source")

    raw = args.get("row")
    row = str(raw).strip() if isinstance(raw, (str, int, float)) else ""
    if not row:
        return ToolResult(
            name="", ok=False,
            content=f"No row was named, so {source} was not read. Give the "
                    f"row's label — the text in its first column — or its "
                    f"number. The file is still attached.",
            detail="nothing read — no row")

    sheet = args.get("sheet")
    sheet = str(sheet).strip() if isinstance(sheet, str) else ""

    headings = args.get("headings")
    headings = headings if isinstance(headings, int) and not isinstance(
        headings, bool) and headings > 0 else None

    return ToolResult(
        name="", ok=True,
        content=f"Reading {row!r} from {source}…",
        detail=f"reading {row!r} from {source}",
        extra={"sheet": {"source": source, "row": row[:120],
                         "sheet": sheet[:120], "headings": headings}})


QUERY_SHEET = Tool(
    name="query_sheet",
    description=DESCRIPTION,
    parameters=PARAMETERS,
    handler=_run,
    #: **PURE.** No network, no socket. The read it causes is of the caller's
    #: own already-stored text at the `api/` seam that holds the principal.
    does_io=False,
)

__all__ = ["MAX_PAIRS", "MAX_ROWS", "QUERY_SHEET"]
