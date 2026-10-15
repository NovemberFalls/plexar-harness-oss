"""CSV, TXT and Markdown. **The format that proves the plumbing.**

CSV shipped first in T40 for a reason that still holds: if the file does not
arrive, the fault is in the pipeline and not in an OOXML package.
"""

from __future__ import annotations

import csv
import io

from .._model import Block, Document
from .._xml import clean
from ._csv import csv_bytes

MAX_ROWS = 20_000


def read(data: bytes) -> Document:
    """Bytes -> Document. A CSV becomes a sheet; anything else becomes prose.

    **Decoded with `utf-8-sig`**, which strips the BOM Excel writes. Without
    that the first header cell arrives as `\ufeffRegion` and never matches
    anything the user searches for.
    """
    text = data.decode("utf-8-sig", "replace")
    document = Document(source_kind="csv")
    sample = text[:4096]
    if "," in sample or "\t" in sample:
        delimiter = "\t" if sample.count("\t") > sample.count(",") else ","
        rows = [row for _, row in
                zip(range(MAX_ROWS), csv.reader(io.StringIO(text),
                                                delimiter=delimiter))]
        if rows:
            document.blocks.append(
                Block(kind="sheet", name="Sheet1",
                      rows=[[clean(c) for c in r] for r in rows]))
            return document
    for line in text.splitlines()[:MAX_ROWS]:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("### "):
            document.blocks.append(Block(kind="heading3", text=stripped[4:]))
        elif stripped.startswith("## "):
            document.blocks.append(Block(kind="heading2", text=stripped[3:]))
        elif stripped.startswith("# "):
            document.blocks.append(Block(kind="heading1", text=stripped[2:]))
        elif stripped[:2] in ("- ", "* "):
            document.blocks.append(Block(kind="bullet", text=stripped[2:]))
        else:
            document.blocks.append(Block(kind="paragraph", text=stripped))
    return document


def write(document: Document) -> bytes:
    """Document -> CSV when it is tabular, otherwise plain text."""
    rows: list[list[str]] = []
    for block in document.blocks:
        if block.kind in ("sheet", "table"):
            rows.extend(block.rows)
    if rows:
        return csv_bytes(rows)
    lines: list[str] = []
    for block in document.blocks:
        if block.kind == "image":
            lines.append(f"[image: {block.image.name if block.image else ''}]")
        elif block.kind == "bullet":
            lines.append(f"- {block.text}")
        elif block.kind.startswith("heading"):
            lines.append("")
            lines.append(block.text)
        elif block.kind == "slide":
            lines.append("")
            lines.append(block.text)
            lines.extend(f"- {b}" for b in block.bullets)
        elif block.text:
            lines.append(block.text)
    return ("\n".join(lines).strip() + "\n").encode("utf-8")


__all__ = ["read", "write", "csv_bytes"]
