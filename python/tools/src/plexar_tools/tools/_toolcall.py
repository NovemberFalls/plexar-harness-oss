"""``ToolCall``, copied from ``plexar-chat/chat/upstream/_sse.py`` (chat-DEC-397).

``chat.tools._contract`` imports ``ToolCall`` from ``chat.upstream`` in Chat.
That package is Chat's SSE/upstream-provider parser and stays in Chat — it
knows the rig's wire format, which is model-facing and outside this
package's host-free tool boundary. ``ToolCall`` itself is a small, self
-contained dataclass with no knowledge of a user, store, bucket, R2,
conversation, sub, App, or upstream provider, so it is copied here
byte-for-byte (only the docstring's ``arguments`` field and
``parsed_arguments``/``argument_fault`` methods, and the ``_flat`` helper
they use) so ``Registry.run``'s ``call: ToolCall`` parameter and ``_run``'s
argument parsing keep their exact shape without pulling in Chat's upstream
package.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


def _flat(text: str) -> str:
    """One line. A newline inside a tool result splits it into two statements
    the model reads as separate facts."""
    return " ".join(str(text).split())


@dataclass(frozen=True)
class ToolCall:
    """One reassembled call. **`arguments` is the raw JSON STRING, unparsed.**

    It is kept as the model emitted it because that string is what gets echoed
    back upstream in the assistant turn on the next round, and re-serialising a
    parsed dict would send the model something it did not write. Parsing is a
    separate, fallible act — see :meth:`parsed_arguments`.
    """

    index: int
    id: str
    name: str
    arguments: str

    def parsed_arguments(self) -> dict[str, Any] | None:
        """The arguments as an object, or ``None`` if they are not one.

        ``None`` is a REAL ANSWER and callers must render it as one. A stream
        that stopped mid-call leaves a truncated JSON string, and `{}` here
        would turn *"the model never finished asking"* into *"the model asked
        for the default"* — a tool invoked with arguments nobody wrote.
        """
        try:
            parsed = json.loads(self.arguments)
        except ValueError:
            return None
        return parsed if isinstance(parsed, dict) else None

    def argument_fault(self) -> str:
        """Why the arguments would not parse, in one short phrase, or `""`.

        The parser already knows why a call did not parse, and this reports
        it: `json` gives the character position; that plus the text either
        side of it is what turns a retry from a re-roll into a correction.
        The snippet is the MODEL'S OWN OUTPUT going back to the model, so it
        is bounded and never rendered to the user — the tool result's
        `detail` is what reaches a person.
        """
        try:
            json.loads(self.arguments)
        except ValueError as exc:
            at = getattr(exc, "pos", None)
            if not isinstance(at, int):
                return _flat(str(exc))[:120]
            near = self.arguments[max(0, at - 60):at + 60]
            return (f"{_flat(str(exc))[:90]} — near: {_flat(near)}")
        if not isinstance(json.loads(self.arguments), dict):
            return "the arguments were valid JSON but not an object"
        return ""
