"""T78 — PDF STOPPED BEING THE ONE FORMAT WE COULD WRITE AND NOT READ.

Len, on two PDFs he attached and asked to combine: *"No we should be able to do
this, why cant we and what are we missing? This is basic if you ask me. Should
have this, same for excels."*

**Measured before anything was written, and one of the two was already built:**

    READERS   csv docx md pptx txt xlsx          <- no pdf
    WRITERS   csv docx pdf pptx txt xlsx         <- pdf, write-only
    _extract_text(b, "a.pdf", "application/pdf") -> no text extractor

`.xlsx` has been read since T41, so *"same for excels"* was already true. PDF
was the whole gap — and it was the format most likely to be attached.

══ WHAT THESE ARMS ASSERT, AND WHY THE ROUND TRIP IS NOT ENOUGH ═══════════
Reading a PDF written by this repo's own writer proves the plumbing and nothing
about the world: the writer emits one font, no compression on some streams and
no kerning, so a reader can be badly wrong and still pass. So the fixtures are
built to be HOSTILE in the specific ways a real producer is — glyph-by-glyph
placement, a Flate content stream, a ToUnicode map, a two-byte font — and the
one arm that matters most is the WORD-JOINING one, because its failure is the
kind that still looks like text.
"""

from __future__ import annotations

import zlib

import pytest

from plexar_tools import office
from plexar_tools.office._model import Block, Document
from plexar_tools.office.pdf import NoTextInPDF, PDFRefused
from plexar_tools.office.pdf import _read as reader


# ══════════════════════════════════════════════════════════════════════════════
# FIXTURES — hand-built PDFs, so each arm names the producer behaviour it covers
# ══════════════════════════════════════════════════════════════════════════════

def _pdf(objects: list[bytes], root: int = 1) -> bytes:
    """Assemble numbered objects into a file with a trailer.

    **No xref table on purpose.** The reader finds objects by scanning, which
    is the decision that makes an appended, linearised or damaged file one code
    path — and an arm whose fixture has a perfect xref would never exercise it.
    """
    out = bytearray(b"%PDF-1.7\n")
    for i, body in enumerate(objects, start=1):
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    out += b"trailer\n<< /Root %d 0 R >>\n%%%%EOF\n" % root
    return bytes(out)


def _one_page(content: bytes, font: bytes, compress: bool = True) -> bytes:
    if compress:
        stream = zlib.compress(content)
        head = b"<< /Length %d /Filter /FlateDecode >>" % len(stream)
    else:
        stream = content
        head = b"<< /Length %d >>" % len(stream)
    return _pdf([
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        head + b"\nstream\n" + stream + b"\nendstream",
        font,
    ])


#: A font that DECLARES ITS WIDTHS. `Helvetica` at 1000 units per em with the
#: real advances for the letters used below; the reader has no font file and
#: must take the producer's numbers.
WIDTHS = b"[ 278 0 0 0 0 0 0 0 0 0 0 0 278 333 278 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 667 667 722 722 667 611 778 722 278 500 667 556 833 722 778 667 778 722 667 611 722 667 944 667 667 611 0 0 0 0 0 0 556 556 500 556 556 278 556 556 222 222 500 222 833 556 556 556 556 333 500 278 556 500 722 500 500 500 ]"
HELVETICA = (b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
             b"/FirstChar 32 /Widths " + WIDTHS + b" >>")


def _glyph_by_glyph(words: str, size: int = 12) -> bytes:
    """The producer behaviour that broke the first version of this reader.

    Every glyph placed with its own `Td`, which is what a typesetter that
    tracks or kerns emits — and it is why the reader has to know how far a
    string ADVANCES rather than where the next fragment starts.
    """
    # **Each glyph is placed at ITS OWN advance**, read from the same
    # `/Widths` the font declares. A fixture that walks at a constant pitch
    # while declaring real widths is a producer that does not exist, and a
    # reader tuned to it would be tuned to nothing.
    advances = [int(w) for w in WIDTHS.strip(b"[] ").split()]
    out = [b"BT", b"/F1 %d Tf" % size]
    x = 72.0
    for char in words:
        width = advances[ord(char) - 32] / 1000.0 * size
        if char == " ":
            x += width + 2.0  # a real word gap on top of the space glyph
            continue
        out.append(b"1 0 0 1 %.2f 700 Tm (%s) Tj"
                   % (x, char.encode("latin-1")))
        x += width
    out.append(b"ET")
    return b"\n".join(out)


# ══════════════════════════════════════════════════════════════════════════════
# THE GAP ITSELF
# ══════════════════════════════════════════════════════════════════════════════

def test_pdf_is_a_format_this_product_can_read() -> None:
    """The table entry, asserted with the one that was already true.

    **Both halves, because Len named both.** An arm asserting only `pdf` would
    pass just as well on a build where somebody had removed `xlsx` — and
    *"same for excels"* was a claim about this product that has to stay true.
    """
    assert "pdf" in office.READERS, "the format we could write and not read"
    assert "xlsx" in office.READERS, "Excel was never the gap; keep it that way"
    assert "pdf" in office.WRITERS


def test_the_words_are_words_and_not_spaced_letters() -> None:
    """**THE ARM THAT MATTERS, because its failure still looks like text.**

    Measured on a real PDF against the first version of this reader:

        L e o n a r d  B o o r d :  Y o u ' v e  B e e n  H e a r d

    Every glyph correct, every word destroyed — and a model handed that will
    answer from it rather than refuse it, which is worse than getting nothing.
    The cause was asking whether one fragment STARTS past where the previous
    one starts, which is true of every pair of adjacent letters ever set.
    """
    document = office.read(
        _one_page(_glyph_by_glyph("Revenue rose twelve percent"), HELVETICA),
        "kerned.pdf")
    assert "Revenue rose twelve percent" in document.text, document.text
    assert "R e v e n u e" not in document.text


def test_watch_to_fail_without_the_advance_the_letters_come_apart() -> None:
    """R23 — the defect re-created in the reader's own arithmetic.

    A font whose `/Widths` are all zero makes every advance zero, which is
    exactly the pre-fix state: the pen never moves, so every fragment appears
    to begin where the last one did. **Asserted as a DIFFERENCE from the real
    output**, so a break that changed nothing cannot pass as "the layout is
    fine" — the failure this repo has caught in its own harnesses before.
    """
    zeroed = (b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
              b"/FirstChar 32 /Widths [" + b" 0" * 95 + b"] >>")
    document = office.read(
        _one_page(_glyph_by_glyph("Revenue rose twelve percent"), zeroed),
        "kerned.pdf")
    assert "Revenue rose twelve percent" not in document.text, (
        "the fixture no longer reproduces the defect, so the arm above is "
        "not measuring the advance at all")
    assert "R e v e n u e" in document.text


def test_a_scan_is_refused_and_never_returned_as_an_empty_document() -> None:
    """**The single most dangerous state this reader can be in.**

    A photographed page has zero glyphs. An empty `Document` is
    indistinguishable from a document with nothing in it, so the model would
    summarise a blank and the user would be told their file was empty. The
    refusal names the reason and the reason is actionable.
    """
    page = _one_page(b"q 200 0 0 100 72 600 cm /Im0 Do Q", HELVETICA)
    with pytest.raises(NoTextInPDF) as caught:
        office.read(page, "scan.pdf")
    assert "scan" in str(caught.value)


def test_an_encrypted_pdf_is_refused_rather_than_decoded_to_mojibake() -> None:
    """Garbled bytes presented as the document's words is the worse failure.

    A model handed them will quote them; a model handed a refusal will say the
    file is protected, which is what the user needs to hear.

    ══ THE FIXTURE WAS A SHAPE NO PRODUCER EMITS, SO IT COULD NOT FAIL (T84) ══
    It used to declare object 9 as `<< /Encrypt 1 /V 2 >>` — a key named
    `Encrypt` INSIDE an object body — which is what the pre-T84 loop scanned for
    and which nothing in the world writes. **So this arm was green for five
    months while every real password-protected PDF was reported as a scan
    (chat-R-235).** Object 9 is now a standard security handler, which holds no
    such key, and the ONLY thing that can refuse this file is `PDF._trailers()`
    reading `/Encrypt 9 0 R` out of the trailer. Watched to fail in
    `tests/test_pdf_hostile.py`.
    """
    body = _one_page(b"BT /F1 12 Tf 72 700 Td (hello) Tj ET", HELVETICA)
    body = body.replace(b"trailer\n<<", b"trailer\n<< /Encrypt 9 0 R")
    body = body.replace(
        b"%PDF-1.7\n",
        b"%PDF-1.7\n9 0 obj\n<< /Filter /Standard /V 4 /R 4 /Length 128 "
        b"/P -1340 /O <0102030405060708090A0B0C0D0E0F10> "
        b"/U <1112131415161718191A1B1C1D1E1F20> >>\nendobj\n")
    assert b"/Encrypt" not in body.split(b"trailer")[0], (
        "the refusal must come from the TRAILER — a fixture that also carries "
        "the key in an object body cannot tell the two readers apart")
    with pytest.raises(PDFRefused) as caught:
        office.read(body, "locked.pdf")
    assert "password" in str(caught.value) or "encrypt" in str(caught.value)


def test_a_pdf_converts_without_being_retyped() -> None:
    """T41's whole point, now reachable from the format it was never reachable
    from. `convert` reports `reformatted` honestly for a real change of kind
    and refuses to pretend for a no-op."""
    source = _one_page(
        b"BT /F1 12 Tf 72 700 Td (Quarterly revenue rose twelve percent) Tj ET",
        HELVETICA)
    data, kind, reformatted = office.convert(source, "q.pdf", "docx")
    assert reformatted and kind == "docx"
    assert "Quarterly revenue rose twelve percent" in office.read(
        data, "q.docx").text
    assert office.convert(source, "q.pdf", "pdf")[2] is False, (
        "same format in, same format out is the original file — a round trip "
        "hands back a lossy near-copy and calls it the same document")


# ══════════════════════════════════════════════════════════════════════════════
# THE BYTES ARE A STRANGER'S (R42)
# ══════════════════════════════════════════════════════════════════════════════

def test_a_reference_cycle_does_not_hang() -> None:
    """A PDF may point an object at itself. Resolution is depth-bounded, so
    this returns rather than spinning — a hang on an uploaded file is a denial
    of service with a friendly extension.

    ══ AND THIS ARM COULD NOT FAIL AS WRITTEN (chat-NOTE-236, T84) ════════════
    `NoTextInPDF` SUBCLASSES `PDFRefused`, and this fixture has no content
    stream at all — so `pytest.raises(PDFRefused)` was satisfied by *"there are
    no glyphs in this"* whether or not `resolve()` carried a depth bound. **A
    bound that was deleted would have left this arm green.** So the REASON is
    asserted: the honest answer for a document with no content is the scan
    sentence, and the cycle itself is driven at `resolve()` directly by
    `test_pdf_hostile.test_a_reference_that_points_at_itself_resolves_rather_
    than_spinning`, where a hang is the only way to fail.
    """
    body = _pdf([
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [2 0 R] /Count 1 >>",
    ])
    with pytest.raises(PDFRefused) as caught:
        office.read(body, "cycle.pdf")
    assert isinstance(caught.value, NoTextInPDF), (
        "the refusal is about the absence of glyphs, and naming it is what "
        "keeps this arm from standing in for the depth bound it never tested")
    assert "scan" in str(caught.value)


def test_a_stream_that_inflates_forever_is_refused() -> None:
    """`zlib` is given a ceiling rather than being asked to finish."""
    bomb = zlib.compress(b"\0" * (80 * 1024 * 1024))
    assert len(reader._inflate(bomb)) <= reader.MAX_STREAM_BYTES


def test_nothing_in_the_reader_executes_anything() -> None:
    """The `store/` module's own rule, applied to the parser this row added.

    A PDF may carry JavaScript, launch actions and embedded files. **None of
    them is filtered out — none of them is ever looked at**, which is the
    difference between a rule and a mechanism.
    """
    import pathlib

    source = pathlib.Path(reader.__file__).read_text(encoding="utf-8")
    for forbidden in ("exec(", "eval(", "subprocess", "pickle",
                      "__import__", "os.system"):
        assert forbidden not in source, forbidden
