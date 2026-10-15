"""Read an `.xlsx` into the Document. **The two traps the handoff named.**

  * `sheet1.xml` is NOT necessarily the first sheet. The order and the names
    live in `xl/workbook.xml`, and the mapping from `r:id` to a part lives in
    `xl/_rels/workbook.xml.rels`. A reader that assumes the filename silently
    transposes a renamed or reordered workbook.
  * **EMPTY CELLS ARE OMITTED FROM THE XML.** The `r` attribute (`"C7"`) is
    what places a cell. A reader that appends positionally collapses a sparse
    row and every column after the gap shifts left — the single most likely
    silent-wrong bug in this format, and it still opens fine.

Shared strings are an indirection: most text cells hold an INDEX into
`xl/sharedStrings.xml`. Without resolving it you get integers where the words
were.

**AND EVERY BOUND IN HERE IS A DENIAL-OF-SERVICE BOUND, NOT A TIDINESS ONE.**
`_extract_text` runs this synchronously on the upload request thread, one thread
per request, in one process, with no admission cap by design
(INVARIANT-NOQUEUE) — so a hang or an OOM here is the whole box. `MAX_FILE_BYTES`
is 8 MiB and bounds only the COMPRESSED input: a 730-byte zip reached ten seconds
of pinned core before `_scan`, and eight bytes of XML asked for a 64 GB list
before `_column` refused. Nothing above this file can help — `signal.alarm` does
not exist on Windows and a thread inside a C-level regex scan cannot be
interrupted. See `_scan`, `_column` and `MAX_WORKBOOK_CELLS` for the numbers.
"""

from __future__ import annotations

import io
import re
import zipfile

from .._model import Block, Document

#: The decompressed ceiling for ONE part. **Left at 24 MiB deliberately, and
#: that is a decision rather than an inheritance (Z6).**
#:
#: It is 3× `MAX_FILE_BYTES`, which looks wrong until you price the alternative:
#: sheet XML compresses 10–20×, so an 8 MiB workbook legitimately carries a
#: 100 MiB `sheet1.xml`, and a part over the ceiling is DROPPED. Lowering it
#: trades a bounded, linear cost for lost rows in real workbooks — T81f's class
#: of defect, where a file reads as smaller than it is and nothing downstream
#: can tell. **The multiplier was the bug, not the ceiling**: every scan in this
#: module is now linear in the part (`_scan`), so 24 MiB costs 24 million
#: character steps once, not 4.8 million openers × 24 MiB. What the constant
#: decides is how much a legitimate workbook may hold, not how bad an attack is.
MAX_XML_BYTES = 24 * 1024 * 1024
MAX_SHEETS = 50
MAX_ROWS = 5000

#: **Excel's own last column is `XFD` — 16,384 of them, 0-based 16,383.**
#: A `r="ZZZZZZZ1"` is not a spreadsheet we should try to read; see `_column`.
EXCEL_MAX_COLUMN = 16_383
#: Three letters reach `XFD` and every legal ref beyond `ZZZ` is out of range
#: anyway, so the base-26 loop never sees a long string. See `_column`.
MAX_COLUMN_REF_LETTERS = 3

#: **Excel's own last row.** The row half of a ref is plain digits, so it has no
#: base-26 bomb — but `r="A99999999999999999999"` is still eight bytes of XML
#: asking for a number nobody can use, and a row number outside the grid is not
#: a row. Bounded here for the reason `_column` is bounded: what a file CLAIMS
#: is not what a file HAS (T87g).
EXCEL_MAX_ROW = 1_048_576
#: One row may not hold more cells than Excel has columns. Bounds the dict that
#: is built BEFORE the width is known.
MAX_CELLS_PER_ROW = EXCEL_MAX_COLUMN + 1

#: How many grid cells ONE WORKBOOK may MATERIALISE (Z5).
#:
#: **Per workbook and not per sheet, and that distinction is this row's own
#: lesson applied to its own fix.** A 2,000,000-cell budget on each of
#: `MAX_SHEETS` sheets is 100,000,000 cells and ~285s per request — the bound
#: holds for every statement and not for the composition, which is exactly what
#: `_REF` did to `_column`. Measured: 2,000,000 cells is 5.7s of list building,
#: so the budget IS the ceiling on this request and there must be one of it.
#:
#: `MAX_ROWS × MAX_CELLS_PER_ROW` is 81,920,000, and every one of those is a
#: real pointer in a real list — reachable from a 150 KB sheet using nothing but
#: refs Excel itself would write (`<c r="XFD1"/>` alone on each row is legal and
#: sparse). Measured before the bound: 500 such rows took **17.1s** and 8.2M
#: cells; 5,000 is ~170s and ~650 MB of pointers, on the upload request thread.
#:
#: 2,000,000 is ~16 MB of pointers and 50× the 40,000-character attachment cut,
#: so nothing a model can ever be shown is lost to it. When it bites, it SAYS SO
#: — silent truncation here is exactly how a sheet comes to read as smaller than
#: it is.
MAX_WORKBOOK_CELLS = 2_000_000
#: Excel's own unique-string ceiling is ~1M; past that a 24 MiB `sharedStrings`
#: is 2.7M entries of list overhead for indices no cell can legally hold.
MAX_SHARED_STRINGS = 1_000_000

#: What a cell holding a formula with **no stored result** reads as (T81f).
#:
#: Excel caches a formula's last computed value in the file; an exporter that
#: writes formulas and never calculates them does not. Those cells are not
#: empty — the value exists in Excel and is absent from these bytes — and
#: rendering them identically to a blank is how a model comes to invent them.
#:
#: **Deliberately two characters.** One real workbook had 1,109 of them, and the
#: attachment text is cut at 40,000 characters, so a verbose marker would evict
#: the very data it exists to explain. Its meaning is stated once, in the
#: attachment header, not 1,109 times in the grid.
FORMULA_UNSET = "=?"

#: Attribute readers. **Run only over ONE start tag or ONE element**, never over
#: a whole part — that is what keeps their `[^>]*` linear (see `_scan`).
_SHEET = re.compile(r'<sheet[^>]*name="([^"]*)"[^>]*r:id="([^"]+)"')
_SHEET_ALT = re.compile(r'<sheet[^>]*r:id="([^"]+)"[^>]*name="([^"]*)"')
#: ══ THE HEADER'S FIRST TRAP WAS LIVE, AND ATTRIBUTE ORDER IS WHY ═══════════
#: `_REL` was `Id="([^"]+)"[^>]*Target="([^"]+)"`, which requires `Id` to come
#: FIRST. **openpyxl writes `Type`, then `Target`, then `Id`** — measured on a
#: two-sheet workbook it produced — so `findall` returned nothing, `rels` was
#: empty, every `rels.get(rid, "worksheets/sheet1.xml")` took its default, and
#: **both sheets read back sheet1's cells under sheet2's name.** That is
#: verbatim the trap this module's own header opens with: *"a reader that assumes
#: the filename silently transposes a renamed or reordered workbook."* It opens
#: fine, it is the right shape, and it is the wrong data — T81f's class again.
#:
#: Two attributes read separately, so no order can hide one. **That is only safe
#: because `_scan` hands over ONE element at a time**: on a whole part these
#: patterns would pair an `Id` with a later element's `Target`. The Z6 fix is
#: what makes the order-independent read possible rather than reckless.
_REL_ID = re.compile(r'\bId="([^"]+)"')
_REL_TARGET = re.compile(r'\bTarget="([^"]+)"')
_REF = re.compile(r'\br="([A-Z]+)(\d+)"')
_TYPE = re.compile(r'\bt="([^"]+)"')

#: A cell's stored value. **This one stayed a regex, and the shape is the fix.**
#:
#: It was `<v>(.*?)</v>`, whose failure cost the rest of the buffer per opener
#: (see `_scan`). `[^<]*` is not a bound on that cost, it REMOVES it: an
#: unmatched `<v>` fails after zero characters instead of scanning to the end,
#: so 4.8 million of them cost 4.8 million steps rather than 10^13.
#:
#: **And it is exact rather than merely cheaper.** A `<v>` payload cannot
#: contain a raw `<` — XML escapes it — and `<v>` never carries an attribute,
#: which is why `_texts(…, "t", …)` goes through `_scan` instead: a `<t>` does
#: (`xml:space="preserve"`), and phonetic runs nest one inside another.
#:
#: The name is also what `tests/test_unevaluated_formula.py`'s watch-to-fail arm
#: reads to prove its own restore took, which is a reason to keep the name and
#: not a reason to keep the pattern.
_V = re.compile(r"<v>([^<]*)</v>")

_ENT = (("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'"), ("&amp;", "&"))


def _unescape(text: str) -> str:
    for a, b in _ENT:
        text = text.replace(a, b)
    return text


def _scan(text: str, name: str, limit: int) -> list[tuple[str, str]]:
    """Every `<name …>…</name>` (and `<name …/>`) as `(inner, whole)`.

    ══ THIS REPLACES FIVE LAZY-SPAN REGEXES, AND THE REASON IS A NUMBER ═══════
    `_ROW`, `_CELL`, `_V`, `_IS_T` and `_SI` were all `<x[ >].*?</x>`. **That is
    not catastrophic backtracking — it is worse-behaved and cheaper to trigger.**
    Every occurrence of the OPENING literal with no matching close costs a scan
    of the whole remaining buffer, so the cost is `O(openers × length)` with no
    exponent to hide behind and nothing to `try`. Measured on this machine, on
    `"<row " * k` and nothing else in the file:

        2,000 openers (10 KB)     0.094s
        4,000 openers (20 KB)     0.414s      4× per doubling, clean
        8,000 openers (40 KB)     1.540s
       16,000 openers (80 KB)     6.424s
       20,000 openers, end to end through `read()`   10.063s
           ...from a zip that is **730 bytes on the wire.**

    `MAX_XML_BYTES` permits ~4.8 million openers, which is 300× the last row
    above and therefore ~90,000× its time — hours of one pinned core, on the
    upload request thread, one thread per request, no admission cap by design
    (INVARIANT-NOQUEUE). And **there is no backstop above this file**:
    `signal.alarm` and `signal.setitimer` do not exist on Windows and CPython
    cannot interrupt a thread inside a C-level regex scan. The bound has to be
    here.

    ══ WHY NOT THE TWO CHEAPER REPAIRS ══════════════════════════════════════
    **A bounded lazy span (`.{0,N}?`) only shrinks the multiplier.** The failure
    still costs N per opener, so 4.8M × N is fatal for any N large enough to
    hold a real row (16,384 cells is ~650 KB). It trades a hang for a slower
    hang and adds a silent truncation at N.
    **Anchoring the opener** (requiring a plausible close) removes the
    multiplier, and this is the anchored form: the close is located with
    `str.find`, so a missing close costs ONE scan and ENDS the walk instead of
    being retried from the next opener. That is sound rather than merely fast —
    a close found from position `k` is the same close any later opener would
    find, so if there is none after `k` there is none for any of them.

    Every `find` here covers a region strictly after the previous one, so the
    whole walk is O(len(text)) with no allocation per opener.

    **The semantics are the lazy pattern's, on purpose (T81f).** A pattern that
    stops matching reads as *"this spreadsheet has no rows"*, which is a silent
    wrong answer and strictly worse than the denial of service: first close
    wins, self-closing tags are elements, and `<rows>`/`<si2>`/`<c1>` are not
    `<row>`/`<si>`/`<c>` — the same boundary `\b` and `[ >]` enforced before.
    """
    out: list[tuple[str, str]] = []
    open_lit, close_lit = "<" + name, "</" + name + ">"
    span, size, i = len(close_lit), len(text), 0
    while len(out) < limit:
        i = text.find(open_lit, i)
        if i < 0:
            break
        j = i + len(open_lit)
        if j < size and not (text[j].isspace() or text[j] in ">/"):
            i = j                      # `<rows`, `<si2`, `<c1` — a different tag.
            continue
        end_of_tag = text.find(">", j)
        if end_of_tag < 0:
            break                      # An unterminated start tag ends the walk.
        if text[end_of_tag - 1] == "/":
            out.append(("", text[i:end_of_tag + 1]))
            i = end_of_tag + 1
            continue
        close = text.find(close_lit, end_of_tag + 1)
        if close < 0:
            break                      # See the docstring: sound, not just fast.
        out.append((text[end_of_tag + 1:close], text[i:close + span]))
        i = close + span
    return out


def _wholes(text: str, name: str, limit: int) -> list[str]:
    return [whole for _, whole in _scan(text, name, limit)]


def _texts(text: str, name: str, limit: int) -> list[str]:
    return [inner for inner, _ in _scan(text, name, limit)]


def _column(ref: str) -> int:
    """`"C"` -> 2. **`-1` means REFUSED**, and the caller must not place it.

    ══ EIGHT BYTES OF XML ASKED FOR A MULTI-BILLION-ELEMENT LIST (Z5) ════════
    `_REF` bounded the SHAPE of a column ref and nothing bounded its LENGTH,
    and this loop is base-26, so `<c r="ZZZZZZZ1">` names column
    **8,353,082,582** — and `read` then built `[cells.get(i, "") for i in
    range(width)]`, a Python list of eight billion pointers (~64 GB), per row.
    Measured before the bound, one cell in one row, nothing else in the file:

        r="AAA1"     column        702     0.002s
        r="AAAA1"    column     18,278     0.041s
        r="AAAAA1"   column    475,254     1.011s      linear from here on
        r="ZZZZZZZ1" column 8,353,082,582  ~5 hours, and it OOMs first

    A second cost sits in this loop by itself: `n` is a Python int, so a long
    ref is quadratic in bignum multiplication before any list is built —
    `_column("A" * 200_000)` measured **5.277s** with no allocation to notice.
    Hence the length check BEFORE the loop, not only the range check after it.

    ══ WHY THE BOUND IS HERE AND NOT IN THE REGEX OR IN A CLAMP ══════════════
    **Not `[A-Z]{1,3}` in `_REF`.** A ref that fails to match is a ref that is
    ABSENT, and the caller's fallback for an absent ref is `index = len(cells)`
    — positional placement. So bounding the pattern converts a hang into every
    cell after the bad one shifting left, which is the exact silent-wrong bug
    this module's own header calls "the single most likely" one in this format.
    **Not a clamp to `EXCEL_MAX_COLUMN` either.** Two out-of-range refs then
    land on one index and the last quietly overwrites the first, so a cell that
    was refused would render as a cell that was read.
    A refusal is the only answer that stays distinguishable, so it is returned
    as one — and the caller counts it and says so (INVARIANT-ENVELOPE).
    """
    if not ref or len(ref) > MAX_COLUMN_REF_LETTERS:
        return -1
    n = 0
    for ch in ref:
        n = n * 26 + (ord(ch) - 64)
    return n - 1 if n - 1 <= EXCEL_MAX_COLUMN else -1


def _read_part(zf: zipfile.ZipFile, name: str) -> str | None:
    """The part's text, `""` if it is absent, **`None` if it was REFUSED.**

    The pre-check on `info.file_size` AND the bounded `read` are both kept: the
    declared size is the zip's own claim and a lying header must gain nothing, so
    the read is bounded independently of it.

    **The three-state return is the change.** Both refusals used to answer `""`,
    which the caller could not tell from a sheet that is genuinely empty — so an
    oversized part became a workbook that read as blank, with the generic *"the
    .xlsx file could not be read"* arriving from the upload seam. Absence and
    refusal must not render the same (INVARIANT-ENVELOPE).
    """
    try:
        info = zf.getinfo(name)
    except KeyError:
        return ""
    if info.file_size > MAX_XML_BYTES:
        return None
    with zf.open(info) as m:
        raw = m.read(MAX_XML_BYTES + 1)
    return None if len(raw) > MAX_XML_BYTES else raw.decode("utf-8", "replace")


def read(data: bytes) -> Document:
    document = Document(source_kind="xlsx")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        workbook = _read_part(zf, "xl/workbook.xml") or ""
        rel_part = _read_part(zf, "xl/_rels/workbook.xml.rels") or ""
        # **The attribute regexes run per ELEMENT, not per part.** `[^>]*` over a
        # whole `.rels` file is `_scan`'s own defect in the other notation, and
        # pairing attributes across elements is how the wrong sheet gets read;
        # see `_REL_ID`. `_scan` finds the elements linearly and hands each one
        # over as a start tag.
        rels: dict[str, str] = {}
        for whole in _wholes(rel_part, "Relationship", 2000):
            rid, target = _REL_ID.search(whole), _REL_TARGET.search(whole)
            if rid and target:
                rels[rid.group(1)] = target.group(1)
        shared_part = _read_part(zf, "xl/sharedStrings.xml") or ""
        shared = [_unescape("".join(_texts(si, "t", MAX_CELLS_PER_ROW)))
                  for si in _texts(shared_part, "si", MAX_SHARED_STRINGS)]

        materialised = 0
        declarations = _wholes(workbook, "sheet", MAX_SHEETS)
        pairs = [p for d in declarations for p in _SHEET.findall(d)] or \
            [(n, r) for d in declarations for r, n in _SHEET_ALT.findall(d)]
        if not pairs:
            pairs = [("Sheet1", "")]

        for sheet_name, rid in pairs[:MAX_SHEETS]:
            target = rels.get(rid, "worksheets/sheet1.xml")
            # **A `Target` may be package-absolute, and openpyxl writes it that
            # way**: `/xl/worksheets/sheet2.xml`. The old line tested
            # `startswith("xl/")` BEFORE stripping the slash, so an absolute
            # target became `xl/xl/worksheets/…` and the sheet vanished. It was
            # unreachable until this row, because `_REL` never resolved anything
            # for such a file and the default target hid it — **one bug standing
            # in front of another, which is why the fix had to be measured on a
            # workbook this repo did not write.**
            target = target.lstrip("/")
            part = target if target.startswith("xl/") else f"xl/{target}"
            xml = _read_part(zf, part)
            # ══ FIVE REFUSALS, FIVE SENTENCES, AND THEY ARRIVE AS TEXT ═══════
            # A part over the ceiling, a part that is missing, more rows than
            # `MAX_ROWS`, the cell budget, and a ref beyond XFD. They are
            # separate sentences because they are separate facts: four of them
            # are about OUR ceilings and the last is about the FILE.
            # This module has no exception the upload seam catches by name (the
            # PDF reader's `PDFRefused` is its own, and `except Exception` here
            # lands on the generic *"the .xlsx file could not be read"*). Its
            # existing channel for *"this cell is not what it looks like"* is an
            # in-band marker — `FORMULA_UNSET`, T81f — so a sheet-level refusal
            # travels the same way: a `paragraph` block, in body order, which
            # `Document.text` renders and `xlsx_bytes` ignores when there is a
            # sheet to write. **No second channel invented, and no refusal that
            # renders as an empty spreadsheet.**
            notes: list[str] = []
            if xml is None:
                document.blocks.append(Block(
                    kind="paragraph",
                    text=f"[sheet {_unescape(sheet_name)!r} was not read: its "
                         f"XML is larger than "
                         f"{MAX_XML_BYTES // (1024 * 1024)} MiB]"))
                continue
            if not xml:
                # A DECLARED sheet whose part is absent or empty. Silence here
                # is how the two defects above stayed invisible: the sheet was
                # simply not in the document and nothing said a sheet had been
                # promised. Absence of a promise and a promise unkept are
                # different facts (INVARIANT-ENVELOPE).
                document.blocks.append(Block(
                    kind="paragraph",
                    text=f"[sheet {_unescape(sheet_name)!r} was not read: "
                         f"{part} is missing from the workbook or empty]"))
                continue
            rows: list[list[str]] = []
            beyond_excel = 0
            row_xmls = _wholes(xml, "row", MAX_ROWS + 1)
            if len(row_xmls) > MAX_ROWS:
                notes.append(f"only the first {MAX_ROWS:,} rows were read; the "
                             f"sheet has more")
                row_xmls = row_xmls[:MAX_ROWS]
            row_numbers: list[int] = []
            for position, row_xml in enumerate(row_xmls, start=1):
                cells: dict[int, str] = {}
                # ══ THE ROW NUMBER, WHICH `_REF` HAS ALWAYS CAPTURED ═════════
                # Group 2 of `r="B7"` and nothing has ever read it. Taken from
                # the row's FIRST ref rather than from a `<row r="…">` attribute
                # because every cell carries one and the row element's own
                # attribute is optional in the spec — and a number we can only
                # sometimes read is a number a consumer would fill in.
                stated = _REF.search(row_xml)
                number = int(stated.group(2)) if stated else 0
                if not 0 < number <= EXCEL_MAX_ROW:
                    # **THE POSITION IS NOT A FALLBACK, IT IS A GUESS**, and it
                    # is exactly the guess `chat-NOTE-223` is about. Recorded as
                    # 0, which the model layer documents as *"this reader does
                    # not know"*, so nothing downstream can present it as an
                    # address.
                    number = 0
                for cell in _wholes(row_xml, "c", MAX_CELLS_PER_ROW):
                    ref = _REF.search(cell)
                    index = _column(ref.group(1)) if ref else len(cells)
                    if index < 0:
                        # `_column` refused: out of Excel's own range, so this
                        # cell has no place in a grid. **Skipped, not placed at
                        # `len(cells)`** — the positional fallback exists for a
                        # cell with NO ref, and using it here would shift every
                        # later column of the row left.
                        beyond_excel += 1
                        continue
                    ctype = _TYPE.search(cell)
                    kind = ctype.group(1) if ctype else ""
                    raw = _V.search(cell)
                    inline = _texts(cell, "t", MAX_CELLS_PER_ROW)
                    # ══ THE PAYLOAD DECIDES, NOT THE `t` ATTRIBUTE (T81f) ════
                    # **A cell that carries text IS text, whatever it claims to
                    # be.** Len's R365 export writes its month headers as
                    # `t="n"` with an `<is><t>Feb 2025 -&gt; 2026</t></is>`
                    # payload. The old branch trusted `t`, looked for a `<v>`,
                    # found none, and emitted "" — so of six month headers
                    # exactly ONE survived (January's, the only one declared
                    # `inlineStr`) and the model had no way to tell which column
                    # was which month.
                    #
                    # C57's rule, one format along: *read from the payload, not
                    # from the field list.* Seven cells in this workbook, and
                    # they were the seven that made the table legible.
                    if inline and not raw:
                        value = _unescape("".join(inline))
                    elif kind == "inlineStr":
                        value = _unescape("".join(inline))
                    else:
                        value = _unescape(raw.group(1)) if raw else ""
                        if kind == "s" and value.isdigit():
                            position = int(value)
                            value = shared[position] if position < len(shared) else ""
                        elif kind == "b":
                            value = "TRUE" if value == "1" else "FALSE"
                        elif not value and "<f" in cell:
                            # ══ A FORMULA WITH NO STORED RESULT IS NOT AN
                            # ══ EMPTY CELL (T81f)
                            # 1,109 of this workbook's 7,141 cells are formulas
                            # the exporter never calculated — including EVERY
                            # `2026 Result`. They arrived as blanks,
                            # indistinguishable from a cell nobody filled in, so
                            # when Len asked for a chart of the 2026 projection
                            # **the model was asked to plot numbers that were
                            # not in the data at all** — and it invented them by
                            # taking the next cell along.
                            #
                            # INVARIANT-ENVELOPE, in a spreadsheet: "nobody
                            # entered a value" and "the value exists in Excel
                            # and is not stored in this file" are different
                            # facts and must not render the same. T77's sentence
                            # for a file, applied to a cell.
                            #
                            # Two characters because there are 1,109 of them and
                            # the attachment text is already cut at 40,000 (a
                            # verbose marker would evict the real data it exists
                            # to explain). What it MEANS is stated once, in the
                            # attachment header.
                            value = FORMULA_UNSET
                    cells[index] = value
                width = (max(cells) + 1) if cells else 0
                # ══ THE PER-CELL BOUND DID NOT BOUND THE COMPOSITION (Z5) ════
                # Every ref is now a legal Excel column, and `MAX_ROWS × 16,384`
                # is still **81,920,000 pointers** — reachable from a ~150 KB
                # sheet with nothing but `<c r="XFD1"/>`, one legal sparse cell
                # per row. `max(cells)` is the whole exposure: it reads the
                # FARTHEST column, not the number of cells, so one cell makes one
                # row 16,384 wide. Measured at 500 rows: 17.1s and 8.2M cells.
                #
                # A per-row clamp was rejected — it would return rows of
                # different widths from one grid, and a short row reads as a row
                # whose later columns are empty. The budget stops the sheet and
                # names the row it stopped at instead.
                if materialised + width > MAX_WORKBOOK_CELLS:
                    notes.append(
                        f"stopped after {len(rows):,} rows: this sheet asks for "
                        f"more than {MAX_WORKBOOK_CELLS:,} grid cells, which is "
                        f"more than Plexar reads from one workbook")
                    break
                materialised += width
                rows.append([cells.get(i, "") for i in range(width)])
                row_numbers.append(number)
            while rows and not any(c.strip() for c in rows[-1]):
                rows.pop()
                row_numbers.pop()
            if beyond_excel:
                # A DIFFERENT FACT from every other note here, and it is about
                # the file rather than about our ceiling: these refs name columns
                # Excel itself has none of.
                notes.append(
                    f"{beyond_excel:,} cell(s) were skipped because their "
                    f"reference names a column beyond Excel's last one (XFD)")
            document.blocks.append(
                Block(kind="sheet", name=_unescape(sheet_name), rows=rows,
                      row_numbers=tuple(row_numbers)))
            for note in notes:
                document.blocks.append(Block(
                    kind="paragraph",
                    text=f"[sheet {_unescape(sheet_name)!r}: {note}]"))
    # **The first SHEET's name, not the first block's.** A refusal note is a
    # block now, so a workbook whose first sheet was refused would otherwise be
    # titled after the note's empty `name` — the title silently changing shape
    # because something else went wrong.
    sheets = [b for b in document.blocks if b.kind == "sheet"]
    document.title = sheets[0].name if sheets else ""
    return document
