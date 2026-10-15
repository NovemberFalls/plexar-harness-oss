"""Inline emphasis, because the model writes markdown whether we ask or not.

══ WHY THIS EXISTS AT ALL, MEASURED ════════════════════════════════════════
Len asked for a contract *"with highlights on the terms"*. The model produced
4,782 characters in which `**bold**` and `*italics*` are the entire mechanism
of the highlighting — it said so itself: *"Key terms are highlighted using bold
for critical obligations, italics for defined terms on first use."*

**A writer that treats that text as literal ships a Word document full of
asterisks**, which is the request failing while appearing to succeed: a file
arrives, it opens, and the one thing that was asked for is not there.

══ WHY IT IS A SPLITTER AND NOT A MARKDOWN PARSER ══════════════════════════
It handles exactly `**strong**` and `*emphasis*` and nothing else. No links, no
code spans, no nesting. A general markdown parser is a second renderer with its
own defects, and this lane already has one in `render.js` — two would be two
places for the same document to look different. Anything unrecognised stays
literal, which is the safe direction: a stray asterisk is a blemish, a dropped
clause is a lie.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: `**` before `*` — the alternation is ordered, and that order IS the rule.
#: With `*` first, `**bold**` matches the single-star arm on its first two
#: characters and yields an empty emphasis followed by literal text.
_TOKEN = re.compile(r"\*\*(.+?)\*\*|\*(.+?)\*", re.S)


@dataclass(frozen=True)
class Run:
    """One stretch of text with one set of marks."""

    text: str
    bold: bool = False
    italic: bool = False


def runs(text: str, *, bold: bool = False, italic: bool = False) -> list[Run]:
    """Split `text` into runs. **Never drops a character.**

    The concatenation of every returned `Run.text` equals the input with its
    emphasis markers removed and nothing else — asserted in the gate, because
    "the formatting is slightly off" and "a sentence vanished" are the two
    failures this function can have and only one of them is acceptable.
    """
    out: list[Run] = []
    pos = 0
    for match in _TOKEN.finditer(text):
        if match.start() > pos:
            out.append(Run(text[pos:match.start()], bold=bold, italic=italic))
        strong, emph = match.group(1), match.group(2)
        if strong is not None:
            out.append(Run(strong, bold=True, italic=italic))
        else:
            out.append(Run(emph, bold=bold, italic=True))
        pos = match.end()
    if pos < len(text):
        out.append(Run(text[pos:], bold=bold, italic=italic))
    # An empty input is one empty run rather than no runs: a paragraph with no
    # runs at all is a `<w:p/>` Word renders as nothing, which silently loses
    # a deliberate blank line.
    return out or [Run("", bold=bold, italic=italic)]
