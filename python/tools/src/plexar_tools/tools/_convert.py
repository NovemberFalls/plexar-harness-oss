"""`convert_document` — a SECOND VERB, because a flag was not enough (T44).

══ WHAT WAS MEASURED, TWICE, ON THE DEPLOYED BUILD ═════════════════════════
Michael's request replayed with his real document attached — *"turn this into a
PDF that outlines the procedure better, and keep the photographs"*:

    run 1   create_document(blocks=…)  ->  3,949 bytes, 2 pages, ZERO images
    run 2   create_document(blocks=…)  ->  2,036 chars of malformed JSON, refused

Both times the model **retyped the document** instead of converting it, which
loses every photograph because it cannot see them and therefore cannot retype
them. T43 had already put the file id in front of it and sharpened the
parameter description to *"never retype a file you were given."* It did not
take.

══ WHY A SEPARATE TOOL AND NOT A FLAG ═════════════════════════════════════
The first plan was `new_document: true` on `create_document`. **Claude Code's
shape is the better answer**: it has no document tool at all, but it does have
`Edit` and `Write` as SEPARATE VERBS — and you cannot `Write` a file you have
not `Read`, and `Edit` fails outright on an inexact match. It does not ask the
model to be careful; the careless path errors out.

Choosing between two well-named tools is a far easier decision than choosing a
parameter inside one — and this schema has **nowhere to put retyped content**,
so for this verb retyping is not discouraged, it is unconstructible. That is
this lane's own principle, applied to the thing that has now failed twice.

It also removes the failure mode of run 2 outright: a conversion is ~60
characters of arguments where a retype was 2,036, and most of the surface where
JSON can go wrong is the retyping itself.

══ THE BET, STATED ═════════════════════════════════════════════════════════
This adds a fifth schema to every request, and **tool SELECTION is exactly
where this model has been going wrong all day.** The bet is that picking
between two verbs is easier than picking a parameter. Claude Code's design is
evidence for it and this file is not proof of it — the proof is a live
observation, not an arm.
"""

from __future__ import annotations

from typing import Any

from .. import office
from ._contract import ToolResult
from ._registry import Tool

PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "file_id": {
            "type": "string",
            "description": (
                "The id of the uploaded file to convert, shown beside its name "
                "in the attached-files list."
            ),
        },
        "to": {
            "type": "string",
            "enum": sorted(office.WRITERS),
            "description": "The format the user asked for.",
        },
        "name": {
            "type": "string",
            "description": (
                "Optional new file name, without a path. Leave it out to keep "
                "the original name with the new extension."
            ),
        },
    },
    "required": ["file_id", "to"],
}

#: **NO `blocks`, NO `slides`, NO `rows`, AND THAT IS THE WHOLE POINT.** There
#: is nowhere in this schema to put content the model typed, so the path that
#: loses photographs does not exist for this verb.
DESCRIPTION = (
    "Convert a file the user already uploaded into another format — Word, PDF, "
    "Excel, PowerPoint or CSV — and attach the result to this conversation. "
    "It carries the text, the tables AND THE PICTURES across, EXACTLY as they "
    "are. "
    # ══ THE SENTENCE THAT WAS HERE FORBADE THE FEATURE (T56) ════════════════
    # It read: *"Do not use create_document for this: writing the content out
    # by hand loses every photograph, because you cannot see them."* True when
    # written; **T52 made it false and removed it from `create_document`'s own
    # description and missed this copy** — so the model was still being told,
    # in the other tool's text, not to use the verb that does the styling.
    #
    # Measured on Len's conversation `c_e892fd7b`: *"Please turn this into a
    # PDF, and make it presentable"* called `convert_document`, and got the
    # byte-identical unstyled file it had produced a turn earlier. It was
    # obeying us.
    #
    # **THE DIVISION OF LABOUR IS THE WHOLE OF WHAT THIS PARAGRAPH IS FOR.**
    # Both verbs keep the photographs now, so "which one keeps the pictures"
    # is no longer the question and saying it is misleads. The question is
    # whether the user wants the SAME document or a BETTER-LOOKING one.
    "**It changes NOTHING about how the document looks** — same wording, same "
    "order, no headings added, no styling. Use it when the user wants THE SAME "
    "document in another format. "
    "**If they ask for it to be presentable, styled, cleaned up, laid out or "
    "made to look good, use create_document instead** — it can place the "
    "user's own photographs by number, so a restyled document keeps them, "
    # ══ THE THIRD COPY, WHICH IS THE ONE THAT GETS MISSED (T81) ══════════════
    # This paragraph summarises what the OTHER tool is for, so it goes stale
    # every time that tool grows. T52 and T56 each shipped a version of this
    # file disagreeing with `_document.py`, and the note above records that the
    # question the two verbs divide on has already changed once. A model reading
    # only this sentence would learn create_document does styling and
    # photographs and would not learn it draws charts.
    "and it can DRAW A CHART from numbers, which this tool cannot do at all. "
    "Choosing this tool for a styling request hands back a file that looks "
    "exactly like the one they already had."
)


def _run(args: dict) -> ToolResult:
    if not isinstance(args, dict):
        return ToolResult(
            name="", ok=False,
            content="The arguments for convert_document were incomplete, so "
                    "nothing was converted. Send the call again.",
            detail="nothing converted — incomplete arguments")

    file_id = str(args.get("file_id") or "").strip()
    target = str(args.get("to") or "").strip().lower().lstrip(".")
    if not file_id:
        return ToolResult(
            name="", ok=False,
            content="No file_id was given, so nothing was converted. The id is "
                    "shown beside each file name in the attached-files list.",
            detail="nothing converted — no file id")
    if target not in office.WRITERS:
        return ToolResult(
            name="", ok=False,
            content=(f"{target or '(none)'} is not a format Plexar can write, "
                     f"and nothing was converted. It writes: "
                     f"{', '.join(sorted(office.WRITERS))}."),
            detail="nothing converted — unsupported format")

    # ══ THE BYTES ARE READ BY `api/`, NOT HERE ═══════════════════════════
    # `tools/` holds no principal and knows no bucket. This names WHICH file
    # and WHICH format; `_attach_generated` does the ownership-scoped read and
    # the store, exactly as it does for `create_document`.
    return ToolResult(
        name="", ok=True,
        content=f"Converting {file_id} to {target}…",
        detail=f"converting to {target}",
        extra={"convert": {"file_id": file_id, "kind": target,
                           "name": args.get("name")}})


CONVERT_DOCUMENT = Tool(
    name="convert_document",
    description=DESCRIPTION,
    parameters=PARAMETERS,
    handler=_run,
    does_io=False,
)
