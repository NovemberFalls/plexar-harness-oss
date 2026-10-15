"""**THE PIVOT. `read()` -> Document -> `write()`, and `convert()` joins them.**

Len: *"when they send these things to us and we spit it back out to them, what
format do they want it in? Often it will be the same exact but sometimes they
want to convert to pdf."*

    .docx ┐                          ┌ .docx
    .xlsx ┤                          ├ .xlsx
    .pptx ┼─> read() -> Document ->  ┼ .pptx
    .csv  ┤            write()       ├ .pdf
    .txt  ┘                          └ .csv

**Five readers times five writers is twenty-five conversions if each pair is
written by hand. Through one model it is ten pieces**, and a format added later
costs one reader and one writer rather than a row of both.

══ "THE SAME EXACT" IS TWO DIFFERENT REQUESTS AND THEY MUST NOT BE CONFLATED ═
*"Give me the same file back"* is satisfied by the ORIGINAL BYTES, which are
already stored — no conversion, no fidelity loss, nothing to get wrong.
*"Same format, but change it"* is a round trip through this model and is
**REFORMATTING**: it keeps headings, paragraphs, bullets, tables and images, and
it does NOT keep fonts, colours, headers, footers, numbering definitions,
section breaks, comments or tracked changes.

`convert()` refuses to blur that. When the target equals the source and nothing
was asked to change, it says so and hands back the original rather than
producing a lossy near-copy the user would have to notice for themselves.
"""

from __future__ import annotations

import dataclasses

from dataclasses import replace

from ._chart import BadChart, Chart, parse_chart
from ._colour import parse_colour
from ._model import Block, Document, Theme

#: suffix -> the module that reads it. **Keyed on the SUFFIX**, which is what a
#: file actually carries; the product name (`word`) is the package, not the key.
READERS: dict[str, str] = {
    "docx": "word", "xlsx": "excel", "pptx": "powerpoint",
    "csv": "plaintext", "txt": "plaintext", "md": "plaintext",
    # ══ PDF JOINED THIS TABLE IN T78, AND IT IS THE LAST ASYMMETRY ═══════
    # It was the one format this product could WRITE and not READ, which made
    # it the one file a user could attach, see listed, and get nothing from.
    # A reader that RECONSTRUCTS structure from geometry is a weaker reader
    # than the OOXML three and is stated as one — `pdf/_read.py`'s header
    # lists what it does not recover. Weaker than the others is not the same
    # as absent, which is what it was.
    "pdf": "pdf",
}

#: suffix -> the module that writes it.
WRITERS: dict[str, str] = {
    "docx": "word", "xlsx": "excel", "pptx": "powerpoint",
    "pdf": "pdf", "csv": "plaintext", "txt": "plaintext",
}


class UnsupportedKind(ValueError):
    """A kind this package cannot read or write. **Names the ones it can** —
    "unsupported" with no list is a dead end for whoever reads it, which here
    is a model that will otherwise try again blind."""


def _module(name: str):
    """suffix-package -> the module object. **Imported statically, on purpose.**

    This was `importlib.import_module(f"{__package__}.{name}")` and
    `test_no_execution.py` fired on it, correctly. That gate bans anything on
    this machine that could run what a model wrote, and `importlib` is on its
    list whether or not today's argument comes from a literal dict — because
    *"it is safe, the value is ours"* is an argument that stops being true the
    first time somebody keys the table on something a caller supplies.

    A static table is also simply better: no import at call time, and the whole
    set of reachable modules is visible in one place.
    """
    from . import excel, pdf, plaintext, powerpoint, word

    return {"word": word, "excel": excel, "powerpoint": powerpoint,
            "pdf": pdf, "plaintext": plaintext}[name]


def kind_of(name: str) -> str:
    """The suffix of a filename, lowercased and without its dot."""
    return name.rsplit(".", 1)[-1].lower() if "." in (name or "") else ""


def can_read(kind: str) -> bool:
    return kind_of(f"x.{kind}") in READERS or kind in READERS


def read(data: bytes, name: str = "") -> Document:
    """Bytes -> Document, chosen by the file's suffix.

    **A kind we cannot read raises rather than returning an empty Document.**
    An empty one is indistinguishable from a document with no content, and the
    model would summarise the emptiness as if it were the file.
    """
    kind = kind_of(name)
    if kind not in READERS:
        raise UnsupportedKind(
            f"Plexar cannot read .{kind or '(no extension)'} files. "
            f"It reads: {', '.join(sorted(READERS))}.")
    document = _module(READERS[kind]).read(data)
    document.source_kind = kind
    document.source_name = name
    return document


def write(document: Document, kind: str) -> bytes:
    """Document -> bytes in `kind`."""
    kind = str(kind or "").strip().lower().lstrip(".")
    if kind not in WRITERS:
        raise UnsupportedKind(
            f"Plexar cannot write .{kind or '(none)'} files. "
            f"It writes: {', '.join(sorted(WRITERS))}.")
    return _module(WRITERS[kind]).write(document)


def convert(data: bytes, name: str, to: str) -> tuple[bytes, str, bool]:
    """`(bytes, kind, was_reformatted)`.

    **The third value is the honesty.** When the target matches the source this
    returns the ORIGINAL bytes and `False`, because the user who says *"same
    format"* almost always means *"my file back"*, and a round trip through the
    model would hand them a lossy near-copy while calling it the same thing.
    A caller that genuinely wants the reformatting asks for it explicitly.
    """
    target = str(to or "").strip().lower().lstrip(".")
    source = kind_of(name)
    if not target or target == source:
        return data, source, False
    return write(outline(read(data, name)), target), target, True


#: The longest a line may be and still be read as a heading rather than as
#: prose. Measured against the real SOP this rule was written for: its steps run
#: 27-42 characters and its shortest sentence is 96.
HEADING_CHARS = 64


def outline(document: Document) -> Document:
    """Give a structureless document a light structure. **Only if it has none.**

    ══ THIS IS AN INFERENCE, AND IT IS FENCED ON PURPOSE ════════════════════
    Len, on a converted SOP: *"Theres no centering, no headers, no
    beautification, nothing."* **Measured first: his source `.docx` has zero
    heading styles, zero bold runs and zero explicit sizes** — 15 plain
    paragraphs and 8 photographs. So nothing was lost in conversion; there was
    never anything to lose, and a faithful converter produced a flat document
    because it was handed one.

    Faithful was the right default and it is not what he wants. So this infers
    the structure a person would read into the page — but under three guards,
    because an inference that fires on a document that already has an outline
    would be *overriding the author*, which is a different and worse defect:

    * **It runs only when the document declares NO heading of its own.** A
      document with real styles is left exactly as written.
    * **The title is the first block, and only if it is short and followed by
      something.** A one-block document has no title, it has a sentence.
    * **A step heading is a SHORT line with no terminal punctuation that is
      followed by a picture.** That last clause is what keeps ordinary short
      sentences out of it: prose does not get illustrated.

    Everything it cannot be confident about stays a paragraph, which is what it
    already was — the failure mode is "no improvement", never "wrong document".
    """
    blocks = document.blocks
    if any(b.kind.startswith("heading") for b in blocks):
        return document
    out = list(blocks)
    for index, block in enumerate(out):
        if block.kind != "paragraph":
            continue
        text = (block.text or "").strip()
        if not text or len(text) > HEADING_CHARS:
            continue
        if index == 0 and len(out) > 1:
            out[index] = replace(block, kind="heading1")
            continue
        # **The picture is the evidence.** A short line that nothing
        # illustrates is just a short line.
        follows = out[index + 1] if index + 1 < len(out) else None
        if follows is not None and follows.kind == "image" \
                and text[-1] not in ".!?:;,":
            out[index] = replace(block, kind="heading2")
    return Document(blocks=out)


class MissingImage(Exception):
    """A block asked for a picture that its source does not have."""


#: How many pictures one composed document may pull in. **A bound, because the
#: reference is model-authored** — the same argument every other limit in this
#: package makes. Generous: Len's SOP is eight.
MAX_IMAGE_REFS = 60


def image_refs(blocks: object) -> list[dict]:
    """Every `{"type": "image", "source": …}` block in a model-authored spec.

    Separated from the substitution because the CALLER has to fetch the source
    documents and the caller is `api/` — the only package holding a principal.
    This function is what tells it which files to fetch, without itself knowing
    that a bucket exists.
    """
    out = []
    for block in blocks if isinstance(blocks, list) else []:
        if not isinstance(block, dict):
            continue
        if str(block.get("type") or "").strip().lower() != "image":
            continue
        if str(block.get("source") or "").strip():
            out.append(block)
    return out


def furniture_refs(spec: object) -> list[dict]:
    """Every image REFERENCE that lives in the page furniture, not the body.

    ══ A FIELD THE MODEL CANNOT REACH IS NOT A FIELD (C77d) ═════════════════
    C77c gave the PDF writer a running header that can carry a logo -- which
    is the whole point of a header on an SOP. **And nothing resolved it.**
    `resolve_images` walks `spec["blocks"]`, `image_refs` collects sources
    from the same list, so a `header.image` reference was never fetched and
    never substituted: the writer would have received the model's raw dict,
    found no `.data` on it, and drawn nothing.

    That is T43 for the fourth time in this row -- and this time I shipped it
    in the same commit that argued against it. **A capability described in a
    schema and unreachable through the code is worse than an absent one**,
    because the model will describe the logo it did not draw.

    Separate from `image_refs` rather than folded into it: that function's
    contract is "blocks in, refs out", and furniture is not a block. The
    caller composes the two, which is also what keeps `api/` the only package
    that knows a file has to be fetched.
    """
    header = (spec or {}).get("header") if isinstance(spec, dict) else None
    ref = header.get("image") if isinstance(header, dict) else None
    if not isinstance(ref, dict) or not str(ref.get("source") or "").strip():
        return []
    return [{**ref, "type": "image"}]


def resolve_furniture(spec: dict, sources: dict[str, Document]) -> dict:
    """`spec` with its header logo swapped for the real picture.

    **Refuses exactly as `resolve_images` does** -- a named source that is not
    there raises `MissingImage`, so the model is told which reference failed
    and can fix it in the same turn. Silently dropping a logo produces a
    document that is a plausible near-miss, which is the failure this
    package refuses to ship.

    A spec with no furniture logo is returned BY IDENTITY, so the common path
    allocates nothing and cannot drift.
    """
    refs = furniture_refs(spec)
    if not refs:
        return spec
    resolved = resolve_images(refs, sources)
    if not resolved:
        return spec
    out = dict(spec)
    header = dict(out.get("header") or {})
    header["image"] = resolved[0].get("image")
    out["header"] = header
    return out


def resolve_images(blocks: list[dict], sources: dict[str, Document]) -> list[dict]:
    """Swap every image REFERENCE for the real picture. **Refuses, never drops.**

    ══ THE MODEL MAY AUTHOR STRUCTURE OVER PICTURES IT CANNOT SEE (T52) ══════
    This is the join that was missing. `create_document` could lay out a styled
    document but had no way to name an image, so using it dropped every
    photograph; `convert_document` kept the photographs but could not be told
    anything about presentation. Neither verb could do what the user asked for,
    and the measurement was a pair of byte-identical PDFs (chat-R-157).

    **A reference that does not resolve raises.** The alternative — leaving the
    block out — produces a document that is a plausible near-miss of what was
    asked for: right headings, one photograph short, and nobody notices until
    the person following the procedure reaches a step with no picture. This
    package's standing rule is that a file the model can describe must exist;
    the same rule applies to what is IN it.
    """
    resolved: list[dict] = []
    used = 0
    for block in blocks if isinstance(blocks, list) else []:
        if not isinstance(block, dict):
            resolved.append(block)
            continue
        if str(block.get("type") or "").strip().lower() != "image":
            resolved.append(block)
            continue
        source = str(block.get("source") or "").strip()
        if not source:
            # An image block with no source is the model's own picture, which
            # it has no way to produce — dropped rather than raised, because
            # this is a malformed block and not a missing file.
            continue
        document = sources.get(source)
        if document is None:
            raise MissingImage(
                f"there is no file {source} in this conversation")
        images = document.images
        try:
            index = int(block.get("index"))
        except (TypeError, ValueError):
            raise MissingImage(
                f"image blocks need a whole-number 'index'; got "
                f"{block.get('index')!r}") from None
        # **1-BASED, because that is what the model was shown.** The attachment
        # block prints `[image 1: …]`, and an off-by-one here would silently
        # shift every picture in the document by one step.
        if not 1 <= index <= len(images):
            raise MissingImage(
                f"that file has {len(images)} image(s), so image {index} "
                f"does not exist")
        used += 1
        if used > MAX_IMAGE_REFS:
            raise MissingImage(
                f"a document may include at most {MAX_IMAGE_REFS} pictures")
        resolved.append({"type": "image", "image": images[index - 1]})
    return resolved


def from_blocks(blocks: list[dict]) -> Document:
    """The MODEL's own spec -> a Document. **The one place model-authored
    block dicts become the internal type**, so every writer sees the same thing
    whether the content came from a file or from a tool call."""
    document = Document()
    for raw in blocks or []:
        if not isinstance(raw, dict):
            document.blocks.append(Block(kind="paragraph", text=str(raw)))
            continue
        rows = raw.get("rows")
        document.blocks.append(Block(
            kind=str(raw.get("type") or raw.get("kind") or "paragraph"),
            text=str(raw.get("text") or ""),
            rows=[[str(c) for c in r] for r in rows
                  if isinstance(r, (list, tuple))] if isinstance(rows, list) else [],
            bullets=[str(b) for b in (raw.get("bullets") or [])
                     if isinstance(raw.get("bullets"), list)],
            name=str(raw.get("name") or ""),
            # ══ WHAT THE MODEL SAYS ABOUT THIS BLOCK'S LOOK (T72) ═══════════
            # **BOTH SPELLINGS OF THE WORD.** `color` is what a model trained
            # on the web writes; `colour` is what this codebase writes. A
            # schema that documents one and a parser that reads the other is a
            # feature that exists and never fires, and nothing would go red.
            colour=parse_colour(raw.get("color", raw.get("colour"))),
            align=_align(raw.get("align")),
            # ══ A CHART, IF THIS BLOCK IS ONE (T81) ═════════════════════════
            # **Parsed here rather than validated here.** A `BadChart` raised
            # on this path would reach a CONVERTER, whose caller is a file on
            # disk and not a model that can be told to try again — so an
            # unparseable chart becomes `None` and `Block.text` still carries
            # whatever the block said. The REFUSAL lives at the tool seam,
            # where there is somebody to refuse.
            chart=_chart_or_none(raw),
        ))
    return document


def _chart_or_none(raw: dict) -> "Chart | None":
    if str(raw.get("type") or raw.get("kind") or "").strip().lower() != "chart":
        return None
    try:
        return parse_chart(raw)
    except BadChart:
        return None


def _align(value: object) -> str | None:
    """`"center"` / `"centre"` -> `"centre"`, `"left"` -> `"left"`, else `None`.

    **`None` is "the kind decides"**, which is what keeps a heading1 centred
    and a paragraph ranged left without either having to say so. An
    unrecognised value is refused rather than guessed at, for `parse_colour`'s
    reason: a silent default is indistinguishable from a value that worked.
    """
    if not isinstance(value, str):
        return None
    folded = value.strip().casefold()
    if folded in ("center", "centre", "centred", "centered"):
        return "centre"
    if folded in ("right", "end"):
        return "right"
    if folded in ("left", "start"):
        return "left"
    return None


def theme_from(spec: object) -> Theme | None:
    """A model-authored `style` object -> a `Theme`, or `None` if it said
    nothing this package recognises.

    **`None` rather than an empty `Theme`**, so "the model did not style this"
    stays distinguishable from "the model styled it and every colour was
    rejected" — the second is worth being able to see, because it means the
    schema and the model disagree about the spelling of a colour.
    """
    if not isinstance(spec, dict):
        return None
    width = spec.get("rule_width", spec.get("rule_weight"))
    # **NOT NORMALISED HERE.** `family_of` in the PDF writer maps every name
    # the model might reach for — `Garamond`, `Arial`, `monospace` — onto the
    # family it belongs to, and doing it twice is two rules for one property.
    font = spec.get("font", spec.get("body_font"))
    heading_font = spec.get("heading_font", spec.get("headings_font"))
    theme = Theme(
        accent=parse_colour(spec.get("accent")),
        ink=parse_colour(spec.get("ink", spec.get("text"))),
        rule=parse_colour(spec.get("rule", spec.get("line"))),
        heading=parse_colour(spec.get("heading", spec.get("headings"))),
        # Both spellings, like every other field here: `subheading` is what a
        # document person writes and `heading2` is what somebody thinking in
        # block kinds writes, and refusing one of them is a silent drop.
        subheading=parse_colour(spec.get("subheading",
                                         spec.get("heading2"))),
        # **NOT COERCED HERE.** The writer clamps it, because the clamp is
        # about what a PAGE can carry and this function is about what the
        # model SAID. A number that survives to the writer unbounded is R42's
        # subject; a number bounded twice is two rules for one property.
        rule_width=width if isinstance(width, (int, float))
        and not isinstance(width, bool) else None,
        font=font if isinstance(font, str) else None,
        heading_font=heading_font if isinstance(heading_font, str) else None,
    )
    # **ENUMERATED FROM THE DATACLASS**, for the reason `office.build` now is:
    # a field added to `Theme` and forgotten in a hand-written tuple here is a
    # theme that reports itself empty and is silently discarded (T74).
    if all(getattr(theme, f.name) is None for f in dataclasses.fields(theme)):
        return None
    return theme
