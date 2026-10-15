"""Colours the MODEL chose, turned into numbers this package can draw with.

══ WHY THIS IS ITS OWN MODULE AND NOT THREE LINES IN THE WRITER (T72) ═══════
Len asked why *"add more color"* never changed the file, and the answer was
measurable and dull: `create_document`'s schema had **no colour field at all**,
and the PDF contained exactly the three constants in `pdf/_write.py`. So the
model described *"blue for preparation, green for setup, yellow for placement,
red for safety"* and produced byte-identical output three times running. It was
not lying about the document; it was describing a document it could not ask
for.

**EVERY VALUE HERE IS MODEL-AUTHORED, WHICH MAKES THIS AN R42 SURFACE.** The
same rule C57 wrote for a blocked-URL string applies to a colour: it arrives as
text the model chose, it reaches a file a person opens, and the parser is the
only thing between the two. So:

* **A refusal is `None`, never a default.** A caller that cannot tell "the
  model said nothing" from "the model said `chartreuse`" would silently paint a
  document in a colour nobody asked for, and the model would then describe the
  colour it asked for. That is the exact shape of the defect this row fixes.
* **Nothing is clamped into range — out of range is REFUSED.** Clamping turns
  `#GGHHII` into a real colour and hides the typo forever.
* **No colour names.** A name table is a second vocabulary to keep in step with
  the schema text, and the model reaches for hex unprompted when hex is what it
  is shown.
"""

from __future__ import annotations

#: `#rgb` and `#rrggbb`, with or without the hash. Nothing else: a length this
#: function does not recognise is a typo, and a typo that renders is a typo
#: nobody fixes.
_LENGTHS = (3, 6)


def parse_colour(value: object) -> tuple[float, float, float] | None:
    """`"#1a3d5c"` -> `(0.101, 0.239, 0.361)`, or `None` if it is not a colour.

    **`None` means "not a colour", and it is the caller's job to keep its
    default** — the same contract `r2_from_env` uses for "not configured", and
    for the same reason: a function that returns a fallback cannot be asked
    whether it recognised its input.
    """
    if not isinstance(value, str):
        return None
    text = value.strip().lstrip("#").strip()
    if len(text) not in _LENGTHS:
        return None
    try:
        digits = int(text, 16)
    except ValueError:
        return None
    if digits < 0:
        return None
    if len(text) == 3:
        # `#abc` is `#aabbcc` — the CSS rule, because that is the shorthand the
        # model has seen ten million times and will therefore write.
        text = "".join(ch * 2 for ch in text)
    red = int(text[0:2], 16) / 255.0
    green = int(text[2:4], 16) / 255.0
    blue = int(text[4:6], 16) / 255.0
    return (round(red, 3), round(green, 3), round(blue, 3))


def readable_on_white(colour: tuple[float, float, float]) -> bool:
    """Is this dark enough to read as text on a white page?

    ══ THE ONE JUDGEMENT THIS MODULE MAKES, AND IT IS NOT TASTE ═════════════
    A model asked for *"yellow for placement"* will write `#ffff00`, which on
    white paper is very nearly invisible — and a heading nobody can read is a
    worse document than a heading in the default slate. **This is a legibility
    floor, not a design opinion**: it does not prefer any colour, it refuses
    the band that cannot be read.

    Relative luminance, sRGB weights, threshold 0.62. `#ffff00` is 0.928 and
    fails; `#e0a800` is 0.694 and fails; `#b8860b` is 0.556 and passes; every
    mid and dark tone of every hue passes.
    """
    red, green, blue = colour
    luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
    return luminance <= 0.62


def hex_of(colour: tuple[float, float, float] | None) -> str:
    """`(0.11, 0.20, 0.31)` -> `"1C3350"`, or `""` for `None`.

    ══ THE OFFICE FORMATS WANT THE STRING BACK (T73) ════════════════════════
    PDF draws in floats and OOXML writes `RRGGBB` with no hash, so the value
    makes a round trip: the model's text -> numbers -> text again. **That is
    deliberate and not waste.** `parse_colour` is the one gate every colour
    passes, so a `.docx` cannot be handed a string this package never
    validated — the alternative is each writer trusting the model's spelling,
    which is "each writer remembers to" and is the shape this lane has already
    refused three times.
    """
    if colour is None:
        return ""
    return "".join(f"{max(0, min(255, round(c * 255))):02X}" for c in colour)
