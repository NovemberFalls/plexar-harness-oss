"""The typefaces a PDF reader is REQUIRED to have, and their exact metrics.

══ WHY THREE FAMILIES AND NOT THIRTY (T75) ══════════════════════════════════
Len: *"it should choose the more prestine fonts… we shouldnt constrain it. the
model should know how good pdf's look, it should have training data on it."*

He is right about the model and there is a hard line underneath the request,
so it is worth stating exactly where it falls.

**The PDF specification names fourteen fonts every conforming reader must
provide** — four Helvetica, four Times, four Courier, Symbol and ZapfDingbats.
A file using them carries no font program at all, opens identically on every
machine, and costs nothing. That is the whole of what this module offers, and
it is a serif, a sans and a monospace in four weights each: the entire
vocabulary of ordinary document typography.

**Anything else — Garamond, Inter, a corporate face — must be EMBEDDED**, which
means vendoring a font file, checking its licence, pinning it by digest, and
writing a `FontFile2` stream with a subset and a widths array. That is C50's
shelf again in every respect, including the part where the model has to be told
the font exists or it will never ask for it. It is a real row and it is not
this one.

══ THE WIDTH TABLES ARE THE WHOLE RISK ══════════════════════════════════════
Wrapping and centring are arithmetic over these numbers. **A wrong table does
not throw — it produces lines that run off the page and centred headings that
sit slightly left**, which reads as sloppiness rather than as a bug. The values
are the published AFM advance widths for codes 32..126, and
`test_office_writer.py` measures the RENDERED character boxes with `pdfminer`
rather than trusting them, which is the only check that can catch a transposed
digit.

**Courier is 600 for every glyph** because it is monospaced; it is written as a
generated list rather than typed out, so it cannot be typed out wrong.
"""

from __future__ import annotations

#: 32..126, per 1000 units.
_HELVETICA = (
    "278 278 355 556 556 889 667 191 333 333 389 584 278 333 278 278 "
    "556 556 556 556 556 556 556 556 556 556 278 278 584 584 584 556 "
    "1015 667 667 722 722 667 611 778 722 278 500 667 556 833 722 778 "
    "667 778 722 667 611 722 667 944 667 667 611 278 278 278 469 556 "
    "333 556 556 500 556 556 278 556 556 222 222 500 222 833 556 556 "
    "556 556 333 500 278 556 500 722 500 500 500 334 260 334 584"
)
_HELVETICA_BOLD = (
    "278 333 474 556 556 889 722 238 333 333 389 584 278 333 278 278 "
    "556 556 556 556 556 556 556 556 556 556 333 333 584 584 584 611 "
    "975 722 722 722 722 667 611 778 722 278 556 722 611 833 722 778 "
    "667 778 722 667 611 722 667 944 667 667 611 333 278 333 584 556 "
    "333 556 611 556 611 556 333 611 611 278 278 556 278 889 611 611 "
    "611 611 389 556 333 611 556 778 556 556 500 389 280 389 584"
)
_TIMES = (
    "250 333 408 500 500 833 778 180 333 333 500 564 250 333 250 278 "
    "500 500 500 500 500 500 500 500 500 500 278 278 564 564 564 444 "
    "921 722 667 667 722 611 556 722 722 333 389 722 611 889 722 722 "
    "556 722 667 556 611 722 722 944 722 722 611 333 278 333 469 500 "
    "333 444 500 444 500 444 333 500 500 278 278 500 278 778 500 500 "
    "500 500 333 389 278 500 500 722 500 500 444 480 200 480 541"
)
_TIMES_BOLD = (
    "250 333 555 500 500 1000 833 278 333 333 500 570 250 333 250 278 "
    "500 500 500 500 500 500 500 500 500 500 333 333 570 570 570 500 "
    "930 722 667 722 722 667 611 778 778 389 500 778 667 944 722 778 "
    "611 778 722 556 667 722 722 1000 722 722 667 333 278 333 581 500 "
    "333 500 556 444 556 444 333 500 556 278 333 556 278 833 556 500 "
    "556 556 444 389 333 556 500 722 500 500 444 394 220 394 520"
)
_TIMES_ITALIC = (
    "250 333 420 500 500 833 778 214 333 333 500 675 250 333 250 278 "
    "500 500 500 500 500 500 500 500 500 500 333 333 675 675 675 500 "
    "920 611 611 667 722 611 611 722 722 333 444 667 556 833 667 722 "
    "611 722 611 500 556 722 611 833 611 556 556 389 278 389 422 500 "
    "333 500 500 444 500 444 278 500 500 278 278 444 278 722 500 500 "
    "500 500 389 389 278 500 444 667 444 444 389 400 275 400 541"
)
_TIMES_BOLD_ITALIC = (
    "250 389 555 500 500 833 778 278 333 333 500 570 250 333 250 278 "
    "500 500 500 500 500 500 500 500 500 500 333 333 570 570 570 500 "
    "832 667 667 667 722 667 667 722 778 389 500 667 611 889 722 722 "
    "611 722 667 556 611 722 667 889 667 611 611 333 278 333 570 500 "
    "333 500 500 444 500 444 333 500 556 278 278 500 278 778 556 500 "
    "500 500 389 389 278 556 444 667 500 444 389 348 220 348 570"
)


def _table(text: str) -> list[int]:
    values = [int(w) for w in text.split()]
    # **95 codes, 32..126.** A table one entry short shifts every glyph after
    # the gap and the error looks like bad kerning rather than like a typo.
    assert len(values) == 95, len(values)
    return values


_COURIER = [600] * 95

#: family -> the four PDF base-14 names, in (plain, bold, italic, bold-italic)
#: order. **Helvetica's oblique faces have the SAME widths as its upright
#: ones**, which is a property of the typeface and not an approximation.
FAMILIES: dict[str, tuple[str, str, str, str]] = {
    "sans": ("Helvetica", "Helvetica-Bold",
             "Helvetica-Oblique", "Helvetica-BoldOblique"),
    "serif": ("Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic"),
    "mono": ("Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique"),
}

#: ══ THE VENDORED FACES (T76) ═══════════════════════════════════════════════
#: Real typefaces, carried inside the file. `figtree` and `jetbrains` are the
#: product's OWN UI faces — SIL OFL 1.1, already in this repo with their notice
#: — instanced to static weights by `tools/vendor_pdf_fonts.py` and pinned by
#: SHA-256.
#:
#: **THERE IS NO ITALIC AND THAT IS THE FONT'S FAULT, NOT A SHORTCUT.** Both
#: variable sources carry ONE axis, `wght`. There is no slanted design to
#: instance, so italic maps to the upright face rather than being faked with a
#: text-matrix skew: a synthetic oblique is a different typeface wearing the
#: name of this one, and the reader would see it in the same document as a real
#: Times-Italic. Ask for italic in a serif and you get a real one.
EMBEDDED: dict[str, tuple[str, str]] = {
    "figtree": ("figtree-regular", "figtree-bold"),
    "jetbrains": ("jetbrains-regular", "jetbrains-bold"),
}

#: (family, bold, italic) -> widths.
METRICS: dict[tuple[str, bool, bool], list[int]] = {
    ("sans", False, False): _table(_HELVETICA),
    ("sans", True, False): _table(_HELVETICA_BOLD),
    ("sans", False, True): _table(_HELVETICA),
    ("sans", True, True): _table(_HELVETICA_BOLD),
    ("serif", False, False): _table(_TIMES),
    ("serif", True, False): _table(_TIMES_BOLD),
    ("serif", False, True): _table(_TIMES_ITALIC),
    ("serif", True, True): _table(_TIMES_BOLD_ITALIC),
    ("mono", False, False): _COURIER,
    ("mono", True, False): _COURIER,
    ("mono", False, True): _COURIER,
    ("mono", True, True): _COURIER,
}

#: The PDF resource name for each face. **All twelve are declared in every
#: file**, at about a hundred bytes each, rather than tracked per document:
#: usage-tracking is a second bookkeeping problem whose failure mode is a
#: `/F7` reference to a font that was never written, which is a page that
#: renders nothing. 1.2 KB is the right price for that not being possible.
def resource(family: str, bold: bool, italic: bool) -> str:
    if family in EMBEDDED:
        # **Two slots, not four.** These faces have no italic (see EMBEDDED),
        # so the italic request resolves to the upright resource rather than
        # to a name no font object was written for — a `/F19` with nothing
        # behind it is a page that renders nothing.
        base = 13 + 2 * list(EMBEDDED).index(family)
        return f"F{base + (1 if bold else 0)}"
    base = {"sans": 1, "serif": 5, "mono": 9}[family]
    return f"F{base + (1 if bold else 0) + (2 if italic else 0)}"


#: What an embedded family falls back to when its font cannot be loaded.
_SUBSTITUTE = {"figtree": "sans", "jetbrains": "mono"}


def effective(family: str, bold: bool) -> str:
    """The family that will ACTUALLY be drawn with (T76).

    ══ THE SUBSTITUTION HAS TO HAPPEN BEFORE MEASUREMENT, NOT AT DRAW TIME ══
    **Found by this row's own watch-to-fail arm.** `resolve()` swapped the
    RESOURCE NAME when a vendored face failed its digest, and left the family
    string alone — so the layout went on measuring with `family="figtree"`,
    `METRICS` had no entry for it, and generating the document raised
    `KeyError` instead of falling back.

    A font that fails its pin must cost the reader a typeface, never the file.
    So the family is substituted once, where it is decided, and both the
    measuring and the drawing see the same answer.
    """
    if family in EMBEDDED and _load(face_stem(family, bold)) is None:
        return _SUBSTITUTE.get(family, "sans")
    return family


def resolve(family: str, bold: bool, italic: bool) -> str:
    """A resource name that is GUARANTEED to have a font object behind it.

    ══ `resource()` NAMES A FACE; THIS ONE PROMISES IT EXISTS (T76) ═════════
    An embedded face is only written into the file if its bytes verified
    against the manifest. `resource("figtree", …)` returns `F13` regardless —
    so a document asking for Figtree on a tree whose font failed its digest
    would reference an object that was never added, and **a `/F13` with
    nothing behind it is a page that renders no text at all.**

    So availability is checked HERE, once, and a face that is not there
    resolves to the base-14 family it stands in for. A document set in
    Helvetica because the vendored font was unreadable is a document; the
    alternative is a blank one.
    """
    if family in EMBEDDED and _load(face_stem(family, bold)) is None:
        family = _SUBSTITUTE.get(family, "sans")
    return resource(family, bold, italic)


def face_stem(family: str, bold: bool) -> str | None:
    """The vendored file behind an embedded face, or `None` for base-14."""
    pair = EMBEDDED.get(family)
    return None if pair is None else pair[1 if bold else 0]


def widths_for(family: str, bold: bool, italic: bool) -> dict[int, int] | None:
    """The advance table for an embedded face, read from the font itself.

    `None` means "not embedded" — the caller uses `METRICS`. **Loaded through
    `verified()`, so a font whose digest does not match is not used at all**
    and the document falls back to a base-14 face rather than being set in
    bytes nobody checked (C50, C62).
    """
    stem = face_stem(family, bold)
    if stem is None:
        return None
    face = _load(stem)
    return None if face is None else face.widths


#: Vendored faces are parsed once per process. **A cache and not a constant**:
#: the digest check is real work and a document may use one face on many pages.
_CACHE: dict[str, object] = {}


def _load(stem: str):
    if stem not in _CACHE:
        from . import _embed
        _CACHE[stem] = _embed.verified(stem)
    return _CACHE[stem]


def embedded_faces() -> list[tuple[str, object]]:
    """`[(resource name, Embedded)]` for every vendored face that verified.

    **A face that fails its digest or its parse is simply absent**, and
    `resource()` still names it — which is why `_write` falls back to the
    base-14 declaration for any name this list does not cover. Missing is a
    document set in Helvetica; wrong is a document with no text in it.
    """
    out = []
    for family in EMBEDDED:
        for bold in (False, True):
            face = _load(face_stem(family, bold))
            if face is not None:
                out.append((resource(family, bold, False), face))
    return out


def declarations() -> list[tuple[str, str]]:
    """`[(resource name, PDF base font name)]` for all twelve base-14 faces."""
    out = []
    for family, names in FAMILIES.items():
        for offset, (bold, italic) in enumerate(
                ((False, False), (True, False), (False, True), (True, True))):
            out.append((resource(family, bold, italic), names[offset]))
    return out


def family_of(value: object, fallback: str = "sans") -> str:
    """A model-authored family name -> one this package can draw.

    **An unrecognised name is the FALLBACK, never an error**, because the model
    will ask for `Garamond` and a refusal there would cost the whole document
    over a font. The names it is offered are in the schema; the ones it invents
    land on the closest family this file has.
    """
    if not isinstance(value, str):
        return fallback
    folded = value.strip().casefold()
    if folded in FAMILIES:
        return folded
    # The words a model reaches for when it means a family. Named typefaces
    # map to the family they belong to rather than being refused: asking for
    # Times and getting Times is the point.
    if folded in ("times", "times new roman", "georgia", "garamond", "cambria",
                  "book antiqua", "palatino", "roman", "serifed"):
        return "serif"
    if folded in ("helvetica", "arial", "inter", "calibri", "roboto",
                  "sans-serif", "sans serif", "grotesk", "gothic"):
        return "sans"
    if folded in ("courier", "courier new", "monospace", "monospaced",
                  "consolas", "menlo", "code"):
        return "mono"
    # ══ THE VENDORED FACES ANSWER TO THEIR OWN NAMES (T76) ═══════════════
    # **And to nothing else.** `inter` and `arial` keep resolving to base-14
    # `sans`, because remapping them would silently restyle every document
    # already asking for a sans — a typography row that changed the default
    # look is a redesign nobody asked for.
    if folded in ("figtree", "plexar", "plexar sans"):
        return "figtree"
    if folded in ("jetbrains", "jetbrains mono", "jetbrainsmono", "plexar mono"):
        return "jetbrains"
    return fallback
