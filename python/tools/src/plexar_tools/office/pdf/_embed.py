"""A vendored TrueType, read with `struct` and embedded in the PDF (T76).

Len: *"it should choose the more prestine fonts."* T75 gave the model the three
PDF base-14 families, which is every typeface a reader is REQUIRED to have and
therefore the only ones available without embedding. This is the other half:
real typefaces, carried inside the file.

══ STDLIB ONLY, AND THAT IS THE WHOLE REASON THIS FILE EXISTS ═══════════════
`fontTools` is installed and is used in `tools/vendor_pdf_fonts.py` to produce
the static TTFs. **It is never imported here.** `chat/office/` is reached by
model-authored input on a public-facing product, so its dependency list is a
dependency list in that path — the same argument that keeps `reportlab` out of
the writer beside it. The vendoring tool is a build step whose output is
committed and digest-pinned; this reads bytes.

══ THE WHOLE FONT IS EMBEDDED. THERE IS NO SUBSETTER. ═══════════════════════
A subsetter would cut each face to the glyphs a given document uses, and it is
the single largest source of malformed-font bugs: `loca` and `glyf` must be
rebuilt in step, composite glyphs drag in components, and **a font object that
is subtly wrong produces a PDF that opens with no text rather than an error.**

The faces are 24 KB and 57 KB against documents that are routinely 800 KB of
photographs. **Paying ~80 KB to make an entire class of defect impossible is
the right trade, and it is a trade rather than an oversight.**

══ WHAT IS READ, AND WHY EACH ══════════════════════════════════════════════
    head   unitsPerEm — every metric below is in these units and must be
           scaled to PDF's 1000; indexToLocFormat is NOT needed because
           nothing here touches `glyf`
    hhea   numberOfHMetrics, so `hmtx` can be walked correctly
    hmtx   the advance width of each glyph — the numbers wrapping depends on
    cmap   character -> glyph, so a character's width can be found at all
    OS/2   sCapHeight and the weight, for the descriptor
    post   italicAngle, for the descriptor

**`cmap` format 4 only.** It is what every Latin subset in the world uses;
format 12 is for fonts beyond the BMP, which WinAnsi cannot address anyway. An
unsupported table returns `None` and the caller keeps the base-14 face — a
missing font is a document that still reads, and a guessed one is not.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import struct
from dataclasses import dataclass

HERE = pathlib.Path(__file__).resolve().parent / "fonts"

#: The PDF widths array is indexed 32..255 and is in 1000ths of an em.
FIRST_CHAR, LAST_CHAR = 32, 255


@dataclass(frozen=True)
class Embedded:
    """One face, ready to be written into a PDF."""

    name: str
    postscript: str
    body: bytes
    #: `char code -> advance in 1000ths of an em`, for 32..255.
    widths: dict[int, int]
    ascent: int
    descent: int
    cap_height: int
    italic_angle: float
    bbox: tuple[int, int, int, int]
    #: **A flags word the reader uses to substitute if the file is damaged.**
    #: Bit 3 (value 4) is "symbolic"; a Latin text face must instead set bit 6
    #: (value 32, non-symbolic) or some readers ignore the encoding entirely
    #: and render the font's own glyph order — which looks like mojibake.
    flags: int = 32

    def width(self, code: int, fallback: int = 500) -> int:
        return self.widths.get(code, fallback)


def _tables(blob: bytes) -> dict[str, tuple[int, int]]:
    if len(blob) < 12:
        return {}
    count = struct.unpack(">H", blob[4:6])[0]
    out: dict[str, tuple[int, int]] = {}
    for index in range(count):
        base = 12 + index * 16
        if base + 16 > len(blob):
            break
        tag = blob[base:base + 4].decode("latin-1")
        offset, length = struct.unpack(">II", blob[base + 8:base + 16])
        out[tag] = (offset, length)
    return out


def _cmap(blob: bytes, start: int) -> dict[int, int]:
    """`cmap` -> `{unicode: glyph id}`. Format 4 subtables only."""
    if start + 4 > len(blob):
        return {}
    count = struct.unpack(">H", blob[start + 2:start + 4])[0]
    chosen = None
    for index in range(count):
        base = start + 4 + index * 8
        if base + 8 > len(blob):
            break
        platform, encoding, offset = struct.unpack(">HHI", blob[base:base + 8])
        # **(3,1) Windows BMP is the one to prefer**, then (3,0) symbol, then
        # (0,x) Unicode. Taking the first subtable would sometimes pick a Mac
        # Roman table whose codes are NOT Unicode.
        rank = {(3, 1): 0, (0, 3): 1, (0, 4): 1, (0, 6): 1, (3, 0): 2}.get(
            (platform, encoding), 3)
        if chosen is None or rank < chosen[0]:
            chosen = (rank, start + offset)
    if chosen is None:
        return {}
    table = chosen[1]
    if table + 14 > len(blob) or struct.unpack(">H", blob[table:table + 2])[0] != 4:
        return {}
    seg_x2 = struct.unpack(">H", blob[table + 6:table + 8])[0]
    segs = seg_x2 // 2
    ends = struct.unpack(f">{segs}H", blob[table + 14:table + 14 + seg_x2])
    starts_at = table + 14 + seg_x2 + 2
    starts = struct.unpack(f">{segs}H", blob[starts_at:starts_at + seg_x2])
    deltas_at = starts_at + seg_x2
    deltas = struct.unpack(f">{segs}h", blob[deltas_at:deltas_at + seg_x2])
    ranges_at = deltas_at + seg_x2
    ranges = struct.unpack(f">{segs}H", blob[ranges_at:ranges_at + seg_x2])

    out: dict[int, int] = {}
    for seg in range(segs):
        for code in range(starts[seg], min(ends[seg], 0xFFFF) + 1):
            if ranges[seg] == 0:
                glyph = (code + deltas[seg]) & 0xFFFF
            else:
                # **The offset is measured from the SLOT, not from the table.**
                # This is the single most misread field in the format, and
                # getting it wrong yields a plausible-looking wrong glyph.
                at = ranges_at + seg * 2 + ranges[seg] + (code - starts[seg]) * 2
                if at + 2 > len(blob):
                    continue
                glyph = struct.unpack(">H", blob[at:at + 2])[0]
                if glyph:
                    glyph = (glyph + deltas[seg]) & 0xFFFF
            if glyph:
                out[code] = glyph
    return out


def read(path: pathlib.Path) -> Embedded | None:
    """A TTF on disk -> everything the writer needs, or `None`.

    **`None` is "this file cannot be embedded" and the caller keeps base-14.**
    Never a partial face: a widths array that silently fell back to a constant
    produces text that overflows its column, which reads as a layout bug and is
    a font bug.
    """
    try:
        blob = path.read_bytes()
    except OSError:
        return None
    tables = _tables(blob)
    if not {"head", "hhea", "hmtx", "cmap", "maxp"} <= set(tables):
        return None
    try:
        head = tables["head"][0]
        upem = struct.unpack(">H", blob[head + 18:head + 20])[0] or 1000
        xmin, ymin, xmax, ymax = struct.unpack(">hhhh", blob[head + 36:head + 44])

        hhea = tables["hhea"][0]
        ascent, descent = struct.unpack(">hh", blob[hhea + 4:hhea + 8])
        pairs = struct.unpack(">H", blob[hhea + 34:hhea + 36])[0]

        hmtx = tables["hmtx"][0]
        advances: list[int] = []
        for index in range(pairs):
            at = hmtx + index * 4
            advances.append(struct.unpack(">H", blob[at:at + 2])[0])

        glyphs = _cmap(blob, tables["cmap"][0])
        if not glyphs:
            return None

        scale = 1000.0 / upem

        def scaled(value: float) -> int:
            return int(round(value * scale))

        widths: dict[int, int] = {}
        for code in range(FIRST_CHAR, LAST_CHAR + 1):
            glyph = glyphs.get(code)
            if glyph is None:
                continue
            # **A glyph past `numberOfHMetrics` uses the LAST advance.** That
            # is the format's own compression for monospaced tails, and
            # indexing past the array would be an exception on a valid font.
            raw = advances[glyph] if glyph < len(advances) else (
                advances[-1] if advances else 0)
            widths[code] = scaled(raw)

        italic = 0.0
        if "post" in tables:
            post = tables["post"][0]
            fixed = struct.unpack(">i", blob[post + 4:post + 8])[0]
            italic = fixed / 65536.0
        cap = scaled(ascent * 0.72)
        if "OS/2" in tables:
            os2, length = tables["OS/2"]
            version = struct.unpack(">H", blob[os2:os2 + 2])[0]
            if version >= 2 and length >= 90:
                value = struct.unpack(">h", blob[os2 + 88:os2 + 90])[0]
                if value:
                    cap = scaled(value)
    except (struct.error, IndexError, ValueError, ZeroDivisionError):
        return None

    return Embedded(
        name=path.stem,
        postscript=path.stem.replace("-", ""),
        body=blob,
        widths=widths,
        ascent=scaled(ascent),
        descent=scaled(descent),
        cap_height=cap,
        italic_angle=round(italic, 2),
        bbox=(scaled(xmin), scaled(ymin), scaled(xmax), scaled(ymax)),
    )


def manifest() -> dict:
    try:
        return json.loads((HERE / "MANIFEST.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def verified(stem: str) -> Embedded | None:
    """Load a vendored face and **check its digest before using it** (C50).

    C62 is why: `core.autocrlf` rewrote the vendored Chart.js on every Windows
    checkout, so the served bytes were not the vetted bytes and the pin was the
    only thing that noticed. A font is worse — a rewritten TTF is not a
    warning, it is a file that will not parse.

    A digest mismatch returns `None`, so the document is set in a base-14 face
    rather than in a font nobody has checked.
    """
    path = HERE / f"{stem}.ttf"
    record = manifest().get(f"{stem}.ttf")
    if record is None or not path.exists():
        return None
    if hashlib.sha256(path.read_bytes()).hexdigest() != record.get("sha256"):
        return None
    face = read(path)
    if face is None:
        return None
    return Embedded(**{**face.__dict__,
                       "postscript": record.get("postscript_name") or face.postscript})
