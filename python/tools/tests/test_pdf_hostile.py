"""T84 — THE PDF READER'S BOUNDS, AND THE COMPOSITIONS THEY EXIST FOR.

Every hostile input in this file is **generated in code and far under the 8 MiB
upload ceiling**, because the point of the row was that a small file bought
minutes of one pinned core: `_extract_text` runs the reader synchronously on the
upload request thread, one thread per request (T3), one process, no admission cap
by design (INVARIANT-NOQUEUE), and there is no wall-clock backstop above it —
`signal.alarm` and `signal.setitimer` do not exist on Windows and CPython cannot
interrupt a thread inside a C-level loop. A blob committed to `tests/fixtures/`
would hide the one thing a reader of this file needs to see, which is what makes
each of these hostile, so every one is built by a function above.

══ EVERY BOUND ARM HAS A COMPANION THAT READS A LEGITIMATE FILE ═══════════
**A bound that refuses a real document is worse than the denial of service it
prevents** — that is T81f's direction, where a file reads as smaller than it is
and nothing downstream can tell. T84 chose its constants against 60 real PDFs
(55/60 byte-identical text before and after), and a personal corpus cannot ship
in a suite, so each companion here is the smallest synthetic fixture carrying the
real-document PROPERTY the corpus measured, and its docstring says which:

    predictor       a real xref/object stream is PNG-predicted with a handful
                    of columns — the shape `_unpredict` exists for
    page content    a real page's `/Contents` is an ARRAY of several streams
    document budget the heaviest real document spent 3.6M operators over 29
                    pages; a per-page bound must not stop at page two
    CMap            the heaviest real document maps 196,608 codes

══ WALL CLOCK **AND** PEAK ALLOCATION, IN SEPARATE PASSES ═════════════════
See `tests/_bounds.py`. Two arms deliberately do not assert a deadline as the
discriminator and say why in place: the predictor refusal is 0.3ms against a
pre-fix 551ms and no honest deadline sits between those two numbers, so the
refusal itself is what separates them.
"""

from __future__ import annotations

import zlib

import pytest

from plexar_tools import office
from plexar_tools.office.pdf import NoTextInPDF, PDFRefused
from plexar_tools.office.pdf import _read as reader
from tests._bounds import elapsed, peak_mib

FONT = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"


# ══════════════════════════════════════════════════════════════════════════════
# FIXTURE BUILDERS — hostile by construction, and visibly so
# ══════════════════════════════════════════════════════════════════════════════

def _file(objects: list[bytes], root: int = 1, trailer: bytes = b"") -> bytes:
    """Numbered objects plus a trailer. No xref, matching `test_pdf_reading`."""
    out = bytearray(b"%PDF-1.7\n")
    for i, body in enumerate(objects, start=1):
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    out += b"trailer\n<< /Root %d 0 R " % root + trailer + b">>\n%%EOF\n"
    return bytes(out)


def _flate(body: bytes, extra: bytes = b"") -> bytes:
    packed = zlib.compress(body)
    return (b"<< /Length %d /Filter /FlateDecode " % len(packed) + extra
            + b">>\nstream\n" + packed + b"\nendstream")


def _one_page(content: bytes, parms: bytes = b"", extra: list[bytes] = []) -> bytes:
    """A one-page document whose content stream is `content`.

    Object 6 is the XObject slot the form fixtures fill, so the page's
    `/Resources` names it whether or not it exists — a dangling name is exactly
    what `_xobject` already refuses, and it keeps one builder for both cases.
    """
    return _file([
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources "
        b"<< /Font << /F1 5 0 R >> /XObject << /X1 6 0 R >> >> "
        b"/Contents 4 0 R >>",
        _flate(content, parms),
        FONT,
    ] + list(extra))


def _pages(contents: list[bytes], extra: list[bytes] = []) -> bytes:
    """One document, several pages, each with its own content stream.

    The page objects are 3..3+n and the streams follow them, so the `/Kids`
    array is real and `pages()` walks the tree rather than falling back to the
    object-number scan.
    """
    n = len(contents)
    first_stream = 3 + n
    kids = b" ".join(b"%d 0 R" % (3 + i) for i in range(n))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [" + kids + b"] /Count %d >>" % n,
    ]
    for i in range(n):
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources "
            b"<< /Font << /F1 %d 0 R >> /XObject << /X1 %d 0 R >> >> "
            b"/Contents %d 0 R >>"
            % (first_stream + n, first_stream + n + 1, first_stream + i))
    objects.extend(_flate(c) for c in contents)
    objects.append(FONT)
    objects.extend(extra or [b"<< >>"])
    return _file(objects)


def _text(words: str, size: int = 12) -> bytes:
    return (b"BT /F1 %d Tf 72 700 Td (%s) Tj ET"
            % (size, words.encode("latin-1")))


def _predicted(body: bytes, columns: int) -> bytes:
    """`body`, PNG-predicted with the None filter on every row.

    Filter tag 0 means *"this row is stored as-is"*, so the predictor is real
    and its inverse is the identity — which is what lets a companion arm assert
    that a legitimately predicted stream comes back UNCHANGED rather than
    merely unrefused.
    """
    padded = body + b"\x00" * (-len(body) % columns)
    return b"".join(b"\x00" + padded[i:i + columns]
                    for i in range(0, len(padded), columns))


def _self_referencing_form(fan_out: int, number: int = 6) -> bytes:
    """A Form XObject that draws itself `fan_out` times.

    **The depth cap was 8 and `8 ** 8` is the number it does not bound.** The
    form's own `/Resources` names itself, so every level of the tree has the
    same breadth — which is the composition, not the recursion.
    """
    return _flate(b"\n".join([b"/X1 Do"] * fan_out),
                  b"/Type /XObject /Subtype /Form /Resources "
                  b"<< /XObject << /X1 %d 0 R >> >> " % number)


def _counted(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """Count `_Page.run` invocations and `_Budget.spend` charges.

    **The count is the assertion that survives a faster machine.** An elapsed
    ceiling on the form-tree arm says nothing on a box twice as fast; `8 ** 8`
    invocations is the same number everywhere.

    `spend` is counted including its recursion into the parent, so a page with a
    document budget charges twice per operator. That is stated rather than
    corrected — the arms compare against the budget they were given x2, and
    hiding the recursion would make the number harder to check by hand.
    """
    tally = {"runs": 0, "spends": 0}
    run, spend = reader._Page.run, reader._Budget.spend

    def counted_run(self, content, depth: int = 0):  # type: ignore[no-untyped-def]
        tally["runs"] += 1
        return run(self, content, depth)

    def counted_spend(self, count: int = 1):  # type: ignore[no-untyped-def]
        tally["spends"] += count
        return spend(self, count)

    monkeypatch.setattr(reader._Page, "run", counted_run)
    monkeypatch.setattr(reader._Budget, "spend", counted_spend)
    return tally


# ══════════════════════════════════════════════════════════════════════════════
# Z1 — /DecodeParms, THREE ATTACKER-AUTHORED NUMBERS THAT GET MULTIPLIED
# ══════════════════════════════════════════════════════════════════════════════

def test_a_predictor_row_of_two_million_columns_is_refused() -> None:
    """**THE REFUSAL IS THE DISCRIMINATOR HERE, NOT THE DEADLINE.**

    Measured: 0.3ms refused, against 551ms and a 2 MB row before T84 — and no
    honest wall-clock ceiling sits between half a second and three tenths of a
    millisecond, so a deadline-only arm would be green against the defect. What
    separates them is that a `PDFRefused` naming the row now arrives at all.

    The deadline and the peak are still asserted, because they are what bound
    the extrapolation the row was actually afraid of: the cost is LINEAR in
    `/Columns`, so `/Columns 2000000000` is the same twelve characters asking
    for 2 GB and ~9 minutes.
    """
    body = _one_page(_text("hello"),
                     b"/DecodeParms << /Predictor 12 /Columns 2000000 >> ")
    assert len(body) < 8 * 1024 * 1024

    seconds, raised, _ = elapsed(lambda: office.read(body, "wide.pdf"))
    assert isinstance(raised, PDFRefused), raised
    assert "predictor" in str(raised) and "2000000 columns" in str(raised)
    assert seconds < 10.0, seconds          # measured 0.0003s
    assert peak_mib(lambda: office.read(body, "wide.pdf")) < 64.0  # measured 0.4


def test_a_predictor_with_sixty_five_thousand_colours_is_refused() -> None:
    """The same product with the columns left at one.

    `/Colors 65535 /BitsPerComponent 32` reaches a 262 KB row from a
    `/Columns` of 1, which is 47ms per 101-byte object — ~63 minutes if the file
    is nothing but those. **Checking the three numbers separately is not the
    same as checking what they multiply to**, and this arm is the half that
    proves the check is on the product: `/Columns 1` passes every bound a
    single-parameter check would apply.
    """
    body = _one_page(
        _text("hello"),
        b"/DecodeParms << /Predictor 12 /Colors 65535 /BitsPerComponent 32 >> ")
    seconds, raised, _ = elapsed(lambda: office.read(body, "deep.pdf"))
    assert isinstance(raised, PDFRefused), raised
    assert "65535 colours" in str(raised)
    assert seconds < 10.0, seconds
    assert peak_mib(lambda: office.read(body, "deep.pdf")) < 64.0


def test_a_real_predictor_stream_still_decodes_unchanged() -> None:
    """**THE COMPANION, and it stands in for every xref stream in the corpus.**

    A real cross-reference or object stream is PNG-predicted with a handful of
    columns — that is the shape `_unpredict` exists for, and a bound tight
    enough to make the arms above fast must not touch it. Asserted as the
    IDENTITY of the round trip rather than as "it did not raise": a predictor
    that returns the wrong width shifts every byte after it, which is the exact
    defect the function exists to undo, delivered silently.
    """
    pdf = reader.PDF(_one_page(_text("hi")))
    payload = bytes(range(256)) * 4
    out = pdf._unpredict(_predicted(payload, 4),
                         {"Predictor": 12, "Columns": 4})
    assert out.startswith(payload), "a legitimate predictor row was mangled"

    document = office.read(
        _one_page(_predicted(_text("Revenue rose twelve percent"), 8),
                  b"/DecodeParms << /Predictor 12 /Columns 8 >> "),
        "predicted.pdf")
    assert "Revenue rose twelve percent" in document.text, document.text


def test_a_bound_hit_inside_an_object_stream_still_reports_a_scan() -> None:
    """**A KNOWN GAP, ASSERTED AS IT STANDS SO A LATER FIX IS VISIBLE.**

    `_expand_object_streams` swallows one bad object with `except Exception:
    continue`, and a `PDFRefused` from `_unpredict` is one of those. So a file
    refused for the predictor bound INSIDE an object stream surfaces as *"this
    PDF is a scan"* when it has no other text — the bound fired and the reason
    was lost.

    **That is defensible** (one damaged object stream must not kill a document
    that still has readable pages) **and it is also the shape of chat-R-235**: a
    confident wrong diagnosis standing in for a bound that fired, which
    INVARIANT-ENVELOPE says must read differently from *"the words are pixels"*.
    Pinned here rather than left unasserted so that closing it reddens this arm
    instead of passing quietly.
    """
    hostile = (b"<< /Type /ObjStm /N 1 /First 4 /Length 20 "
               b"/Filter /FlateDecode /DecodeParms << /Predictor 12 "
               b"/Columns 2000000 >> >>\nstream\n"
               + zlib.compress(b"9 0 << >>") + b"\nendstream")
    body = _one_page(b"q /Im0 Do Q", extra=[b"<< >>", hostile])

    seconds, raised, _ = elapsed(lambda: office.read(body, "objstm.pdf"))
    assert isinstance(raised, NoTextInPDF), raised
    assert "scan" in str(raised), (
        "if this reddened because the reason now names the predictor, the gap "
        "above has been closed — update the docstring, do not loosen the arm")
    assert seconds < 10.0, seconds


# ══════════════════════════════════════════════════════════════════════════════
# Z2 — THE FORM TREE, WHERE A DEPTH CAP IS NOT A BOUND
# ══════════════════════════════════════════════════════════════════════════════

def test_a_self_referencing_form_cannot_multiply_a_small_budget(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """**THE SPEND IS ASSERTED, NOT THE CLOCK.**

    Eight `Do`s in a form that references itself is `8 ** 8` ≈ 16.7 million
    `run()` invocations under the old per-`_Page` counter, each entitled to its
    own two million operators. This arm hands the page a 200,000-operator
    document budget and asserts the whole tree spends it ONCE — which is the
    property `_Budget`'s parent expresses and no per-node constant can.

    The budget is reduced deliberately: `MAX_DOCUMENT_OPERATORS` is 12,000,000
    and spending all of it costs ~5.4s, which is measured by the next arm. The
    composition is the same at any size, and a small ruler makes the peak pass
    affordable.
    """
    monkeypatch.setattr(reader, "MAX_DOCUMENT_OPERATORS", 200_000)
    tally = _counted(monkeypatch)
    body = _one_page(_text("seed") + b"\n" + b"\n".join([b"/X1 Do"] * 8),
                     extra=[_self_referencing_form(8)])
    assert len(body) < 8 * 1024 * 1024

    seconds, raised, document = elapsed(lambda: office.read(body, "form.pdf"))
    assert raised is None, raised
    assert "seed" in document.text
    # x2 because `spend` charges the page budget and then its parent; see
    # `_counted`. The ceiling is the document budget, not the tree's breadth.
    assert tally["spends"] <= 2 * 200_000 + 1_000, tally
    assert tally["runs"] < 20_000, tally      # `8 ** 8` is 16,777,216
    assert seconds < 15.0, seconds            # measured 0.09s


def test_the_form_tree_is_bounded_with_the_shipped_constants(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """The same fixture against the real numbers. **It did not finish in 110s.**

    Measured after T84: 5.4s, 93,756 `run()` invocations, 3,000,018 charges —
    exactly twice `MAX_CONTENT_OPERATORS`, i.e. the PAGE budget is what stopped
    it and the document budget was never reached. The counts are the assertion;
    the 40s ceiling exists only to fail a genuine hang, and it is ~7x the
    measurement so a slower box does not flake.

    **No peak pass on this arm, on purpose.** `tracemalloc` inflated T84's own
    timings by up to 17x, so tracing a 5.4s run would cost a minute and a half
    of suite time to learn what the arm above already measured. The memory
    quantity here is the `lines.extend` accumulation on the way back up the
    tree, and it is asserted as a COUNT of blocks instead.
    """
    tally = _counted(monkeypatch)
    body = _one_page(_text("seed") + b"\n" + b"\n".join([b"/X1 Do"] * 8),
                     extra=[_self_referencing_form(8)])
    seconds, raised, document = elapsed(lambda: office.read(body, "form.pdf"))
    assert raised is None, raised
    assert tally["runs"] < 200_000, tally
    assert tally["spends"] <= 2 * reader.MAX_CONTENT_OPERATORS + 1_000, tally
    assert len(document.blocks) < reader.MAX_LINES, len(document.blocks)
    assert seconds < 40.0, seconds


def test_one_hostile_page_does_not_read_the_rest_of_the_document(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """**`_Budget.parent`, AND `read()`'s BREAK — the arm T84 said it lacked.**

    `MAX_PAGES` is 2,000 and the per-page bound is 1,500,000 operators, so
    without a parent one document is entitled to three billion. The parent means
    a single hostile page CAN spend the whole document allowance — and then
    `read()` must LEAVE THE PAGE LOOP rather than starting page two with an
    exhausted budget.

    **Asserted as a DIFFERENCE, because the absence of page two's text is only
    evidence if page two is readable at all.** The second half of this arm runs
    the identical bytes with the shipped constant and requires every page to
    arrive; without it, a fixture whose later pages were malformed would report
    a working bound (R23).
    """
    body = _pages([_text("seed") + b"\n" + b"\n".join([b"/X1 Do"] * 8),
                   _text("second page"), _text("third page")],
                  extra=[_self_referencing_form(8, number=10)])

    monkeypatch.setattr(reader, "MAX_DOCUMENT_OPERATORS", 30_000)
    seconds, raised, spent = elapsed(lambda: office.read(body, "pages.pdf"))
    assert raised is None, raised
    assert "second page" not in spent.text, (
        "the document budget was exhausted by page one and page two was read "
        "anyway — the break in read()'s page loop is gone")
    assert seconds < 15.0, seconds

    # **3,000,000 rather than the shipped 12,000,000**: page one is stopped by
    # its OWN 1,500,000-operator budget and leaves half the document allowance
    # unspent, which is the state that must let pages two and three through.
    # The shipped constant would prove the same thing and cost 5.4s, which the
    # arm above already pays once.
    monkeypatch.setattr(reader, "MAX_DOCUMENT_OPERATORS", 3_000_000)
    whole = office.read(body, "pages.pdf")
    assert "second page" in whole.text and "third page" in whole.text, (
        "the fixture's later pages do not read even with a full budget, so the "
        "assertion above proves nothing")


def test_a_forty_page_document_reads_every_page() -> None:
    """**THE COMPANION for the document budget.**

    Stands in for the heaviest document in T84's corpus — 3,594,702 operators
    over 29 pages, 48,214 lines — which is the file a bound tight enough to
    make the arms above cheap would have truncated. Asserted on the LAST page,
    because a truncation at page two and a truncation at page thirty-nine read
    the same in a total character count.
    """
    document = office.read(
        _pages([_text("page marker %d" % i) for i in range(1, 41)]),
        "long.pdf")
    assert "page marker 1" in document.text
    assert "page marker 40" in document.text, "the last page was dropped"


# ══════════════════════════════════════════════════════════════════════════════
# Z4 — THE DECODE BUDGET, AND THE CACHE HIT IS THE HALF THAT MATTERS
# ══════════════════════════════════════════════════════════════════════════════

def _four_hundred_references() -> bytes:
    """One 4 MiB stream, named 400 times in one `/Contents` array.

    19 KB on the wire before T84 measured **9.1s and 3,366 MB resident**, with
    every per-stream bound in the file holding every time.
    """
    packed = zlib.compress(b" " * (4 * 1024 * 1024))
    return _file([
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources "
        b"<< /Font << /F1 5 0 R >> >> /Contents ["
        + b" ".join([b"4 0 R"] * 400) + b"] >>",
        b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(packed)
        + packed + b"\nendstream",
        FONT,
    ])


def test_one_stream_named_four_hundred_times_is_refused() -> None:
    """The refusal, and the ONE number that says the aggregate is what stopped it.

    Measured: 0.10s and a 67 MiB peak from a 6,899-byte file, against 9.1s and
    3,366 MB. **The peak ceiling is the assertion that matters** — a
    deadline-only arm would have been green at 3.3 GB, which is the whole reason
    `tests/_bounds.py` exists.

    The sentence that arrives is the PAGE-CONTENT one rather than the decode
    budget's, because 64 MiB of assembled page content is reached at reference
    sixteen and the 256 MiB document allowance at sixty-four. That is pinned
    here on purpose: two aggregates guard this file and the tighter one fires
    first, so an arm expecting the decode sentence would redden on a correct
    reader.
    """
    body = _four_hundred_references()
    assert len(body) < 32 * 1024

    seconds, raised, _ = elapsed(lambda: office.read(body, "amplified.pdf"))
    assert isinstance(raised, PDFRefused), raised
    assert "more content than Plexar will assemble for a single page" \
        in str(raised)
    assert seconds < 15.0, seconds                       # measured 0.10s
    assert peak_mib(lambda: office.read(body, "amplified.pdf")) < 256.0


def test_the_decode_budget_is_charged_on_every_cache_hit() -> None:
    """**THE OTHER HALF OF THE PAIR, AND ALONE EITHER ONE PROVES NOTHING.**

    The fixture holds exactly ONE stream. It is decoded once — `Stream.decoded`
    caches it — so a bound that charged only the decode would see 4 MiB and
    refuse nothing, and every single-stream assertion in this file would still
    pass. What the aggregate is spent on is the RETURN: `body.extend` copies the
    bytes again each time.

    Asserted on `_decode_left` directly, three returns of the same stream, with
    the count of distinct streams asserted first — because *"the budget went
    down"* is satisfied by one charge as well as by three.
    """
    pdf = reader.PDF(_four_hundred_references())
    streams = [o for o in pdf.objects.values() if isinstance(o, reader.Stream)]
    assert len(streams) == 1, "the fixture must name ONE stream many times"

    before = pdf._decode_left
    sizes = []
    for _ in range(3):
        sizes.append(len(pdf.stream_bytes(streams[0])))
    assert sizes == [4 * 1024 * 1024] * 3
    assert before - pdf._decode_left == 3 * 4 * 1024 * 1024, (
        "the second and third returns came out of the cache for free, so "
        "/Contents may name one stream as often as it likes")


def test_watch_to_fail_charging_only_the_first_decode_refuses_nothing() -> None:
    """R23 for the pair, as arithmetic rather than as a patched module.

    `_charge` is one line inside `stream_bytes`; removing it from the cache-hit
    path cannot be done through CSSOM or a patched copy, and T5/C54c forbid
    leaving a file on disk wrong even for a millisecond. So the removed rule is
    re-implemented here and required to DIFFER from what ships: 400 returns of a
    4 MiB stream is 1,600 MiB against a 256 MiB allowance, and charging only the
    first is 4 MiB — which refuses nothing and reports *"this PDF is a scan"*,
    which is what Len would have been shown.
    """
    allowance = reader.MAX_DECODED_BYTES
    size = 4 * 1024 * 1024
    charged_once = size
    charged_every_time = 400 * size
    assert charged_once < allowance, "the fixture must be safe under the defect"
    assert charged_every_time > allowance, (
        "the fixture no longer exceeds the allowance, so the arm above would "
        "pass with no aggregate at all")


def test_a_page_with_three_content_streams_reads_all_three() -> None:
    """**THE COMPANION for the page-content aggregate.**

    A real page's `/Contents` is legitimately an ARRAY — a producer that writes
    its header, body and footer as separate streams is ordinary, and a reader
    that bounded the array's LENGTH instead of its total size would drop the
    footer. Asserted on all three fragments.
    """
    document = office.read(_file([
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources "
        b"<< /Font << /F1 7 0 R >> >> /Contents [4 0 R 5 0 R 6 0 R] >>",
        _flate(b"BT /F1 12 Tf 72 700 Td (header line) Tj ET"),
        _flate(b"BT /F1 12 Tf 72 600 Td (body line) Tj ET"),
        _flate(b"BT /F1 12 Tf 72 500 Td (footer line) Tj ET"),
        FONT,
    ]), "three.pdf")
    for fragment in ("header line", "body line", "footer line"):
        assert fragment in document.text, (fragment, document.text)


# ══════════════════════════════════════════════════════════════════════════════
# Z3 — THE CMap BOUND COUNTS WRITES, AND THAT IS A CORRECTION TO THE AUDIT
# ══════════════════════════════════════════════════════════════════════════════

def _wide_bfranges(copies: int) -> bytes:
    """`<0000><FFFF><0041>` repeated. 18 bytes each, 65,536 entries each."""
    return (b"%d beginbfrange\n" % copies
            + b"<0000><FFFF><0041>\n" * copies + b"endbfrange\n")


def test_the_cmap_bound_counts_writes_and_not_the_size_of_the_result() -> None:
    """**AN ARM ON `len(to_unicode)` WOULD BE GREEN WITH NO BOUND AT ALL.**

    Twenty copies of `<0000><FFFF>` write 1,310,720 times into 65,536 DISTINCT
    keys. So the mapping never passes any ceiling, the audit's recommended
    `len(mapping) >= ceiling` check measured **411ms against 335ms unbounded**,
    and counting writes measured **62ms**. Three facts, asserted separately:

      * the result is SMALLER than the ceiling — which is why the obvious
        assertion is vacuous, and this arm states that rather than implying it;
      * exactly `MAX_CMAP_ENTRIES` writes were charged to the document, read
        off `cmap_left`, which is the only observable that distinguishes the
        shipped bound from no bound;
      * the clock, at a ceiling that cannot separate 56ms from 335ms and is
        therefore not the discriminator.
    """
    data = _wide_bfranges(20)
    assert len(data) < 1024

    pdf = reader.PDF(_one_page(_text("hi")))
    seconds, raised, mapping = elapsed(lambda: reader._cmap(data, pdf))
    assert raised is None, raised
    assert len(mapping) == 65_536
    assert len(mapping) < reader.MAX_CMAP_ENTRIES, (
        "the fixture's result is now bigger than the ceiling, so an assertion "
        "on len(mapping) would start to mean something and this arm's point "
        "has been lost")
    written = reader.MAX_DOCUMENT_CMAP_ENTRIES - pdf.cmap_left
    assert written == reader.MAX_CMAP_ENTRIES, written
    assert seconds < 10.0, seconds                       # measured 0.056s
    assert peak_mib(lambda: reader._cmap(data, reader.PDF(_one_page(_text("hi")))
                                        )) < 64.0        # measured ~9 MiB


def test_a_document_wide_cmap_allowance_bounds_the_number_of_fonts() -> None:
    """The per-font ceiling multiplies by the number of FONTS, which is also
    attacker-chosen. Five fonts each asking for 65,536 entries must not each get
    their own allowance.

    Asserted on the document's own counter after five `_cmap` calls: the first
    ones are served and the last ones are refused room, so the SUM is bounded.
    """
    pdf = reader.PDF(_one_page(_text("hi")))
    pdf.cmap_left = 100_000
    for _ in range(5):
        reader._cmap(_wide_bfranges(20), pdf)
    assert pdf.cmap_left <= 0, pdf.cmap_left
    assert pdf.cmap_left > -200_000, (
        "one font overspent the whole document allowance by more than a "
        "per-font ceiling, so the allowance is not being read")


def test_a_three_thousand_entry_cmap_maps_every_code() -> None:
    """**THE COMPANION, and it is the corpus's heaviest font.**

    The heaviest real document in T84's corpus mapped 196,608 codes across its
    fonts — one CJK subset legitimately uses thousands. A bound that truncated
    those would produce a page of missing glyphs, which reads as *"our reader is
    broken"* rather than as a refusal.
    """
    entries = b"".join(b"<%04X><%04X>\n" % (i, 0x41 + (i % 26))
                       for i in range(3_000))
    mapping = reader._cmap(b"3000 beginbfchar\n" + entries + b"endbfchar\n")
    assert len(mapping) == 3_000, len(mapping)


def test_twenty_thousand_unclosed_bfchar_openers_cost_one_scan() -> None:
    """Z6 — `re.findall(rb"beginbfchar(.*?)endbfchar")` is O(openers x length).

    **Did not finish in 110s** before T84; measured 0.0001s after, because a
    close found from position k is the close any later opener would find, so a
    missing one ends the walk instead of being retried from the next opener.
    Here the deadline IS a real discriminator — the ratio is five orders of
    magnitude — so 10s is both far above the measurement and far below the
    defect.
    """
    data = b"beginbfchar\n" * 20_000 + b"x" * (1024 * 1024)
    seconds, raised, sections = elapsed(
        lambda: reader._sections(data, b"beginbfchar", b"endbfchar"))
    assert raised is None, raised
    assert sections == [], "an unclosed opener is not a section"
    assert seconds < 10.0, seconds
    assert peak_mib(lambda: reader._sections(
        data, b"beginbfchar", b"endbfchar")) < 16.0


def test_a_closed_bfchar_section_is_still_found() -> None:
    """The companion to the walk. `_sections` replaced a regex, and a scanner
    that found NOTHING would make every arm above pass while reporting *"this
    PDF has no text"* — the symptom this module already emits for a scan."""
    data = (b"junk beginbfchar\n<0041><0042>\nendbfchar tail "
            b"beginbfchar\n<0043><0044>\nendbfchar")
    found = reader._sections(data, b"beginbfchar", b"endbfchar")
    assert len(found) == 2, found
    assert b"<0041><0042>" in found[0] and b"<0043><0044>" in found[1]


# ══════════════════════════════════════════════════════════════════════════════
# Z7 — LZW: THE MEMORY WAS THE UNBOUNDED PART, AND THE TIME STILL IS
# ══════════════════════════════════════════════════════════════════════════════

def _lzw_that_never_clears(codes: int) -> bytes:
    """A bit-packed LZW stream that emits one legal code forever.

    Code 256 is the CLEAR and this stream never sends it, so every code after
    the first appends a row to the table. **The width schedule mirrors the
    shipped decoder** — the table stops growing at `MAX_LZW_TABLE`, and an
    encoder that kept counting past it would desynchronise and measure a
    different function than the one under test.
    """
    out = bytearray()
    buffer = bits = 0
    width, table = 9, 258
    for i in range(codes):
        buffer = (buffer << width) | 65
        bits += width
        while bits >= 8:
            out.append((buffer >> (bits - 8)) & 0xFF)
            bits -= 8
        buffer &= (1 << bits) - 1
        if i and table < reader.MAX_LZW_TABLE:
            table += 1
        if table + 1 >= (1 << width) and width < 12:
            width += 1
    if bits:
        out.append((buffer << (8 - bits)) & 0xFF)
    return bytes(out)


def _lzw_with_an_unbounded_table(raw: bytes) -> bytes:
    """`_read._lzw` with its two `len(table) < MAX_LZW_TABLE` guards removed.

    **The pre-T84 function, re-implemented in the test rather than patched into
    the module.** T5/C54c: no file on disk may be wrong, not even for a
    millisecond, and this is the only way to compare the two rules in one
    process. It is a copy and it will drift; the arm that uses it asserts the
    OUTPUT of both is identical, so a drifted copy reddens instead of quietly
    measuring something else.
    """
    out = bytearray()
    table: list[bytes] = [bytes([i]) for i in range(256)] + [b"", b""]
    width = 9
    previous: bytes | None = None
    buffer = value = 0
    for byte in raw:
        buffer = (buffer << 8) | byte
        value += 8
        while value >= width:
            code = (buffer >> (value - width)) & ((1 << width) - 1)
            value -= width
            if code == 256:
                table = [bytes([i]) for i in range(256)] + [b"", b""]
                width, previous = 9, None
                continue
            if code == 257:
                return bytes(out)
            if previous is None:
                if code >= len(table):
                    return bytes(out)
                entry = table[code]
            elif code < len(table):
                entry = table[code]
                table.append(previous + entry[:1])
            else:
                entry = previous + previous[:1]
                table.append(entry)
            out.extend(entry)
            previous = entry
            if len(table) + 1 >= (1 << width) and width < 12:
                width += 1
            if len(out) > reader.MAX_STREAM_BYTES:
                return bytes(out)
    return bytes(out)


def test_the_lzw_table_stops_at_the_twelve_bit_code_space() -> None:
    """**MEMORY, NOT TIME — and the arm says so because the row does.**

    1 MiB of codes that never clear built 700,284 table rows and 32.7 MB while
    `len(out)` stayed far under its cap: the existing bound watched the wrong
    quantity. PDF LZW is 12-bit, so past 4,096 rows no code in the stream can
    address what is being appended.

    **Asserted as a DIFFERENCE against the pre-T84 rule re-implemented above**,
    not against a constant, so a break that changed nothing cannot pass as
    *"the memory is fine"* — and the two are required to return the same BYTES
    first, because a copy that had drifted would compare two different
    functions and call the gap a saving. **No speed claim**: the work is linear
    in the input and T84 measured 478ms -> 400ms, which is noise.
    """
    raw = _lzw_that_never_clears(50_000)
    assert len(raw) < 128 * 1024

    shipped = reader._lzw(raw)
    unbounded = _lzw_with_an_unbounded_table(raw)
    assert shipped == unbounded, (
        "the re-implementation has drifted from the module, so the peaks below "
        "are not measuring one rule against another")

    bounded_peak = peak_mib(lambda: reader._lzw(raw))
    growing_peak = peak_mib(lambda: _lzw_with_an_unbounded_table(raw))
    assert growing_peak > bounded_peak * 2, (bounded_peak, growing_peak)
    assert bounded_peak < 8.0, bounded_peak      # measured 0.44 MiB


def test_lzw_is_linear_in_the_stream_length() -> None:
    """**THIS ARM REPLACED ONE THAT PINNED THE DEFECT, ON ITS OWN INSTRUCTIONS.**

    Its predecessor asserted that `_lzw`'s cost was SUPERLINEAR, because that was
    the truth when this gate was written: `buffer = (buffer << 8) | byte`
    accumulated the bit reservoir and never masked off the bits already consumed,
    so `buffer` grew by eight bits per INPUT byte and every
    `buffer >> (value - width)` shifted a bignum sized by the whole stream.
    `value` tracked the valid bit COUNT correctly; the integer holding them was
    unbounded.

        25,000 codes    28 KB    0.157s
        50,000 codes    56 KB    0.546s
       100,000 codes   112 KB    2.128s      ~4x per doubling

    The raw stream is bounded only by the 8 MiB upload ceiling, so ONE legal
    `/Filter /LZWDecode` object extrapolated to hours of a pinned core. **T84
    bounded the TABLE and left this, and its docstring claimed the time was
    "linear in the input" — measured on a stream that exits at the first code,
    so the measurement was of nothing.** The gate found both.

    One `&` closed it, and the same fixture now measures:

        25,000 codes    0.013s
       100,000 codes    0.053s
     1,000,000 codes    0.504s      <- linear, 1.1 MB of input

    **A ratio arm would be the wrong shape now.** Linear growth means the ratio
    IS about 2, and asserting `second < first * 2.5` against a 0.013s baseline is
    a coin flip inside Windows' 15.6 ms scheduler granularity — a flaky arm about
    a fixed defect is worse than no arm. So this is a DEADLINE on a stream large
    enough that the old behaviour could not possibly have met it: at 1 MiB the
    pre-fix cost was hours, and the ceiling below is ~20x the measured 0.5s.
    """
    raw = _lzw_that_never_clears(1_000_000)
    assert len(raw) > 1_000_000, len(raw)      # 1.1 MB, and the ceiling is real
    seconds, _, _ = elapsed(lambda: reader._lzw(raw))
    assert seconds < 10.0, seconds             # measured 0.504s; pre-fix: hours


def test_a_real_lzw_stream_decodes_to_its_original_bytes() -> None:
    """**THE COMPANION.** Old files and many scanners still write LZW, and a
    decoder that refused them reads as a page with no text on it. A stream that
    clears its table and terminates properly must come back whole."""
    # `clear`, then the literal codes for "AB", then EOD — the shortest stream
    # that exercises the clear code, a table append and the terminator.
    out, buffer, bits = bytearray(), 0, 0
    for code in (256, 65, 66, 257):
        buffer = (buffer << 9) | code
        bits += 9
        while bits >= 8:
            out.append((buffer >> (bits - 8)) & 0xFF)
            bits -= 8
        buffer &= (1 << bits) - 1
    if bits:
        out.append((buffer << (8 - bits)) & 0xFF)
    assert reader._lzw(bytes(out)) == b"AB"


# ══════════════════════════════════════════════════════════════════════════════
# 2c — A MEGABYTE OF DIGITS, AND THE QUADRATIC ERROR PATH
# ══════════════════════════════════════════════════════════════════════════════

def test_a_megabyte_of_digits_in_a_content_stream_does_not_re_lex_it() -> None:
    """`int()` raises above 4,300 digits, and `run`'s error path retried at
    `before + 1` — so a million-digit token was a million retries each lexing to
    the end of the buffer. **Did not finish in 110s**; measured 0.11s after.

    The refusal is `NoTextInPDF`, which is CORRECT and worth pinning: a content
    stream of digits draws no glyphs, so *"there is no text in this"* is the
    honest sentence rather than a bound's. The deadline is the discriminator
    here and 15s is ~140x the measurement.
    """
    body = _one_page(b"1" * (1024 * 1024))
    assert len(body) < 8 * 1024 * 1024

    seconds, raised, _ = elapsed(lambda: office.read(body, "digits.pdf"))
    assert isinstance(raised, NoTextInPDF), raised
    assert seconds < 15.0, seconds
    assert peak_mib(lambda: office.read(body, "digits.pdf")) < 128.0


def test_a_real_number_in_a_content_stream_still_places_its_text() -> None:
    """The companion, and the reason `MAX_TOKEN_DIGITS` is 32 rather than 8: a
    producer writes coordinates like `123.456789`, and a token bound tight
    enough to look safe would drop the operand and mis-place the line."""
    document = office.read(
        _one_page(b"BT /F1 12 Tf 1 0 0 1 72.123456789 700.987654321 Tm "
                  b"(placed precisely) Tj ET"), "real.pdf")
    assert "placed precisely" in document.text


# ══════════════════════════════════════════════════════════════════════════════
# chat-R-235 — THE ENCRYPTED REFUSAL, WATCHED TO FAIL
# ══════════════════════════════════════════════════════════════════════════════

def _encrypted() -> bytes:
    """A realistic encrypted PDF: `/Encrypt 9 0 R` in the TRAILER.

    **The two properties that make it realistic and that the old fixture had
    neither of.** Object 9 is a standard security handler — `/Filter /Standard
    /V 4 /R 4` — and holds NO key named `Encrypt`, which is why scanning object
    bodies found nothing across five real DocuSign packets. And the content
    stream is ENCIPHERED, i.e. bytes that are not Flate, so `_inflate` returns
    nothing and the document yields zero glyphs — which is what made the old
    answer *"this PDF has no text in it, it is a scan."*
    """
    ciphertext = bytes(range(256)) * 4
    return _file([
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources "
        b"<< /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(ciphertext)
        + ciphertext + b"\nendstream",
        FONT,
        b"<< >>", b"<< >>", b"<< >>",
        b"<< /Filter /Standard /V 4 /R 4 /Length 128 /P -1340 "
        b"/O <0102030405060708090A0B0C0D0E0F10> "
        b"/U <1112131415161718191A1B1C1D1E1F20> >>",
    ], trailer=b"/Encrypt 9 0 R ")


def test_an_encrypted_pdf_is_refused_by_reading_the_trailer() -> None:
    """chat-R-235, on the shape a producer actually emits.

    Five of nine PDFs reported as scans out of Len's own Downloads folder were
    encrypted DocuSign packets whose TRAILER reads `/Encrypt 1176 0 R`. **The
    word `trailer` appeared nowhere in the reader**, so the refusal had never
    once fired on a conventional PDF and the user was handed a confident wrong
    diagnosis — the actionable step is *supply the password*, which is not the
    one *"it is a scan"* suggests.
    """
    with pytest.raises(PDFRefused) as caught:
        office.read(_encrypted(), "locked.pdf")
    assert "password-protected or encrypted" in str(caught.value)
    assert "scan" not in str(caught.value)


def test_watch_to_fail_without_the_trailer_scan_it_reads_as_a_scan(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """R23 — the pre-T84 reader, re-created by taking `_trailers` away.

    **The sabotage is confirmed before the result is read**: `_trailers()` must
    genuinely return nothing on this file, and the file must genuinely contain
    the bytes `/Encrypt`, or the arm would be reporting that a refusal is
    missing from a document that never asked for one.
    """
    body = _encrypted()
    assert b"/Encrypt" in body

    monkeypatch.setattr(reader.PDF, "_trailers", lambda self: [])
    assert reader.PDF(body)._trailers() == [], "the sabotage did not take"

    with pytest.raises(NoTextInPDF) as caught:
        office.read(body, "locked.pdf")
    assert "scan" in str(caught.value), (
        "the encrypted file is no longer diagnosed as a scan without the "
        "trailer scan, so this arm is not re-creating chat-R-235")


def test_a_document_about_encryption_is_not_refused_for_saying_so() -> None:
    """**THE PAIR, and it is why a byte-presence refusal was rejected as the fix.**

    `if b"/Encrypt" not in self.data: return` is a FAST PATH and never a
    verdict. A document whose own words contain `/Encrypt` — a manual, a
    security review, this repo's own notes — must still read, and what decides
    is a parsed dictionary. Asserted on the text coming back, not merely on the
    absence of a raise: a reader that refused nothing and returned an empty
    document would pass the weaker assertion.
    """
    document = office.read(
        _one_page(_text("The /Encrypt key lives in the trailer")),
        "about-encryption.pdf")
    assert "/Encrypt key lives in the trailer" in document.text


def test_a_reference_that_points_at_itself_resolves_rather_than_spinning(
) -> None:
    """chat-NOTE-236's other half, driven at `resolve()` instead of through a
    document. See `test_pdf_reading.test_a_reference_cycle_does_not_hang` for
    why the document-level arm could not fail: `NoTextInPDF` subclasses
    `PDFRefused`, so *"no glyphs"* satisfied it whether or not this bound
    existed.

    Here the cycle is the thing under test. `9 0 obj` is `9 0 R`, and
    `resolve()` must come back with `None` — a `Ref` that survived resolution is
    also a pass-shaped answer, so the type is asserted too.
    """
    pdf = reader.PDF(
        b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
        b"9 0 obj\n9 0 R\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n")
    assert pdf.objects[9] == reader.Ref(9, 0), pdf.objects.get(9)

    seconds, raised, resolved = elapsed(lambda: pdf.resolve(reader.Ref(9, 0)))
    assert raised is None, raised
    assert resolved is None, resolved
    assert seconds < 5.0, seconds


# ══════════════════════════════════════════════════════════════════════════════
# THE OBJECT SCAN
# ══════════════════════════════════════════════════════════════════════════════

def test_two_hundred_thousand_object_headers_stop_at_the_object_ceiling() -> None:
    """`MAX_OBJECTS` bounds the scan, and the scan runs in `__init__` — so it is
    paid before any caller has decided whether to read the file. Measured under
    the deadline; the count is the real assertion because it does not move on a
    faster box."""
    body = bytearray(b"%PDF-1.7\n")
    for i in range(1, 250_001):
        body += b"%d 0 obj\n<< >>\nendobj\n" % i
    body += b"trailer\n<< >>\n%%EOF\n"
    data = bytes(body)
    assert len(data) < 8 * 1024 * 1024

    seconds, raised, _ = elapsed(lambda: reader.PDF(data))
    assert raised is None, raised
    assert seconds < 30.0, seconds
    pdf = reader.PDF(data)
    assert len(pdf.objects) <= reader.MAX_OBJECTS, len(pdf.objects)
