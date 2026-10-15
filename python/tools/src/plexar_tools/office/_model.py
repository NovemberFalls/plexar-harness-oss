"""**THE INTERCHANGE DOCUMENT. One structure, N readers, M writers (T41).**

Len: *"not only /word but /excel /powerpoint… when they send these things to us
and we spit it back out to them, what format do they want it in? Often it will
be the same exact but sometimes they want to convert to pdf."*

That is a PIVOT, and the package was not shaped for one. T40 shipped five
WRITERS, each taking its own ad-hoc spec — `blocks` for Word, `rows` for Excel,
`slides` for PowerPoint — and the READ side was not a document reader at all:
`chat/store/_projects.py` regex-strips `<w:t>` out of a `.docx` for the search
index. **Five writers times four readers is twenty conversions if each pair is
written; through one model it is nine pieces.**

══ WHY IMAGES ARE IN THE MODEL AND NOT AN AFTERTHOUGHT ═════════════════════
Michael's tuna SOP is 728 KB of which **712 KB is photographs**. Measured, the
model saw 330 characters of it and no mention that any image existed, because
the text extractor drops `word/media/` before anything downstream can care. A
procedure for kitchen staff IS the pictures. So `Image` is a block like any
other and every reader emits it **in body order** — which is recoverable from
the file, and is why none of this needs a vision model:

    TEXT   "Remove frozen Tuna from bag"                -> image1.png
    TEXT   "Use a 1/3 pan for 2-3 bags…"                -> image2, image3
    TEXT   "Please Frozen Tuna in pan with drip insert" -> image4, image5

Each photo already sits under the step it illustrates. **The association is
structural, not visual.** A model that cannot see a pixel can still say "put
image 3 back after step 2", because it is told that is where it came from.

══ WHAT THIS MODEL DOES NOT CLAIM ══════════════════════════════════════════
**It is not a fidelity-preserving round trip and must never be described as
one.** It carries headings, paragraphs, bullets, tables, images, sheets and
slides. It does NOT carry fonts, colours, headers and footers, numbering
definitions, section breaks, comments, tracked changes or embedded objects. A
document read into this model and written back out is REFORMATTED, not
preserved — which is exactly what *"make this look good"* asked for and exactly
NOT what *"give me the same file back"* means. For the second, the original
bytes are already stored and can simply be handed over; `convert()` refuses to
pretend otherwise.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

# `_chart` imports only `_colour`, never this module, so the direction is one
# way and there is no cycle to manage.
from ._chart import Chart

#: What a block may be. **A closed set on purpose** — an open one becomes a
#: place where each writer invents its own handling and they drift.
BLOCK_KINDS = frozenset({
    "heading1", "heading2", "heading3", "paragraph", "bullet",
    "table", "image", "spacer", "sheet", "slide",
    # ══ T81 ══════════════════════════════════════════════════════════════════
    # **`image` re-uses a photograph; `chart` DRAWS.** Len asked for a chart of
    # one row of a P&L and the model spent its whole tool budget trying to put
    # a picture it had no way to make into a PDF, because this set was the
    # closed vocabulary and nothing in it drew anything.
    "chart",
    # ══ C77 ══════════════════════════════════════════════════════════════════
    # **The safety sentences went missing, not unstyled.** Len's target SOP
    # carries two full-width tinted bands with a left rule — *"Always use a
    # drip tray to keep the product out of any released liquid"* and *"Always
    # label thawed product with prep date, use-by date and employee
    # initials"*. Ours has neither, and they are the only safety-critical lines
    # in the document.
    #
    # A model with no way to SAY "this is a warning" did not fall back to a
    # paragraph — it dropped the content. That is T43's sentence again, in its
    # expensive form: a capability the model cannot address is not a
    # capability, and here the thing it could not address was a food-safety
    # instruction rather than a picture.
    #
    # ONE kind with a `tone`, not four kinds. `warning`/`caution`/`success`/
    # `note` as separate members would multiply every writer's dispatch by four
    # and make "a callout" unsayable in general — and a reader that met an
    # unknown fifth tone would have nowhere to put it.
    "callout",
})

#: What a callout may be. **`note` is the fallback and it is never a refusal**:
#: an unrecognised tone renders as a plain bordered band with the text intact,
#: because a callout whose tone we do not know is still a sentence the author
#: meant to stand out. Losing it to a spelling is the defect this kind exists
#: to end.
CALLOUT_TONES: tuple[str, ...] = ("note", "warning", "caution", "success")


@dataclass(frozen=True)
class Theme:
    """A document's palette, chosen by the MODEL rather than by this package.

    ══ THREE COLOURS, BECAUSE THAT IS WHAT THE PAGE ACTUALLY HAS (T72) ══════
    T51 picked one accent and wrote down why: *"a converter cannot know a
    company's brand, so inventing three is how a document ends up looking like
    a template somebody forgot to fill in."* **That reasoning was right about
    the DEFAULT and wrong as a ceiling.** It is still the default — a model
    that says nothing gets T51's slate — but a model that has been TOLD what
    the document is for can choose better than a constant can.

    `heading` is separate from `accent` so a document can have a coloured rule
    and black headings, or the reverse, without either implying the other.
    `None` on any field means "keep the writer's own", so a theme naming one
    colour changes one thing.
    """

    accent: tuple[float, float, float] | None = None
    ink: tuple[float, float, float] | None = None
    rule: tuple[float, float, float] | None = None
    heading: tuple[float, float, float] | None = None
    #: The SECOND heading tier (C77e). **`None` falls back to `heading`, so a
    #: document that names one heading colour looks exactly as it did.**
    #:
    #: Len's target SOP sets its numbered sections in one colour and its step
    #: headings in another -- ordinary document typography, and unsayable here:
    #: `Theme` had ONE heading colour, so `heading1`, `heading2` and `heading3`
    #: all resolved to it. Per-block `colour` could express it, at the cost of
    #: the model remembering to set it on every heading in the document, which
    #: is an instruction rather than a mechanism -- and instructions are 0-for-9
    #: in this repo. **One document-level field makes the two-tier page the
    #: cheap thing to ask for instead of the diligent thing.**
    subheading: tuple[float, float, float] | None = None
    #: `"sans"` / `"serif"` / `"mono"`, or `None` for the writer's own. **Two
    #: fields, because pairing a sans heading with a serif body is what good
    #: documents do** and one field would make it unsayable (T75).
    font: str | None = None
    heading_font: str | None = None
    #: Points. `None` keeps the writer's 0.7pt hairline. **A number, not a
    #: colour**, so it does not go through `parse_colour` — and it is on the
    #: theme rather than on a block because a document with two rule weights
    #: is a document with a mistake in it.
    rule_width: float | None = None


@dataclass(frozen=True)
class Image:
    """One picture, carried by VALUE. **The bytes travel with the document.**

    A path or an id would make the model depend on where files live, and
    `chat/office/` is not allowed to know that — `store/` is the only package
    that may. So an image is bytes plus enough to write it back out.
    """

    data: bytes
    #: `png` / `jpeg` / `gif`. Read from the CONTENT, never from the filename.
    kind: str = "png"
    name: str = ""
    #: Natural size in pixels where the source knew it. `None` means the writer
    #: chooses, which is honest — a guessed size is a distorted picture.
    width: int | None = None
    height: int | None = None
    alt: str = ""

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.data).hexdigest()[:16]

    @property
    def media_type(self) -> str:
        return f"image/{'jpeg' if self.kind in ('jpg', 'jpeg') else self.kind}"


@dataclass
class Block:
    """One piece of a document, in reading order."""

    kind: str = "paragraph"
    text: str = ""
    #: `table` only. Rows of cell strings; the first row is the header.
    rows: list[list[str]] = field(default_factory=list)
    #: `image` only.
    image: Image | None = None
    #: `slide` only — the bullets under a slide title.
    bullets: list[str] = field(default_factory=list)
    #: `sheet` only — the sheet's name; its `rows` carry the cells.
    name: str = ""
    #: `sheet` only — the WORKSHEET row number of each entry in `rows`, 1-based
    #: as Excel counts, or empty when the reader did not record them (T87g).
    #:
    #: ══ THE NUMBER WAS ALWAYS PARSED AND ALWAYS DISCARDED ═══════════════════
    #: `excel/_read.py`'s `_REF` is `r="([A-Z]+)(\\d+)"` and has been since the
    #: module existed: group 1 places the cell in its COLUMN, and **group 2 was
    #: never read by anything.** So `chat-NOTE-223` — *"rows are placed
    #: POSITIONALLY, so row 1 and row 1000 read as adjacent"* — was a defect
    #: whose fix was already sitting in the regex.
    #:
    #: **Kept beside `rows` rather than folded into them.** Putting the number
    #: in as a first cell would corrupt the grid for every other consumer: the
    #: chart renderer reads `rows[i][0]` as a category label, and a row index
    #: there would plot the numbers 1..N against themselves.
    #:
    #: Empty is a real state and means *"this reader does not know"* — every
    #: non-Excel producer of a `sheet` block, and every workbook whose cells
    #: carry no `r` at all. A consumer must not invent `i + 1` from it, which
    #: is the positional assumption this field exists to end.
    row_numbers: tuple[int, ...] = ()
    #: `chart` only. **Carried by value like `image`, and for the same reason**
    #: — `chat/office/` may not know where a file lives, so a chart travels as
    #: its own data rather than as a reference to a range in some workbook.
    chart: "Chart | None" = None
    # ══ WHAT THE MODEL MAY SAY ABOUT ONE BLOCK'S LOOK (T72) ═════════════════
    # **`None` is "the style decides", and it is not the same as a colour.**
    # Len asked for *"color-coded step headings"* and got the same three
    # constants three times, because there was nowhere for a per-block colour
    # to live. These two fields are that place.
    #
    # They are OPTIONAL by construction: a document that says nothing about
    # colour is laid out exactly as it was before this row, which is what
    # keeps every existing conversion byte-identical.
    #: An RGB triple in 0..1, or `None` to use the theme's colour for this kind.
    colour: tuple[float, float, float] | None = None
    #: `"left"`, `"centre"` or `None` for the kind's own default.
    align: str | None = None
    #: `callout` only — which of :data:`CALLOUT_TONES` this band is. Normalised
    #: rather than validated: an unknown tone becomes `note` and KEEPS its
    #: text, because the alternative is losing a sentence to a spelling.
    tone: str = "note"

    def __post_init__(self) -> None:
        self.kind = str(self.kind or "paragraph").strip().lower()
        if self.kind in ("title", "heading"):
            self.kind = "heading1"
        if self.kind in ("list", "listitem", "item"):
            self.kind = "bullet"
        # Normalised here, with the other spellings, so every producer and
        # every writer sees one of four values and none of them re-decides.
        self.tone = str(self.tone or "note").strip().lower()
        if self.tone not in CALLOUT_TONES:
            self.tone = "note"
        if self.kind not in BLOCK_KINDS:
            # **UNKNOWN BECOMES A PARAGRAPH, NEVER NOTHING.** A reader or a
            # model naming a kind we do not have must not lose its text.
            self.kind = "paragraph"


@dataclass
class Document:
    """A document, format-independent. **The only thing readers and writers
    agree on.**"""

    blocks: list[Block] = field(default_factory=list)
    title: str = ""
    #: The suffix this came from, when it came from somewhere: `docx`, `xlsx`,
    #: `pptx`, `csv`, `txt`. **Empty means the model wrote it from nothing**,
    #: and that difference decides what "the same format" means on the way out.
    source_kind: str = ""
    source_name: str = ""
    # ══ THE DOCUMENT'S OWN PALETTE (T72) ════════════════════════════════════
    # **`None` means "the writer's defaults", which is the pre-T72 look.** A
    # `Theme()` here with the same values would be indistinguishable in the
    # output and distinguishable in the code, and the difference matters when
    # asking "did the model style this document or not".
    theme: "Theme | None" = None

    @property
    def images(self) -> list[Image]:
        return [b.image for b in self.blocks if b.kind == "image" and b.image]

    @property
    def text(self) -> str:
        """Everything a search index or a preamble wants. **Images announce
        themselves** rather than being silently absent, which is the whole
        defect this row exists to end."""
        out: list[str] = []
        # ══ THE PICTURES ARE NUMBERED NOW, AND THAT IS THE WHOLE ROW (T52) ═══
        # They announced themselves and could not be POINTED AT. The model
        # could see that a photograph existed and had no way to say *"put that
        # one here"*, so the only tool that can lay out a styled document —
        # `create_document` — could never include one, and every styled
        # conversion silently dropped all eight of Len's photographs.
        #
        # **A capability the model cannot ADDRESS is not a capability**, which
        # is T43's sentence for the third time in this product. The number is
        # the address: 1-based, in body order, matching `document.images`.
        seen = 0
        for block in self.blocks:
            if block.kind == "image":
                image = block.image
                label = image.name or f"{image.kind} image" if image else "image"
                seen += 1
                out.append(f"[image {seen}: {label}]")
            elif block.kind == "table":
                for row in block.rows:
                    out.append("\t".join(str(c) for c in row))
            elif block.kind == "sheet":
                out.append(f"--- sheet {block.name!r} "
                           f"({len(block.rows)} rows)")
                # ══ EVERY ROW CARRIES ITS OWN NUMBER (T87g) ═════════════════
                # `chat-NOTE-223`: rows were emitted in reading order with
                # nothing saying which row each was, **so row 9 and row 47 read
                # as adjacent** and a model asked for "row 47" had no way to
                # find it. The number was in `_REF` all along.
                #
                # `R47\t` rather than `47\t` so a reader can tell an address
                # from a first column that happens to hold a number — which a
                # spreadsheet's first column very often does.
                #
                # **A row we could not number is printed WITHOUT a prefix**
                # rather than with its position. A position looks exactly like
                # an address and is wrong precisely when the sheet is sparse,
                # which is when somebody is asking.
                numbers = block.row_numbers or ()
                for i, row in enumerate(block.rows):
                    cells = "\t".join(str(c) for c in row)
                    number = numbers[i] if i < len(numbers) else 0
                    out.append(f"R{number}\t{cells}" if number else cells)
            elif block.kind == "chart":
                # **A chart announces itself AND its numbers** (T81), the way
                # T52's images announce themselves rather than being silently
                # absent. This text is what the search index and the attachment
                # block carry, so a chart that printed nothing here would be a
                # document the model could not later answer questions about.
                if block.chart is not None:
                    out.append(block.chart.text)
                else:
                    out.append("[chart]")
            elif block.kind == "slide":
                out.append(block.text)
                out.extend(f"- {b}" for b in block.bullets)
            elif block.text:
                out.append(block.text)
        return "\n".join(out)

    def summary(self) -> dict[str, Any]:
        """What the MODEL is told it is holding. Counted, never estimated."""
        kinds: dict[str, int] = {}
        for block in self.blocks:
            kinds[block.kind] = kinds.get(block.kind, 0) + 1
        return {"blocks": len(self.blocks), "images": len(self.images),
                "kinds": kinds, "source_kind": self.source_kind,
                "source_name": self.source_name}


def sniff_image(data: bytes) -> str:
    """`png` / `jpeg` / `gif` from the CONTENT.

    **Never from the filename.** Michael's document contains `image3.jpeg`
    beside `image2.jpg`; a writer keyed on the extension would declare two
    different content types for one format, and one of them wrong is a picture
    the reader refuses to draw.
    """
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return ""


def image_size(data: bytes) -> tuple[int | None, int | None]:
    """Pixel dimensions, from the header, with no image library.

    Only PNG and baseline/progressive JPEG are read; anything else returns
    `(None, None)` and the writer picks a size. **A guessed dimension is a
    distorted photograph**, so not knowing is reported rather than invented.
    """
    kind = sniff_image(data)
    if kind == "png" and len(data) >= 24:
        return (int.from_bytes(data[16:20], "big"),
                int.from_bytes(data[20:24], "big"))
    if kind == "jpeg":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            # SOF0..SOF15 carry the frame header; DHT/DAC/RST/SOS do not.
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                return (int.from_bytes(data[i + 7:i + 9], "big"),
                        int.from_bytes(data[i + 5:i + 7], "big"))
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            length = int.from_bytes(data[i + 2:i + 4], "big")
            if length <= 0:
                break
            i += 2 + length
    return (None, None)


#: ══ THE READER OF `Document.text`'s SHEET FORMAT, BESIDE ITS WRITER ═════════
#: `Document.text` emits `--- sheet 'Revenue' (412 rows)` and then `R7\tcell…`
#: per row (T87g). This parses that back. **It lives in this module and nowhere
#: else, because a format has exactly two halves and they must be edited
#: together** — T87a paid for the re-typed-literal shape once with
#: `ATTACHMENT_HEADERS`, T87d again with `_structure_of`'s marker, and a third
#: copy of this grammar in `api/` or `tools/` would drift the first time
#: somebody adjusts the header line.
_SHEET_LINE = re.compile(r"^--- sheet '(?P<name>.*)' \((?P<rows>\d+) rows\)$")
_ROW_LINE = re.compile(r"^R(?P<number>\d+)\t(?P<cells>.*)$", re.DOTALL)


def parse_sheets(text: str) -> list[dict]:
    """``[{name, rows: [(number, [cells])]}]`` read back out of `Document.text`.

    ══ WHY PARSE OUR OWN OUTPUT RATHER THAN KEEP THE GRID ═══════════════════
    The grid exists at extraction time and is flattened on the way into the
    index. Keeping it instead would be a second stored object per file — a new
    shape under `DEC-26`, a new thing that can be stale, and a migration for
    every file already uploaded. **The text is already stored, already scoped
    to one conversation, and since T87g already carries the row numbers**, so
    the addressing this returns costs no bytes and no new failure mode.

    That is a deliberate trade and it has a ceiling: this recovers ROWS and
    their numbers, not cell types, formulas or merges. When something needs
    those, the structured object is the row to do — not another parser.

    **A row we could not number is skipped, not renumbered.** `Document.text`
    prints such a row with no `R` prefix precisely so nothing downstream can
    present a position as an address (T87g), and inventing one here would undo
    that in the consumer.
    """
    sheets: list[dict] = []
    for line in (text or "").splitlines():
        header = _SHEET_LINE.match(line)
        if header:
            sheets.append({"name": header.group("name"), "rows": []})
            continue
        if not sheets:
            continue
        row = _ROW_LINE.match(line)
        if row:
            sheets[-1]["rows"].append(
                (int(row.group("number")), row.group("cells").split("\t")))
    return sheets
