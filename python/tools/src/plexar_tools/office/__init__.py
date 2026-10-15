"""**N4 — Chat can write a document, not only read one (T40).**

Len, twice, on the same file: *"Can you modify it and deliver it back to me"*
and then *"Well where is the docx?"* Reading was already built — a `.docx`
uploads and `_extract_text` pulls its words out, which is why the model could
summarise his Olo amendment accurately. **Writing did not exist**, so the model
offered a download it could not produce and then said *"we can't actually send
files"*, which is wrong in the other direction: any fenced block already gets a
download (DEC-39(b)). It had no way to know either fact.

══ THIS PACKAGE HOLDS NO BUCKET, NO SESSION AND NO ROUTE ═══════════════════
It turns a spec into BYTES. `store/` is the only package permitted to know a
bucket exists, so the tool that calls this returns the bytes and `api/` does
the upload — the same boundary `upstream/` and `store/` already keep, and the
reason `chat/tools/` can stay a pure registry.

══ NO NEW DOWNLOAD ROUTE, DELIBERATELY ═════════════════════════════════════
`_file_download` already serves stored files with `Content-Disposition:
attachment`, an ASCII-sanitised name, `nosniff`, and `application/octet-stream`
**unconditionally**. That last one is a decision, not an omission — the browser
may not upgrade our declared type to something executable by guessing — so this
row does NOT teach it per-kind MIME types. A generated file is delivered by
exactly the machinery an uploaded one is.

══ WHAT IS NOT BUILT, AND WHY EACH ═════════════════════════════════════════
* **Speaker notes on a `.pptx`.** A notes slide needs its own part, its own
  relationships and a notesMaster; a dangling reference is a deck that will not
  open, so notes are dropped rather than half-built.
* ~~**A native Excel chart**~~ — **BUILT IN T81, and the reason it was refused
  is still true, so read it before touching `excel/`.** *"A malformed
  `chart1.xml` makes the ENTIRE workbook unopenable, which is a worse failure
  than no chart."* That is a sharper failure mode than anything else in this
  package: a bad heading is a bad heading, a bad chart part is a file Excel
  refuses to open at all. What changed is not the risk assessment but what it
  is measured against — Len asked for a chart off a spreadsheet and got three
  tool refusals and no file, so "values-only workbooks are useful on their own"
  stopped being an answer to the question being asked. The gate is a real
  reader loading every generated workbook, because a source scan cannot tell a
  valid chart part from a plausible one.
* **A round-trip that preserves the ORIGINAL document's formatting.** What is
  built writes a NEW document from text. Editing a `.docx` in place — keeping
  its styles, headers and numbering — means reading and rewriting parts we do
  not parse. Say so plainly to the user rather than implying an edit.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from ._chart import (Axis, BadChart, Chart, Series, fraction, nice_axis,
                     parse_chart, tick_labels)
from . import _template
from ._model import BLOCK_KINDS, Block, Document, Image
from ._colour import parse_colour
from ._pivot import (READERS, WRITERS, MissingImage, convert, from_blocks,
                     furniture_refs, image_refs, kind_of, outline, read,
                     resolve_furniture, resolve_images,
                     theme_from, write)
from ._pivot import UnsupportedKind as _PivotUnsupported
from ._xml import clean, escape
from .excel._read import FORMULA_UNSET
from .excel._write import xlsx_bytes
from .html._write import build as _html_build
from .pdf._write import build as _pdf_build
from .plaintext import csv_bytes
from .powerpoint._write import build as _pptx_build
from .word._write import build as _docx_build

#: kind -> (suffix, the type we DECLARE at upload). The declared type is stored
#: on the record and shown to the user; it is never what the download serves.
KINDS: dict[str, tuple[str, str]] = {
    "docx": (".docx",
             "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "xlsx": (".xlsx",
             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "pptx": (".pptx",
             "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    "pdf": (".pdf", "application/pdf"),
    "csv": (".csv", "text/csv"),
    # ══ HTML IS A FILE NOW, AND IT IS SELF-CONTAINED (T81) ═══════════════════
    # **It cannot use the artifact shelf.** `/lib/chart.umd.js` resolves only on
    # the artifact origin, and a generated file is served as an attachment from
    # Chat's — so a downloaded document referencing it would render a blank box
    # on the user's own disk, which is C50's defect with the CDN swapped for us.
    # Charts in this kind are therefore INLINE SVG: no script, no request, and
    # it still draws when the file is opened from a thumb drive in five years.
    "html": (".html", "text/html"),
}


#: ONE exception for the whole package. `_pivot` raises it and `build()` raises
#: it, so a caller catches a single type whether it was reading or writing.
UnsupportedKind = _PivotUnsupported


@dataclass(frozen=True)
class Generated:
    """Bytes plus the two facts the uploader needs. No path, no id, no owner —
    this package does not know where files live."""

    name: str
    declared_type: str
    body: bytes

    @property
    def size(self) -> int:
        return len(self.body)


def safe_name(name: object, kind: str) -> str:
    """A filename with the right suffix and nothing hostile in it.

    `Projects.upload`'s own `clean_name` is the authority and runs after this;
    this exists so the name the MODEL chose cannot arrive with a directory
    separator or a control character in the first place, and so the suffix
    matches the bytes. **A `.docx` called `report.txt` is a file the user's
    machine opens with the wrong application.**
    """
    suffix = KINDS[kind][0]
    text = clean(name).strip().replace("\\", "-").replace("/", "-")
    text = "".join(c for c in text if c.isprintable()).strip(". ")
    if not text:
        text = "document"
    lowered = text.lower()
    if lowered.endswith(suffix):
        text = text[: -len(suffix)]
    return f"{text[:80]}{suffix}"


def _styled(block: object) -> object:
    """One model-authored block with its look turned into values (T72).

    **Both spellings of colour, and alignment normalised**, in the one place
    both writers pass through. The alternative — each writer reading the raw
    dict — is two parsers for one field, and the second one to be written is
    the one that forgets `color`.

    A block that says nothing about its look is returned UNCHANGED, by
    identity, so the default path allocates nothing and cannot drift.
    """
    if not isinstance(block, dict):
        return block
    raw_colour = block.get("color", block.get("colour"))
    raw_align = block.get("align")
    # `size`, `bold`, `italic` and `font` are read straight off the block by
    # the PDF writer — they are already a number, a boolean and a family name,
    # so there is nothing to normalise and no second spelling to reconcile.
    # Only the colour needs parsing and only alignment needs a vocabulary.
    if raw_colour is None and raw_align is None:
        return block
    out = dict(block)
    parsed = parse_colour(raw_colour) if isinstance(raw_colour, str)         else (raw_colour if isinstance(raw_colour, tuple) else None)
    if parsed is None:
        out.pop("colour", None)
    else:
        out["colour"] = parsed
    out["align"] = _align_of(raw_align)
    return out


def _furniture(spec: dict) -> dict | None:
    """The running header and footer the model asked for, or `None` (C77).

    **`None` and an empty dict are the same to the writer and different
    here**: a spec that says nothing about furniture must produce the file
    it produced before this row, byte for byte, and the writer only reserves
    a band when something will be drawn in it.

    A header IMAGE is resolved the same way a body image is, through the
    already-resolved block list -- this function never learns where a file
    lives, which is `store/`'s business and not this package's.
    """
    header = spec.get("header")
    footer = spec.get("footer")
    out: dict = {}
    if isinstance(header, dict):
        kept = {k: header[k] for k in ("left", "right", "image")
                if header.get(k)}
        if kept:
            out["header"] = kept
    elif isinstance(header, str) and header.strip():
        # A bare string is the commonest thing a model writes. Read as the
        # RIGHT slot, which is where a document class ("SOP") belongs and
        # where the left is reserved for a mark.
        out["header"] = {"right": header.strip()}
    if isinstance(footer, dict):
        kept = {k: footer[k] for k in ("left", "right", "pages")
                if footer.get(k)}
        if kept:
            out["footer"] = kept
    elif isinstance(footer, str) and footer.strip():
        out["footer"] = {"right": footer.strip()}
    return out or None


def _align_of(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    folded = value.strip().casefold()
    if folded in ("center", "centre", "centred", "centered"):
        return "centre"
    if folded in ("right", "end"):
        return "right"
    return "left" if folded in ("left", "start") else None


def build(kind: object, name: object, spec: dict) -> Generated:
    """`kind` + a spec -> bytes. **The only entry point.**

    `spec` is what the model wrote, so every read of it is defensive: a missing
    key is an empty document, never an exception that reaches the tool loop as
    an unexplained failure.
    """
    key = str(kind or "").strip().lower().lstrip(".")
    if key not in KINDS:
        raise UnsupportedKind(
            f"{key or '(none)'} is not a document kind Plexar can write. "
            f"Supported: {', '.join(sorted(KINDS))}."
        )
    spec = spec if isinstance(spec, dict) else {}
    # ══ THE TEMPLATE RUNS BEFORE ANYTHING READS THE SPEC (C78) ══════════════
    # It supplies furniture and a palette, so it must run before `theme_from`
    # and before the furniture is collected -- otherwise a template's style
    # would be parsed as `None` and its header would never be seen. Returned
    # BY IDENTITY when no template was named, so the default path is unchanged.
    spec = _template.apply(spec.get("template"), spec)
    theme = theme_from(spec.get("style"))
    # **EVERY FIELD OF THE THEME, ENUMERATED FROM THE DATACLASS.** The list was
    # hand-written and `rule_width` was added to `Theme` without reaching here,
    # so the whole feature was parsed, stored and dropped one line before the
    # writer — T72's own defect, in T72's own plumbing (T74).
    palette = {f.name: getattr(theme, f.name)
               for f in dataclasses.fields(theme)} if theme else None
    if key in ("docx", "pdf", "html"):
        blocks = spec.get("blocks")
        blocks = blocks if isinstance(blocks, list) else []
        # ══ THE MODEL'S OWN PALETTE REACHES THE WRITER (T72) ════════════════
        # Parsed HERE rather than inside the writer, so the string the model
        # wrote is bounded in exactly one place (`_colour.parse_colour`) and
        # the writer only ever sees numbers. `None` means it said nothing
        # recognisable, and the writer keeps T51's defaults.
        # ══ THE MODEL'S STRINGS BECOME NUMBERS HERE, ONCE (T72) ═════════════
        # **Found by the gate, and it is the whole reason for this function.**
        # `from_blocks` already maps `color` -> `colour` and parses it — and
        # this path does not go through `from_blocks`, it hands the model's raw
        # dicts straight to a writer. So the writer looked for `colour` and the
        # model had written `color`, and every per-block colour was silently
        # dropped while the schema advertised it. A feature that exists, never
        # fires, and reddens nothing.
        blocks = [_styled(b) for b in blocks]
        # **Three writers, one already-normalised block list** (T81). `html`
        # joins `docx` and `pdf` here rather than getting its own branch,
        # because the thing that must not diverge is `_styled` — a fourth
        # writer reading raw dicts would rediscover the `color`/`colour` defect
        # this function was extracted to end.
        body = (_docx_build(blocks, palette) if key == "docx"
                else _html_build(blocks, palette) if key == "html"
                else _pdf_build(blocks, palette, _furniture(spec)))
    elif key == "pptx":
        slides = spec.get("slides")
        # **THE PALETTE REACHES THE DECK TOO (T73).** `slides` are dicts the
        # model wrote, so they go through `_styled` for the same reason blocks
        # do: `color` is the spelling it uses and `colour` is the one the
        # writers read.
        slides = [_styled(s) for s in (slides if isinstance(slides, list) else [])]
        body = _pptx_build(slides, palette)
    else:
        rows = spec.get("rows")
        rows = [list(r) for r in rows if isinstance(r, (list, tuple))] \
            if isinstance(rows, list) else []
        # ══ CSV CANNOT BE STYLED, AND THAT IS A FACT ABOUT THE FORMAT ═══════
        # A `.csv` is rows of text with commas between them. There is nowhere
        # for a colour to live, so `style` is IGNORED rather than half-honoured
        # — and the schema says so, because a field that is silently dropped is
        # the same lie as a control that does nothing (T10).
        # ══ A SPREADSHEET MAY CARRY CHARTS, AND THEY ARRIVE IN `blocks` (T81) ══
        # **`rows` is the sheet and `blocks` is where a chart lives**, so an
        # xlsx is the one kind that reads both. The chart materialises its own
        # numbers into cells below `rows` and the native chart part points at
        # them — which is what makes it a chart the user can click and
        # re-point, rather than a picture of one.
        #
        # Filtered here rather than passed whole: `xlsx_bytes` should not have
        # to know that a paragraph exists.
        charts = [b for b in (spec.get("blocks") or [])
                  if isinstance(b, dict)
                  and str(b.get("type") or b.get("kind") or "").strip().lower()
                  == "chart"] if key == "xlsx" else []
        body = (csv_bytes(rows) if key == "csv"
                else xlsx_bytes(rows, sheet=str(spec.get("sheet") or "Sheet1"),
                                theme=palette, charts=charts or None))
    return Generated(name=safe_name(name, key), declared_type=KINDS[key][1], body=body)


__all__ = ["Generated", "KINDS", "MissingImage", "UnsupportedKind",
           "build", "furniture_refs", "image_refs", "outline",
           "resolve_furniture", "resolve_images", "safe_name",
           "theme_from",
           "clean", "escape"]


__all__ += ["Block", "Document", "Image", "READERS", "WRITERS", "convert",
            "from_blocks", "kind_of", "read", "write"]
