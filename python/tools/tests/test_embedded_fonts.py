"""T76 · a real typeface, carried inside the PDF.

Len picked this off the open list: *"Embed a real typeface."* T75 gave the model
the three PDF base-14 families, which is every typeface a reader is REQUIRED to
have and therefore the only ones available without embedding. This is the other
half.

══ WHAT MAKES THIS ROW DANGEROUS ═══════════════════════════════════════════
**A subtly wrong font object does not raise. It produces a PDF that opens with
no text in it.** So nothing here is asserted against the bytes this package
wrote — every claim goes through `pypdf` or `pdfminer`, which are readers used
only by the gate. Generating and verifying with the same code is not a gate.

══ THE THREE DECISIONS THIS FILE PINS ══════════════════════════════════════
1. **Stdlib at runtime.** `fontTools` and `brotli` are installed and are used in
   `tools/vendor_pdf_fonts.py` to produce the static TTFs. `chat/office/` may
   not import them — it is reached by model-authored input on a public product,
   and its dependency list is a dependency list in that path.
2. **Only the faces a document USES are embedded.** Declaring all four
   unconditionally took an unstyled two-block PDF from 1,630 bytes to 93,994:
   every conversion this product has ever done paying 92 KB for typefaces it
   never asked for.
3. **A face whose digest fails is not used**, and the document falls back to
   base-14. C62 is why the digest is checked at all — `core.autocrlf` rewrote
   the vendored Chart.js on every Windows checkout, and a rewritten TTF is a
   file that will not parse.
"""

from __future__ import annotations

import io
import pathlib
import os
import subprocess
import sys

import pytest

from plexar_tools.office.pdf import _faces
from plexar_tools.office.pdf._write import build

ROOT = pathlib.Path(__file__).resolve().parents[1]
FONTS = ROOT / "src" / "plexar_tools" / "office" / "pdf" / "fonts"

PROSE = [{"type": "heading1", "text": "Quarterly Report"},
         {"type": "paragraph", "text": "Body copy in a vendored typeface."}]


def _fonts_on_page(pdf: bytes) -> dict[str, tuple[str, bool]]:
    """`{resource: (base font, is embedded)}`, read by `pypdf`."""
    from pypdf import PdfReader

    page = PdfReader(io.BytesIO(pdf)).pages[0]
    out = {}
    for key, ref in page["/Resources"]["/Font"].items():
        obj = ref.get_object()
        out[key] = (str(obj.get("/BaseFont")), "/FontDescriptor" in obj)
    return out


# ══════════════════════════════════════════════════════════════════════════════
# 1 · IT IS REALLY EMBEDDED, AND SOMEBODY ELSE'S PARSER SAYS SO
# ══════════════════════════════════════════════════════════════════════════════

def test_a_vendored_face_is_a_REAL_embedded_TrueType() -> None:
    pdf = build(PROSE, {"font": "figtree", "heading_font": "figtree"})
    fonts = _fonts_on_page(pdf)
    embedded = {k: v for k, v in fonts.items() if v[1]}
    assert embedded, ("no font on the page carries a descriptor — nothing was "
                      "embedded", fonts)
    assert any("Figtree" in name for name, _ in embedded.values()), embedded
    # THE FONT PROGRAM ITSELF, not just a descriptor pointing at nothing.
    assert b"/FontFile2" in pdf
    assert b"/Length1" in pdf, (
        "the font stream has no /Length1 — a reader cannot tell where the "
        "program ends and the face silently does not load")


def test_the_TEXT_survives_two_independent_readers() -> None:
    """**The claim that matters.** A malformed embedded font is a page that
    extracts nothing, and it looks exactly like a page that was never written.
    Two parsers, because one agreeing with us is not agreement."""
    from pdfminer.high_level import extract_text
    from pypdf import PdfReader

    pdf = build(PROSE + [{"type": "paragraph", "text": "mono()",
                          "font": "jetbrains"}],
                {"font": "figtree", "heading_font": "figtree"})
    miner = extract_text(io.BytesIO(pdf))
    pypdf_text = PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
    for text in (miner, pypdf_text):
        assert "Quarterly Report" in text, repr(text[:120])
        assert "Body copy in a vendored typeface." in text, repr(text[:120])
        assert "mono()" in text, repr(text[:120])


# ══════════════════════════════════════════════════════════════════════════════
# 2 · ONLY WHAT IS USED — the measurement that changed the design
# ══════════════════════════════════════════════════════════════════════════════

def test_an_unstyled_document_EMBEDS_NOTHING() -> None:
    """**Asserted on the bytes AND on the size.** Every conversion this product
    has ever done takes this path, and the first version of this row put 92 KB
    of typefaces into all of them."""
    pdf = build(PROSE)
    assert b"/FontFile2" not in pdf
    assert len(pdf) < 8_000, (
        "an unstyled PDF grew — a font is being embedded that nobody asked "
        "for", len(pdf))
    assert all(not embedded for _, embedded in _fonts_on_page(pdf).values())


def test_only_the_families_the_document_ASKS_FOR_are_carried() -> None:
    """One family in, one family embedded. Asserted as a count, because
    "some font is embedded" would pass while all four rode along."""
    pdf = build(PROSE, {"font": "figtree", "heading_font": "figtree"})
    embedded = [v for v in _fonts_on_page(pdf).values() if v[1]]
    assert embedded, "nothing embedded"
    assert all("Figtree" in name for name, _ in embedded), embedded
    assert pdf.count(b"/FontFile2") == len(embedded), (
        "a font program was written that no page references", embedded)


# ══════════════════════════════════════════════════════════════════════════════
# 3 · THE METRICS ARE THE FONT'S OWN
# ══════════════════════════════════════════════════════════════════════════════

def test_the_stdlib_parser_AGREES_WITH_fontTools() -> None:
    """**The whole risk of hand-parsing a TTF is a width table that is wrong
    and does not throw**, which yields lines that run off the page. `fontTools`
    is the independent opinion; it is a gate dependency, never a runtime one.

    Every code 32..126 is compared, not a sample: `cmap` format 4 stores
    segments, and a mistake in the `idRangeOffset` branch affects some ranges
    and not others.
    """
    fonttools = pytest.importorskip("fontTools.ttLib")

    for stem in ("figtree-regular", "figtree-bold", "jetbrains-regular"):
        ours = _faces.widths_for(
            "figtree" if stem.startswith("figtree") else "jetbrains",
            stem.endswith("bold"), False)
        assert ours, stem
        theirs = fonttools.TTFont(str(FONTS / f"{stem}.ttf"))
        cmap = theirs.getBestCmap()
        upem = theirs["head"].unitsPerEm
        for code in range(32, 127):
            glyph = cmap.get(code)
            if glyph is None:
                continue
            want = round(theirs["hmtx"][glyph][0] * 1000 / upem)
            assert ours.get(code) == want, (stem, code, chr(code),
                                            ours.get(code), want)


def test_a_monospaced_face_measures_as_monospaced() -> None:
    """A property of the typeface that a wrong `hmtx` walk would destroy: every
    advance identical. Cheap, and it fails loudly."""
    widths = _faces.widths_for("jetbrains", False, False)
    values = {widths[c] for c in range(33, 127) if c in widths}
    assert len(values) == 1, values


# ══════════════════════════════════════════════════════════════════════════════
# 4 · THE PIN, AND WHAT HAPPENS WHEN IT FAILS
# ══════════════════════════════════════════════════════════════════════════════

def test_every_vendored_face_is_pinned_and_matches() -> None:
    import hashlib
    import json

    manifest = json.loads((FONTS / "MANIFEST.json").read_text(encoding="utf-8"))
    files = sorted(p.name for p in FONTS.glob("*.ttf"))
    assert files, "no vendored fonts"
    assert sorted(manifest) == files, (sorted(manifest), files)
    for name, record in manifest.items():
        blob = (FONTS / name).read_bytes()
        assert hashlib.sha256(blob).hexdigest() == record["sha256"], name
        assert record["licence"] == "SIL Open Font License 1.1", name


def test_WATCH_TO_FAIL_a_font_whose_digest_is_wrong_is_NOT_USED(tmp_path) -> None:
    """**The failure this pin exists for, driven rather than argued.**

    C62's shape: the bytes on disk stop being the bytes that were vetted. A
    rewritten TTF is not a warning — it is a file that will not parse — so the
    document must fall back to base-14 rather than referencing a font object
    that was never written.

    Asserted as a PAIR: the tampered face must be REFUSED **and** the document
    must still contain its text. A refusal that produced a blank page would
    satisfy "not used" perfectly.
    """
    from pypdf import PdfReader

    from plexar_tools.office.pdf import _embed

    # **BOTH FACES OF THE FAMILY**, because that is the real scenario: a
    # checkout that rewrites text-mode files hits every one of them. The first
    # version of this arm tampered only with the regular face and then called
    # the legitimately-embedded BOLD heading a failure — the arm was wrong,
    # not the code.
    faces = [FONTS / "figtree-regular.ttf", FONTS / "figtree-bold.ttf"]
    originals = [f.read_bytes() for f in faces]
    try:
        for face, blob in zip(faces, originals):
            face.write_bytes(blob + b"\x00")
        _faces._CACHE.clear()
        for stem in ("figtree-regular", "figtree-bold"):
            assert _embed.verified(stem) is None, (
                "a tampered font passed its digest check", stem)
        pdf = build(PROSE, {"font": "figtree", "heading_font": "figtree"})
        assert b"/FontFile2" not in pdf, "a font nobody vetted was embedded"
        # **AND THE DOCUMENT IS STILL A DOCUMENT.** Asserting only the refusal
        # would pass against a build that produced a blank page, which is the
        # failure this pin exists to prevent.
        text = PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
        assert "Body copy in a vendored typeface." in text, repr(text[:120])
        assert "Quarterly Report" in text, repr(text[:120])
    finally:
        for face, blob in zip(faces, originals):
            face.write_bytes(blob)
        _faces._CACHE.clear()
    # AND THE RESTORE TOOK — R23. The next arm must not inherit a broken tree.
    assert _embed.verified("figtree-regular") is not None
    assert _embed.verified("figtree-bold") is not None


# ══════════════════════════════════════════════════════════════════════════════
# 5 · THE BOUNDARY
# ══════════════════════════════════════════════════════════════════════════════

def test_the_office_package_imports_NO_font_library() -> None:
    """**A grep would miss a transitive import; the interpreter does not** —
    C49's technique, for the same reason. `chat/office/` is reached by
    model-authored input on a public-facing product."""
    probe = (
        "import sys; import plexar_tools.office as o; "
        "from plexar_tools.office.pdf._write import build; "
        "build([{'type':'paragraph','text':'x','font':'figtree'}]); "
        "bad = [m for m in sys.modules if m.split('.')[0] in "
        "('fontTools','brotli','brotlicffi','reportlab','matplotlib')]; "
        "print('LEAKED:' + ','.join(bad) if bad else 'CLEAN')"
    )
    # The child interpreter imports the package from src/, as pytest's `pythonpath` does here.
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    out = subprocess.run([sys.executable, "-c", probe], cwd=ROOT, env=env,
                         capture_output=True, text=True, encoding="utf-8",
                         errors="replace")
    assert out.returncode == 0, out.stderr[-600:]
    assert "CLEAN" in out.stdout, out.stdout
