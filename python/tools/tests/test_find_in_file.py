"""T87f — the model can ADDRESS a file now, not only page it.

MIXED source (chat-DEC-397): trimmed from `plexar-chat/tests/test_find_in_file.py`.
Only the two arms that drive `_findfile._run` directly are kept. Every other
arm in the source file drives `chat.api.App._find_attached`, which is a
`chat.api`/`chat.store` seam this package does not own, and stays in Chat.
"""

from __future__ import annotations

import pytest

from plexar_tools.tools._findfile import MAX_QUERY, _run


def test_an_overlong_query_is_clipped_and_the_reply_says_so():
    """Truncated, not refused — a well-formed request for more than we allow
    gets the limit plus a note, the same asymmetry `read_file` draws between a
    clamped window and a malformed number."""
    out = _run({"source": "pnl.csv", "query": "x" * (MAX_QUERY + 50)})
    assert out.ok
    assert out.extra["find"]["clipped"] is True
    assert len(out.extra["find"]["query"]) == MAX_QUERY


@pytest.mark.parametrize("args,expect", [
    ({}, "no source"),
    ({"source": "pnl.csv"}, "no query"),
    ({"source": "pnl.csv", "query": "   "}, "no query"),
    ({"source": "", "query": "x"}, "no source"),
])
def test_a_malformed_call_refuses_and_says_what_is_still_true(args, expect):
    out = _run(args)
    assert out.ok is False
    assert expect in out.detail
