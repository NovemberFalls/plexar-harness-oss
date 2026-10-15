"""A minimal, valid `.pptx`. **The one the handoff said to defer, and why it isn't.**

T40 shipped without this on the handoff's advice: *"a valid deck needs slide
masters and layouts, and authoring those from scratch is where this node's time
goes."* That was the right call for one row. Len then said the product will have
**heavy users of the entire Office suite**, which changes the arithmetic — a
suite missing a third of itself is not a suite.

══ THE ELEVEN-PART CLOSURE, AND IT IS ALL-OR-NOTHING ═══════════════════════
PowerPoint repairs nothing. A deck needs, and this is the whole reason the
handoff called it hard:

    [Content_Types].xml                        every part declared, by name
    _rels/.rels                             -> ppt/presentation.xml
    ppt/presentation.xml                       masters, slide ids, slide size
    ppt/_rels/presentation.xml.rels         -> master + every slide
    ppt/slideMasters/slideMaster1.xml          the placeholder geometry
    ppt/slideMasters/_rels/...rels          -> layout AND theme
    ppt/slideLayouts/slideLayout1.xml
    ppt/slideLayouts/_rels/...rels          -> master
    ppt/theme/theme1.xml                       fonts and the colour map
    ppt/slides/slideN.xml                      one per slide
    ppt/slides/_rels/slideN.xml.rels        -> layout

**`theme1.xml` is the part everyone forgets.** It is not decoration: the master
carries a `clrMap` that resolves against the theme, and a master whose theme
relationship is missing makes the file unopenable — not ugly, unopenable. So
the gate below asserts CLOSURE rather than presence: every relationship target
resolves to a part that exists, and every part is declared in the content types.
That is the property PowerPoint actually enforces, and asserting it is what a
structural check can honestly do.

══ WHAT THIS CANNOT PROVE, STATED PLAINLY ═════════════════════════════════
`python-docx` and `openpyxl` read our `.docx` and `.xlsx` back, so those two
have an INDEPENDENT parser's opinion. **There is no equivalent here** —
`python-pptx` is not installed and adding a dependency is not this row's call.
So the deck is gated structurally, and *"it opens in real PowerPoint"* remains a
human check that has not been performed. Said out loud rather than implied by a
green suite.
"""

from __future__ import annotations

import io
import zipfile

from .._model import Document
from .._colour import hex_of, readable_on_white
from .._runs import runs
from .._xml import escape

#: 16:9 at the size PowerPoint itself uses. EMUs: 914,400 per inch.
SLIDE_W, SLIDE_H = 12_192_000, 6_858_000

A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

_HEAD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'


def _rels(entries: list[tuple[str, str, str]]) -> str:
    body = "".join(
        f'<Relationship Id="{rid}" Type="{typ}" Target="{target}"/>'
        for rid, typ, target in entries)
    return f'{_HEAD}<Relationships xmlns="{REL_NS}">{body}</Relationships>'


_T = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
REL_SLIDE = _T + "slide"
REL_MASTER = _T + "slideMaster"
REL_LAYOUT = _T + "slideLayout"
REL_THEME = _T + "theme"
REL_DOC = _T + "officeDocument"

THEME = (
    f'{_HEAD}<a:theme xmlns:a="{A_NS}" name="Plexar">'
    "<a:themeElements>"
    '<a:clrScheme name="Plexar">'
    '<a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>'
    '<a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>'
    '<a:dk2><a:srgbClr val="1F2430"/></a:dk2><a:lt2><a:srgbClr val="F2F4F7"/></a:lt2>'
    '<a:accent1><a:srgbClr val="2F6FEB"/></a:accent1>'
    '<a:accent2><a:srgbClr val="E8710A"/></a:accent2>'
    '<a:accent3><a:srgbClr val="12A150"/></a:accent3>'
    '<a:accent4><a:srgbClr val="8E4EC6"/></a:accent4>'
    '<a:accent5><a:srgbClr val="D6336C"/></a:accent5>'
    '<a:accent6><a:srgbClr val="0B7285"/></a:accent6>'
    '<a:hlink><a:srgbClr val="2F6FEB"/></a:hlink>'
    '<a:folHlink><a:srgbClr val="8E4EC6"/></a:folHlink>'
    "</a:clrScheme>"
    '<a:fontScheme name="Plexar">'
    '<a:majorFont><a:latin typeface="Calibri Light"/><a:ea typeface=""/>'
    '<a:cs typeface=""/></a:majorFont>'
    '<a:minorFont><a:latin typeface="Calibri"/><a:ea typeface=""/>'
    '<a:cs typeface=""/></a:minorFont>'
    "</a:fontScheme>"
    '<a:fmtScheme name="Plexar">'
    "<a:fillStyleLst>"
    '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
    '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
    '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
    "</a:fillStyleLst>"
    "<a:lnStyleLst>"
    + ('<a:ln w="6350"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>' * 3)
    + "</a:lnStyleLst>"
    "<a:effectStyleLst>"
    + ("<a:effectStyle><a:effectLst/></a:effectStyle>" * 3)
    + "</a:effectStyleLst>"
    "<a:bgFillStyleLst>"
    + ('<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>' * 3)
    + "</a:bgFillStyleLst>"
    "</a:fmtScheme></a:themeElements></a:theme>"
)


def _shape(sid: int, name: str, ph: str, x: int, y: int, cx: int, cy: int,
           paragraphs: str, *, idx: str = "") -> str:
    """One text shape. `ph` is the placeholder type the layout expects."""
    index = f' idx="{idx}"' if idx else ""
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{sid}" name="{escape(name)}"/>'
        '<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
        f'<p:nvPr><p:ph type="{ph}"{index}/></p:nvPr></p:nvSpPr>'
        f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
        f"<p:txBody><a:bodyPr wrap=\"square\"><a:normAutofit/></a:bodyPr>"
        f"<a:lstStyle/>{paragraphs}</p:txBody></p:sp>"
    )


def _paragraph(text: str, *, level: int = 0, bullet: bool = False,
               size: int | None = None, colour: str = "",
               align: str | None = None) -> str:
    props = [f' lvl="{level}"'] if level else []
    # ══ ALIGNMENT IS AN ATTRIBUTE HERE, NOT AN ELEMENT (T73) ════════════════
    # DrawingML spells it `algn` on `<a:pPr>`; WordprocessingML uses a child
    # `<w:jc>`. Two formats, two spellings of one idea — written out in each
    # writer rather than abstracted, because a shared helper would have to
    # know both anyway and would hide which one it got wrong.
    if align == "centre":
        props.append(' algn="ctr"')
    elif align == "left":
        props.append(' algn="l"')
    marker = "" if bullet else "<a:buNone/>"
    body = []
    for run in runs(str(text)):
        rpr = ""
        marks = ("<a:b val=\"1\"/>" if run.bold else "") + \
                ("<a:i val=\"1\"/>" if run.italic else "")
        # **THE FILL IS A CHILD OF `a:rPr`**, which is where DrawingML puts
        # text colour. There is no `val` attribute for it and no equivalent of
        # Word's `<w:color>`; a colour written as an attribute here is dropped
        # in silence and the deck opens in black.
        if colour:
            marks += f'<a:solidFill><a:srgbClr val="{colour}"/></a:solidFill>'
        attrs = f' sz="{size}"' if size else ""
        if marks or attrs:
            rpr = f'<a:rPr lang="en-US"{attrs}>{marks}</a:rPr>' if marks else \
                  f'<a:rPr lang="en-US"{attrs}/>'
        body.append(f'<a:r>{rpr}<a:t>{escape(run.text)}</a:t></a:r>')
    return (f'<a:p><a:pPr{"".join(props)}>{marker}</a:pPr>'
            f'{"".join(body)}</a:p>')


SLIDE_MASTER = (
    f'{_HEAD}<p:sldMaster xmlns:a="{A_NS}" xmlns:r="{R_NS}" xmlns:p="{P_NS}">'
    "<p:cSld><p:spTree>"
    '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
    '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
    '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
    + _shape(2, "Title Placeholder", "title", 838200, 365125,
             SLIDE_W - 1676400, 1325563, "<a:p/>")
    + _shape(3, "Text Placeholder", "body", 838200, 1825625,
             SLIDE_W - 1676400, SLIDE_H - 2360613, "<a:p/>", idx="1")
    + "</p:spTree></p:cSld>"
    # THE COLOUR MAP RESOLVES AGAINST THE THEME. A master without it, or
    # without the theme relationship beside it, is a file PowerPoint refuses.
    '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1"'
    ' accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5"'
    ' accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
    '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>'
    "</p:sldMaster>"
)

SLIDE_LAYOUT = (
    f'{_HEAD}<p:sldLayout xmlns:a="{A_NS}" xmlns:r="{R_NS}" xmlns:p="{P_NS}"'
    ' type="titleAndBody" preserve="1">'
    "<p:cSld name=\"Title and Content\"><p:spTree>"
    '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
    '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
    '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
    + _shape(2, "Title 1", "title", 838200, 365125,
             SLIDE_W - 1676400, 1325563, "<a:p/>")
    + _shape(3, "Content Placeholder 2", "body", 838200, 1825625,
             SLIDE_W - 1676400, SLIDE_H - 2360613, "<a:p/>", idx="1")
    + "</p:spTree></p:cSld>"
    '<p:clrMapOvr><a:overrideClrMapping bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2"'
    ' accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4"'
    ' accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
    "</p:clrMapOvr></p:sldLayout>"
)


#: Where a picture sits when a slide has one. **The right half**, so the title
#: and bullets keep the left and neither overlaps the other — a slide is a
#: layout, and a picture dropped at the origin lands on top of the title.
PIC_X = SLIDE_W // 2 + 152400
PIC_Y = 1825625
PIC_W = SLIDE_W - PIC_X - 838200
PIC_H = SLIDE_H - PIC_Y - 534988


def _picture(sid: int, image, rid: str, slot: int = 0, of: int = 1) -> str:
    """One picture on a slide. **`<p:pic>`, not `<p:sp>`** — a shape holds
    text, a picture holds a blip, and the two are not interchangeable.

    The aspect ratio is preserved inside the box rather than stretched to it: a
    photograph squashed to fit is worse than a smaller photograph, and the
    natural size is known because the reader carried it.
    """
    # ══ N PICTURES TILE; THEY DO NOT STACK ═══════════════════════════════
    # **Found by the gate**: every picture was placed at the same offset, so a
    # step with three photographs rendered as three photographs on top of one
    # another and looked like one. The box is divided into a grid — one column
    # for one or two, two columns beyond that — and each picture is centred in
    # its own cell.
    columns = 1 if of <= 2 else 2
    rows = (of + columns - 1) // columns
    cell_w = PIC_W // columns
    cell_h = PIC_H // rows
    col, row = slot % columns, slot // columns

    px_w = getattr(image, "width", None) or 4
    px_h = getattr(image, "height", None) or 3
    pad = 91440 if of > 1 else 0          # 0.1in of air between tiles
    scale = min((cell_w - pad) / px_w, (cell_h - pad) / px_h)
    cx, cy = max(1, int(px_w * scale)), max(1, int(px_h * scale))
    # Centred in its own cell, so differently shaped photographs still line up.
    x = PIC_X + col * cell_w + (cell_w - cx) // 2
    y = PIC_Y + row * cell_h + (cell_h - cy) // 2
    name = escape(getattr(image, "name", "") or f"Picture {sid}")
    return (
        f'<p:pic><p:nvPicPr><p:cNvPr id="{sid}" name="{name}" '
        f'descr="{escape(getattr(image, "alt", ""))}"/>'
        "<p:cNvPicPr><a:picLocks noChangeAspect=\"1\"/></p:cNvPicPr>"
        "<p:nvPr/></p:nvPicPr>"
        f'<p:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/>'
        "</a:stretch></p:blipFill>"
        f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/>'
        '</a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
        "</p:pic>"
    )


def _slide_xml(slide: dict, images: list | None = None,
               theme: dict | None = None) -> str:
    # ══ THE SAME PALETTE THE PDF AND THE DOCX GET (T73) ═════════════════════
    # Len: *"what if they want to style a docx or excel or power point?"* A
    # palette that reached only one writer would mean the same request gave him
    # a coloured PDF and a black-and-white deck, which reads as the model
    # ignoring him on one format and not the other.
    theme = theme if isinstance(theme, dict) else {}
    title_hex = hex_of(theme.get("heading") or theme.get("accent"))
    body_hex = hex_of(theme.get("ink"))
    own = slide.get("colour")
    if own is not None and readable_on_white(own):
        title_hex = hex_of(own)
    align = slide.get("align")
    title = str(slide.get("title") or "")
    bullets = slide.get("bullets")
    bullets = [b for b in bullets if str(b).strip()] if isinstance(bullets, list) else []
    notes = str(slide.get("notes") or "")

    title_body = _paragraph(title, size=3200, colour=title_hex,
                            align=align) if title else "<a:p/>"
    if bullets:
        body = "".join(_paragraph(str(b), bullet=True, size=2000,
                                  colour=body_hex, align=align)
                       for b in bullets)
    else:
        # A DECK WITH NOTHING IN THE BODY IS STILL A SLIDE. An empty `<p:txBody>`
        # with no paragraph at all is malformed, and the whole deck fails to open
        # because one slide had only a title.
        body = "<a:p/>"

    # ══ A SLIDE WITH A PICTURE GIVES IT HALF THE ROOM ═══════════════════
    # The text placeholder is narrowed rather than the picture being laid over
    # it. Two shapes on top of each other is a deck that looks broken in the
    # one place a deck is looked at.
    pictures = list(slide.get("images") or [])
    body_w = (SLIDE_W // 2 - 838200 - 152400) if pictures else (SLIDE_W - 1676400)
    shapes = (
        _shape(2, "Title 1", "title", 838200, 365125,
               SLIDE_W - 1676400, 1325563, title_body)
        + _shape(3, "Content Placeholder 2", "body", 838200, 1825625,
                 body_w, SLIDE_H - 2360613, body, idx="1")
    )
    for offset, picture in enumerate(pictures):
        if images is None:
            break
        images.append(picture)
        shapes += _picture(4 + offset, picture, f"rIdImg{len(images)}",
                           slot=offset, of=len(pictures))
    # Speaker notes are DROPPED rather than half-built: a real notes slide needs
    # its own part, its own rels and a notesMaster, and a dangling reference is
    # a file that will not open. Recorded here so the omission is a decision.
    del notes
    return (
        f'{_HEAD}<p:sld xmlns:a="{A_NS}" xmlns:r="{R_NS}" xmlns:p="{P_NS}">'
        "<p:cSld><p:spTree>"
        '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
        '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
        '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
        f"{shapes}</p:spTree></p:cSld>"
        '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>'
    )


def build(slides: list[dict], theme: dict | None = None) -> bytes:
    """Slides -> a `.pptx`. Each slide is `{title, bullets: [...]}`.

    `theme` is the same already-parsed palette the PDF and the docx take
    (T72/T73), so one `style` from the model reaches every writer."""
    slides = [s if isinstance(s, dict) else {"title": str(s)} for s in (slides or [])]
    if not slides:
        slides = [{"title": "", "bullets": []}]

    count = len(slides)
    # Slide relationships start at rId2: rId1 is the master, and an id reused
    # across two targets silently points every slide at the same part.
    pres_rels = [("rId1", REL_MASTER, "slideMasters/slideMaster1.xml")]
    pres_rels += [(f"rId{i + 2}", REL_SLIDE, f"slides/slide{i + 1}.xml")
                  for i in range(count)]
    pres_rels.append((f"rId{count + 2}", REL_THEME, "theme/theme1.xml"))

    sld_ids = "".join(
        f'<p:sldId id="{256 + i}" r:id="rId{i + 2}"/>' for i in range(count))
    presentation = (
        f'{_HEAD}<p:presentation xmlns:a="{A_NS}" xmlns:r="{R_NS}" xmlns:p="{P_NS}">'
        '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
        f"<p:sldIdLst>{sld_ids}</p:sldIdLst>"
        f'<p:sldSz cx="{SLIDE_W}" cy="{SLIDE_H}"/>'
        f'<p:notesSz cx="{SLIDE_H}" cy="{SLIDE_W}"/>'
        "</p:presentation>"
    )

    parts: dict[str, str] = {
        "_rels/.rels": _rels([("rId1", REL_DOC, "ppt/presentation.xml")]),
        "ppt/presentation.xml": presentation,
        "ppt/_rels/presentation.xml.rels": _rels(pres_rels),
        "ppt/slideMasters/slideMaster1.xml": SLIDE_MASTER,
        "ppt/slideMasters/_rels/slideMaster1.xml.rels": _rels([
            ("rId1", REL_LAYOUT, "../slideLayouts/slideLayout1.xml"),
            ("rId2", REL_THEME, "../theme/theme1.xml")]),
        "ppt/slideLayouts/slideLayout1.xml": SLIDE_LAYOUT,
        "ppt/slideLayouts/_rels/slideLayout1.xml.rels": _rels([
            ("rId1", REL_MASTER, "../slideMasters/slideMaster1.xml")]),
        "ppt/theme/theme1.xml": THEME,
    }
    # ══ EVERY PICTURE NEEDS ITS PART, ITS RELATIONSHIP AND ITS TYPE ═══════
    # chat-R-130 in a third container: a media part nothing points at is not in
    # the deck, and PowerPoint shows a placeholder rather than an error.
    media: list = []
    for i, slide in enumerate(slides, start=1):
        before = len(media)
        parts[f"ppt/slides/slide{i}.xml"] = _slide_xml(slide, media, theme)
        slide_rels = [("rId1", REL_LAYOUT, "../slideLayouts/slideLayout1.xml")]
        for n in range(before + 1, len(media) + 1):
            slide_rels.append((f"rIdImg{n}", _T + "image",
                               f"../media/image{n}.{media[n - 1].kind}"))
        parts[f"ppt/slides/_rels/slide{i}.xml.rels"] = _rels(slide_rels)

    base = "application/vnd.openxmlformats-officedocument."
    overrides = [
        ("/ppt/presentation.xml", base + "presentationml.presentation.main+xml"),
        ("/ppt/slideMasters/slideMaster1.xml", base + "presentationml.slideMaster+xml"),
        ("/ppt/slideLayouts/slideLayout1.xml", base + "presentationml.slideLayout+xml"),
        ("/ppt/theme/theme1.xml", base + "theme+xml"),
    ] + [(f"/ppt/slides/slide{i}.xml", base + "presentationml.slide+xml")
         for i in range(1, count + 1)]
    image_defaults = "".join(
        f'<Default Extension="{ext}" ContentType="image/'
        f'{"jpeg" if ext in ("jpg", "jpeg") else ext}"/>'
        for ext in sorted({img.kind for img in media}))
    parts["[Content_Types].xml"] = (
        f'{_HEAD}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        + image_defaults
        + "".join(f'<Override PartName="{p}" ContentType="{c}"/>' for p, c in overrides)
        + "</Types>"
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in parts.items():
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, data.encode("utf-8"))
        for n, img in enumerate(media, start=1):
            info = zipfile.ZipInfo(f"ppt/media/image{n}.{img.kind}",
                                   date_time=(2026, 1, 1, 0, 0, 0))
            # STORED: a JPEG is already compressed.
            info.compress_type = zipfile.ZIP_STORED
            zf.writestr(info, img.data)
    return buffer.getvalue()


def write(document: Document) -> bytes:
    """Document -> `.pptx`.

    **A document that is not already slides is CUT INTO them at its headings**,
    which is what "make this a deck" means. Prose with no headings becomes one
    slide per paragraph rather than one slide holding an essay.
    """
    slides = [b for b in document.blocks if b.kind == "slide"]
    if slides:
        return build([{"title": b.text, "bullets": b.bullets} for b in slides])

    # ══ A PROCEDURE HAS NO HEADINGS AND IS STILL A SEQUENCE OF STEPS ══════
    # **Measured on Michael's SOP**: five paragraphs, no headings, so nothing
    # ever started a new slide and all eight photographs landed on slide one.
    # When a document has no headings at all, each PARAGRAPH is a step and gets
    # its own slide — which is what a numbered procedure looks like as a deck.
    headed = any(b.kind.startswith("heading") for b in document.blocks)

    out: list[dict] = []
    current: dict | None = None
    for block in document.blocks:
        if not headed and block.kind == "paragraph":
            current = {"title": block.text, "bullets": [], "images": []}
            out.append(current)
            continue
        if block.kind.startswith("heading"):
            current = {"title": block.text, "bullets": [], "images": []}
            out.append(current)
        elif block.kind == "image":
            # **THE PICTURE JOINS THE SLIDE IT FOLLOWED IN THE SOURCE.** That
            # ordering is the whole reason a deck built from a procedure still
            # shows the right photograph beside the right step.
            if block.image is None:
                continue
            if current is None:
                current = {"title": document.title or "", "bullets": [],
                           "images": []}
                out.append(current)
            current.setdefault("images", []).append(block.image)
        elif block.kind == "table":
            if current is None:
                current = {"title": document.title or "", "bullets": [],
                           "images": []}
                out.append(current)
            current["bullets"].extend("   ".join(r) for r in block.rows[:12])
        elif block.text:
            if current is None:
                current = {"title": document.title or "", "bullets": [],
                           "images": []}
                out.append(current)
            current["bullets"].append(block.text)
    return build(out or [{"title": document.title or "", "bullets": [],
                          "images": []}])
