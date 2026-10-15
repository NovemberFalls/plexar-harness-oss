"""`find_in_file` — the model can ADDRESS a file's text now, not just page it.

══ WHAT WAS MEASURED BEFORE A LINE WAS WRITTEN (T87f) ═══════════════════════
The first live turn after the manifest landed (`c_849c0d3d4535651779aea64d`):

    read r365_pnl_projection.xlsx      0–6000  of 42402
    read r365_pnl_projection.xlsx   6000–12000 of 42402
    read r365_pnl_projection.xlsx  12000–18000 of 42402
    ! Plexar reached its limit of 3 rounds of tool use

**`MAX_TOOL_ROUNDS` × `READ_WINDOW` is 18,000 characters, and the file was
42,402.** The answer was right because the rows it needed sat in the first
42.5% of the file. *That is luck, and the next question will not have it.*

T87e made the reach-per-round bigger by telling the model it may ask for
several windows at once. **This makes the reach irrelevant**: a model that can
say WHERE does not need to read everything on the way there.

══ THIS IS THE SENTENCE `read_file`'s OWN DOCSTRING ALREADY WROTE ═══════════
    *"A P&L question is 'the exact value at Dine In × February 2026'. A
    plausible neighbourhood is precisely the failure that produced
    `936205 x 24` … What was missing was ADDRESSING, not similarity."*

That paragraph argued against embeddings and then shipped a tool that pages by
OFFSET, which is not addressing either — it is the same linear scan with the
model driving. This is the addressing half: **name the thing, get the offsets.**

**LITERAL SUBSTRING, NEVER A PATTERN (R42).** `query` is model-chosen text and
a regex would put an attacker-chosen automaton in front of a 200,000-character
string — T84 spent a whole row on exactly that class in the binary readers, and
there is nothing to be right about here when a literal `in` operator answers the
question. Case-folded, because a model asking for `dine in` and a sheet holding
`Dine In` is the common case and a miss reads as *"that row does not exist"*.

══ WHAT THIS MODULE DOES NOT DO ═════════════════════════════════════════════
It reads no bytes and it knows no bucket, exactly as `read_file` does not.
This names WHICH file and WHAT to look for; `App._find_attached` performs the
ownership-scoped search behind the same two barriers — the candidate list comes
from the caller's own conversation, and the text from that conversation's own
index object. **INVARIANT-OWNSCOPE gains no new way to name a file here.**
"""

from __future__ import annotations

from typing import Any

from ._contract import ToolResult
from ._registry import Tool

#: How many places are reported. **A bound on the RESULT, and the total is
#: still stated** — a model told "8 matches" when there are 300 would conclude
#: it had seen them all, which is `chat-R-221`'s shape in a search reply.
MAX_HITS = 8

#: Characters of surrounding text per hit. Enough to carry a spreadsheet row —
#: a label plus its figures — and not enough to become a second delivery
#: channel for the file this row exists to stop delivering.
CONTEXT = 360

#: The longest thing that may be looked for. A query is untrusted text; this is
#: not about cost (a literal scan is linear either way) but about what gets
#: echoed back into the model's context in the reply header.
MAX_QUERY = 200

PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "source": {
            "type": "string",
            "description": (
                "Which file to search — its NAME as shown in the attached-files "
                "list, or its file id. The name is easier to get right."
            ),
        },
        "query": {
            "type": "string",
            "description": (
                "The exact text to look for — a row label, a column heading, a "
                "month, a product name. Matching ignores capitals. This is "
                "PLAIN TEXT and not a pattern: no wildcards, no regular "
                "expressions. Search for the shortest thing that identifies "
                "the row you want."
            ),
        },
    },
    "required": ["source", "query"],
}

#: ══ THE DESCRIPTION IS THE ROUTING RULE (T81, INHERITED) ════════════════════
#: `read_file` and this tool overlap, and a model that reaches for the wrong one
#: wastes a round it may not have. So the rule is stated as a QUESTION SHAPE
#: rather than as a preference: *do you know what you are looking for?*
DESCRIPTION = (
    "Find where something is in a file the user attached, without reading the "
    "whole file. "
    "**Use this INSTEAD of read_file whenever you know what you are looking "
    "for** — a row called 'Dine In', a column headed 'February', a product "
    "name. It returns every place that text appears, with the surrounding "
    "lines and the exact character position, so you can read just that part. "
    "A long spreadsheet is many more characters than you can read in one turn, "
    "and paging through it from the start will run out before you reach the "
    "rows you need. Searching does not. "
    "Use read_file instead only when you need a stretch of the file you have "
    "already located, or when you do not yet know what the file contains. "
    "It returns TEXT for you to read — it creates, converts and attaches "
    "nothing, and the user does not see a file appear."
)


def _run(args: dict) -> ToolResult:
    """Validate, and hand the intent back. **No bytes are read here.**

    Every refusal names what was wrong AND what is still true, for the reason
    `read_file._run` records: a model told only *"that failed"* fills the gap
    with the most familiar explanation, and T77 measured that to be *"the
    upload did not arrive"* — a false claim about our storage in our own voice.
    """
    if not isinstance(args, dict):
        return ToolResult(
            name="", ok=False,
            content="The arguments for find_in_file were incomplete, so "
                    "nothing was searched. Send the call again with a source "
                    "and a query.",
            detail="nothing searched — incomplete arguments")

    source = str(args.get("source") or "").strip()
    if not source:
        return ToolResult(
            name="", ok=False,
            content="No source was given, so nothing was searched. Name the "
                    "file as it appears in the attached-files list.",
            detail="nothing searched — no source")

    raw = args.get("query")
    query = str(raw).strip() if isinstance(raw, (str, int, float)) else ""
    if not query:
        return ToolResult(
            name="", ok=False,
            content=f"No text to look for was given, so {source} was not "
                    f"searched. Say what to find — a row label, a heading or a "
                    f"month. The file is still attached and still readable.",
            detail="nothing searched — no query")

    # **TRUNCATED, NOT REFUSED, AND THE REPLY SAYS SO.** A query longer than
    # the ceiling is a well-formed request; refusing it would spend a round to
    # teach a limit the reply can simply state. A missing one is different —
    # there is no correct value to fall back to, which is why it refuses above.
    # Same asymmetry `read_file` draws between a clamped window and a malformed
    # number, and for the same reason.
    clipped = query[:MAX_QUERY]

    return ToolResult(
        name="", ok=True,
        content=f"Searching {source} for {clipped!r}…",
        detail=f"searching {source}",
        extra={"find": {"source": source, "query": clipped,
                        "clipped": len(query) > MAX_QUERY}})


FIND_IN_FILE = Tool(
    name="find_in_file",
    description=DESCRIPTION,
    parameters=PARAMETERS,
    handler=_run,
    # **PURE.** It reaches no network and opens no socket. The read it causes is
    # of the caller's own already-stored text, performed at the `api/` seam that
    # holds the principal — the same shape `read_file` declares.
    does_io=False,
)

__all__ = ["CONTEXT", "FIND_IN_FILE", "MAX_HITS", "MAX_QUERY"]
