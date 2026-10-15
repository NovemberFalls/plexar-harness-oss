"""A real `.pdf`, written by hand with the standard library.

══ WHY THIS EXISTS, AND IT IS THE SECOND USER TO ASK ═══════════════════════
Michael, on his tuna-thawing SOP: *"Please help me turn this into a PDF that
outlines the procedure better."* What he expected — and had got elsewhere — was
a 4-page PDF exported by Word. What Plexar gave him before T40 was an HTML
artifact and instructions to *"copy the entire code above, paste it into a text
editor… File > Print > Save as PDF."*

**And T40 made it worse before it made it better.** With `create_document`
shipped, the model called it with `kind="docx"`, got back an accurate
*"created Tuna_Poke_Thawing_Procedure.docx"*, and then told him **"The PDF
document is ready and attached."** It was not a PDF. `_attach_generated` guards
the case where NO file exists; it could not catch a file that exists and is the
WRONG KIND, because the lie was in the prose and not in the tool result.

The durable fix for that is not another guard. **It is writing the format he
asked for**, so the honest answer and the useful one are the same file.

══ WHY IT IS HAND-WRITTEN WHEN `reportlab` IS INSTALLED ════════════════════
`reportlab` is present in this environment and is NOT used. `chat/office/` is
stdlib-only by construction — it is reached by model-authored input on a
public-facing product, and every dependency there is a dependency in that path.
The third-party PDF libraries in this repo are READERS, used only by the gate.
**Generating with stdlib and verifying with somebody else's parser is the
arrangement; generating and verifying with the same library is not a gate.**

══ NO FONT IS EMBEDDED, DELIBERATELY ═══════════════════════════════════════
Helvetica is one of the 14 standard fonts every PDF reader must provide, so the
file needs no font program and no CID machinery. The cost is that text is
WinAnsi (Latin-1): characters outside it are transliterated where there is an
obvious equivalent and dropped otherwise, which is stated rather than silently
producing the wrong glyph. Embedding a Unicode font is a real row — it needs a
font file we would have to vendor, licence and pin, exactly as C50 did for
Chart.js.
"""

from __future__ import annotations

import io
import zlib

from .._chart import BadChart, fraction, nice_axis, parse_chart, tick_labels
from .._colour import readable_on_white
from ._faces import (METRICS, declarations, effective, embedded_faces,
                     family_of, resolve, widths_for)
from .._model import Document, sniff_image
from .._runs import runs
from .._xml import clean

#: US Letter in points, and a one-inch margin. Portrait, because every document
#: this writes is prose.
PAGE_W, PAGE_H = 612.0, 792.0
MARGIN = 72.0
TEXT_W = PAGE_W - 2 * MARGIN

#: Advance widths per 1000 units for the two faces used, from the standard AFM
#: metrics. **Wrapping is arithmetic, not guesswork** — a wrong table produces
#: lines that run off the page, which is why the gate measures the rendered
#: character boxes with `pdfminer` rather than trusting these numbers.
_HELV = (
    "278 278 355 556 556 889 667 191 333 333 389 584 278 333 278 278 "
    "556 556 556 556 556 556 556 556 556 556 278 278 584 584 584 556 "
    "1015 667 667 722 722 667 611 778 722 278 500 667 556 833 722 778 "
    "667 778 722 667 611 722 667 944 667 667 611 278 278 278 469 556 "
    "333 556 556 500 556 556 278 556 556 222 222 500 222 833 556 556 "
    "556 556 333 500 278 556 500 722 500 500 500 334 260 334 584"
)
_HELV_BOLD = (
    "278 333 474 556 556 889 722 238 333 333 389 584 278 333 278 278 "
    "556 556 556 556 556 556 556 556 556 556 333 333 584 584 584 611 "
    "975 722 722 722 722 667 611 778 722 278 556 722 611 833 722 778 "
    "667 778 722 667 611 722 667 944 667 667 611 333 278 333 584 556 "
    "333 556 611 556 611 556 333 611 611 278 278 556 278 889 611 611 "
    "611 611 389 556 333 611 556 778 556 556 500 389 280 389 584"
)
WIDTHS = {False: [int(w) for w in _HELV.split()],
          True: [int(w) for w in _HELV_BOLD.split()]}
_FALLBACK = 556

#: The codes an embedded face's `/Widths` array covers. **32..255, not
#: 32..126**: the text is WinAnsi, so an accented character is an ordinary byte
#: in that range and a shorter array leaves the reader guessing its width (T76).
FIRST_CHAR, LAST_CHAR = 32, 255

#: Characters WinAnsi cannot carry that have an obvious ASCII equivalent. The
#: model writes these constantly — em dashes and curly quotes are its default
#: punctuation — and dropping them silently would eat the punctuation out of
#: every sentence.
_TRANSLIT = {
    "—": "-", "–": "-", "‘": "'", "’": "'",
    "“": '"', "”": '"', "…": "...", "•": "-",
    " ": " ", "‑": "-", "′": "'", "″": '"',
}


def latin(text: str) -> str:
    """Text -> something WinAnsi can encode. **Lossy, and only where it must be.**"""
    out = []
    for ch in clean(text):
        if ch in _TRANSLIT:
            out.append(_TRANSLIT[ch])
            continue
        try:
            ch.encode("cp1252")
        except UnicodeEncodeError:
            continue
        out.append(ch)
    return "".join(out)


def width_of(text: str, size: float, *, bold: bool = False,
             italic: bool = False, family: str = "sans") -> float:
    # ══ AN EMBEDDED FACE CARRIES ITS OWN METRICS (T76) ══════════════════════
    # A vendored font's widths come out of its own `hmtx`, not out of a table
    # in this file — there is nothing to transcribe and therefore nothing to
    # transcribe wrong. `None` means base-14, which keeps the AFM tables.
    embedded = widths_for(family, bool(bold), bool(italic))
    if embedded is not None:
        return sum(embedded.get(ord(ch), _FALLBACK)
                   for ch in text) * size / 1000.0
    table = METRICS[(family, bool(bold), bool(italic))]
    total = 0
    for ch in text:
        code = ord(ch)
        total += table[code - 32] if 32 <= code <= 126 else _FALLBACK
    return total * size / 1000.0


def wrap(text: str, size: float, limit: float, *, bold: bool = False,
         italic: bool = False, family: str = "sans") -> list[str]:
    """Greedy word wrap. **A word longer than the line is broken**, because the
    alternative is a line that runs off the page and a reader who cannot see it."""
    # ══ THE MEASURE MUST BE THE FACE THAT WILL BE DRAWN (T75) ═══════════════
    # Times is narrower than Helvetica at the same size and Courier is wider.
    # Measuring every line with the sans table gives short lines in a serif
    # document and lines running off the page in a monospaced one — and neither
    # throws, so the only symptom is a page that looks badly set. **One
    # closure**, so the four call sites below cannot disagree about which face
    # they are measuring.
    def measure(chunk: str) -> float:
        return width_of(chunk, size, bold=bold, italic=italic, family=family)

    lines: list[str] = []
    for hard in text.split("\n"):
        current = ""
        for word in hard.split(" "):
            candidate = f"{current} {word}".strip()
            if current and measure(candidate) > limit:
                lines.append(current)
                current = word
            else:
                current = candidate
            while measure(current) > limit and len(current) > 1:
                cut = len(current)
                while cut > 1 and measure(current[:cut]) > limit:
                    cut -= 1
                lines.append(current[:cut])
                current = current[cut:]
        lines.append(current)
    return lines or [""]


def _pdf_string(text: str) -> str:
    """A PDF literal string. `\\`, `(` and `)` are the three that matter — an
    unescaped `)` ends the string early and the rest of the sentence becomes
    operators, which is a corrupt page rather than a stray character."""
    return (text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)"))


def _rgb_of(data: bytes):
    """PNG bytes -> `(raw RGB, width, height)`, or `None`.

    ══ WHY A DECODER LIVES HERE AT ALL ═════════════════════════════════════
    PDF can carry a JPEG verbatim (`DCTDecode`) and **has no PNG filter**. A
    PNG must therefore be decompressed, un-filtered and re-deflated as raw
    samples. Michael's document is one PNG and seven JPEGs, so skipping PNG
    would silently drop exactly one photograph out of eight — the shape of
    defect this whole row exists to end.

    **Only the common case is handled**: 8-bit non-interlaced greyscale, RGB or
    RGBA. Anything else — 16-bit, palette, interlaced — returns `None` and the
    picture is left out rather than painted as garbage. Returning None is a
    decision the caller can report; returning wrong pixels is not.
    """
    import zlib

    if sniff_image(data) != "png":
        return None
    pos = 8
    width = height = depth = colour = interlace = 0
    idat = bytearray()
    while pos + 8 <= len(data):
        length = int.from_bytes(data[pos:pos + 4], "big")
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length          # 4 len + 4 tag + body + 4 crc
        if tag == b"IHDR" and len(body) >= 13:
            width = int.from_bytes(body[0:4], "big")
            height = int.from_bytes(body[4:8], "big")
            depth, colour, interlace = body[8], body[9], body[12]
        elif tag == b"IDAT":
            idat += body
        elif tag == b"IEND":
            break
    channels = {0: 1, 2: 3, 6: 4}.get(colour)
    if not (width and height and channels) or depth != 8 or interlace:
        return None
    try:
        raw = zlib.decompress(bytes(idat))
    except zlib.error:
        return None

    stride = width * channels
    if len(raw) < (stride + 1) * height:
        return None
    out = bytearray(width * height * 3)
    previous = bytearray(stride)
    at = 0
    for row in range(height):
        filter_type = raw[at]
        line = bytearray(raw[at + 1:at + 1 + stride])
        at += 1 + stride
        # THE FIVE PNG FILTERS. Each references the pixel to the LEFT by a
        # whole channel-count, not by one byte — getting that wrong produces a
        # picture that is recognisably the right image and colour-smeared.
        if filter_type == 1:
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 0xFF
        elif filter_type == 2:
            for i in range(stride):
                line[i] = (line[i] + previous[i]) & 0xFF
        elif filter_type == 3:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((left + previous[i]) >> 1)) & 0xFF
        elif filter_type == 4:
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                b = previous[i]
                c = previous[i - channels] if i >= channels else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pred) & 0xFF
        elif filter_type != 0:
            return None
        previous = line

        base = row * width * 3
        if channels == 3:
            out[base:base + stride] = line
        elif channels == 1:
            for x in range(width):
                out[base + x * 3:base + x * 3 + 3] = bytes((line[x],)) * 3
        else:      # RGBA — alpha is DROPPED onto white rather than ignored,
                   # or a transparent PNG prints as a black rectangle.
            for x in range(width):
                r, g, b, a = line[x * 4:x * 4 + 4]
                if a == 255:
                    out[base + x * 3:base + x * 3 + 3] = bytes((r, g, b))
                else:
                    f = a / 255.0
                    out[base + x * 3:base + x * 3 + 3] = bytes((
                        int(r * f + 255 * (1 - f)),
                        int(g * f + 255 * (1 - f)),
                        int(b * f + 255 * (1 - f))))
    return bytes(out), width, height


class _Page:
    #: How much of the page the running header and footer have taken. **Class
    #: attributes so a `_Page()` built anywhere -- and there are three such
    #: sites -- cannot be constructed without them.** They are set once per
    #: document by `_layout`; a document with no furniture leaves them 0.0 and
    #: is laid out exactly as it was before C77.
    head_band = 0.0
    foot_band = 0.0

    def __init__(self) -> None:
        self.ops: list[str] = []
        #: `(xobject_name, image)` placed on this page. The image DATA becomes
        #: its own PDF object; the page only names it.
        self.images: list[tuple[str, object]] = []
        self.y = PAGE_H - MARGIN - self.head_band

    def room(self, height: float) -> bool:
        return self.y - height >= MARGIN + self.foot_band

    @property
    def top(self) -> float:
        """Where the text column starts. **The furniture is not part of it.**"""
        return PAGE_H - MARGIN - self.head_band

    @property
    def bottom(self) -> float:
        return MARGIN + self.foot_band


#: ══ ONE ACCENT, AND IT IS A DECISION RATHER THAN A DEFAULT (T51) ═══════════
#: Len, comparing our output with another product's: *"why does ours suck?"*
#: Part of the answer was measurable and dull — **every glyph we emitted was
#: pure black and every rule was absent**, so the page had no hierarchy beyond
#: size. A single restrained accent on the headings and the rules is most of
#: the visible difference, and it costs two PDF operators.
#:
#: **ONE colour, not a palette.** A converter cannot know a company's brand, so
#: inventing three is how a document ends up looking like a template somebody
#: forgot to fill in. This is a deep slate — legible on a monochrome printer,
#: which a kitchen SOP will actually meet.
ACCENT = (0.11, 0.20, 0.31)
RULE = (0.78, 0.80, 0.83)
INK = (0.10, 0.10, 0.11)


def _rgb(colour: tuple[float, float, float]) -> str:
    return f"{colour[0]:.3f} {colour[1]:.3f} {colour[2]:.3f}"


def _rule(page: _Page, y: float, *, width: float = TEXT_W,
          thickness: float = 0.7,
          colour: tuple[float, float, float] = RULE) -> None:
    """A hairline across the column. **`re f` — a filled rectangle, not a
    stroke** — because a stroked line's width is affected by the CTM and a
    filled box of known height is the same on every reader."""
    page.ops.append(
        f"q {_rgb(colour)} rg {MARGIN:.1f} {y:.1f} {width:.1f} "
        f"{thickness:.2f} re f Q")


#: A callout's ink and its wash, per tone. **The wash is a tint of the ink**
#: rather than an independently chosen grey, so a band reads as one object and
#: cannot end up with a colour nobody picked.
#:
#: Printed in a kitchen, on a monochrome laser, these become four greys — so
#: the MARK (`!`, `*`) carries the tone as well as the colour does. A callout
#: that only says "warning" in red says nothing on the printer this document
#: actually meets.
CALLOUT_INK: dict[str, tuple[float, float, float]] = {
    "note": (0.11, 0.20, 0.31),
    "warning": (0.69, 0.29, 0.06),
    "caution": (0.69, 0.29, 0.06),
    "success": (0.10, 0.40, 0.24),
}
CALLOUT_MARK: dict[str, str] = {
    "note": "i", "warning": "!", "caution": "!", "success": "*"}

#: The bar down the left edge, the air inside the band, and the air around it.
CALLOUT_BAR = 3.0
CALLOUT_PAD = 8.0


#: The running header and footer (C77).
#:
#: ══ WHY THIS IS NOT JUST TWO MORE BLOCKS ═════════════════════════════════════
#: Len's target SOP puts a logo and an `SOP` tab at the top of every page, and a
#: confidentiality line, a revision date and *"Página 1 de 3"* at the bottom of
#: every page. Ours had a single faint centred `Page N of M` and nothing else,
#: because **`_model.py` says in as many words that a document "does NOT carry
#: headers and footers"** and `_Page` ran from `PAGE_H - MARGIN` to `MARGIN`
#: with no band reserved at either end.
#:
#: Three properties make this page FURNITURE rather than content:
#:   * it repeats on every page, including ones produced by a break the author
#:     never asked for;
#:   * it is outside the text column, so a paragraph cannot collide with it;
#:   * `of M` cannot be known until pagination is finished.
#: The last one is why this is painted AFTER `_layout` has produced every page
#: rather than as each page opens. A running footer that says "of 3" on a
#: document that turned out to be 4 pages long is the kind of confident wrong
#: number this repo has a rule about.
HEAD_SIZE = 8.5
FOOT_SIZE = 8.0
HEAD_GAP = 12.0
FOOT_GAP = 10.0
#: The tallest a header logo may be drawn. Small on purpose: a mark that
#: competes with the title is a mark in the wrong place.
LOGO_H = 22.0


def _furniture_bands(furniture: dict) -> tuple[float, float]:
    """`(head, foot)` — how much vertical room the running text needs.

    **Zero when there is nothing to draw**, so a document with no furniture is
    laid out byte-identically to one written before this row.
    """
    head = furniture.get("header") or {}
    foot = furniture.get("footer") or {}
    head_h = 0.0
    if head.get("left") or head.get("right") or head.get("image") is not None:
        head_h = max(HEAD_SIZE + HEAD_GAP,
                     (LOGO_H + HEAD_GAP) if head.get("image") is not None else 0.0)
    foot_h = 0.0
    if foot.get("left") or foot.get("right") or foot.get("pages"):
        # Two lines' worth: the target's own footer runs the confidentiality
        # notice over two lines beside the page number.
        foot_h = 2 * FOOT_SIZE * 1.25 + FOOT_GAP
    return head_h, foot_h


def _paint_furniture(pages: list, furniture: dict, *, rule_colour, weight: float,
                     family: str) -> None:
    """Draw the running header and footer on every page, once pagination is done."""
    head = furniture.get("header") or {}
    foot = furniture.get("footer") or {}
    total = len(pages)
    head_h, foot_h = _furniture_bands(furniture)
    faint = (0.42, 0.44, 0.47)
    for number, page in enumerate(pages, start=1):
        if head_h:
            base = PAGE_H - MARGIN - HEAD_SIZE
            image = head.get("image")
            if image is not None and getattr(image, "data", b""):
                px_w = getattr(image, "width", None) or 200
                px_h = getattr(image, "height", None) or 60
                scale = min(LOGO_H / px_h, 160.0 / px_w, POINTS_PER_PIXEL)
                name = f"Hd{number}"
                page.images.append((name, image))
                page.ops.append(
                    f"q {px_w * scale:.2f} 0 0 {px_h * scale:.2f} {MARGIN:.1f} "
                    f"{PAGE_H - MARGIN - px_h * scale:.2f} cm /{name} Do Q")
            elif head.get("left"):
                page.y = base
                _emit(page, latin(str(head["left"])), HEAD_SIZE, bold=True,
                      colour=faint, family=family)
            if head.get("right"):
                page.y = base
                _emit(page, latin(str(head["right"])), HEAD_SIZE, bold=True,
                      right=True, colour=faint, family=family)
            _rule(page, PAGE_H - MARGIN - head_h + FOOT_GAP * 0.5,
                  thickness=weight, colour=rule_colour)
        if foot_h:
            top = MARGIN + foot_h - FOOT_GAP * 0.5
            _rule(page, top, thickness=weight, colour=rule_colour)
            line = top - FOOT_GAP - FOOT_SIZE * 0.4
            left = str(foot.get("left") or "")
            if foot.get("pages"):
                # **`N of M`, and M is real.** Substituted rather than appended
                # so an author who wrote their own wording keeps it.
                stamp = str(foot.get("pages"))
                stamp = (stamp.replace("{n}", str(number))
                              .replace("{of}", str(total)))
                page.y = line
                _emit(page, latin(stamp), FOOT_SIZE, colour=faint, family=family)
            elif left:
                page.y = line
                _emit(page, latin(left), FOOT_SIZE, colour=faint, family=family)
            right = str(foot.get("right") or "")
            if right:
                for offset, text in enumerate(
                        wrap(latin(right), FOOT_SIZE, TEXT_W * 0.62,
                             family=family)[:2]):
                    page.y = line - offset * FOOT_SIZE * 1.25
                    _emit(page, text, FOOT_SIZE, right=True, colour=faint,
                          family=family)
            if foot.get("pages") and left:
                # Both were asked for: the page stamp took the left slot, so
                # the author's own left text goes under it rather than being
                # silently dropped.
                page.y = line - FOOT_SIZE * 1.25
                _emit(page, latin(left), FOOT_SIZE, colour=faint, family=family)


def _wash(ink: tuple[float, float, float]) -> tuple[float, float, float]:
    """The band's fill: the ink, most of the way to white.

    **Computed, not tabulated.** A second table of four pale colours is a
    second thing to keep in step with the first, and the failure mode is a
    green band with an orange bar that nobody notices until it prints.
    """
    return tuple(c + (1.0 - c) * 0.88 for c in ink)  # type: ignore[return-value]


def _emit(page: _Page, text: str, size: float, *, bold: bool = False,
          italic: bool = False, indent: float = 0.0,
          centre: bool = False, right: bool = False,
          colour: tuple[float, float, float] = INK,
          tracking: float = 0.0, family: str = "sans") -> None:
    font = resolve(family, bold, italic)
    # **Centring measures with the SAME width table the wrapper uses.** A second
    # measurement would drift from the first and the line would sit slightly off
    # its axis, which reads as a mistake rather than as a choice.
    # **TRACKING WIDENS THE LINE, so it is measured before centring.** `Tc`
    # adds its value after every glyph including the last, which is why the
    # trailing one is taken back off: otherwise a centred tracked line sits
    # half a space left of centre and looks like a rounding error.
    drawn = width_of(text, size, bold=bold, italic=italic, family=family)         + tracking * max(len(text) - 1, 0)
    x = MARGIN + indent
    if centre:
        x = MARGIN + (TEXT_W - drawn) / 2.0
    elif right:
        # **RIGHT IS A REAL ALIGNMENT, not centre with a bigger offset.** Len:
        # *"it should know what to bold, what to center, what to right
        # align."* A date, a signature line or a figure reference ranged right
        # is ordinary document typography and there was no way to ask for it.
        x = MARGIN + TEXT_W - drawn - indent
    # **`q`/`Q` AROUND THE COLOUR.** Without the save/restore the fill colour
    # leaks into every operator after it, so one accented heading would tint
    # the rest of the document — and it would look deliberate.
    space = f"{tracking:.2f} Tc " if tracking else ""
    page.ops.append(
        f"q {_rgb(colour)} rg BT {space}/{font} {size:.1f} Tf "
        f"{x:.1f} {page.y:.1f} Td "
        f"({_pdf_string(text)}) Tj ET Q"
    )


#: The tallest a picture may be drawn.
#:
#: ══ THIS WAS 320 AND IT MISSED ITS OWN PURPOSE BY EIGHT POINTS (T49) ═══════
#: The comment here used to say the ceiling existed "so a step and its
#: illustration can share a sheet". **Measured on Len's real SOP: it never
#: could.** The column is 648pt; two pictures at 320 plus their 8pt leads come
#: to 656. Eight points over, so the second one always started a new page —
#: eight photographs, eight pages, two of them carrying no text at all.
#:
#: A fraction of the column rather than a constant, for C54's reason one format
#: over: the number that matters is "how much of the page does this eat", and a
#: literal stops being that the moment the page size or the margin changes.
#: 0.44 leaves room for two pictures AND a line of text between them, which is
#: what a procedure actually looks like.
MAX_IMAGE_H = 0.44 * (PAGE_H - 2 * MARGIN)

#: PDF user-space units are points; a pixel is a point at 72 DPI, and screen
#: images are conventionally 96. **A picture is never drawn larger than this**
#: — enlarging a 238x227 thumbnail to 336x320 is how a photograph that was
#: merely small becomes a photograph that is visibly soft, and no scaling can
#: add back detail that is not in the file.
POINTS_PER_PIXEL = 72.0 / 96.0


def image_scale(px_w: float, px_h: float) -> float:
    """How much to scale a picture. **Three ceilings, and the third is new.**

    Width and height keep it inside the column; the natural size keeps it from
    being blown up past what the pixels can support. `min` of the three, so
    whichever binds first is the one that matters.
    """
    if px_w <= 0 or px_h <= 0:
        return 1.0
    return min(TEXT_W / px_w, MAX_IMAGE_H / px_h, POINTS_PER_PIXEL)


def _place_image(page: _Page, image, name: str,
                 scale: float | None = None) -> None:
    """Draw one picture at the current cursor. **The CTM is the whole trick.**

    PDF has no "draw this image at this size" operator: an XObject is painted
    into the unit square, so the current transformation matrix IS the position
    and the size. `cm` takes `a b c d e f` — width, 0, 0, height, x, y — and a
    matrix with the height left at 1 paints a one-point-tall smear rather than
    raising an error.
    """
    px_w = getattr(image, "width", None) or 600
    px_h = getattr(image, "height", None) or 400
    # ══ THE CALLER'S SCALE WINS, AND THIS PARAMETER IS WHY ═══════════════════
    # **This function used to recompute `image_scale()` itself**, which was
    # correct until T54 taught the LAYOUT to squeeze a picture into the room
    # left on a page. The layout then reserved the squeezed height and this
    # drew the full one: measured, a photograph ran 47pt past the bottom margin
    # and printed over the page number.
    #
    # The comment at the call site has warned about exactly this since T49 —
    # *two copies of this arithmetic is how the reservation and the drawing
    # come to disagree* — and the divergence was introduced anyway, by adding a
    # third place that computes it. The scale is now passed, so there is one.
    if scale is None:
        scale = image_scale(px_w, px_h)
    w, h = px_w * scale, px_h * scale
    page.y -= h
    # ══ CENTRED IN THE COLUMN (T50) ═════════════════════════════════════════
    # Every picture used to start at the left margin, so a portrait photo in a
    # 468pt column sat in the left half with a river of white down the right.
    # Len: *"Theres no cventering, no headers, no beautification, nothing."*
    x = MARGIN + (TEXT_W - w) / 2.0
    page.ops.append(
        f"q {w:.2f} 0 0 {h:.2f} {x:.2f} {page.y:.2f} cm /{name} Do Q")


#: ══ THE CHART BOX — CLAMPED FOR THE SAME REASON `MAX_IMAGE_H` IS (T81) ═════
#: `advance()` does not detect "never fits" and loops forever handed a box
#: taller than the usable column (`PAGE_H - 2*MARGIN` = 648). A chart has no
#: natural size to shrink from the way a photograph does, so the ceiling is
#: simply never offered in the first place — a fraction of the column, for
#: C54's reason one format over: the number that matters is "how much of the
#: page does this eat", and a literal stops being that the moment the margin
#: changes.
MAX_CHART_H = 0.5 * (PAGE_H - 2 * MARGIN)

#: A small set of hues distinct from the theme's accent and from each other,
#: for the second series onward. **The FIRST series takes the document's own
#: accent** — a chart with one series should read as part of the same
#: document as its headings, not as a plugin with its own palette.
_CHART_PALETTE = (
    (0.72, 0.36, 0.14), (0.20, 0.52, 0.36), (0.55, 0.24, 0.58),
    (0.78, 0.55, 0.09), (0.19, 0.45, 0.66), (0.62, 0.20, 0.24),
    (0.35, 0.35, 0.35),
)


def _chart_colour(index: int, own: tuple[float, float, float] | None,
                  accent: tuple[float, float, float]):
    """`None` means "the renderer decides" (T81's own contract, restated)."""
    if own is not None:
        return own
    if index == 0:
        return accent
    return _CHART_PALETTE[(index - 1) % len(_CHART_PALETTE)]


def _chart_text(page: "_Page", x: float, y: float, text: str, size: float,
                colour: tuple[float, float, float], *,
                family: str = "sans", align: str = "left") -> None:
    """Text at an EXPLICIT point, not at `page.y`. `_emit` always draws at the
    cursor; a chart places labels against plot coordinates it just computed,
    so it needs its own placement rather than a second copy of `_emit`'s
    measuring rules — reusing `width_of`/`latin`/`_pdf_string` so it cannot
    disagree with the wrapper about what a glyph costs."""
    font = resolve(family, False, False)
    body = latin(text)
    drawn = width_of(body, size, family=family)
    if align == "centre":
        x -= drawn / 2.0
    elif align == "right":
        x -= drawn
    page.ops.append(
        f"q {_rgb(colour)} rg BT /{font} {size:.1f} Tf "
        f"{x:.2f} {y:.2f} Td ({_pdf_string(body)}) Tj ET Q")


def _chart_text_vertical(page: "_Page", x: float, y_centre: float, text: str,
                         size: float, colour: tuple[float, float, float], *,
                         family: str = "sans") -> None:
    """An axis title, rotated 90 degrees. `0 1 -1 0 x y Tm` is the rotation
    matrix; the text then runs bottom-to-top, so it is centred on its own
    length before being placed."""
    font = resolve(family, False, False)
    body = latin(text)
    drawn = width_of(body, size, family=family)
    y = y_centre - drawn / 2.0
    page.ops.append(
        f"q {_rgb(colour)} rg BT /{font} {size:.1f} Tf "
        f"0 1 -1 0 {x:.2f} {y:.2f} Tm ({_pdf_string(body)}) Tj ET Q")


def _chart_fill(page: "_Page", x: float, y: float, w: float, h: float,
                colour: tuple[float, float, float]) -> None:
    """A filled rectangle. **`re f`, never a stroke** — `_rule`'s reason
    applies to every axis line and every bar in this chart: a stroke's
    apparent width moves with the CTM and a filled box does not."""
    if w <= 0 or h <= 0:
        return
    page.ops.append(
        f"q {_rgb(colour)} rg {x:.2f} {y:.2f} {w:.2f} {h:.2f} re f Q")


#: Legend geometry. **One row height, one swatch size, one gap** — the same
#: "one constant, not three call sites disagreeing" reasoning as everywhere
#: else in this file.
_LEGEND_ROW_H = 14.0
_LEGEND_SWATCH = 9.0
_LEGEND_GAP = 16.0


def _legend_label(index: int, series) -> str:
    return series.name or f"Series {index + 1}"


def _truncate_to_width(text: str, size: float, limit: float, *,
                       family: str = "sans") -> str:
    """`text`, or as much of it as fits `limit` with an ellipsis. **The same
    shrink-from-the-right shape `wrap`'s inner loop uses**, so a legend label
    that is pathologically long (a model can name a series anything) cannot
    push the swatch after it off the page."""
    if width_of(text, size, family=family) <= limit:
        return text
    cut = len(text)
    while cut > 0 and width_of(text[:cut] + "…", size, family=family) > limit:
        cut -= 1
    return (text[:cut] + "…") if cut > 0 else ""


def _legend_rows(chart, accent: tuple[float, float, float], family: str,
                 *, size: float = 8.0) -> list[list[tuple]]:
    """Series -> rows of `(colour, label, item_width)`, greedily wrapped to
    `TEXT_W` so a chart with many series grows a second legend row instead of
    running off the column. **No legend at all is a valid answer** — the
    caller decides that from `len(chart.series)`; this only lays out what it
    is given."""
    limit = TEXT_W * 0.6   # no single item may claim more than 60% of a row
    items = []
    for index, series in enumerate(chart.series):
        colour = _chart_colour(index, series.colour, accent)
        label = _truncate_to_width(_legend_label(index, series), size, limit,
                                   family=family)
        width = (_LEGEND_SWATCH + 4.0
                 + width_of(latin(label), size, family=family) + _LEGEND_GAP)
        items.append((colour, label, width))

    rows: list[list[tuple]] = []
    current: list[tuple] = []
    current_w = 0.0
    for item in items:
        if current and current_w + item[2] > TEXT_W:
            rows.append(current)
            current, current_w = [], 0.0
        current.append(item)
        current_w += item[2]
    if current:
        rows.append(current)
    return rows


def _wants_legend(chart) -> bool:
    """**A single unnamed series gets no legend** (C57's rule, one field
    over): a swatch and a blank label is furniture, telling the reader
    nothing they could not already see from the one colour on the page."""
    if len(chart.series) >= 2:
        return True
    return len(chart.series) == 1 and bool(chart.series[0].name)


def _place_legend(page: "_Page", rows: list[list[tuple]], top_y: float,
                  colour: tuple[float, float, float], family: str) -> None:
    """Draw the legend rows, each row centred in the column. **Swatch and
    label share a baseline** — `_chart_fill`'s box is nudged down 2pt from
    the text's `Td` point so a 9pt square reads as sitting ON the text line
    rather than floating above it."""
    y = top_y
    for row in rows:
        total_w = sum(item[2] for item in row) - _LEGEND_GAP
        x = MARGIN + (TEXT_W - total_w) / 2.0
        for swatch, label, width in row:
            _chart_fill(page, x, y - 2.0, _LEGEND_SWATCH, _LEGEND_SWATCH, swatch)
            _chart_text(page, x + _LEGEND_SWATCH + 4.0, y, label, 8.0, colour,
                       family=family)
            x += width
        y -= _LEGEND_ROW_H


def _chart_path(page: "_Page", points: list[tuple[float, float]],
                colour: tuple[float, float, float], *, width: float = 1.6) -> None:
    """One unbroken run of a line series. **This is the one place this chart
    strokes rather than fills** — a line's whole meaning is its slope between
    points, which `re f` cannot express. Fewer than two points draws nothing:
    a lone surviving point either side of two gaps is not a segment."""
    if len(points) < 2:
        return
    parts = [f"q {width:.2f} w 1 J 1 j {_rgb(colour)} RG"]
    x0, y0 = points[0]
    parts.append(f"{x0:.2f} {y0:.2f} m")
    for x, y in points[1:]:
        parts.append(f"{x:.2f} {y:.2f} l")
    parts.append("S Q")
    page.ops.append(" ".join(parts))


def legend_height(rows: list[list[tuple]]) -> float:
    """0 with no rows — **absence, not a zero-height box someone has to
    remember means "nothing here"** (INVARIANT-ENVELOPE, one field over)."""
    return (len(rows) * _LEGEND_ROW_H + 6.0) if rows else 0.0


def _place_chart(page: "_Page", chart, height: float, *,
                 accent: tuple[float, float, float] = ACCENT,
                 rule_colour: tuple[float, float, float] = RULE,
                 ink: tuple[float, float, float] = INK,
                 family: str = "sans",
                 legend_rows: list[list[tuple]] | None = None) -> None:
    """Draw one chart at the current cursor. Same convention as
    `_place_image`: `page.y` is the top edge on entry and the bottom edge
    (`top - height`) on return.

    ══ THE AXIS IS NEVER RECOMPUTED HERE ═══════════════════════════════════
    `nice_axis`, `tick_labels` and `fraction` are the shared contract — three
    renderers computing their own range is the exact defect `_chart.py`
    exists to prevent, so every number this function draws with comes from
    one of those three calls.

    ══ THE LEGEND COMES OUT OF `height`, NOT ON TOP OF IT ═══════════════════
    `_layout` grew the reserved box by `legend_height(rows)` before calling
    here — so the plot area below shrinks to make room, rather than the
    legend being drawn over the plot or past the bottom of the reserved box.
    """
    top = page.y
    page.y -= height
    bottom = page.y

    axis = nice_axis(chart)
    ticks = axis.ticks
    labels = tick_labels(axis)

    rows = legend_rows or []
    legend_h = legend_height(rows)
    title_h = 18.0 if chart.title else 0.0
    xtitle_h = 14.0 if chart.x_title else 0.0
    cat_h = 16.0
    ytitle_w = 12.0 if chart.y_title else 0.0
    ytick_w = (max((width_of(t, 8.0, family=family) for t in labels),
                   default=0.0) + 8.0) if labels else 8.0

    plot_left = MARGIN + ytitle_w + ytick_w
    plot_right = MARGIN + TEXT_W - 4.0
    plot_top = top - title_h - legend_h
    plot_bottom = bottom + xtitle_h + cat_h
    # **A degenerate box still draws something rather than dividing by a
    # non-positive span** — a very short chart loses its gridlines before it
    # loses its bars, which is the same "the picture gives way" rule T54 used
    # for a photograph that would not fit.
    if plot_bottom >= plot_top:
        plot_bottom = plot_top - 1.0
    if plot_right <= plot_left:
        plot_right = plot_left + 1.0
    plot_h = plot_top - plot_bottom
    plot_w = plot_right - plot_left

    if chart.title:
        _chart_text(page, (plot_left + plot_right) / 2.0, top - 13.0,
                   chart.title, 11.5, ink, family=family, align="centre")

    # ══ THE LEGEND — UNDER THE TITLE, ABOVE THE PLOT (T81b) ══════════════════
    # **A picture found this, not a text-extracting assertion**: two bars in
    # two colours and nothing on the page says which is which. Placed here
    # rather than under the x-axis labels because that row already carries
    # the category names — stacking the legend under them would put two
    # different kinds of caption on the same baseline.
    if rows:
        _place_legend(page, rows, top - title_h - 10.0, ink, family)

    # ══ GRIDLINES AND TICK LABELS — ONE PER AXIS VALUE, NEVER RECOMPUTED ════
    for value, label in zip(ticks, labels):
        y = plot_bottom + fraction(value, axis) * plot_h
        _chart_fill(page, plot_left, y - 0.35, plot_w, 0.7, rule_colour)
        _chart_text(page, plot_left - 5.0, y - 2.8, label, 7.5, ink,
                   family=family, align="right")
    # The baseline is drawn heavier and last, so it sits above the gridlines
    # it shares a row with rather than being redrawn over by one of them.
    _chart_fill(page, plot_left, plot_bottom - 0.6, plot_w, 1.1, ink)

    points = max(1, chart.points)
    slot_w = plot_w / points
    for i, label in enumerate(chart.labels):
        cx = plot_left + slot_w * (i + 0.5)
        _chart_text(page, cx, plot_bottom - 11.0, label, 7.5, ink,
                   family=family, align="centre")

    if chart.x_title:
        _chart_text(page, (plot_left + plot_right) / 2.0, bottom + 2.0,
                   chart.x_title, 8.0, ink, family=family, align="centre")
    if chart.y_title:
        _chart_text_vertical(page, MARGIN + 2.0, (plot_top + plot_bottom) / 2.0,
                             chart.y_title, 8.0, ink, family=family)

    n_series = max(1, len(chart.series))
    if chart.shape == "bar":
        gutter = 4.0
        group_w = max(1.0, slot_w - gutter)
        bar_w = max(1.0, (group_w / n_series) - 2.0)
        baseline_y = plot_bottom + fraction(0.0, axis) * plot_h
        for si, series in enumerate(chart.series):
            colour = _chart_colour(si, series.colour, accent)
            for i in range(points):
                value = series.values[i] if i < len(series.values) else None
                # ══ A GAP IS NOT A ZERO (T81, from `_chart.py`'s own docstring)
                # A `None` value emits NO fill at all — not a zero-height bar,
                # which would still occupy the slot and read as "measured, and
                # it was nothing." One fewer operator is the only honest way
                # to draw absence.
                if value is None:
                    continue
                x = (plot_left + slot_w * i + gutter / 2.0
                     + (group_w / n_series) * si + 1.0)
                y = plot_bottom + fraction(value, axis) * plot_h
                lo, hi = (baseline_y, y) if y >= baseline_y else (y, baseline_y)
                _chart_fill(page, x, lo, bar_w, max(0.6, hi - lo), colour)
    else:
        for si, series in enumerate(chart.series):
            colour = _chart_colour(si, series.colour, accent)
            run: list[tuple[float, float]] = []
            for i in range(points):
                value = series.values[i] if i < len(series.values) else None
                if value is None:
                    # **The gap breaks the line rather than being bridged.**
                    # Joining across it would draw a slope through data that
                    # was never measured — the same lie a zero-height bar
                    # would tell, in the shape a line makes instead.
                    _chart_path(page, run, colour)
                    run = []
                    continue
                x = plot_left + slot_w * (i + 0.5)
                y = plot_bottom + fraction(value, axis) * plot_h
                run.append((x, y))
            _chart_path(page, run, colour)


#: block type -> (font size, space before, bold, centred)
#:
#: **`heading1` IS CENTRED AND NOTHING ELSE IS.** A document has one title and
#: it is the only line that belongs on the page's axis. Centring section
#: headings too gives a ragged middle column with no left edge for the eye to
#: track down, which reads as decoration rather than as structure.
#: `(size, space before, bold, centred, colour, rule under)`
#:
#: ══ THE SCALE WAS TIMID AND THAT IS WHY IT READ AS UNDESIGNED (T53) ════════
#: Len: *"Im talking better headers / colors / depth / spacing."*
#:
#: The first pass gave the title 20pt against 10.5pt body — **1.9x, which the
#: eye reads as "slightly bigger text" rather than as a title** — and put the
#: section headings at 13pt, close enough to the body to look like bold prose.
#: Depth in a document is CONTRAST plus AIR, and there was little of either.
#:
#: 26 / 10 / 11 is 2.6x to the title and a section label that is SMALLER than
#: the body but set in caps, letterspaced and coloured — the editorial
#: convention, and the one the comparison document used. A label that is
#: smaller and louder reads as a signpost; one that is bigger and heavier reads
#: as a sentence somebody bolded.
STYLES = {
    "heading1": (26.0, 30.0, True, True, ACCENT, True),
    "heading2": (10.0, 26.0, True, False, ACCENT, True),
    "heading3": (12.5, 16.0, True, False, ACCENT, False),
    "paragraph": (11.0, 9.0, False, False, INK, False),
    "bullet": (11.0, 5.0, False, False, INK, False),
}

#: Section labels are set in capitals and letterspaced. **`Tc` — the PDF
#: character-spacing operator** — so it is real tracking rather than spaces
#: pushed between letters, which would break wrapping and copy back out of the
#: document as `S T E P  1`.
TRACKING = {"heading2": 1.1}

#: Line height as a multiple of the font size. **1.5 for prose**, which is the
#: single change that makes a page of text look composed rather than typed; the
#: old 1.3 is right for a heading, where the lines belong together.
LEADING = 1.5
HEADING_LEADING = 1.18

#: How much a picture may be squeezed to stay on the page it belongs to.
#:
#: **0.72 is the floor, and the number is a judgement about legibility rather
#: than about layout.** A photograph at 72% of its intended height is still an
#: illustration; at half it is a thumbnail, and a reader looking for the drip
#: insert in a hotel pan cannot see one. Below the floor the picture moves and
#: takes its white space with it — a hole is better than an unreadable photo.
SQUEEZE = 0.72

#: Two pictures side by side when they are CONSECUTIVE and both fit.
#:
#: ══ THE SINGLE BIGGEST DIFFERENCE FROM THE DOCUMENT LEN COMPARED US TO ═════
#: His SOP has runs of two and three photographs between steps. Stacked one per
#: row they eat a page each and the reader scrolls past a column of white; side
#: by side they read as *"here are the two states"*, which is what they are.
#: The gutter is generous because two photographs 6pt apart read as one wide
#: photograph with a seam.
IMAGE_GUTTER = 18.0


def _block_height(block: object) -> float:
    """Roughly how tall the NEXT block will be. **For keep-with-next only.**

    ══ A HEADING ALONE AT THE FOOT OF A PAGE IS THE ONE FLAW A PICTURE FOUND ══
    T50 centred the titles and the photographs, and the render showed *"Please
    Frozen Tuna in pan with drip insert"* sitting at the bottom of page 2 with
    both of its photographs on page 3 — a heading pointing at nothing, which is
    worse than the flat document it replaced because it now looks deliberate.

    An estimate is the right tool here and an exact measurement is not: this
    only ever decides *"is there enough room after the heading to be worth
    starting here"*, and being a few points out changes nothing. Being WRONG in
    the generous direction is what matters, so an unknown block is treated as
    needing nothing rather than as needing a page.
    """
    if not isinstance(block, dict):
        return 0.0
    kind = str(block.get("type") or "paragraph").strip().lower()
    if kind == "image":
        image = block.get("image")
        if image is None:
            return 0.0
        px_w = getattr(image, "width", None) or 600
        px_h = getattr(image, "height", None) or 400
        return px_h * image_scale(px_w, px_h) + 10.0
    if kind == "chart":
        # A chart has no natural size to measure — its own layout branch
        # clamps to `MAX_CHART_H` regardless of what this returns, so the
        # estimate only needs to be big enough that a heading right before a
        # chart still asks to keep them together. **The legend is part of
        # that estimate now** (T81b): a two-series chart reserves a taller
        # box than a one-series one, and an estimate that ignored it would
        # under-reserve exactly the case that most needs a legend.
        try:
            chart = parse_chart(block)
        except BadChart:
            return MAX_CHART_H + 10.0
        rows = _legend_rows(chart, ACCENT, "sans") if _wants_legend(chart) else []
        return MAX_CHART_H + legend_height(rows) + 10.0
    size, before = STYLES.get(kind, STYLES["paragraph"])[:2]
    # **THE BLOCK'S OWN SIZE, when it chose one (T75).** This is an estimate by
    # design, but an estimate that ignores a 32pt heading and reserves 10pt for
    # it puts the heading back at the foot of the page — which is the exact
    # flaw this function was written to remove.
    size = _size_of(block.get("size"), size)
    # Two lines' worth. **Not the whole paragraph** — requiring a long one to
    # fit entirely would push every heading before it onto a fresh page and
    # leave the previous one half empty, which is the same defect mirrored.
    return before + 2 * size * 1.3


#: Half the column, less half the gutter — the width one picture of a pair gets.
HALF_W = (TEXT_W - IMAGE_GUTTER) / 2.0

def _pairable(first: object, second: object) -> dict | None:
    """`second` if these two photographs should share a row, else `None`.

    **Both must be real images and both must be reasonably shaped.** A very
    wide panorama beside a portrait is two pictures at wildly different scales
    pretending to be a comparison, so a picture whose natural width already
    exceeds the half-column is left to take the full one.
    """
    if not isinstance(first, dict) or not isinstance(second, dict):
        return None
    if str(second.get("type") or "").strip().lower() != "image":
        return None
    a, b = first.get("image"), second.get("image")
    if a is None or b is None:
        return None
    if not getattr(a, "data", b"") or not getattr(b, "data", b""):
        return None
    return second


def _pair_size(image: object) -> tuple[float, float]:
    """A picture drawn into HALF the column. Same three ceilings as
    `image_scale`, with the width halved — never the natural-size one dropped,
    or a thumbnail would be enlarged to fill its half."""
    px_w = getattr(image, "width", None) or 600
    px_h = getattr(image, "height", None) or 400
    scale = min(HALF_W / px_w, MAX_IMAGE_H / px_h, POINTS_PER_PIXEL)
    return px_w * scale, px_h * scale


def _place_pair(advance, pages, first: dict, second: dict, room: float) -> None:
    """Draw two photographs on one row, each centred in its own half.

    ══ ONE HEIGHT FOR BOTH, WHICH IS NOT WHAT THIS DID (C77) ═════════════════
    This used to scale each picture independently and sit them on a shared
    BOTTOM baseline, reasoning that a common top *"leaves a ragged shelf under
    the shorter one"*. The reasoning was right and the remedy only moved the
    shelf: bottom-aligning two pictures of different heights leaves the ragged
    edge on TOP instead, which is what every pair in Len's SOP shows.

    **A figure row has one height.** Both are scaled to the shorter one's, so
    the widths differ and the band is flush on both edges — which is what the
    document he compared us to does, and what makes a pair read as one row
    rather than as two pictures that happen to be adjacent.

    ══ AND THE SQUEEZE NEVER REACHED THIS PATH (C77) ════════════════════════
    T54 added `SQUEEZE` so a picture gives way rather than the page — *"four
    pages, four holes"*. It was wired into the SINGLE-image branch only, and a
    procedure's photographs come in twos, so **the mechanism built to close
    that hole never fired on the shape that causes it.** Measured on the Tuna
    Poke SOP: 4 pages, two of them 42% empty, every pair pushed past the text
    it illustrates. `room` is what is left on the current page; the row gives
    way down to the same 72% floor, and below it still moves.
    """
    left, right = first["image"], second["image"]
    lw, lh = _pair_size(left)
    rw, rh = _pair_size(right)
    # ONE height for the row: the shorter picture's. Scaling the shorter one UP
    # to meet the taller would enlarge it past its natural size, which is the
    # soft-photograph defect `POINTS_PER_PIXEL` exists to prevent.
    row = min(lh, rh)
    lw, rw = lw * (row / lh), rw * (row / rh)
    lh = rh = row
    # The row gives way before the page does — same floor, same reason as the
    # single-image branch. Applied to the ROW, so both halves stay equal.
    if row + 10.0 > room >= (row + 10.0) * SQUEEZE and room > 0:
        shrink = (room - 10.0) / row
        lw, rw, row = lw * shrink, rw * shrink, row * shrink
        lh = rh = row
    current = advance(row + 10.0)
    current.y -= 8.0
    baseline = current.y - row
    for image, w, h, centre_x in (
        (left, lw, lh, MARGIN + HALF_W / 2.0),
        (right, rw, rh, MARGIN + HALF_W + IMAGE_GUTTER + HALF_W / 2.0),
    ):
        name = f"Im{len(current.images) + 1}_{len(pages)}"
        current.images.append((name, image))
        current.ops.append(
            f"q {w:.2f} 0 0 {h:.2f} {centre_x - w / 2.0:.2f} "
            f"{baseline:.2f} cm /{name} Do Q")
    current.y = baseline


def _size_of(value: object, fallback: float) -> float:
    """A model-authored point size, or the role's own (T75).

    **Clamped, not trusted (R42).** The number reaches a layout that reserves
    space by arithmetic and decides page breaks from it; 4000 here is a single
    glyph that never fits and an infinite advance loop. 5pt is smaller than any
    footnote and 96pt is already a cover-page title on US Letter.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return fallback
    try:
        return min(96.0, max(5.0, float(value)))
    except (TypeError, ValueError):
        return fallback


def _layout(blocks: list[dict],
            theme: dict | None = None,
            furniture: dict | None = None) -> list[_Page]:
    # ══ THE PALETTE, RESOLVED ONCE (T72) ═════════════════════════════════════
    # Len: *"Theres no color variations in the header, is this a model
    # limitation or a harness limitation?"* It was ours — three constants, and
    # no field on the schema through which anything else could arrive.
    #
    # **Each colour falls back INDEPENDENTLY**, so a theme naming only an
    # accent leaves the ink and the rules exactly as T51 set them. A theme that
    # had to be complete would make "one coloured heading" a whole-document
    # redesign, and the model would either write four colours it does not mean
    # or none at all.
    theme = theme if isinstance(theme, dict) else {}
    # ══ THE RULE HAS A WEIGHT NOW, AND IT IS THE SAME DEFECT AS THE COLOUR ══
    # Len: *"can you make the lines thicker for the headers?"* The model
    # answered *"this version features thicker, more prominent header lines"*
    # and produced a file with the identical 0.7pt hairline — T72's defect
    # exactly, one field over, and it survived T72 because that row added
    # COLOUR and stopped there.
    #
    # Clamped rather than trusted (R42): a model-authored number reaches a
    # layout that reserves space by arithmetic, and 400 here is a black band
    # across the page. 0.3 is the thinnest a printer resolves; 6 is already a
    # bar rather than a rule.
    weight = theme.get("rule_width")
    try:
        weight = min(6.0, max(0.3, float(weight))) if weight is not None else 0.7
    except (TypeError, ValueError):
        weight = 0.7
    # ══ A DOCUMENT HAS TWO FACES, AND PAIRING THEM IS THE POINT (T75) ══════
    # Good documents set headings in one family and body text in another — a
    # sans heading over a serif body is the commonest pairing in print. One
    # `font` field would have made that unsayable, so there are two and
    # `heading_font` falls back to `font` rather than to a constant.
    body_family = family_of(theme.get("font"), "sans")
    heading_family = family_of(theme.get("heading_font"), body_family)
    ink = theme.get("ink") or INK
    accent = theme.get("accent") or ACCENT
    heading = theme.get("heading") or accent
    rule_colour = theme.get("rule") or RULE
    # ══ THE SECOND HEADING TIER (C77e) ══════════════════════════════════════
    # Applied AFTER the palette rather than through it: `STYLES` names the
    # ROLE, and all three heading kinds legitimately share the heading role.
    # Giving `heading2` its own sentinel colour in `STYLES` would make that
    # table carry a distinction it does not own, and the sentinel would be a
    # colour that renders if the mapping is ever missed.
    subheading = theme.get("subheading") or heading
    palette = {ACCENT: heading, INK: ink}
    # ══ THE BANDS ARE RESERVED BEFORE THE FIRST PAGE EXISTS (C77) ══════
    # `_Page.__init__` reads them to place its own cursor, so setting them
    # after `pages = [_Page()]` would leave page 1 running under its header
    # and every later page correct -- the hardest kind of layout bug to see,
    # because the document looks right from page 2 onward.
    furniture = furniture if isinstance(furniture, dict) else {}
    _Page.head_band, _Page.foot_band = _furniture_bands(furniture)
    pages = [_Page()]

    def page() -> _Page:
        return pages[-1]

    def advance(height: float) -> _Page:
        if not page().room(height):
            pages.append(_Page())
        return page()

    sequence = list(blocks or [])
    #: Positions already drawn as the right-hand half of a pair. **A set of
    #: INDICES rather than a "skip next" flag**, because a flag survives into
    #: the next iteration only by accident and reads as a bug the first time
    #: somebody adds a `continue` above it.
    consumed: set[int] = set()
    for position, block in enumerate(sequence):
        # The block AFTER this one, for keep-with-next. `None` at the end,
        # which `_block_height` reads as "nothing to keep with".
        after = sequence[position + 1] if position + 1 < len(sequence) else None
        if not isinstance(block, dict):
            block = {"type": "paragraph", "text": str(block)}
        kind = str(block.get("type") or "paragraph").strip().lower()
        if kind in ("title", "heading"):
            kind = "heading1"

        if kind in ("spacer", "break"):
            advance(12.0).y -= 12.0
            continue

        if kind == "callout":
            # ══ THE BAND IS MEASURED, THEN DRAWN, THEN FILLED ════════════════
            # Its height depends on how the text wraps, and the rectangle has
            # to be painted BEFORE the glyphs or it covers them — PDF has no
            # z-order beyond operator order. So the lines are wrapped first,
            # the box is reserved and filled from that count, and only then is
            # the text emitted into it.
            tone = str(block.get("tone") or "note").strip().lower()
            if tone not in CALLOUT_INK:
                tone = "note"
            ink = CALLOUT_INK[tone]
            chosen = block.get("colour")
            if chosen is not None and readable_on_white(chosen):
                ink = chosen
            size = _size_of(block.get("size"), 10.5)
            mark = CALLOUT_MARK.get(tone, "i")
            inner = TEXT_W - CALLOUT_BAR - 2 * CALLOUT_PAD - 14.0
            flat = latin("".join(r.text for r in runs(str(block.get("text") or ""))))
            lines = wrap(flat, size, inner, bold=True, family=body_family) or [""]
            box = len(lines) * size * LEADING + 2 * CALLOUT_PAD
            current = advance(box + 14.0)
            current.y -= 6.0
            top = current.y
            bottom = top - box
            # The wash, then the bar, then the glyphs — in that order.
            current.ops.append(
                f"q {_rgb(_wash(ink))} rg {MARGIN:.1f} {bottom:.1f} "
                f"{TEXT_W:.1f} {box:.1f} re f Q")
            current.ops.append(
                f"q {_rgb(ink)} rg {MARGIN:.1f} {bottom:.1f} "
                f"{CALLOUT_BAR:.1f} {box:.1f} re f Q")
            text_y = top - CALLOUT_PAD - size
            # The mark sits on the FIRST line's baseline, not on the box's top
            # edge — `_emit` draws at `page.y`, so the cursor moves first.
            current.y = text_y
            _emit(current, mark, size, bold=True, colour=ink,
                  indent=CALLOUT_BAR + CALLOUT_PAD, family=body_family)
            for offset, line in enumerate(lines):
                current.y = text_y - offset * size * LEADING
                _emit(current, line, size, bold=True, colour=ink,
                      indent=CALLOUT_BAR + CALLOUT_PAD + 14.0,
                      family=body_family)
            current.y = bottom - 8.0
            continue

        if kind == "image":
            if position in consumed:
                continue
            image = block.get("image")
            if image is None or not getattr(image, "data", b""):
                continue
            # ══ TWO SIDE BY SIDE WHEN THEY ARE A PAIR (T51) ══════════════════
            # A run of photographs stacked one per row is a column of white with
            # pictures in it. Paired, they read as *"here are the two states"*,
            # which is what a procedure's photographs usually are.
            partner = _pairable(block, after)
            if partner is not None:
                consumed.add(position + 1)
                # The room LEFT on the page the pair would land on, measured
                # the same way the single-image branch measures it below.
                _place_pair(advance, pages, block, partner,
                            page().y - page().bottom - 10.0)
                continue
            px_w = getattr(image, "width", None) or 600
            px_h = getattr(image, "height", None) or 400
            # **ONE FUNCTION, BECAUSE TWO COPIES OF THIS ARITHMETIC IS HOW THE
            # RESERVATION AND THE DRAWING COME TO DISAGREE** — and a layout
            # that reserves less than it paints overlaps the next block.
            scale = image_scale(px_w, px_h)
            # ══ SHRINK TO FIT RATHER THAN LEAVE A HOLE (T54) ═════════════════
            # A step is a heading, some prose, a photograph and a caption —
            # about 380pt — so two never shared a page and the bottom of every
            # page was ~270pt of white with the picture pushed over. Measured
            # on Len's own document: four pages, four holes.
            #
            # **The picture gives way, not the page.** If what is left is at
            # least `SQUEEZE` of what the picture wants, it is drawn smaller
            # and stays with the text it belongs to. Below that it would be a
            # thumbnail pretending to be an illustration, so it moves.
            room = page().y - page().bottom - 10.0
            wanted = px_h * scale
            if wanted > room >= wanted * SQUEEZE:
                scale = min(scale, room / px_h)
            current = advance(px_h * scale + 10.0)
            current.y -= 8.0
            name = f"Im{len(current.images) + 1}_{len(pages)}"
            current.images.append((name, image))
            _place_image(current, image, name, scale)
            continue

        if kind == "chart":
            try:
                chart = parse_chart(block)
            except BadChart:
                # **Skipped, not raised.** The contract says a block reaching
                # here is already validated upstream, but a writer that
                # crashes on the one path nobody re-checked is worse than one
                # that quietly leaves the block out — the same rule `image`
                # follows for a missing picture two branches up.
                continue
            # ══ THE LEGEND GROWS THE RESERVED BOX (T81b) ════════════════════
            # It is drawn OUT OF the chart's own height, not squeezed into a
            # fixed one — a legend that shrank the plot area of every chart
            # regardless of series count would make a one-series chart pay
            # for a caption a two-series chart needs.
            legend_rows = (_legend_rows(chart, accent, body_family)
                          if _wants_legend(chart) else [])
            # ══ CLAMPED HERE TOO, NOT ONLY AT THE CONSTANT (T81) ═══════════
            # `advance()` never detects "this box can never fit" — it just
            # keeps opening pages. Reading the ceiling through a second
            # `min()` against the page's own usable height means a corrupted
            # or overridden constant cannot reintroduce the hang; the ceiling
            # is enforced at the one call site that could loop, not only
            # declared where it is defined.
            height = min(MAX_CHART_H + legend_height(legend_rows),
                        PAGE_H - 2 * MARGIN - 8.0)
            current = advance(height + 10.0)
            current.y -= 8.0
            _place_chart(current, chart, height, accent=accent,
                        rule_colour=rule_colour, ink=ink, family=body_family,
                        legend_rows=legend_rows)
            continue

        if kind == "table":
            rows = [r for r in (block.get("rows") or [])
                    if isinstance(r, (list, tuple))]
            for index, row in enumerate(rows):
                # RENDERED AS A LINE PER ROW, cells joined. A real ruled table
                # needs column measurement and cell-wrapping; a misaligned one
                # is worse than a clean list, and this row is about the format
                # the user asked for, not about typesetting.
                text = "   |   ".join(latin(str(c)) for c in row)
                bold = index == 0
                # Sliced rather than unpacked: this only wants the size, and a
                # positional unpack here has now broken twice when the tuple
                # grew a field it does not care about.
                size = STYLES["paragraph"][0]
                for line in wrap(text, size, TEXT_W, bold=bold,
                                 family=body_family):
                    current = advance(size * 1.3)
                    current.y -= size * 1.3
                    _emit(current, line, size, bold=bold, family=body_family)
            advance(8.0).y -= 8.0
            continue

        size, before, bold, centre, colour, ruled = \
            STYLES.get(kind, STYLES["paragraph"])
        # ══ THE THEME, THEN THIS BLOCK'S OWN COLOUR (T72) ════════════════════
        # `STYLES` names the ROLE — heading colour or body colour — and the
        # palette maps that role onto whatever this document chose. A per-block
        # `colour` then overrides it, which is what *"color-coded step
        # headings"* actually needs and what nothing in this file could express.
        colour = palette.get(colour, colour)
        # `heading1` is the document's voice; 2 and 3 are its sections. When
        # no second tier was named this is the same value and nothing moves.
        if kind in ("heading2", "heading3"):
            colour = subheading
        chosen = block.get("colour")
        # **REFUSED WHEN IT CANNOT BE READ, NOT DARKENED.** A model asked for
        # "yellow for placement" writes `#ffff00`, which on white paper is very
        # nearly invisible; nudging it to a readable yellow would put a colour
        # in the document that nobody chose and that the answer will then
        # describe wrongly. The heading falls back to the theme's, which is
        # legible by construction.
        if chosen is not None and readable_on_white(chosen):
            colour = chosen
        # **ALIGNMENT IS THREE-STATE, NOT A BOOLEAN.** `None` keeps the kind's
        # own default — heading1 centred, everything else ranged left — so a
        # block that says nothing about alignment lays out exactly as it did
        # before this row.
        wanted = block.get("align")
        right = False
        if wanted == "centre":
            centre = True
        elif wanted == "left":
            centre = False
        elif wanted == "right":
            centre, right = False, True

        # ══ THE MODEL SETS THE TYPE NOW (T75) ═══════════════════════════════
        # Len: *"it should choose the more prestine fonts… it should know what
        # to bold, what to center, what to right align."* Every one of these
        # was a constant in `STYLES`, so the model could describe a document it
        # had no way to ask for — T72's defect, across the whole of typography
        # rather than across one colour.
        #
        # **Each override is INDEPENDENT and `None` means "the role decides".**
        # A block naming only a size keeps the weight, the face and the
        # alignment its kind has always had, so a document that says nothing
        # is the document this writer produced before this row.
        size = _size_of(block.get("size"), size)
        if isinstance(block.get("bold"), bool):
            bold = block["bold"]
        italic = bool(block.get("italic"))
        # **`effective` and not `family_of` alone**: a vendored face that
        # failed its digest must be swapped for its base-14 stand-in HERE, so
        # the wrap arithmetic and the drawn resource agree (T76).
        family = effective(
            family_of(block.get("font"), body_family
                      if not kind.startswith("heading") else heading_family),
            bold)
        raw = str(block.get("text") or "")
        indent = 18.0 if kind == "bullet" else 0.0
        prefix = "- " if kind == "bullet" else ""

        # **The emphasis is flattened to the paragraph's own weight.** Mixed
        # runs inside one line would need per-run x-positioning; a heading is
        # bold either way, and a bold word inside a paragraph is dropped to
        # plain rather than mis-placed. Stated because it is a real limit.
        flat = prefix + latin("".join(r.text for r in runs(raw)))
        # **CAPS ARE A STYLE, APPLIED HERE, NOT A CHANGE TO THE CONTENT.** The
        # block still holds what the model wrote, so a docx of the same
        # document is unaffected and nothing downstream inherits a shout.
        track = TRACKING.get(kind, 0.0)
        if kind == "heading2":
            flat = flat.upper()
        lead = HEADING_LEADING if kind.startswith("heading") else LEADING
        # ══ KEEP A HEADING WITH WHAT IT INTRODUCES ═══════════════════════════
        # The break decision reserves the heading AND the head of the next
        # block; only the heading is then consumed. So a heading that would sit
        # alone at the foot of a page starts the next one instead, and its
        # photograph follows it there.
        keep = _block_height(after) if kind.startswith("heading") else 0.0
        current = advance(size + before + keep)
        current.y -= before
        for line in wrap(flat, size, TEXT_W - indent, bold=bold,
                         italic=italic, family=family):
            current = advance(size * lead)
            current.y -= size * lead
            _emit(current, line, size, bold=bold, italic=italic, indent=indent,
                  centre=centre, right=right, colour=colour, tracking=track,
                  family=family)
        # ══ THE RULE, AND THE AIR UNDER IT ═══════════════════════════════════
        # A hairline 6pt under a heading and 3pt above the next paragraph is a
        # line with text crowded against both sides. The gap below is larger
        # than the gap above, so the rule belongs to the heading rather than
        # floating between two things — which is what makes a section read as
        # a section instead of as a divided page.
        if ruled:
            current = advance(20.0)
            current.y -= 7.0
            _rule(current, current.y, colour=rule_colour, thickness=weight)
            current.y -= 13.0
    if furniture:
        _paint_furniture(pages, furniture, rule_colour=rule_colour,
                         weight=weight, family=body_family)
    else:
        # **The author's own footer REPLACES the default stamp**, rather
        # than both appearing. Two page numbers on one page is the kind of
        # detail that reads as a bug in the product rather than as a
        # choice, and the furniture path already offers `{n} of {of}`.
        _number(pages)
    # **Restored, because these are CLASS attributes.** A document laid out
    # after one that had furniture would otherwise inherit its bands, and
    # the symptom is a short second document with an unexplained inset --
    # state leaking between two calls that share nothing else.
    _Page.head_band = _Page.foot_band = 0.0
    return pages


def _number(pages: list[_Page]) -> None:
    """`Page n of m`, centred in the bottom margin. **Only when there is more
    than one**, because a single-page document with `Page 1 of 1` on it is
    furniture — the reader can see it is one page.

    It runs AFTER layout because the total is not knowable during it, and it
    draws INTO the margin rather than reserving column space, so adding it
    cannot reflow a document that was already fitted.
    """
    if len(pages) < 2:
        return
    for index, page in enumerate(pages, start=1):
        label = f"Page {index} of {len(pages)}"
        width = width_of(label, 8.5)
        page.ops.append(
            f"q {_rgb(RULE)} rg BT /F1 8.5 Tf "
            f"{MARGIN + (TEXT_W - width) / 2.0:.1f} {MARGIN - 26.0:.1f} Td "
            f"({_pdf_string(label)}) Tj ET Q")


def build(blocks: list[dict], theme: dict | None = None,
          furniture: dict | None = None) -> bytes:
    """Blocks -> a PDF every reader will open.

    `theme` is an optional `{"accent"|"ink"|"rule"|"heading": (r, g, b)}` —
    already PARSED, because the string the model wrote is bounded in
    `office/_colour.py` and a second parser here would be a second rule (T72).
    """
    pages = _layout(blocks, theme, furniture)

    objects: list[bytes] = []

    def add(body: str | bytes) -> int:
        objects.append(body if isinstance(body, bytes) else body.encode("cp1252",
                                                                        "replace"))
        return len(objects)

    # Object 1 is the catalog and object 2 the page tree; their numbers are
    # referenced before the pages exist, so they are reserved here.
    objects.append(b"")   # 1, catalog
    objects.append(b"")   # 2, pages
    # ══ ALL TWELVE BASE-14 FACES, ALWAYS (T75) ═══════════════════════════
    # A serif, a sans and a monospace in four weights each — the whole
    # vocabulary a document needs, and none of it embedded, so the file opens
    # identically everywhere and carries no font program. See `_faces.py` for
    # why anything beyond this is a vendoring row rather than a parameter.
    font_ids = {}
    for key, base in declarations():
        font_ids[key] = add(
            f"<< /Type /Font /Subtype /Type1 /BaseFont /{base} "
            f"/Encoding /WinAnsiEncoding >>")

    # ══ ONLY THE VENDORED FACES THIS DOCUMENT ACTUALLY USES (T76) ══════════
    # **Measured, and it is why usage tracking earns its keep here where it did
    # not for the base-14 twelve.** Declaring all four unconditionally took an
    # unstyled two-block PDF from 1,630 bytes to 93,994 — every conversion this
    # product has ever done paying 92 KB for typefaces it never asks for.
    #
    # The set is read from the CONTENT STREAMS rather than tracked alongside
    # them, so it cannot drift from what the pages reference: the ops are the
    # only authority on which face was drawn with.
    drawn = set()
    for page in pages:
        for op in page.ops:
            for token in op.split("/"):
                name = token.split(" ")[0]
                if name.startswith("F") and name[1:].isdigit():
                    drawn.add(name)

    # ══ AND THE VENDORED FACES, WHICH TAKE THREE OBJECTS EACH (T76) ═════════
    # A TrueType needs the font program, a descriptor that points at it, and
    # the font dictionary that points at THAT. **The order matters only in
    # that each must exist before it is referenced**, which is why the stream
    # is added first and its number carried forward.
    for key, face in embedded_faces():
        if key not in drawn:
            continue
        stream = zlib.compress(face.body)
        program = add(
            b"<< /Length " + str(len(stream)).encode()
            # `/Length1` is the UNCOMPRESSED size and is not optional: a
            # reader uses it to know where the font program ends, and a
            # missing or wrong one is a face that silently does not load.
            + b" /Length1 " + str(len(face.body)).encode()
            + b" /Filter /FlateDecode >>\nstream\n" + stream + b"\nendstream")
        widths = " ".join(
            str(face.width(code)) for code in range(FIRST_CHAR, LAST_CHAR + 1))
        descriptor = add(
            f"<< /Type /FontDescriptor /FontName /{face.postscript} "
            f"/Flags {face.flags} /FontBBox [{face.bbox[0]} {face.bbox[1]} "
            f"{face.bbox[2]} {face.bbox[3]}] /ItalicAngle {face.italic_angle} "
            f"/Ascent {face.ascent} /Descent {face.descent} "
            f"/CapHeight {face.cap_height} /StemV 80 "
            f"/FontFile2 {program} 0 R >>")
        font_ids[key] = add(
            f"<< /Type /Font /Subtype /TrueType /BaseFont /{face.postscript} "
            f"/FirstChar {FIRST_CHAR} /LastChar {LAST_CHAR} "
            f"/Widths [{widths}] /FontDescriptor {descriptor} 0 R "
            f"/Encoding /WinAnsiEncoding >>")

    resources = "/Font << " + " ".join(
        f"/{k} {v} 0 R" for k, v in font_ids.items()) + " >>"

    page_ids: list[int] = []
    for page in pages:
        # ══ EACH PICTURE IS AN XOBJECT, AND A JPEG GOES IN UNTOUCHED ═══════
        # `DCTDecode` means "these bytes are a JPEG": the PDF carries the
        # original file with no re-encoding, so nothing is lost and nothing is
        # spent. PDF has NO PNG filter, so a PNG is decoded to raw samples and
        # re-deflated — and anything neither is SKIPPED rather than written as
        # bytes no reader can paint.
        xobjects: list[tuple[str, int]] = []
        for name, image in page.images:
            data = getattr(image, "data", b"")
            width = getattr(image, "width", None) or 0
            height = getattr(image, "height", None) or 0
            if getattr(image, "kind", "") == "jpeg" and width and height:
                xobjects.append((name, add(
                    b"<< /Type /XObject /Subtype /Image /Width "
                    + str(width).encode() + b" /Height " + str(height).encode()
                    + b" /ColorSpace /DeviceRGB /BitsPerComponent 8"
                    b" /Filter /DCTDecode /Length " + str(len(data)).encode()
                    + b" >>\nstream\n" + data + b"\nendstream")))
                continue
            decoded = _rgb_of(data)
            if decoded is None:
                continue
            pixels, width, height = decoded
            packed = zlib.compress(pixels, 6)
            xobjects.append((name, add(
                b"<< /Type /XObject /Subtype /Image /Width "
                + str(width).encode() + b" /Height " + str(height).encode()
                + b" /ColorSpace /DeviceRGB /BitsPerComponent 8"
                b" /Filter /FlateDecode /Length " + str(len(packed)).encode()
                + b" >>\nstream\n" + packed + b"\nendstream")))

        stream = "\n".join(page.ops).encode("cp1252", "replace")
        content_id = add(b"<< /Length " + str(len(stream)).encode() +
                         b" >>\nstream\n" + stream + b"\nendstream")
        # **A `Do` naming an XObject the page does not declare paints nothing**
        # and raises no error — the same "present but not related" shape as
        # chat-R-130, in a different container format.
        xobj = (" /XObject << " + " ".join(f"/{n} {o} 0 R" for n, o in xobjects)
                + " >>") if xobjects else ""
        page_ids.append(add(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W:.0f} {PAGE_H:.0f}] "
            f"/Resources << {resources}{xobj} >> /Contents {content_id} 0 R >>"))

    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects[1] = (f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>"
                  ).encode("cp1252", "replace")

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    # A binary comment marks the file as binary for tools that sniff it.
    out.write(b"%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{number} 0 obj\n".encode())
        out.write(body)
        out.write(b"\nendobj\n")

    xref_at = out.tell()
    count = len(objects) + 1
    out.write(f"xref\n0 {count}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        # **EXACTLY 20 BYTES PER ENTRY, and the trailing space is part of it.**
        # A reader seeks by multiplication, so one short line shifts every
        # object after it and the file reads as corrupt.
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {count} /Root 1 0 R >>\n".encode())
    out.write(f"startxref\n{xref_at}\n%%EOF\n".encode())
    return out.getvalue()


def write(document: Document) -> bytes:
    """Document -> PDF."""
    blocks = []
    for block in document.blocks:
        if block.kind == "image":
            blocks.append({"type": "image", "image": block.image})
        elif block.kind == "sheet":
            if block.name:
                blocks.append({"type": "heading2", "text": block.name})
            blocks.append({"type": "table", "rows": block.rows})
        elif block.kind == "slide":
            blocks.append({"type": "heading2", "text": block.text})
            blocks.extend({"type": "bullet", "text": b} for b in block.bullets)
        elif block.kind == "table":
            blocks.append({"type": "table", "rows": block.rows})
        elif block.kind == "callout":
            # **`tone` travels or the band is a paragraph.** Every other
            # bridge here loses a field by omission rather than by
            # decision, which is how a kind arrives styled in one format
            # and plain in the next.
            blocks.append({"type": "callout", "text": block.text,
                           "tone": block.tone, "colour": block.colour})
        else:
            blocks.append({"type": block.kind, "text": block.text})
    return build(blocks)
