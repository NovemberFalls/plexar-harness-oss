"""`read_file` — the model can ASK for a file's text now (T82).

══ WHAT WAS MEASURED BEFORE A LINE WAS WRITTEN ══════════════════════════════
Len's spreadsheet, the one behind T81f's confidently wrong chart:

    extracted and stored          77,578 characters
    MAX_INDEXED_CHARS_PER_FILE   200,000    store/_projects.py:165
    reached the model              40,000    api/_app.py:1669  (MAX_ATTACHED_CHARS)

**All 77,578 characters were in the bucket. The model saw 52% of something we
hold 100% of, and 37,578 characters of the user's own file were unreachable by
any code path in the product.** Not a storage defect and not an extraction
defect — an ACCESS defect, which is a far cheaper class of problem than the one
T81f's narrative implies.

And the reason there was no path is structural rather than accidental. Of the
five tools that existed — `web_search`, `calculator`, `current_datetime`,
`convert_document`, `create_document` — **not one returned file CONTENT to the
model.** `convert_document` is the near miss: it reads an attached file and
emits another FILE, so the model never sees the text.

So the model's only channel to a user's data was `_attachment_block`: assembled
ONCE, before the turn, at a budget WE choose, **before the question is known.**
A push with no pull. When the answer lives past character 40,000 the model does
not fail — it answers from what it has, which is exactly `chat-R-221`.

══ WHY THIS IS NOT EMBEDDINGS, AND THE REASON IS THE DATA ═══════════════════
Nearest-neighbour retrieval answers *"find me passages resembling this
question."* A P&L question is *"the exact value at Dine In × February 2026."*
**A plausible neighbourhood is precisely the failure that produced `936205 x
24`** — the model already had a plausible neighbourhood and filled the gap from
the next cell along. What was missing was ADDRESSING, not similarity. An index
would also add a second thing that can be silently stale, for worse answers on
the file type actually uploaded.

══ THE TOOL NAMES A FILE THE WAY A PERSON WOULD (T70, INHERITED) ════════════
`source` takes the id OR the file's NAME, resolved by `resolve_source` at the
seam in `api/`. That is not a convenience: T70 measured the model dropping two
characters out of a 24-hex id on a document that was otherwise perfect, and the
user was told to re-upload a file sitting in the rail beside the answer. **An
opaque token is the kind of string a language model reproduces ALMOST
correctly**, and this product chooses what it asks the model to reproduce.

══ WHAT THIS MODULE DOES NOT DO ════════════════════════════════════════════
It reads no bytes. `tools/` holds no principal and knows no bucket — the same
boundary `convert_document` and `create_document` observe — so this names WHICH
file and WHICH window, and `App._read_attached` performs the ownership-scoped
read. **INVARIANT-OWNSCOPE gains no new way to name a file here**, only a new
reason to read one: the candidate set is the caller's own conversation and
nothing else.
"""

from __future__ import annotations

from typing import Any

from ._contract import ToolResult
from ._registry import Tool

#: The largest window one call may ask for, in characters. **THE ONLY BOUND ON
#: THIS TOOL'S OUTPUT, and the first design got that wrong.**
#:
#: ══ `MAX_RESULT_CHARS` DOES NOT APPLY HERE, AND NOT FOR THE REASON I WROTE ══
#: The first version of this row added a declared per-tool ceiling to `Tool` so
#: `read_file` could return 6,600 characters where every other tool is held to
#: `MAX_RESULT_CHARS` (4,000). The justification was about PROVENANCE and it was
#: sound: 4,000 exists because **tool output is hostile input** — `web_search`'s
#: content comes from the open internet — whereas what comes back here is the
#: caller's own already-extracted text, the SAME characters
#: `_attachment_block` volunteers up to 40,000 of into the prompt unasked.
#:
#: **The mechanism was inert and a probe proved it.** With the registry's ceiling
#: set to TEN, a 6,000-character window still reached the model:
#:
#:     registry ceiling for read_file   6600
#:     what the registry actually cut   'Reading f.txt…'   <- 14 characters
#:     window that reached the model    6000
#:     truncation notice present        False
#:
#: `Registry.run` bounds what the HANDLER returned, and this handler returns a
#: placeholder — the window is assembled afterwards by `App._read_attached`,
#: which rewrites `content` and never passes back through the registry. So the
#: per-tool ceiling gated nothing, while its docstring claimed to be the thing
#: holding the line. **A bound that does not bind, documented as if it did, is
#: worse than no bound**: it is the fifth time this file's parent CLAUDE.md
#: records a flag that survives everything except being relied upon. It was
#: DELETED rather than propped up with a second mechanism.
#:
#: So the bound lives where the bytes are made: `_read_attached` slices at most
#: this many characters, and `_run` clamps `length` to it as well — **both, on
#: purpose**, because the slice is what actually protects the context window and
#: the clamp is what lets the reply state the window it really returned.
#:
#: THE TOTAL IS BOUNDED THREE WAYS AND NONE OF THEM IS A PER-TOOL CEILING:
#:   * `MAX_INDEXED_CHARS_PER_FILE` (200,000) bounds what exists to be read;
#:   * this window bounds one call;
#:   * `MAX_TOOL_ROUNDS` (3) bounds the ROUNDS in one turn.
#: **The calls WITHIN a round are not bounded by anything in this repo** — that
#: is a property of the tool loop this tool inherits rather than introduces, and
#: it is recorded on the board rather than fixed here. The replay of a past read
#: is ELIDED rather than repeated (`_elide_replayed_read`), so the cost does not
#: compound across later turns, which is the part that would have grown without
#: limit.
MAX_WINDOW = 6_000

#: How many characters of file text ONE TURN may be handed, across every
#: `read_file` call in every round of it (T87h).
#:
#: ══ MEASURED, AND IT IS A REGRESSION T87e CAUSED ═════════════════════════
#: T87e told the model *"you may emit several read_file calls in ONE reply —
#: this whole file is 8 window(s)"*, and on `c_ff219befea4c88721f6d1bcf` it did
#: exactly that: **seven calls in one round, 44,322 characters of tool output,
#: `in=` 6,160 → 38,382.** That is MORE than the 41,147-character attachment
#: block T87d deleted. The manifest saved round 0 and the model gave it all
#: back in round 1.
#:
#: **`MAX_TOOL_ROUNDS` bounds COMPLETIONS and `MAX_WINDOW` bounds one CALL, and
#: nothing bounded the turn** — `chat-NOTE-228`, filed by T82's security review
#: as a theoretical note and now a measured cost. A bound on each of two
#: factors is not a bound on their product; T84 wrote that sentence about
#: `MAX_SHEETS` × per-sheet budgets and it is the same shape here.
#:
#: 18,000 is what `MAX_TOOL_ROUNDS` × `MAX_WINDOW` used to allow before
#: multi-call, so no question that was answerable yesterday stops being
#: answerable. **It is deliberately BELOW the whole of a typical workbook**: a
#: model that wants the entire file should be asking a narrower question or
#: calling `find_in_file`, and the refusal says so.
READ_BUDGET_PER_TURN = 18_000

#: The window when the model does not ask for one. Deliberately the same as
#: `MAX_WINDOW`: a model that omits the parameter wants "as much as I can have",
#: and a smaller default would spend a whole tool round to discover that.
DEFAULT_WINDOW = 6_000

PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "source": {
            "type": "string",
            "description": (
                "Which file to read — its NAME as shown in the attached-files "
                "list, or its file id. The name is easier to get right."
            ),
        },
        "start": {
            "type": "integer",
            "minimum": 0,
            "description": (
                "The character to start reading at, counting from 0. Use 0 for "
                "the beginning. The attached-files list tells you how many "
                "characters of each file you have already been given, so "
                "continue from there."
            ),
        },
        "length": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_WINDOW,
            "description": (
                f"How many characters to read, up to {MAX_WINDOW}. Leave it "
                f"out to get {DEFAULT_WINDOW}."
            ),
        },
    },
    "required": ["source"],
}

#: ══ THE DESCRIPTION IS THE ROUTING RULE, AND T81 IS WHY IT SAYS SO MUCH ══════
#: T81's finding was that the chart renderers were the cheap part and the
#: ROUTING was the row: *"make me a chart"* hit no rule at all, so the most
#: emphatic tool description won. The same trap is open here — a model that does
#: not know the file text was cut will never think to ask for more, because
#: *"was I given all of it"* is not a question a model knows it needs to ask.
#: That is T2's lesson exactly: **a tool the model must remember to call is not
#: knowledge it has.** So the ATTACHMENT BLOCK names this tool at the point of
#: truncation, and this text says when to reach for it.
DESCRIPTION = (
    "Read more of a file the user attached to this conversation. "
    "**The attached-files list above may hold only the FIRST PART of a long "
    "file** — it says so, with the exact number of characters you were given "
    "and the number the file has. When the answer might be in the part you "
    "were not given, read it rather than answering from what you have. "
    "Spreadsheets and long reports are the usual case: the rows you need are "
    "often past the point where the list stopped. "
    "You can call this more than once to keep going through a file. "
    "It returns the file's TEXT for you to read — it does not create, convert "
    "or attach anything, and the user does not see a file appear. "
    "**Never guess, interpolate or repeat a figure because the text ran out. "
    "Read the part you are missing, or say which part you could not see.**"
)


def _run(args: dict) -> ToolResult:
    """Validate, and hand the intent back. **No bytes are read here.**

    Every refusal names what was wrong AND what is still true, because a model
    told only *"that failed"* fills the gap with the most familiar explanation —
    which T77 measured to be *"the upload did not arrive"*, a false claim about
    our storage made in our own voice.
    """
    if not isinstance(args, dict):
        return ToolResult(
            name="", ok=False,
            content="The arguments for read_file were incomplete, so nothing "
                    "was read. Send the call again with a source.",
            detail="nothing read — incomplete arguments")

    source = str(args.get("source") or "").strip()
    if not source:
        return ToolResult(
            name="", ok=False,
            content="No source was given, so nothing was read. Name the file "
                    "as it appears in the attached-files list.",
            detail="nothing read — no source")

    # ══ A NON-NUMBER IS A REFUSAL, NEVER A COERCION TO ZERO (R42) ════════════
    # `start` and `length` are chosen by the MODEL, so they are untrusted input
    # in the same sense C54's height claim was. Coercing `"page 2"` to 0 would
    # silently hand back the beginning of the file and let the model report it
    # as the middle — a wrong answer that looks exactly like a right one, which
    # is the class of defect this whole row exists to close.
    start, bad = _whole(args.get("start"), default=0)
    if bad is not None:
        return ToolResult(
            name="", ok=False,
            content=f"start must be a whole number of characters, and {bad} is "
                    f"not one, so nothing was read. Use 0 for the beginning of "
                    f"the file.",
            detail="nothing read — start is not a number")
    length, bad = _whole(args.get("length"), default=DEFAULT_WINDOW)
    if bad is not None:
        return ToolResult(
            name="", ok=False,
            content=f"length must be a whole number of characters, and {bad} is "
                    f"not one, so nothing was read. Leave it out to read "
                    f"{DEFAULT_WINDOW} characters.",
            detail="nothing read — length is not a number")

    if start < 0:
        return ToolResult(
            name="", ok=False,
            content="start cannot be negative, so nothing was read. Character "
                    "positions count from 0.",
            detail="nothing read — negative start")
    if length < 1:
        return ToolResult(
            name="", ok=False,
            content="length must be at least 1 character, so nothing was read.",
            detail="nothing read — empty window")

    # **CLAMPED, NOT REFUSED — and this asymmetry is deliberate.** A window
    # bigger than the ceiling is a well-formed request for more than we give,
    # and the honest answer is the ceiling plus a note saying so; the reply
    # states the window it actually returned, so the model can page correctly
    # from a clamp it did not ask for. A malformed NUMBER is different: there is
    # no correct value to fall back to, which is why the branches above refuse.
    length = min(length, MAX_WINDOW)

    return ToolResult(
        name="", ok=True,
        content=f"Reading {source}…",
        detail=f"reading {source}",
        extra={"read": {"source": source, "start": start, "length": length}})


def _whole(value: object, *, default: int) -> tuple[int, str | None]:
    """``(number, None)`` or ``(0, what_arrived)``. **Three states, not two.**

    Absent is not the same as unreadable: an omitted `start` means "the
    beginning" and is correct, while `start: "middle"` is a call we cannot
    honour. A single `int(x or default)` collapses those, and the collapsed
    branch is the one that hands back the wrong part of the file quietly.

    A `bool` is refused even though `bool` is an `int` in Python — `True`
    reaching an offset as 1 is arithmetic on a type confusion, and T81's
    `_number()` refuses one for the same reason.
    """
    if value is None or value == "":
        return default, None
    if isinstance(value, bool):
        return 0, repr(value)
    if isinstance(value, int):
        return value, None
    if isinstance(value, float):
        # A whole-valued float is what a JSON encoder produces for `6000`, so
        # it is accepted; `6000.5` is not a character position.
        return (int(value), None) if value.is_integer() else (0, repr(value))
    text = str(value).strip()
    try:
        return int(text), None
    except ValueError:
        return 0, repr(text[:40])


READ_FILE = Tool(
    name="read_file",
    description=DESCRIPTION,
    parameters=PARAMETERS,
    handler=_run,
    does_io=False,
)

__all__ = ["DEFAULT_WINDOW", "DESCRIPTION", "MAX_WINDOW", "PARAMETERS", "READ_FILE"]
