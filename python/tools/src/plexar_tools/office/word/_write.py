"""A minimal, valid `.docx`, written with `zipfile` and nothing else.

══ THE PACKAGE IS FIVE PARTS AND EVERY ONE IS REQUIRED ═════════════════════
`[Content_Types].xml`, `_rels/.rels`, `word/_rels/document.xml.rels`,
`word/document.xml`, `word/styles.xml`. Word does not repair a package missing
any of them — it refuses to open it and says the file is corrupt, which reads
to the user as *we* corrupted it.

`styles.xml` is the one a reader assumes is optional. It is not: a paragraph
naming `Heading1` with no style of that name defined renders as body text, so
every heading in the document silently flattens.

**And it is not enough for it to be in the zip** — see `DOC_RELS`. This module
shipped it unrelated, which produced exactly the flattening described in the
paragraph above it.

══ WHAT IS DELIBERATELY NOT HERE ═══════════════════════════════════════════
No images, no numbering.xml, no theme, no settings.xml. Bullets are rendered as
a literal `•` in an indented paragraph rather than as a real list, because a
real list needs `numbering.xml` with abstract and concrete numbering
definitions, and a malformed one makes the whole document unopenable. **A
document that opens with simple bullets beats a document that does not open.**
That is the same call the handoff made about native Excel charts.
"""

from __future__ import annotations

import io
import zipfile

from .._colour import hex_of, readable_on_white
from .._model import Document
from .._runs import Run, runs
from .._xml import escape

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""

RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

#: ══ THE DOCUMENT MUST RELATE TO ITS STYLES, AND IT DID NOT ═════════════════
#: `styles.xml` was in the package and declared in `[Content_Types].xml`, and
#: **nothing pointed at it**. A part that is present but related to nothing is
#: not part of the document: every `Heading1` resolved to Normal and every
#: heading rendered as body text — the exact silent flattening the module
#: docstring warns about, shipped by the module that warns about it.
#:
#: **Found by `python-docx`, not by us.** Our own reader concatenates `<w:t>`
#: and never looks at a style, so it was green; the zip was valid, every part
#: parsed, and the round trip passed. Only a parser that resolves the object
#: model could see it. That is the argument for gating against a third party.
DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""


def _style(sid: str, name: str, size_half_pt: int, bold: bool, outline: int) -> str:
    return (
        f'<w:style w:type="paragraph" w:styleId="{sid}">'
        f'<w:name w:val="{name}"/><w:basedOn w:val="Normal"/><w:qFormat/>'
        f'<w:pPr><w:outlineLvl w:val="{outline}"/>'
        f'<w:spacing w:before="240" w:after="120"/></w:pPr>'
        f'<w:rPr>{"<w:b/>" if bold else ""}'
        f'<w:sz w:val="{size_half_pt}"/><w:szCs w:val="{size_half_pt}"/></w:rPr>'
        f'</w:style>'
    )


STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
    '<w:name w:val="Normal"/><w:qFormat/></w:style>'
    + _style("Heading1", "heading 1", 40, True, 0)
    + _style("Heading2", "heading 2", 32, True, 1)
    + _style("Heading3", "heading 3", 26, True, 2)
    + "</w:styles>"
)


def _run_xml(run: Run, colour: str = "") -> str:
    props = ""
    if run.bold:
        props += "<w:b/>"
    if run.italic:
        props += "<w:i/>"
    # ══ THE COLOUR IS A RUN PROPERTY, NOT A PARAGRAPH ONE (T73) ═════════════
    # Word colours TEXT, so `<w:color>` belongs in `<w:rPr>` beside bold and
    # italic. Put on `<w:pPr>` it is silently ignored — a valid document that
    # opens in Word with none of the colour asked for, which is the same
    # invisible failure the PDF had before T72.
    if colour:
        props += f'<w:color w:val="{colour}"/>'
    rpr = f"<w:rPr>{props}</w:rPr>" if props else ""
    # `xml:space="preserve"` or Word eats leading and trailing spaces, which
    # welds the last word of one run to the first word of the next.
    return f'<w:r>{rpr}<w:t xml:space="preserve">{escape(run.text)}</w:t></w:r>'


def _para(text: str, *, style: str = "", indent: int = 0, prefix: str = "",
          colour: str = "", align: str | None = None) -> str:
    parts = []
    if style:
        parts.append(f'<w:pStyle w:val="{style}"/>')
    if indent:
        parts.append(f'<w:ind w:left="{indent}"/>')
    # **Alignment IS a paragraph property**, which is why it sits here and the
    # colour does not: `<w:jc>` is about the block of text, `<w:color>` is
    # about the glyphs. Two properties, two homes, and putting either in the
    # other's is a document that opens fine and ignores you.
    if align == "centre":
        parts.append('<w:jc w:val="center"/>')
    elif align == "left":
        parts.append('<w:jc w:val="left"/>')
    ppr = f"<w:pPr>{''.join(parts)}</w:pPr>" if parts else ""
    body = ""
    if prefix:
        body += _run_xml(Run(prefix), colour)
    body += "".join(_run_xml(r, colour) for r in runs(text))
    return f"<w:p>{ppr}{body}</w:p>"


def _table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    grid = "".join('<w:gridCol w:w="2400"/>' for _ in range(width))
    out = [
        "<w:tbl><w:tblPr>"
        '<w:tblBorders>'
        + "".join(f'<w:{e} w:val="single" w:sz="4" w:color="999999"/>'
                  for e in ("top", "left", "bottom", "right", "insideH", "insideV"))
        + "</w:tblBorders></w:tblPr>"
        f"<w:tblGrid>{grid}</w:tblGrid>"
    ]
    for index, row in enumerate(rows):
        cells = []
        for column in range(width):
            value = row[column] if column < len(row) else ""
            # The header row is bolded by POSITION, which is a presentation
            # choice; the text itself is never altered.
            marked = f"**{value}**" if index == 0 and value else value
            cells.append(
                '<w:tc><w:tcPr><w:tcW w:w="2400" w:type="dxa"/></w:tcPr>'
                f"{_para(str(marked))}</w:tc>"
            )
        out.append(f"<w:tr>{''.join(cells)}</w:tr>")
    out.append("</w:tbl>")
    # A table must be followed by a paragraph or Word considers the body
    # malformed when the table is the last element.
    return "".join(out) + "<w:p/>"


#: What a block may be. **Anything else is rendered as a paragraph** rather
#: than dropped — an unknown `type` from the model must not lose its text.
HEADINGS = {"heading1": "Heading1", "heading2": "Heading2", "heading3": "Heading3",
            "title": "Heading1", "heading": "Heading1"}

#: A callout's ink and wash as Word hex, and the mark that carries the tone on
#: a monochrome printer. **The same four tones the PDF writer knows** — two
#: tables that must agree is how one format ends up with a tone the other has
#: never heard of (T73's rule, one kind over).
CALLOUT_HEX = {"note": "1C334F", "warning": "B04A0F",
               "caution": "B04A0F", "success": "1A6640"}
CALLOUT_FILL = {"note": "EAEEF3", "warning": "FBEDE4",
                "caution": "FBEDE4", "success": "E5F0EA"}
CALLOUT_MARK = {"note": "i", "warning": "!", "caution": "!", "success": "*"}


def _callout(text: str, *, ink: str, fill: str, mark: str) -> str:
    """A one-cell table: left bar, wash, and the text in the tone's ink.

    **Not a shaded paragraph.** Word will keep a paragraph's shading but there
    is no paragraph-level left bar, and the bar is what makes the band read as
    an aside rather than as a sentence somebody highlighted. A single-cell
    table is how Word's own callouts are built, so this survives being opened,
    edited and saved rather than being flattened on the first round trip.
    """
    borders = ('<w:tcBorders>'
               f'<w:left w:val="single" w:sz="18" w:color="{ink}"/>'
               '<w:top w:val="nil"/><w:bottom w:val="nil"/>'
               '<w:right w:val="nil"/></w:tcBorders>')
    return (
        '<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="pct"/>'
        '<w:tblBorders>'
        + "".join(f'<w:{e} w:val="nil"/>'
                  for e in ("top", "bottom", "right", "insideH", "insideV"))
        + f'<w:left w:val="single" w:sz="18" w:color="{ink}"/>'
        '</w:tblBorders></w:tblPr>'
        '<w:tblGrid><w:gridCol w:w="9360"/></w:tblGrid>'
        '<w:tr><w:tc><w:tcPr><w:tcW w:w="9360" w:type="dxa"/>'
        f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>'
        f'{borders}</w:tcPr>'
        + _para(f"**{mark}  {text}**", colour=ink)
        + "</w:tc></w:tr></w:tbl><w:p/>")


def body_xml(blocks: list[dict], media: list | None = None,
             theme: dict | None = None) -> str:
    """Blocks -> body XML. `media` collects the images that were placed, in
    order, so `build` can write the parts and the relationships that make them
    appear. **A picture referenced with no relationship is a red X.**"""
    # ══ THE SAME PALETTE THE PDF GETS (T73) ═════════════════════════════════
    # Len: *"what if they want to style a docx or excel or power point?"* T72
    # gave the model a palette and only the PDF read it, so the same request
    # produced a coloured PDF and a black-and-white Word file — which is a
    # worse state than no styling at all, because it looks like the model
    # ignored him on one format and not the other.
    theme = theme if isinstance(theme, dict) else {}
    heading_hex = hex_of(theme.get("heading") or theme.get("accent"))
    # The second heading tier (C77e), falling back to the first so a theme
    # naming one heading colour produces the file it produced before.
    sub_hex = hex_of(theme.get("subheading")) or heading_hex
    ink_hex = hex_of(theme.get("ink"))
    out = []
    for block in blocks or []:
        if not isinstance(block, dict):
            out.append(_para(str(block)))
            continue
        kind = str(block.get("type") or "paragraph").strip().lower()
        text = block.get("text") or ""
        own = block.get("colour")
        # The block's own colour, then the palette's for this ROLE, then
        # nothing — which leaves Word's own default and is the pre-T73 file.
        chosen = hex_of(own) if own is not None and readable_on_white(own) else ""
        align = block.get("align")
        if kind == "image" and media is not None and block.get("image") is not None:
            image = block["image"]
            media.append(image)
            index = len(media)
            out.append(_drawing(index, image, f"rIdImg{index}"))
            continue
        if kind == "table":
            rows = block.get("rows") or []
            out.append(_table([[str(c) for c in (r or [])] for r in rows
                               if isinstance(r, (list, tuple))]))
        elif kind in HEADINGS:
            out.append(_para(str(text), style=HEADINGS[kind],
                             colour=chosen or (sub_hex if kind in
                                               ("heading2", "heading3")
                                               else heading_hex),
                             align=align))
        elif kind in ("bullet", "list", "listitem", "item"):
            out.append(_para(str(text), indent=360, prefix="•  ",
                             colour=chosen or ink_hex, align=align))
        elif kind == "callout":
            # ══ WORD HAS NO CALLOUT, SO IT IS A ONE-CELL TABLE (C77) ═════════
            # A shaded paragraph would lose the left bar, and the bar is what
            # makes the band read as an aside rather than as a highlighted
            # sentence. A single-cell table with a left border and a fill is
            # how Word's own callouts are built, and it survives a round trip
            # through Word rather than being flattened on first save.
            tone = str(block.get("tone") or "note").strip().lower()
            ink = CALLOUT_HEX.get(tone, CALLOUT_HEX["note"])
            out.append(_callout(str(text), ink=chosen or ink,
                                fill=CALLOUT_FILL.get(tone,
                                                      CALLOUT_FILL["note"]),
                                mark=CALLOUT_MARK.get(tone, "i")))
        elif kind in ("spacer", "break"):
            out.append("<w:p/>")
        else:
            out.append(_para(str(text), colour=chosen or ink_hex, align=align))
    return "".join(out) or "<w:p/>"


#: EMU per pixel at 96 dpi. Word measures in English Metric Units; a picture
#: sized in pixels and written as EMU without this factor is 9,525 times too
#: small, which renders as an invisible dot rather than as an error.
EMU_PER_PX = 9525
#: The widest a picture may be laid out: the text column of a Letter page with
#: one-inch margins. A 4,000px photo at natural size runs off the page.
MAX_IMAGE_EMU = int(6.5 * 914400)


def _drawing(index: int, image, rid: str) -> str:
    """One inline picture. **The `r:embed` is what makes it appear** — a
    `<w:drawing>` whose relationship is missing renders as a red X with a
    "the linked image cannot be displayed" caption."""
    px_w = image.width or 600
    px_h = image.height or 400
    cx = px_w * EMU_PER_PX
    cy = px_h * EMU_PER_PX
    if cx > MAX_IMAGE_EMU:
        cy = int(cy * MAX_IMAGE_EMU / cx)
        cx = MAX_IMAGE_EMU
    name = escape(image.name or f"image{index}")
    return (
        "<w:p><w:r><w:drawing>"
        f'<wp:inline distT="0" distB="0" distL="0" distR="0">'
        f'<wp:extent cx="{cx}" cy="{cy}"/>'
        f'<wp:docPr id="{index}" name="{name}" descr="{escape(image.alt)}"/>'
        "<a:graphic xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\">"
        '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        f'<pic:nvPicPr><pic:cNvPr id="{index}" name="{name}"/><pic:cNvPicPr/>'
        "</pic:nvPicPr>"
        f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/>'
        "</a:stretch></pic:blipFill>"
        f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
        "</pic:pic></a:graphicData></a:graphic></wp:inline>"
        "</w:drawing></w:r></w:p>"
    )


def build(blocks: list[dict], theme: dict | None = None) -> bytes:
    """Blocks -> a `.docx` a real Word will open.

    `theme` is the same already-parsed `{"accent"|"ink"|"rule"|"heading":
    (r, g, b)}` the PDF writer takes (T72/T73), so one palette from the model
    reaches both formats and they cannot disagree about it."""
    media: list = []
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document '
        'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        f"<w:body>{body_xml(blocks, media, theme)}"
        '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/>'
        "</w:sectPr></w:body></w:document>"
    )
    # ══ EVERY PICTURE NEEDS THREE THINGS OR IT DOES NOT APPEAR ═══════════
    # the part, a relationship from the document to it, and a content-type
    # declaration for its extension. Missing any one is a red X, and chat-R-130
    # is this lane already learning that a part nothing points at is not part
    # of the document.
    extra_rels = "".join(
        f'<Relationship Id="rIdImg{i}" Type="http://schemas.openxmlformats.org/'
        f'officeDocument/2006/relationships/image" Target="media/image{i}.'
        f'{img.kind}"/>'
        for i, img in enumerate(media, start=1))
    doc_rels = DOC_RELS.replace("</Relationships>", extra_rels + "</Relationships>")
    seen_ext = {img.kind for img in media}
    defaults = "".join(
        f'<Default Extension="{ext}" ContentType="image/'
        f'{"jpeg" if ext in ("jpg", "jpeg") else ext}"/>'
        for ext in sorted(seen_ext))
    content_types = CONTENT_TYPES.replace(
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>' + defaults)

    buffer = io.BytesIO()
    # DEFLATED and a fixed date: two builds of the same blocks are the same
    # bytes, which is what makes a round-trip gate meaningful.
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in (("[Content_Types].xml", content_types),
                           ("_rels/.rels", RELS),
                           ("word/_rels/document.xml.rels", doc_rels),
                           ("word/document.xml", document),
                           ("word/styles.xml", STYLES)):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, data.encode("utf-8"))
        for i, img in enumerate(media, start=1):
            info = zipfile.ZipInfo(f"word/media/image{i}.{img.kind}",
                                   date_time=(2026, 1, 1, 0, 0, 0))
            # STORED, not deflated: a JPEG is already compressed and deflating
            # it again costs time to make the file marginally larger.
            info.compress_type = zipfile.ZIP_STORED
            zf.writestr(info, img.data)
    return buffer.getvalue()


def write(document: Document) -> bytes:
    """Document -> `.docx`. **The one entry point the pivot calls.**

    `build()` still takes the dict shape the model emits; this adapts the
    internal type onto it so a file read from disk and a tool call from the
    model reach the same writer.
    """
    blocks = []
    for block in document.blocks:
        if block.kind == "image":
            blocks.append({"type": "image", "image": block.image})
        elif block.kind == "sheet":
            # A workbook written as a document becomes its tables, with the
            # sheet name as a heading — the alternative is silently dropping
            # every cell because "a sheet is not a paragraph".
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
