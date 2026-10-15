"""Heading-row choice for `query_sheet`, copied verbatim from Chat.

`_header_row`, `_composed_header` and `_looks_numeric` from
`plexar-chat/chat/api/_app.py`, unchanged. Pure functions over one parsed sheet.
"""

from __future__ import annotations

def _header_row(sheet: dict, override: int | None = None) -> tuple:
    """The row whose cells NAME the columns. **Chosen, never assumed to be 1.**

    Real workbooks carry a title, a blank line, then headings — so `rows[0]` is
    often *"R365 P&L Projection"* in one cell and nothing else. The first row
    that is mostly NON-numeric is the heading row in every sheet this product
    has seen, and when it is wrong the reply says the choice was a heuristic
    rather than presenting it as fact.

    **A heading row picked silently and wrongly relabels every figure while
    looking exactly like this working** — which is `chat-R-221`'s whole shape,
    so the disclosure is not decoration.

    ══ TWO ADJACENT HEADING ROWS ARE A BANDED HEADER, AND ARE COMPOSED (T90c) ═
    RCA'd off the rig's payload capture for `c_571f810366b26d1680ad742c`, not
    off a screenshot. Len's P&L has a TWO-TIER header:

        R1   Account  Driver  Jan 2025 -> 2026  ␣  ␣  Feb 2025 -> 2026  ␣  ␣ …
        R2   ␣        ␣       2025 Actual  Change %  2026 Result  2025 Actual …

    This function picked R1 alone, so every month's actual was paired with an
    ambiguous band name and its Change % and 2026 Result became `column 4` and
    `column 5 | =?`. **The pairs were unusable for the question asked, and the
    model was RIGHT to reject them** — it retried with a `sheet` argument, got
    the same bytes, fell back to the raw text and plotted the annual Total as
    June.

    The blank cells in R1 are what a MERGED band looks like after extraction,
    so the composition is the merge undone: forward-fill the band across its
    blanks, join band and sub-header per column —

        Jan 2025 -> 2026 — 2025 Actual | 936204.81
        Jan 2025 -> 2026 — Change %    | 0.1015…
        Jan 2025 -> 2026 — 2026 Result | =?

    Nothing ambiguous survives. An OVERRIDE stays a single row — the model that
    sends one has seen the composition and rejected it, and composing on top of
    an explicit choice would be second-guessing it.
    """
    rows = sheet.get("rows", [])
    if override is not None:
        # **THE MODEL'S OWN CHOICE WINS, AND IS NOT SECOND-GUESSED.** It has
        # seen the row this function picked and rejected it; re-applying the
        # heuristic on top would make the override unreliable in exactly the
        # case it exists for.
        for number, cells in rows:
            if number == override:
                return cells, number
        return [], None
    candidates = []
    for number, cells in rows[:12]:
        filled = [c for c in cells if str(c).strip()]
        if len(filled) < 2:
            continue
        wordy = sum(1 for c in filled if not _looks_numeric(c))
        candidates.append((number, cells, wordy * 2 > len(filled)))
    for i, (number, cells, is_wordy) in enumerate(candidates):
        if not is_wordy:
            continue
        after = candidates[i + 1] if i + 1 < len(candidates) else None
        # Adjacent WORKSHEET rows, not adjacent candidates: a wordy row with a
        # blank line before the next wordy one is two separate facts, not a
        # banded header.
        if after and after[2] and after[0] == number + 1:
            return _composed_header(cells, after[1]), f"{number} and {after[0]}"
        return cells, number
    return (candidates[0][1], candidates[0][0]) if candidates else ([], None)


def _composed_header(band: list, sub: list) -> list:
    """One heading per column out of a banded pair. The forward-fill IS the
    merge, undone: a blank band cell under `Jan 2025 -> 2026` means the band
    still applies, because that is what a merged cell becomes when a grid is
    flattened."""
    out = []
    carry = ""
    for i in range(max(len(band), len(sub))):
        b = str(band[i]).strip() if i < len(band) else ""
        if b:
            carry = b
        s = str(sub[i]).strip() if i < len(sub) else ""
        out.append(f"{carry} — {s}" if carry and s else (s or carry))
    return out


def _looks_numeric(cell: object) -> bool:
    """Is this cell a number a heading would not be? Currency and thousands
    separators count as numeric — `$936,204.81` is a value, not a name."""
    text = str(cell).strip().lstrip("$-+(").rstrip("%)").replace(",", "")
    if not text:
        return False
    try:
        float(text)
    except ValueError:
        return False
    return True
