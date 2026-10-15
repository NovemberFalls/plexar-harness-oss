"""**THE TOOL TRACKER. One place, and it is the source of truth.**

Len asked whether we had a tool tracker. We did not — there was no tool, no
schema, no `tools` key on the wire and no list of anything. This is it.

══ THE PROPERTY THIS MODULE EXISTS FOR ══════════════════════════════════════
**A tool that exists but is not declared, or is declared but not implemented,
must be IMPOSSIBLE rather than discouraged.** Both halves fail the same way and
neither is visible in a diff:

  * declared-not-implemented — the model is told a tool exists, calls it, and
    the loop dispatches into nothing. The user sees a search that never happens
    and a model that answers as though it had searched.
  * implemented-not-declared — a handler nobody can reach. Dead code that reads
    as a capability, and the next person adds a second one beside it.

The mechanism is that **a `Tool` cannot be constructed without both**: the
schema and the callable are fields of one frozen object, and `schemas()` and
`run()` read the SAME list. There is no second place to add either one. A
structural gate walks this package and fails if a tool module grows a handler
that no `Tool` names.

══ THE PUBLIC INTERFACE ═════════════════════════════════════════════════════

    Tool(name, description, parameters, handler, does_io, enabled, reason,
         action)
    Registry(tools)          .schemas() · .choice() · .run(call) · .declared()

    default_registry(env)    the product's own set, built from configuration

══ `does_io` IS RECORDED BECAUSE IT IS THE ONLY AXIS THAT MATTERS HERE ══════
`calculator` and `current_datetime` are pure functions with no address and no
key. `web_search` talks to a third party over the network, blocks the request
while it does, and returns text from the open internet. **Those are not the
same kind of object and a tracker that could not tell them apart would be a
list of names.** It is a declared field rather than an inference from whether a
handler imports `urllib`, because the inference is exactly the kind that is
true until somebody adds a helper.

══ A DISABLED TOOL IS NOT AN ABSENT TOOL, AND IT IS NOT A BROKEN ONE ════════
`web_search` with no provider key is DECLARED, DISABLED, and carries the
`reason` and `action` that say so (INVARIANT-ENVELOPE). It is not sent upstream
— the model must not be told about a capability it cannot use — but it is
visible to the operator through :meth:`Registry.declared`, so "why is there no
search" has an answer that is not "read the source".

══ THIS MODULE DOES NOT ═════════════════════════════════════════════════════
* implement any tool. The handlers live in their own modules and this one
  imports them;
* know a URL or a key. `_search.py` holds both, behind a provider interface;
* decide when to CALL anything. That is the loop's, in `api/_app.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ._contract import MAX_RESULT_CHARS, ToolCall, ToolResult

#: What a handler is handed and what it must give back. **A handler receives
#: PARSED arguments and returns a `(content, detail)` pair or raises.** It never
#: sees the `ToolCall`, so it cannot read the call id, the raw string, or
#: anything else about the conversation — a tool is a function of its
#: arguments and nothing else.
#: A handler returns `(content, detail)` — or, since T40, a whole `ToolResult`.
#:
#: ══ WHY THE SECOND SHAPE EXISTS, AND WHY IT IS NOT A `dict` SMUGGLED IN ═════
#: The tuple is right for a tool whose entire output is text, which was all
#: three of the original set. `create_document` produces BYTES that another
#: layer has to store, and it has refusals that are not exceptions — "no
#: content was supplied" is a fact to report, not a crash. Expressing either
#: through the tuple would mean encoding them in the string and parsing it back
#: out, which is how a typed answer becomes a substring check (R25).
#:
#: **A returned `ToolResult` is passed through with `name` and `call_id` filled
#: in here** rather than trusted from the handler, so a tool still cannot
#: answer for a call it was not given.
Handler = Callable[[dict[str, Any]], "tuple[str, str] | ToolResult"]


@dataclass(frozen=True)
class Tool:
    """One declared tool. **Schema and handler in one object, or neither.**"""

    name: str
    description: str
    #: JSON Schema for the arguments, exactly as it goes on the wire.
    parameters: dict[str, Any]
    handler: Handler
    #: Does running this touch anything outside the process? See the module
    #: docstring: this is the axis the tracker exists to record.
    does_io: bool
    #: `False` means DECLARED BUT NOT OFFERED. The schema is never sent and the
    #: handler is never reached, and `reason`/`action` say why in words an
    #: operator can act on.
    enabled: bool = True
    reason: str | None = None
    action: str | None = None

    def __post_init__(self) -> None:
        # **CONSTRUCTION IS THE GATE.** Not a test that could be skipped and not
        # a review habit: a `Tool` with no callable, or with a callable and no
        # name, cannot come into existence at all.
        if not self.name:
            raise ValueError("a tool with no name cannot be declared")
        if not callable(self.handler):
            raise ValueError(f"tool {self.name!r} is declared with no handler")
        if not isinstance(self.parameters, dict):
            raise ValueError(f"tool {self.name!r} has no parameter schema")
        if self.enabled and (self.reason or self.action):
            # A tool that is offered AND carries a refusal is two answers to one
            # question, and the surface would have to pick one.
            raise ValueError(f"tool {self.name!r} is enabled and also gives a reason")
        if not self.enabled and not self.reason:
            raise ValueError(f"tool {self.name!r} is disabled with no reason given")

    def schema(self) -> dict[str, Any]:
        """The OpenAI-compatible declaration. **Built here, never by a caller.**"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


#: Bidi overrides and line/paragraph separators, named by CODEPOINT.
#:
#: **THE SAME SET IN `_search.py` WAS FIRST WRITTEN AS A STRING LITERAL AND THE
#: LITERAL BEGAN WITH TWO ORDINARY SPACES**, so `ch not in "…"` deleted every
#: space it saw: `what is vLLM` became `whatisvLLM`, silently, in the field a
#: human reads. A gate caught it. Nothing about the code looked wrong, and the
#: characters it is naming are invisible on screen — which is the whole reason
#: they are dangerous and the whole reason they are written as escapes here.
_HOSTILE = frozenset(
    "\u202a\u202b\u202c\u202d\u202e\u200e\u200f"
    "\u2066\u2067\u2068\u2069\u2028\u2029"
)


def _flatten(text: str, limit: int) -> str:
    """One line, printable, bounded. **For a `detail`, which humans read.**

    Control characters, line separators and bidi overrides are removed rather
    than escaped, which is C57's rule for the blocked-report band and for the
    same reason: that is how a one-line note becomes a fake dialog. Applied to
    every tool's detail centrally, because "each tool remembers to" is not a
    property.
    """
    clean = "".join(
        ch for ch in str(text or "") if ch.isprintable() and ch not in _HOSTILE
    )
    clean = " ".join(clean.split())
    return clean if len(clean) <= limit else clean[: limit - 1].rstrip() + "…"


@dataclass(frozen=True)
class Registry:
    """The declared set. **`schemas()` and `run()` read the same list.**"""

    tools: tuple[Tool, ...] = ()
    #: The ceiling on a result's text. A field rather than a constant read at
    #: the point of use so a test can shrink it and watch the truncation happen
    #: rather than having to generate 4,000 characters to see it.
    max_result_chars: int = MAX_RESULT_CHARS
    _by_name: dict[str, Tool] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        by_name: dict[str, Tool] = {}
        for tool in self.tools:
            if tool.name in by_name:
                # TWO TOOLS, ONE NAME. The model would call one and get the
                # other, deterministically but not predictably, and nothing
                # would say so.
                raise ValueError(f"tool {tool.name!r} is declared twice")
            by_name[tool.name] = tool
        object.__setattr__(self, "_by_name", by_name)

    # ── WHAT GOES UPSTREAM ───────────────────────────────────────────────
    def schemas(self) -> list[dict[str, Any]]:
        """The `tools` array. **Enabled tools only, and possibly empty.**

        A disabled tool is omitted rather than sent with a note, because the
        model cannot act on a note: told that `web_search` exists, it will call
        it, and the only honest answer then is a failure the user did not need
        to be shown.
        """
        return [tool.schema() for tool in self.tools if tool.enabled]

    def choice(self) -> str:
        """`auto` — the MODEL selects.

        Not `required`: forcing a tool call onto *"hello"* makes every greeting
        cost a round-trip and teaches the model to call something arbitrary.
        Not a named tool: that would make the selection OURS, and the selection
        is precisely what two pure tools were added to this row to exercise.
        """
        return "auto"

    def declared(self) -> list[dict[str, Any]]:
        """**The tracker, as data.** Every tool, enabled or not, with its axis.

        This is the answer to *"what can Chat do, and what is switched off and
        why"* that does not require reading the source. It is deliberately not
        an HTTP route — nothing about it is per-user, and a route would make it
        a surface with a scope question attached.
        """
        return [
            {"name": t.name, "does_io": t.does_io, "enabled": t.enabled,
             "reason": t.reason, "action": t.action}
            for t in self.tools
        ]

    # ── RUNNING ONE ──────────────────────────────────────────────────────
    def run(self, call: ToolCall) -> ToolResult:
        """Execute one call. **Never raises, and never dispatches by guess.**

        Four refusals before a handler is reached, and each is a distinct
        sentence because collapsing them makes the model retry the one thing it
        cannot fix:

          * a name that is not declared — including one that IS declared and
            disabled, which the model should never have seen;
          * arguments that are not a JSON object, which is what a stream that
            died mid-call leaves behind;
          * a handler that raised;
          * a result too large, which is bounded rather than refused.
        """
        tool = self._by_name.get(call.name)
        if tool is None or not tool.enabled:
            reason = (tool.reason if tool is not None and tool.reason
                      else f"There is no tool called {call.name!r} on this server.")
            # ══ AN ARTIFACT IS NOT A TOOL, AND THE REFUSAL SAYS WHAT IS ══════
            # `c_e9997c389d3a687d01906cc2`: the model wanted a live chart,
            # called a tool named `artifact`, and got only the sentence above.
            # A bare refusal is re-rolled, not corrected (T59). Mechanisms, not
            # prohibitions: the refusal carries the form that works, in
            # RUNTIME_FACTS' own words, so the next round can just write it.
            if tool is None and "artifact" in (call.name or "").lower():
                reason += (" An artifact is not a tool call: write the "
                           "self-contained HTML, SVG or Markdown document in a "
                           "fenced code block in your reply, and Plexar renders "
                           "it beside the conversation.")
            return ToolResult(
                name=call.name or "", content=reason, ok=False,
                detail=_flatten(reason, 160), call_id=call.id,
            )

        arguments = call.parsed_arguments()
        if arguments is None:
            # NOT `{}`. See `ToolCall.parsed_arguments` — a default here is a
            # tool invoked with arguments nobody wrote.
            # ══ THE MODEL IS TOLD WHERE IT BROKE (T59) ═══════════════════════
            # *"Not readable"* alone is the least actionable true statement
            # available: it has to guess what went wrong in a payload it can no
            # longer see, and a guess is a re-roll rather than a correction.
            # The parser already knows the position; `argument_fault` reports it
            # with the surrounding characters.
            fault = ""
            try:
                fault = call.argument_fault()
            except Exception:
                # A diagnostic that raises would turn a bad tool call into a
                # failed TURN. It is allowed to know nothing.
                fault = ""
            message = (
                f"The arguments for {tool.name} were not readable, so it was "
                "not run. Send the call again with the arguments as ONE valid "
                "JSON object."
            )
            if fault:
                message += f" The problem was: {fault}"
            # **The DETAIL stays short and blameless.** It is what a person
            # reads in the thread; the parser's position and a slice of raw
            # arguments are for the model, not for them.
            return ToolResult(
                name=tool.name, content=message, ok=False,
                detail=_flatten(
                    f"The arguments for {tool.name} were not readable, so it "
                    f"was not run.", 160),
                call_id=call.id)

        try:
            returned = tool.handler(arguments)
            if isinstance(returned, ToolResult):
                # THE NAME AND THE CALL ID ARE OURS, NOT THE HANDLER'S. A tool
                # answering for a call it was not given would produce a `tool`
                # turn the server drops as unmatched, silently.
                from dataclasses import replace as _replace

                result = _replace(returned, name=tool.name, call_id=call.id)
                if len(result.content) > self.max_result_chars:
                    result = _replace(result, content=(
                        result.content[: self.max_result_chars]
                        + f"\n\n[truncated at {self.max_result_chars} characters]"))
                return result
            content, detail = returned
        except Exception as exc:  # noqa: BLE001 - the boundary is the point
            # ══ A TOOL THAT THROWS IS A 500 MID-STREAM ══════════════════════
            # The response headers went out before the first token, so there is
            # nowhere to put an exception except the conversation. The message
            # is the exception's TYPE and text, which is a fact; it is not
            # dressed up as an answer.
            message = f"{tool.name} failed: {type(exc).__name__}: {exc}"
            return ToolResult(name=tool.name, content=_flatten(message, 400),
                              ok=False, detail=_flatten(message, 160),
                              call_id=call.id)

        text = str(content or "")
        if len(text) > self.max_result_chars:
            # BOUNDED, AND THE BOUND IS DISCLOSED IN THE TEXT THE MODEL READS.
            # Silent truncation would let the model quote a sentence that stops
            # mid-word and present it as the source's words.
            text = text[: self.max_result_chars] + (
                f"\n\n[truncated at {self.max_result_chars} characters]"
            )
        return ToolResult(name=tool.name, content=text, ok=True,
                          detail=_flatten(detail, 160), call_id=call.id)


def default_registry(env: dict[str, str] | None = None) -> Registry:
    """The product's own set, built from configuration. **The only builder.**

    `env` is injected rather than read from `os.environ` at the point of use so
    a gate can drive both the configured and the unconfigured case without
    touching the process — and so "the key is missing" is a testable state
    rather than one that depends on whoever ran the suite.

    **The order is the order the model sees them in.** `web_search` first
    because it is the one that changes what the product can answer; the two
    pure tools after it, and they are in the set specifically so that SELECTION
    between tools is exercised, which one tool cannot test.
    """
    import os

    from ._calculator import CALCULATOR
    from ._convert import CONVERT_DOCUMENT
    from ._datetime import CURRENT_DATETIME
    from ._document import CREATE_DOCUMENT
    from ._findfile import FIND_IN_FILE
    from ._querysheet import QUERY_SHEET
    from ._readfile import READ_FILE
    from ._search import web_search_tool

    environ = dict(os.environ if env is None else env)
    # `create_document` is LAST and that is deliberate: it is the only tool
    # whose output the user keeps, so it should be reached when the answer is
    # known rather than instead of finding one (T40).
    # `convert_document` sits BESIDE `create_document`, not inside it. T43 put
    # the file id in front of the model and sharpened the parameter text, and
    # it retyped the document twice anyway. Two verbs is a choice the model
    # makes well; a parameter inside one verb is a choice it has been making
    # badly all day (T44).
    # ══ `read_file` COMES BEFORE THE TWO DOCUMENT VERBS (T82) ════════════════
    # It is the tool that changes what the product can ANSWER, which is the
    # reason `web_search` leads — and it belongs above `create_document` for
    # exactly T40's reason, restated: the writing verbs should be reached when
    # the answer is known rather than instead of finding one. A model that has
    # not finished reading the file has not found the answer yet.
    # ══ `find_in_file` COMES BEFORE `read_file` (T87f) ══════════════════════
    # Same argument T82 made for putting `read_file` above the document verbs,
    # one step further along: **the tool that answers the question should be
    # reached before the tool that hunts for the answer.** Measured — the model
    # paged 0-6000, 6000-12000, 12000-18000 and hit the round budget having seen
    # 42.5% of a 42,402-character file. Paging from the start runs out;
    # searching does not.
    # ══ `query_sheet` LEADS THE THREE FILE VERBS (T87i) ═════════════════════
    # T82 put `read_file` above the document verbs because the tool that
    # changes what the product can ANSWER belongs before the tools that write
    # something down. T87f put `find_in_file` above `read_file` for the step
    # after that. This goes above both for the step after THAT: **a row read
    # with its headings cannot be mis-attributed, and a row read as text can**
    # — measured, twice, on the same spreadsheet.
    return Registry(tools=(web_search_tool(environ), QUERY_SHEET, FIND_IN_FILE,
                           READ_FILE, CALCULATOR, CURRENT_DATETIME,
                           CREATE_DOCUMENT, CONVERT_DOCUMENT))


__all__ = ["Handler", "Registry", "Tool", "default_registry"]
