"""Read a `.docx` into the interchange Document — **images included**.

══ THIS IS THE HALF THAT NEVER EXISTED ═════════════════════════════════════
`chat/store/_projects.py::_docx_text` unzips `word/document.xml`, strips tags
with a regex, and returns a string. That is correct for a search index and it
is why Michael's eight photographs were invisible: the extractor never opened
`word/media/`, so nothing downstream could carry what it was never handed.

══ AND IT STILL DOES NOT PARSE XML WITH A PARSER, DELIBERATELY ═════════════
`_projects.py` rejects `xml.etree` BY NAME, on entity expansion, and that call
was right. This module inherits the ban rather than arguing with it: the body
is walked with the same bounded regex technique, because what is needed here is
ORDER — paragraph, then which images hung off it — and order is recoverable
from the tag stream without building a tree.

The handoff proposed amending the invariant (refuse any part declaring a DTD,
then parse properly). **That amendment is still worth making and is still not
made here** — it is a `chat-DEC` and it belongs to whoever needs real cell
coordinates, which is the spreadsheet reader, not this one.

══ THE BOUNDS ARE THE OLD ONES PLUS TWO ════════════════════════════════════
`MAX_DOCX_XML_BYTES` per part is unchanged. **New: a cap on the number of media
members and on total decompressed image bytes** — a `.docx` is one XML part but
an arbitrary number of pictures, and "one bounded member" does not generalise
to "unbounded members that are each bounded".
"""

from __future__ import annotations

import io
import re
import zipfile

from .._model import Block, Document, Image, image_size, sniff_image

#: One XML part. Carried over from `_projects.py` unchanged.
MAX_XML_BYTES = 24 * 1024 * 1024
#: **NEW.** A document is one body and many pictures.
MAX_IMAGES = 200
MAX_IMAGE_BYTES = 40 * 1024 * 1024

_PARA = re.compile(r"<w:p[ >].*?</w:p>", re.S)
#: ══ `<w:t` IS A PREFIX OF `<w:tab/>` AND THAT COST A REAL BUG ══════════════
#: `<w:t[^>]*>` happily matches `<w:tab/>`, so a TAB was read as the opening of
#: a TEXT run and the capture then swallowed every tag up to the next
#: `</w:t>` — markup landed in what the model reads. Caught by
#: `test_docx_extraction.py`, which predates this reader and asserts that no
#: XML tag survives. The tag name must therefore END, at a `>` or at
#: whitespace, and nowhere else.
_TEXT = re.compile(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>", re.S)
#: A tab and a line break are CONTENT, not decoration: the old stripper turned
#: them into `\t` and `\n`, and a reader that drops them flattens a two-column
#: line into one run-on string.
_TAB = re.compile(r"<w:tab\s*/>")
_BR = re.compile(r"<w:br\s*/>|<w:cr\s*/>")
_STYLE = re.compile(r'<w:pStyle\s+w:val="([^"]+)"')
_EMBED = re.compile(r'r:(?:embed|link)="([^"]+)"')
_NUMPR = re.compile(r"<w:numPr[ />]")
_ROW = re.compile(r"<w:tr[ >].*?</w:tr>", re.S)
_CELL = re.compile(r"<w:tc[ >].*?</w:tc>", re.S)
_TBL = re.compile(r"<w:tbl>.*?</w:tbl>", re.S)
_REL = re.compile(r'Id="([^"]+)"[^>]*Target="([^"]+)"')

_ENTITIES = (("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'),
             ("&apos;", "'"), ("&amp;", "&"))


def _unescape(text: str) -> str:
    for entity, char in _ENTITIES:
        text = text.replace(entity, char)
    return text


def _para_text(xml: str) -> str:
    """The text of one paragraph, **with its tabs and breaks kept as such.**

    Runs are walked in document order and the separators between them are
    preserved, so a tabbed two-column line stays two columns instead of
    becoming one run-on string.
    """
    out: list[str] = []
    for piece in re.split(r"(<w:tab\s*/>|<w:br\s*/>|<w:cr\s*/>)", xml):
        if _TAB.fullmatch(piece):
            out.append("\t")
        elif _BR.fullmatch(piece):
            out.append("\n")
        else:
            out.append("".join(_TEXT.findall(piece)))
    return _unescape("".join(out))


def _heading_of(xml: str) -> str:
    match = _STYLE.search(xml)
    if not match:
        return ""
    style = match.group(1).lower().replace(" ", "")
    for level in ("1", "2", "3"):
        if style in (f"heading{level}", f"h{level}") or \
                (style.startswith("heading") and style.endswith(level)):
            return f"heading{level}"
    if style in ("title", "subtitle"):
        return "heading1"
    return ""


def _relationships(zf: zipfile.ZipFile) -> dict[str, str]:
    try:
        raw = zf.read("word/_rels/document.xml.rels").decode("utf-8", "replace")
    except KeyError:
        return {}
    return {rid: target for rid, target in _REL.findall(raw)}


def read(data: bytes) -> Document:
    """`.docx` bytes -> a Document whose blocks are in body order."""
    document = Document(source_kind="docx")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        try:
            info = zf.getinfo("word/document.xml")
        except KeyError:
            return document
        if info.file_size > MAX_XML_BYTES:
            return document
        with zf.open(info) as member:
            body = member.read(MAX_XML_BYTES + 1)
        if len(body) > MAX_XML_BYTES:
            return document
        xml = body.decode("utf-8", "replace")
        rels = _relationships(zf)

        # ══ MEDIA IS READ LAZILY AND BOUNDED ══════════════════════════════
        # `file_size` is the archive's claim about itself and is never trusted;
        # every read is capped and the running total is capped too.
        budget = MAX_IMAGE_BYTES
        cache: dict[str, Image | None] = {}

        def media(rid: str) -> Image | None:
            nonlocal budget
            if rid in cache:
                return cache[rid]
            cache[rid] = None
            target = rels.get(rid, "")
            if not target or target.startswith(("http://", "https://")):
                # A LINKED image lives outside the file. Nothing is fetched —
                # `chat/office/` opens no sockets, and a document that could
                # make us fetch a URL is an SSRF the T1 search design refused.
                return None
            name = f"word/{target.lstrip('/')}" if not target.startswith("word/") \
                else target
            try:
                entry = zf.getinfo(name)
            except KeyError:
                return None
            if entry.file_size > budget:
                return None
            with zf.open(entry) as member:
                raw = member.read(budget + 1)
            if len(raw) > budget:
                return None
            budget -= len(raw)
            kind = sniff_image(raw)
            if not kind:
                # Not an image format we can write back out. Dropped rather
                # than carried as bytes nothing can render.
                return None
            width, height = image_size(raw)
            cache[rid] = Image(data=raw, kind=kind,
                               name=target.rsplit("/", 1)[-1],
                               width=width, height=height)
            return cache[rid]

        # ══ WALK THE BODY IN ORDER. Tables and paragraphs interleave. ══════
        pieces: list[tuple[int, str, str]] = []
        for match in _TBL.finditer(xml):
            pieces.append((match.start(), "table", match.group(0)))
        spans = [(m.start(), m.end()) for m in _TBL.finditer(xml)]
        for match in _PARA.finditer(xml):
            if any(start <= match.start() < end for start, end in spans):
                continue      # a paragraph INSIDE a table cell
            pieces.append((match.start(), "para", match.group(0)))
        pieces.sort()

        images_seen = 0
        for _, kind, chunk in pieces:
            if kind == "table":
                rows = []
                for row in _ROW.findall(chunk):
                    rows.append([_para_text(cell) for cell in _CELL.findall(row)])
                if rows:
                    document.blocks.append(Block(kind="table", rows=rows))
                continue

            text = _para_text(chunk).strip()
            if text:
                heading = _heading_of(chunk)
                block_kind = heading or ("bullet" if _NUMPR.search(chunk)
                                         else "paragraph")
                document.blocks.append(Block(kind=block_kind, text=text))
                if not document.title and block_kind.startswith("heading"):
                    document.title = text

            # **THE IMAGES OF THIS PARAGRAPH, AFTER ITS TEXT.** That ordering
            # is the entire point: a photo belongs to the step above it, and
            # that is knowable from the file rather than from looking at it.
            for rid in _EMBED.findall(chunk):
                if images_seen >= MAX_IMAGES:
                    break
                picture = media(rid)
                if picture is not None:
                    images_seen += 1
                    document.blocks.append(Block(kind="image", image=picture))

    if not document.title:
        first = next((b.text for b in document.blocks if b.text), "")
        document.title = first[:120]
    return document
