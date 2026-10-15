"""The work Chat's `App` does after ownership resolution, without the resolution.

Each function takes the `ToolResult` a tool module's handler returned (through
`Registry.run`) plus the caller-supplied document text or file bytes, and returns
the `ToolResult` Chat's `App._read_attached`, `_find_attached`, `_query_attached`
and the conversion arm of `_attach_generated` produce today. The sentences are
copied from `plexar-chat/chat/api/_app.py`; only the resolution step
(`_resolve_attached`: store, principal, conversation, file id) is removed, because
the caller has already resolved the file and passes its name and text.

Differences from Chat, all decided under chat-DEC-397:

* `read_file` has no per-turn budget here. `READ_BUDGET_PER_TURN` is cross-call
  state owned by the conversation, so Chat's client keeps it; the server bounds
  one call to `READ_WINDOW` characters.
* `read_file`'s substitution disclosure compares `source` with the document name
  and its stem only; the file id is Chat's and never reaches the server.
  `extra.read_span` carries `start`, `end`, `total` and no `file_id`.
* `create_document` stores nothing and resolves no file: pictures come from
  the caller's `sources` (file name -> bytes), and success says
  ``Created {name}, a {EXT} file, {n} bytes.`` with `extra.literal_markup`
  carrying the count Chat's `_markup_note` reads.
* `convert_document` stores nothing, so success says
  ``Converted to {name}, a {EXT} file, {n} bytes.`` and returns the bytes to the
  caller; Chat writes its own attached/refusal wording after storing.

Every result carries `extra.kind`, one of ``ok``, ``no_match``, ``bound``,
``failed``, ``not_extractable``, ``missing_image``, as a machine tag that
never changes `content` or `detail`. Argument refusals from the tool modules carry no `kind`.
"""

from __future__ import annotations

from dataclasses import replace as _replace
from typing import Any

from .. import office
from ..office._model import parse_sheets
from ..tools import FIND_CONTEXT as CONTEXT
from ..tools import FIND_MAX_HITS as MAX_HITS
from ..tools import READ_WINDOW as _READ_WINDOW
from ..tools import SHEET_MAX_PAIRS, SHEET_MAX_ROWS
from ..tools import ToolResult
from ..tools._findfile import MAX_QUERY
from ._extract import FAILED, INDEXED, _extract_text, _sniff
from ._sheet import _header_row

OK = "ok"
NO_MATCH = "no_match"
BOUND = "bound"
MISSING_IMAGE = "missing_image"


def _tagged(result: ToolResult, kind: str, **extra: Any) -> ToolResult:
    return _replace(result, extra={**extra, "kind": kind})


def _refuse(result: ToolResult, sentence: str, detail: str, kind: str) -> ToolResult:
    return _replace(result, ok=False, content=sentence, detail=detail,
                    extra={"kind": kind})


def extract(name: str, body: bytes) -> ToolResult:
    """Chat's upload-time extraction: `(text, state, reason)` for one file.

    @param name: The file's display name; its suffix selects the reader.
    @param body: The file's bytes.
    @returns: `ok` is true only for state ``indexed``; `content` is the stored
        text; `extra` holds `text`, `state`, `reason` exactly as Chat stores them,
        `sniffed` (`_sniff`'s value, Chat's `FileRecord.sniffed_type`) and
        `convertible` (Chat's `office.kind_of(name) in office.READERS` check).
    """
    sniffed = _sniff(body, name)
    text, state, reason = _extract_text(body, name, sniffed)
    detail = (f"extracted {name} — {len(text)} characters" if state == INDEXED
              else f"no text for {name} — {reason}")
    return ToolResult(name="extract_document", content=text,
                      ok=state == INDEXED, detail=detail,
                      extra={"text": text, "state": state, "reason": reason,
                             "convertible": office.kind_of(name) in office.READERS,
                             "sniffed": sniffed,
                             "kind": OK if state == INDEXED else state})


def read(result: ToolResult, name: str, text: str) -> ToolResult:
    """`App._read_attached` after resolution, without the per-turn budget.

    @param result: The validated `read_file` result carrying `extra.read`.
    @param name: The resolved document name.
    @param text: The document's stored text.
    @returns: The window with Chat's header, or Chat's refusal.
    """
    request = (result.extra or {}).get("read")
    if request is None:
        return result
    source = str(request.get("source") or "")
    total = len(text)
    start = int(request.get("start") or 0)
    length = int(request.get("length") or 0)
    if total == 0:
        return _refuse(
            result,
            f"{name} is attached and its stored text is empty, so there was "
            f"nothing to read.",
            "nothing read — no stored text", "not_extractable")
    if start >= total:
        return _refuse(
            result,
            f"{name} has {total} characters of text in total, so there is "
            f"nothing at character {start}. Read a start below {total}.",
            f"nothing read — past the end of {total}", BOUND)

    window = text[start:start + min(length, _READ_WINDOW)]
    end = start + len(window)
    asked = source.strip()
    folded = asked.casefold()
    recognised = folded in {
        (name or "").casefold(),
        (name or "").rsplit(".", 1)[0].casefold(),
    }
    head = (f"{name} — characters {start} to {end} of {total}.")
    if asked and not recognised:
        head = (f"You asked for \"{asked}\", which is not the name of any "
                f"file here. This conversation has exactly one file and it "
                f"is \"{name}\", so THAT is what was read — say so if you "
                f"quote it. {head}")
    if end < total:
        remaining = -(-(total - end) // _READ_WINDOW)
        head += (f" There are {total - end} characters after this. To "
                 f"continue, call read_file again with start {end}. "
                 f"**You may ask for more than one window in a single "
                 f"reply** — {remaining} more call(s) would reach the end "
                 f"of this file, and emitting them together costs one "
                 f"round instead of {remaining}.")
    else:
        head += " That is the end of the file."
    return _replace(
        result, ok=True,
        content=f"{head}\n\n{window}",
        detail=f"read {name} {start}–{end} of {total}",
        extra={"read_span": {"start": start, "end": end, "total": total},
               "kind": OK})


def find(result: ToolResult, name: str, text: str) -> ToolResult:
    """`App._find_attached` after resolution.

    @param result: The validated `find_in_file` result carrying `extra.find`.
    @param name: The resolved document name.
    @param text: The document's stored text.
    @returns: Every hit position with context, a no-match fact, or a refusal.
    """
    request = (result.extra or {}).get("find")
    if request is None:
        return result
    query = str(request.get("query") or "")
    total = len(text)
    if total == 0:
        return _refuse(
            result,
            f"{name} is attached and its stored text is empty, so there "
            f"was nothing to search.",
            "nothing searched — no stored text", "not_extractable")

    hay = text.casefold()
    needle = query.casefold()
    hits: list[int] = []
    found = 0
    step = max(1, len(needle))
    at = hay.find(needle)
    while at != -1:
        found += 1
        if len(hits) < MAX_HITS:
            hits.append(at)
        at = hay.find(needle, at + step)

    if not hits:
        return _tagged(_replace(
            result, ok=True,
            content=(
                f"{name} — {query!r} does not appear anywhere in its "
                f"{total} characters. The file IS attached and readable; "
                f"this is a fact about the text, not a failure. Try a "
                f"shorter or differently-spelled phrase, or read part of "
                f"the file to see what the labels actually are."),
            detail=f"searched {name} — no match for {query!r}"), NO_MATCH)

    shown = hits
    more = found - len(shown)
    blocks = []
    for at in shown:
        begin = max(0, at - CONTEXT // 3)
        end = min(total, at + CONTEXT)
        blocks.append(
            f"\n--- at character {begin} "
            f"(read_file source \"{name}\" start {begin})\n"
            f"{text[begin:end]}")

    head = (f"{name} — {query!r} appears {found} time(s) in "
            f"{total} characters.")
    if more:
        head += (f" The {len(shown)} shown below are the first ones; "
                 f"{more} more were not listed.")
    if request.get("clipped"):
        head += (f" Your query was longer than {MAX_QUERY} characters and "
                 f"was cut to that length before searching.")
    head += (" Each block below gives the exact start for read_file if you "
             "need more around it.")
    return _tagged(_replace(
        result, ok=True,
        content=head + "\n" + "".join(blocks),
        detail=f"found {query!r} in {name} — {found} place(s)"), OK)


def query(result: ToolResult, name: str, text: str) -> ToolResult:
    """`App._query_attached` after resolution.

    @param result: The validated `query_sheet` result carrying `extra.sheet`.
    @param name: The resolved document name.
    @param text: The document's stored text; sheets are parsed back out of it.
    @returns: Heading-paired rows, a no-match fact, or a refusal.
    """
    request = (result.extra or {}).get("sheet")
    if request is None:
        return result

    sheets = parse_sheets(text)
    if not sheets:
        return _refuse(
            result,
            f"{name} has no addressable sheets — its stored text carries no "
            f"row numbers, which means it is not a spreadsheet Plexar read "
            f"as a grid, or it was uploaded before Plexar recorded row "
            f"numbers. **It IS attached.** Read it with read_file, or ask "
            f"the user to attach it again to get addressable rows.",
            "nothing read — no addressable sheets", "not_extractable")

    wanted_sheet = str(request.get("sheet") or "").casefold()
    if wanted_sheet:
        chosen = [s for s in sheets
                  if s["name"].casefold() == wanted_sheet] or [
            s for s in sheets if wanted_sheet in s["name"].casefold()]
        if not chosen:
            names = ", ".join(repr(s["name"]) for s in sheets)
            return _refuse(
                result,
                f"{name} has no sheet matching {request.get('sheet')!r}. Its "
                f"sheets are: {names}. Nothing was read.",
                "nothing read — no such sheet", NO_MATCH)
        sheets = chosen

    override = request.get("headings")
    override = override if isinstance(override, int) and override > 0 else None
    shown_header: list = []
    shown_header_at: int | None = None

    wanted = str(request.get("row") or "").strip()
    as_number = wanted[1:] if wanted[:1].upper() == "R" else wanted
    number = int(as_number) if as_number.isdigit() else None
    folded = wanted.casefold()

    matches: list[tuple[dict, int, list[str]]] = []
    for sheet in sheets:
        for row_number, cells in sheet["rows"]:
            label = (cells[0] if cells else "").strip().casefold()
            if number is not None and row_number == number:
                matches.append((sheet, row_number, cells))
            elif number is None and folded and folded in label:
                matches.append((sheet, row_number, cells))

    if not matches:
        labels = []
        for sheet in sheets[:2]:
            labels += [c[0] for _, c in sheet["rows"][:12] if c and c[0].strip()]
        return _tagged(_replace(
            result, ok=True,
            content=(
                f"{name} — no row matching {wanted!r}. **This is a fact "
                f"about the sheet, not a failure**; the file is attached "
                f"and readable. Row labels near the top include: "
                f"{', '.join(repr(l) for l in labels[:12]) or 'none'}. "
                f"Call find_in_file to locate the label you want."),
            detail=f"queried {name} — no row {wanted!r}"), NO_MATCH)

    blocks = []
    for sheet, row_number, cells in matches[:SHEET_MAX_ROWS]:
        header, header_at = _header_row(sheet, override)
        if not shown_header:
            shown_header, shown_header_at = header, header_at
        pairs = []
        for i, cell in enumerate(cells[:SHEET_MAX_PAIRS]):
            if not str(cell).strip():
                continue
            title = header[i] if i < len(header) else ""
            title = str(title).strip() or f"column {i + 1}"
            pairs.append(f"    {title} | {cell}")
        dropped = max(0, len(cells) - SHEET_MAX_PAIRS)
        blocks.append(
            f"\n--- {sheet['name']} row {row_number}"
            + (f", headings from row {header_at}" if header_at else
               ", NO HEADING ROW FOUND — the names below are positions")
            + (f" (the next {dropped} column(s) are not shown)"
               if dropped else "")
            + "\n" + "\n".join(pairs))

    more = len(matches) - len(matches[:SHEET_MAX_ROWS])
    head = (f"{name} — {len(matches)} row(s) match {wanted!r}. "
            f"Each value below is paired with its own column heading, so "
            f"**do not count columns**: read the pairing.")
    if more:
        head += (f" {len(matches[:SHEET_MAX_ROWS])} are shown; {more} more "
                 f"matched and were not listed — narrow the row if you "
                 f"need them.")
    head += (
        f" Headings were taken from row {shown_header_at or 'none'}"
        + (f": {' | '.join(str(c) for c in shown_header[:12] if str(c).strip())}"
           if shown_header_at else "")
        + ". If those are the wrong headings — a merged title row, or the "
          "real names one row below — call query_sheet again with "
          "headings set to the right row number.")
    if any("| =?" in b for b in blocks):
        head += (
            " Values shown as =? hold a formula whose result is not stored "
            "in the file — never plot or total =? as a number. If the "
            "neighbouring pairs give you the inputs (a base value and a "
            "change %), compute the missing values yourself and say that "
            "you did. **Compute them ALL in one reply** — several "
            "calculator calls in one message cost one round; one per "
            "message costs a round each, and the turn has three.")

    return _tagged(_replace(
        result, ok=True,
        content=head + "\n" + "\n".join(blocks),
        detail=f"queried {name} — {len(matches)} row(s) for {wanted!r}"), OK)


def convert(result: ToolResult, name: str, body: bytes
            ) -> tuple[ToolResult, office.Generated | None]:
    """The conversion arm of `App._attach_generated`, minus the store.

    @param result: The validated `convert_document` result carrying `extra.convert`.
    @param name: The source file's name.
    @param body: The source file's bytes.
    @returns: The result and the produced file, or `None` when nothing was produced.
    """
    request = (result.extra or {}).get("convert")
    if request is None:
        return result, None
    try:
        data, kind, reformatted = office.convert(
            body, name, str(request.get("kind") or ""))
    except Exception as exc:  # noqa: BLE001 - Chat's own boundary, same sentence
        return _refuse(result, f"That file could not be converted: {exc}. No "
                               f"file was created.",
                       "no file — conversion failed", FAILED), None
    if not reformatted:
        return _replace(
            result, ok=True, extra={"kind": OK},
            content=(f"{name} is already a {kind.upper()} and "
                     f"the user already has it — nothing was created. "
                     f"Say so, and offer a different format or ask what "
                     f"should change."),
            detail="nothing to convert — already that format"), None
    generated = office.Generated(
        name=office.safe_name(request.get("name") or name, kind),
        declared_type=office.KINDS[kind][1], body=data)
    suffix = (generated.name.rsplit(".", 1)[-1].lower()
              if "." in generated.name else "")
    return _replace(
        result, ok=True, extra={"kind": OK},
        content=(f"Converted to {generated.name}, a {suffix.upper()} file, "
                 f"{generated.size} bytes."),
        detail=f"converted to {generated.name}"), generated


def create(result: ToolResult, sources: dict[str, tuple[str, bytes]]
           ) -> tuple[ToolResult, office.Generated | None]:
    """The create arm of `App._attach_generated`, minus the store.

    A spec without pictures was built by the tool module; a spec with pictures
    comes back as `extra.compose` and is built here from the caller's
    `sources`, keyed by the reference each image block names exactly as the
    spec names it (a file name, a partial name or a file id).

    @param result: The validated `create_document` result.
    @param sources: Reference -> (the file's real name, its bytes).
    @returns: The result and the produced file, or `None` when nothing was produced.
    """
    extra = result.extra or {}
    generated = extra.get("file")
    compose = extra.get("compose")
    if generated is None and compose is None:
        return result, None
    if compose is not None:
        spec = dict(compose.get("spec") or {})
        wanted = {str(b.get("source") or "")
                  for b in (office.image_refs(spec.get("blocks"))
                            + office.furniture_refs(spec))}
        documents: dict[str, Any] = {}
        for named in sorted(wanted):
            given = sources.get(named)
            if given is None:
                known = ", ".join(sorted(sources)) or "none"
                refused = _refuse(
                    result,
                    f"There is no file {named} in this conversation, so "
                    f"nothing was created. The files here are: {known}. "
                    f"Use one of those as the image source and send it "
                    f"again — do NOT tell the user their file is missing.",
                    "no file — a source is missing", MISSING_IMAGE)
                return _replace(refused, extra={
                    "needed_sources": sorted(wanted - set(sources)),
                    "kind": MISSING_IMAGE}), None
            source_name, body = given
            try:
                documents[named] = office.read(body, source_name)
            except Exception:  # noqa: BLE001 - Chat's own boundary, same sentence
                return _refuse(
                    result,
                    f"{source_name} could not be read, so its pictures "
                    f"could not be re-used and no file was created.",
                    "no file — a source could not be read", MISSING_IMAGE), None
        try:
            spec["blocks"] = office.resolve_images(spec.get("blocks"), documents)
            spec = office.resolve_furniture(spec, documents)
        except office.MissingImage as exc:
            return _refuse(
                result,
                f"That document could not be assembled: {exc}. No file was "
                f"created — check the image numbers against the file's own "
                f"text and send it again.",
                "no file — an image reference did not resolve", MISSING_IMAGE), None
        try:
            generated = office.build(compose.get("kind"), compose.get("name"), spec)
        except Exception:  # noqa: BLE001 - Chat's own boundary, same sentence
            return _refuse(
                result, "That document could not be built and no file was created.",
                "no file — build failed", FAILED), None
    suffix = (generated.name.rsplit(".", 1)[-1].lower()
              if "." in generated.name else "")
    return _replace(
        result, ok=True,
        extra={"literal_markup": extra.get("literal_markup", 0), "kind": OK},
        content=(f"Created {generated.name}, a {suffix.upper()} file, "
                 f"{generated.size} bytes."),
        detail=f"created {generated.name}"), generated
