"""Read a `.pptx` into the Document. **Slide order is not slide-number order.**

`slide1.xml` is not necessarily slide 1. The order lives in `<p:sldIdLst>` in
`ppt/presentation.xml` as a list of `r:id`s, and those resolve through
`ppt/_rels/presentation.xml.rels`. A reader that sorts filenames presents a
reordered deck as the author's sequence — which reads as correct and is not.

Text is grouped by `<a:p>` so bullets stay separate lines, and the FIRST shape
carrying a title placeholder is the slide title. Speaker notes live in a
separate part and are read when present, because they are frequently where the
actual content is.
"""

from __future__ import annotations

import io
import re
import zipfile

from .._model import Block, Document

MAX_XML_BYTES = 24 * 1024 * 1024
MAX_SLIDES = 300

_SLD_ID = re.compile(r'<p:sldId[^>]*r:id="([^"]+)"')
_REL = re.compile(r'Id="([^"]+)"[^>]*Target="([^"]+)"')
_SHAPE = re.compile(r"<p:sp>.*?</p:sp>", re.S)
_PARA = re.compile(r"<a:p>.*?</a:p>|<a:p/>", re.S)
_T = re.compile(r"<a:t[^>]*>(.*?)</a:t>", re.S)
_TITLE_PH = re.compile(r'<p:ph[^>]*type="(?:ctrTitle|title)"')

_ENT = (("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'"), ("&amp;", "&"))


def _unescape(text: str) -> str:
    for a, b in _ENT:
        text = text.replace(a, b)
    return text


def _read_part(zf: zipfile.ZipFile, name: str) -> str:
    try:
        info = zf.getinfo(name)
    except KeyError:
        return ""
    if info.file_size > MAX_XML_BYTES:
        return ""
    with zf.open(info) as m:
        raw = m.read(MAX_XML_BYTES + 1)
    return "" if len(raw) > MAX_XML_BYTES else raw.decode("utf-8", "replace")


def read(data: bytes) -> Document:
    document = Document(source_kind="pptx")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        presentation = _read_part(zf, "ppt/presentation.xml")
        rels = dict(_REL.findall(_read_part(zf, "ppt/_rels/presentation.xml.rels")))
        order = [rels.get(rid, "") for rid in _SLD_ID.findall(presentation)]
        if not order:
            order = sorted(n[len("ppt/"):] for n in zf.namelist()
                           if re.fullmatch(r"ppt/slides/slide\d+\.xml", n))

        for target in order[:MAX_SLIDES]:
            if not target:
                continue
            part = target if target.startswith("ppt/") else f"ppt/{target.lstrip('/')}"
            xml = _read_part(zf, part)
            if not xml:
                continue
            title = ""
            bullets: list[str] = []
            for shape in _SHAPE.findall(xml):
                lines = []
                for para in _PARA.findall(shape):
                    text = _unescape("".join(_T.findall(para))).strip()
                    if text:
                        lines.append(text)
                if not lines:
                    continue
                if not title and _TITLE_PH.search(shape):
                    title = lines[0]
                    bullets.extend(lines[1:])
                else:
                    bullets.extend(lines)
            if not title and bullets:
                title = bullets.pop(0)

            notes_part = part.replace("ppt/slides/slide",
                                      "ppt/notesSlides/notesSlide")
            notes_xml = _read_part(zf, notes_part)
            if notes_xml:
                for para in _PARA.findall(notes_xml):
                    text = _unescape("".join(_T.findall(para))).strip()
                    # A notes slide repeats the slide number as a field; a bare
                    # numeral is that artefact and not the author's words.
                    if text and not text.isdigit() and text not in bullets:
                        bullets.append(f"(notes) {text}")
            document.blocks.append(
                Block(kind="slide", text=title, bullets=bullets))
    document.title = document.blocks[0].text if document.blocks else ""
    return document
