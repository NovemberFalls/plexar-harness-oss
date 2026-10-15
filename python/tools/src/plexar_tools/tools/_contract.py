"""**What a tool is, and what running one is allowed to produce.**

This module is the contract between the LOOP (``api/_app.py``, which decides
when to run a tool) and the REGISTRY (``tools/_registry.py``, which decides
what a tool IS). It is deliberately the smaller half and it is written first,
because the loop must be gateable without any real tool existing — a loop
proven only against `web_search` is a loop proven against one provider's
latency and one schema's shape.

══ THE PUBLIC INTERFACE ═════════════════════════════════════════════════════

    MAX_TOOL_ROUNDS : int          the bound. See below — it is a REJECTION.
    ToolResult                     what one execution produced, always.
    ToolBox (Protocol)             schemas() · choice() · run(call)

══ THE BOUND IS A NUMBER AND IT IS A REJECTION, NOT A HOLD ══════════════════
A tool loop is a cycle the MODEL drives: it emits a call, we answer it, it may
emit another. Nothing in that cycle has to terminate. **An unbounded loop here
is a model-driven spend of somebody else's GPU**, and the failure mode is not a
crash — it is a request that keeps costing until a socket dies.

``MAX_TOOL_ROUNDS`` was 3 for its first eight months, justified as a SHAPE:
*search → read → refine once → answer*, one call per round. **The model does
not call one tool per round.** Len's screenshot (2026-09-04) shows eight
searches inside three rounds, so the shape argument was already describing a
different loop than the one running, and the banner it produced fired on a
turn that had answered well.

**THE REAL BOUND IS THE WINDOW, AND IT IS MEASURED, NOT COUNTED (T95).** The
loop reads `usage.prompt_tokens` off every round and the model's context
limit off `/v1/models`; when the next round could not fit alongside room for
an answer, the tools are withdrawn and the user is told *that* reason. This
constant is now only the runaway ceiling — the guard against a model that
re-issues the same call forever at a cost too small for the window to notice
— and it is high enough that a working model rarely meets it. **When it does,
the turn is CONTINUABLE**: the user presses Continue and the loop starts
again with a fresh count and the whole transcript, tool results included.
Two different stops, two different sentences, two different actions
(INVARIANT-ENVELOPE): a round ceiling says *Continue*; a full window says
*start a new chat*, because pressing Continue into a full window is the same
wall one turn later.

Within one turn the re-POSTs are nearly free on the rig's prefix cache
(R-125: 58× faster prefill at 100% hit), which is why the count was never a
spend argument either.

**When the bound is reached the user is TOLD, in band, and the answer stops
being extended.** INVARIANT-ENVELOPE: "the model stopped talking" and "we
refused to keep calling tools for it" must not render the same, and the second
one is not the user's fault to fix.

══ THIS MODULE DOES NOT ═════════════════════════════════════════════════════
* declare, name or implement any tool — that is `_registry.py` and the tool
  modules, and the separation is what makes "declared but not implemented"
  impossible rather than merely discouraged;
* know a URL, a key, or an environment variable;
* decide how a result is RENDERED. It bounds the size of the text because an
  unbounded result is a context-window attack, but the escaping rules belong to
  whoever paints it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ._toolcall import ToolCall

#: The RUNAWAY CEILING on tool rounds in one user turn. A round is: the model
#: asked for one or more tools, we ran them, we sent the results back. The
#: number of upstream completions is therefore at most `MAX_TOOL_ROUNDS + 1`.
#: **Not the working bound** — that is the context window, measured per round
#: in `_relay` (T95). Reaching this one is continuable from the UI.
MAX_TOOL_ROUNDS = 10

#: The ceiling on one tool result's text, in characters. **Tool output is
#: hostile input** — `web_search`'s comes from the open internet and every
#: tool's is chosen by whatever it talked to — and the cheapest attack on a
#: chat product is a result that fills the context window so the user's own
#: question falls out of it. Enforced by the registry on every tool, not by
#: each tool remembering to.
MAX_RESULT_CHARS = 4000


@dataclass(frozen=True)
class ToolResult:
    """One execution. **INVARIANT-ENVELOPE, on the tool boundary too.**

    ``ok`` is not decoration. A tool that failed and a tool that succeeded and
    found nothing are different facts, and both of them get sent to the model —
    so if they render the same, the model cannot tell "search is misconfigured"
    from "there are no results", and it will confidently answer as though it
    had looked. That is the same collapse `upstream.Response` exists to stop,
    one layer down.
    """

    name: str
    #: What goes back to the model as the `tool` turn's content. **Always a
    #: string**, including for a failure — the wire has no other shape here.
    content: str
    ok: bool
    #: One short line for a human: what this call did. Shown in the thread and
    #: stored in the transcript. **Never markup, never the raw content.**
    detail: str = ""
    #: The call this answered. Carried so the `tool` turn can name the
    #: `tool_call_id` the model is waiting on — a `tool` turn that does not
    #: name its call is dropped by the server as unmatched.
    call_id: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


class ToolBox(Protocol):
    """What the loop needs, and nothing else.

    A Protocol rather than a concrete import so `api/` never learns that a
    search provider exists — the same boundary discipline that keeps the rig's
    URL inside `upstream/`. The loop can be driven by a stub that returns fixed
    strings, which is how it is gated without a network.
    """

    def schemas(self) -> list[dict[str, Any]]:
        """The `tools` array as it goes on the wire. **Possibly empty.**

        An empty list means *send no `tools` key at all*; the loop enforces
        that, because `"tools": []` is a different request from a request with
        no tools and some servers refuse it.
        """
        ...

    def choice(self) -> str:
        """The `tool_choice` policy. ``"auto"`` — the model decides."""
        ...

    def run(self, call: ToolCall) -> ToolResult:
        """Execute one call. **Never raises.**

        A tool that throws is a 500 in the middle of a stream whose headers
        have already been sent, so there is nowhere to put the error except the
        conversation. Every failure comes back as a `ToolResult` with
        ``ok=False`` and words the model can act on.
        """
        ...


__all__ = ["MAX_RESULT_CHARS", "MAX_TOOL_ROUNDS", "ToolBox", "ToolCall", "ToolResult"]
