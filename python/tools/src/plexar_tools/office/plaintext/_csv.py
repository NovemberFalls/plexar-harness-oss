"""RFC 4180 with a UTF-8 BOM. Lives here rather than with the spreadsheet
writer because a CSV is not a workbook — it is the plain-text format, and
keeping it beside `.xlsx` is what made `plaintext` look optional."""

from __future__ import annotations

import io

from .._xml import clean


def csv_bytes(rows: list[list[str]]) -> bytes:
    """RFC 4180, with a UTF-8 BOM.

    **The BOM is for Excel and it is a deliberate concession.** Without it,
    Excel on Windows opens a UTF-8 CSV in the locale codepage and every accented
    character is mojibake — the same class of fault C51/C56 recorded on our own
    side, arriving in the user's spreadsheet instead of our terminal.
    """
    out = io.StringIO(newline="")
    for row in rows or []:
        cells = []
        for value in row or []:
            text = clean(value).replace("\r\n", "\n")
            if any(c in text for c in (',', '"', "\n")):
                text = '"' + text.replace('"', '""') + '"'
            cells.append(text)
        out.write(",".join(cells) + "\r\n")
    return b"\xef\xbb\xbf" + out.getvalue().encode("utf-8")
