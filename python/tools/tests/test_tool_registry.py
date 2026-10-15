"""**T1 · THE REGISTRY.** The tool tracker, and the two states it forbids.

Len asked whether we had a tool tracker. The point of this file is not that a
list exists — a list is trivial — but that **the two ways a list drifts from
reality are unreachable**:

    declared but not implemented   the model is told a tool exists, calls it,
                                   and the dispatch finds nothing
    implemented but not declared   a handler nobody can reach, which reads as
                                   a capability and grows a twin

Both are asserted as CONSTRUCTION failures, not as review habits. And the
schemas sent upstream and the handlers run are asserted to come from the same
list, because two lists that agree today is the shape this program calls a seam.
"""

from __future__ import annotations

import pytest

from plexar_tools.tools import Registry, Tool, ToolCall


def _call(name: str, arguments: str = "{}", call_id: str = "call_1") -> ToolCall:
    return ToolCall(index=0, id=call_id, name=name, arguments=arguments)


def _echo(args):
    return (f"echoed {args.get('x')}", f"echoed {args.get('x')}")


def tool(**kw) -> Tool:
    base = dict(name="echo", description="echo", parameters={"type": "object"},
                handler=_echo, does_io=False)
    base.update(kw)
    return Tool(**base)


# ══════════════════════════════════════════════════════════════════════════════
# THE TWO FORBIDDEN STATES.
# ══════════════════════════════════════════════════════════════════════════════

def test_a_tool_cannot_be_declared_without_a_handler() -> None:
    """**Declared-but-not-implemented is a TypeError, not a code review.**

    Two refusals, and they are different: `handler` has no default, so omitting
    it entirely does not compile; passing `None` is caught in `__post_init__`,
    which is the case a helpful edit actually produces.
    """
    with pytest.raises(TypeError):
        Tool(name="x", description="d", parameters={}, does_io=False)  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="no handler"):
        tool(handler=None)


def test_a_handler_is_unreachable_unless_a_tool_names_it() -> None:
    """**Implemented-but-not-declared: there is no path to it at all.**

    The dispatch is a lookup on the declared list. It is not a `getattr` on a
    module and it is not a name-to-function map maintained beside the schemas —
    which is the design where the two drift.
    """
    ran = []

    def orphan(_args):
        ran.append(True)          # pragma: no cover - reaching this IS the bug
        return ("", "")

    registry = Registry(tools=(tool(),))
    result = registry.run(_call("orphan"))

    assert ran == [], "an undeclared handler was reached"
    assert result.ok is False
    assert "no tool called 'orphan'" in result.content
    # AND THE REFUSAL DOES NOT NAME A TOOL THAT DOES EXIST. A fallback to the
    # only declared tool would be worse than the error: the model would get an
    # answer to a question it did not ask.
    assert "echo" not in result.content
    # And the artifact hint is NOT sprayed onto every unknown name.
    assert "fenced code block" not in result.content


def test_a_call_to_an_artifact_tool_is_told_the_form_that_works() -> None:
    """`c_e9997c389d3a687d01906cc2` step 17: the model called `artifact`.

    Still a refusal — nothing runs — but it names the fenced block, so the
    next round can write the chart instead of re-rolling the call.
    """
    registry = Registry(tools=(tool(),))
    for name in ("artifact", "create_artifact", "Artifact"):
        result = registry.run(_call(name))
        assert result.ok is False
        assert f"no tool called {name!r}" in result.content
        assert "fenced code block in your reply" in result.content


def test_the_schemas_sent_and_the_handlers_run_come_from_one_list() -> None:
    """R26 — **the seam.** Asserted as an exact equality of the two name sets.

    A registry that built `schemas()` from one source and dispatched from
    another would pass every test in this file that looked at either half
    alone, and fail only in production, as a tool call into nothing.
    """
    registry = Registry(tools=(tool(name="a"), tool(name="b"), tool(name="c")))
    declared = {s["function"]["name"] for s in registry.schemas()}
    dispatchable = {
        name for name in ("a", "b", "c", "d")
        if registry.run(_call(name)).ok
    }
    assert declared == dispatchable == {"a", "b", "c"}


def test_two_tools_may_not_share_a_name() -> None:
    """The model calls one and gets the other, and nothing says so."""
    with pytest.raises(ValueError, match="declared twice"):
        Registry(tools=(tool(name="same"), tool(name="same")))


# ══════════════════════════════════════════════════════════════════════════════
# DISABLED IS A THIRD STATE. INVARIANT-ENVELOPE.
# ══════════════════════════════════════════════════════════════════════════════

def test_a_disabled_tool_is_declared_to_the_operator_and_hidden_from_the_model() -> None:
    """**Three states, pairwise distinct** (R10): offered, declared-off, absent.

    Sending a disabled tool's schema would be the worst of the three: the model
    would call something that cannot work, and the user would be shown a
    failure they did not need to see. Omitting it from `declared()` as well
    would be the other end — "why is there no search" answerable only by
    reading the source.
    """
    registry = Registry(tools=(
        tool(name="on"),
        tool(name="off", enabled=False,
             reason="web_search has no provider key on this server.",
             action="Set PLEXAR_CHAT_SEARCH_KEY and restart Chat."),
    ))

    assert [s["function"]["name"] for s in registry.schemas()] == ["on"]

    rows = {row["name"]: row for row in registry.declared()}
    assert set(rows) == {"on", "off"}, "the tracker hides a tool it declared"
    assert rows["off"]["enabled"] is False
    assert rows["off"]["action"].startswith("Set PLEXAR_CHAT_SEARCH_KEY")
    assert rows["on"]["reason"] is None

    # AND THE HANDLER IS NOT REACHED even if a call for it arrives — a model
    # carrying a stale schema from an earlier turn is a real case.
    result = registry.run(_call("off"))
    assert result.ok is False
    assert result.content == "web_search has no provider key on this server."
    # ABSENT IS THE THIRD STATE AND IT DOES NOT BORROW THE SECOND'S WORDS.
    assert registry.run(_call("never")).content != result.content


def test_a_tool_may_not_be_both_enabled_and_carrying_a_refusal() -> None:
    """Two answers to one question; the surface would have to pick one."""
    with pytest.raises(ValueError, match="enabled and also gives a reason"):
        tool(reason="broken")
    with pytest.raises(ValueError, match="disabled with no reason"):
        tool(enabled=False)


def test_the_io_axis_is_declared_and_not_inferred() -> None:
    """**The tracker's one substantive field.**

    Inferring it from whether a handler imports `urllib` is true until somebody
    adds a helper — and the day it stops being true, nothing anywhere reports
    that a pure function became a network call.
    """
    registry = Registry(tools=(
        tool(name="pure", does_io=False), tool(name="net", does_io=True),
    ))
    rows = {row["name"]: row["does_io"] for row in registry.declared()}
    assert rows == {"pure": False, "net": True}


# ══════════════════════════════════════════════════════════════════════════════
# RUNNING ONE. The four refusals, and the bound.
# ══════════════════════════════════════════════════════════════════════════════

def test_unreadable_arguments_do_not_become_an_empty_object() -> None:
    """A stream that died mid-call. **`{}` would run the tool anyway.**

    For `web_search` that is a query nobody typed; for any tool it is a call
    the model did not make, answered as though it had.
    """
    ran = []
    registry = Registry(tools=(tool(handler=lambda a: (ran.append(a), ("", ""))[1]),))
    result = registry.run(_call("echo", '{"x": "half a quest'))
    assert ran == [], "a tool ran on arguments that never finished arriving"
    assert result.ok is False
    assert "not readable" in result.content


def test_a_handler_that_raises_becomes_a_result_and_never_an_exception() -> None:
    """**The headers are already gone.** There is nowhere to put a traceback.

    Watched to fail in the only form that matters: the same registry with a
    raising handler must not propagate, and the loop above it must still be
    able to continue — which it cannot do if this raises.
    """
    def explodes(_args):
        raise RuntimeError("the provider went away")

    registry = Registry(tools=(tool(handler=explodes),))
    result = registry.run(_call("echo"))
    assert result.ok is False
    assert "RuntimeError" in result.content
    assert "the provider went away" in result.content
    assert result.detail and "\n" not in result.detail


def test_a_result_is_bounded_and_the_bound_is_disclosed() -> None:
    """**Tool output is hostile input.** The cheapest attack is a big one.

    A result that fills the context window pushes the user's own question out
    of it. Silent truncation would be the other defect: the model would quote a
    sentence that stops mid-word and present it as the source's words.
    """
    registry = Registry(
        tools=(tool(handler=lambda _a: ("x" * 500, "big")),), max_result_chars=100,
    )
    result = registry.run(_call("echo"))
    assert result.ok is True
    assert result.content.startswith("x" * 100)
    assert "[truncated at 100 characters]" in result.content
    assert len(result.content) < 200


def test_a_detail_is_one_printable_line_whatever_the_tool_returned() -> None:
    """**A one-line note is how a fake dialog gets drawn** (C57's rule).

    A search detail is built partly from titles the open internet chose. Newline
    and bidi handling is applied HERE, centrally, because "each tool remembers
    to" is not a property — it is the state before the first tool forgets.
    """
    hostile = "line one\nline two\r\n‮gnihtemos‬\x07 " + "z" * 400
    registry = Registry(tools=(tool(handler=lambda _a: ("body", hostile)),))
    detail = registry.run(_call("echo")).detail

    assert "\n" not in detail and "\r" not in detail
    assert "‮" not in detail and "‬" not in detail
    assert "\x07" not in detail
    assert len(detail) <= 160
    # R23's spirit: the hostile string really was hostile before it was cleaned.
    assert "‮" in hostile and len(hostile) > 160


def test_a_registry_with_nothing_in_it_offers_nothing_and_refuses_everything() -> None:
    """A predicted ZERO, and it is an assertion (R22).

    This is the deployment a machine with no configuration gets, and it must be
    exactly the pre-T1 product: no `tools` key, no dispatch, no difference.
    """
    registry = Registry()
    assert registry.schemas() == []
    assert registry.declared() == []
    assert registry.run(_call("anything")).ok is False


# ══════════════════════════════════════════════════════════════════════════════
# WATCHED TO FAIL. **No file on disk is ever wrong** — every arm patches an
# attribute on an imported class and restores it, which is C56's technique in
# its Python form.
# ══════════════════════════════════════════════════════════════════════════════

def test_arm_without_the_construction_check_a_handlerless_tool_exists() -> None:
    """**Predicted: it constructs, and then it explodes at CALL time.**

    That is the whole argument for putting the check in `__post_init__`. Without
    it the defect is not caught at import, not caught at declaration, and not
    caught by review — it is caught by the model calling the tool, in the middle
    of a stream, in front of a user.
    """
    import plexar_tools.tools._registry as registry_module

    original = registry_module.Tool.__post_init__
    registry_module.Tool.__post_init__ = lambda self: None
    try:
        # R23 — confirm the break LANDED before reading the result.
        assert registry_module.Tool.__post_init__ is not original, \
            "the arm changed nothing — R23"
        broken = tool(handler=None)
        assert broken.handler is None, "a handlerless tool was still refused"
        # IT IS DECLARED. Its schema goes upstream, so the model is told the
        # tool exists — and the failure has moved from declaration time to the
        # middle of somebody's conversation.
        registry = Registry(tools=(broken,))
        assert [s["function"]["name"] for s in registry.schemas()] == ["echo"]
        result = registry.run(_call("echo"))
        assert result.ok is False
        assert "'NoneType' object is not callable" in result.content, result.content
    finally:
        registry_module.Tool.__post_init__ = original

    # AND BACK: the real class still refuses it.
    with pytest.raises(ValueError, match="no handler"):
        tool(handler=None)


def test_arm_a_second_list_of_schemas_passes_every_half_and_fails_the_seam() -> None:
    """**Predicted: `schemas()` and `run()` disagree and only the seam sees it.**

    This is the design the registry exists instead of — a name-to-schema map
    beside a name-to-handler map — and it is what somebody will reach for the
    day a schema needs to differ from the declaration. Each half is internally
    consistent; the product is broken.
    """
    class TwoLists(Registry):
        #: A schema list maintained separately. It has drifted by ONE name,
        #: which is exactly how it drifts in life: a tool was renamed.
        def schemas(self):
            return [{"type": "function", "function": {
                "name": n, "description": "", "parameters": {}}}
                for n in ("a", "b", "search_web")]

    drifted = TwoLists(tools=(tool(name="a"), tool(name="b"), tool(name="web_search")))

    declared = {s["function"]["name"] for s in drifted.schemas()}
    dispatchable = {n for n in declared if drifted.run(_call(n)).ok}
    assert declared != dispatchable, "the arm changed nothing — R23"
    # THE SYMPTOM, NAMED: the model is told about `search_web` and calling it
    # reaches nothing. Neither list is wrong on its own.
    assert "search_web" in declared and "search_web" not in dispatchable

    # The real registry, same tools, has no such gap.
    honest = Registry(tools=(tool(name="a"), tool(name="b"), tool(name="web_search")))
    real_declared = {s["function"]["name"] for s in honest.schemas()}
    assert real_declared == {n for n in real_declared if honest.run(_call(n)).ok}
