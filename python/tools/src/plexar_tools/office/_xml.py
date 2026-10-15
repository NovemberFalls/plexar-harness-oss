"""**THE ONE NON-NEGOTIABLE OF THIS PACKAGE (T40).**

Every string that reaches an OOXML part was written by the model, and the model
wrote it because a user asked for it. So it is hostile by default — the same
standing this lane already gives an uploaded filename (`clean_name`) and a
search result's title (T1's `_clean`).

══ WHAT AN UNESCAPED STRING DOES HERE ══════════════════════════════════════
A `.docx` is a zip of XML. A cell or paragraph containing `</w:t></w:r>` does
not render as those characters — it CLOSES THE ELEMENT and restructures the
document. The failure is not a stray glyph: Word refuses to open the file, with
a message that blames the user for a corrupt document.

══ AND CONTROL CHARACTERS ARE ILLEGAL EVEN ESCAPED ═════════════════════════
XML 1.0 §2.2 permits `\\t`, `\\n`, `\\r` and everything from `\\x20` up. It
permits **nothing else below `\\x20`**, and `&#x1;` is just as invalid as a raw
`\\x01` — an escape does not launder a character the grammar forbids. A model
that quotes a PDF, a database dump or its own tool output will emit one
eventually. They are DROPPED rather than escaped, because there is no encoding
of them that Word will open.
"""

from __future__ import annotations

#: Characters XML 1.0 allows below `\x20`. Everything else in that range is
#: unrepresentable and is removed.
_ALLOWED_LOW = {0x09, 0x0A, 0x0D}


def clean(text: object) -> str:
    """Coerce to text and remove what XML 1.0 cannot carry.

    **Applied before escaping, never after.** Escaping first would turn a raw
    `\\x01` into the string `&#x1;`, which no longer looks like a control
    character to this function and would ship a file Word refuses.
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    out = []
    for ch in text:
        code = ord(ch)
        if code < 0x20 and code not in _ALLOWED_LOW:
            continue
        # The surrogate range and the two permanently-unassigned noncharacters
        # are also refused by every XML parser worth the name.
        if 0xD800 <= code <= 0xDFFF or code in (0xFFFE, 0xFFFF):
            continue
        out.append(ch)
    return "".join(out)


def escape(text: object) -> str:
    """Text -> XML character data. **Five entities, and the order matters.**

    `&` is replaced FIRST. Doing it after `<` would rewrite the ampersand of
    the `&lt;` this function had just produced, yielding `&amp;lt;` — a
    document that renders its own markup as visible text. That ordering bug is
    invisible in any input without both characters, which is most of them.
    """
    s = clean(text)
    s = s.replace("&", "&amp;")
    s = s.replace("<", "&lt;").replace(">", "&gt;")
    s = s.replace('"', "&quot;").replace("'", "&apos;")
    return s


def attr(text: object) -> str:
    """An attribute VALUE, quoted with `"`. Same escaping; named separately so
    a caller reads as what it meant, and so a later change to one cannot
    silently change the other."""
    return escape(text)
