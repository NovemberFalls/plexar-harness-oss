# The typefaces embedded in generated PDFs

**All faces here are SIL Open Font License 1.1.** The OFL requires this notice to travel
with the fonts, and it is a condition of the licence rather than a courtesy — so it lives
beside them rather than in a document somewhere else.

| file | family | upstream | licence |
|---|---|---|---|
| `figtree-regular.ttf` · `figtree-bold.ttf` | Figtree | google/fonts `ofl/figtree` | OFL 1.1 |
| `jetbrains-regular.ttf` · `jetbrains-bold.ttf` | JetBrains Mono | google/fonts `ofl/jetbrainsmono` | OFL 1.1 |

**The full licence text is in [`chat/web/static/fonts/LICENSE.md`](../../../web/static/fonts/LICENSE.md)**, where these
same families are already vendored for the UI. There is one copy of the notice, not two
that can drift apart.

## These are not the same files as the UI's

The UI ships `woff2` — Brotli-compressed, and **variable** fonts carrying one `wght` axis
from 300 to 900. No PDF reader understands either. `tools/vendor_pdf_fonts.py` instances
each source at a static weight and writes a plain TTF; that tool is a build step and its
output is what is committed here.

**Every file is pinned by SHA-256 in `MANIFEST.json` and the digest is checked before the
font is used.** C62 is the reason: `core.autocrlf` silently rewrote the vendored Chart.js
on every Windows checkout, so the served bytes were not the vetted bytes and only the pin
noticed. A rewritten TTF is worse than a rewritten script — it is a file that will not
parse, and the symptom is a PDF that opens with no text.

A face whose digest does not match is **not used**: the document is set in a base-14
typeface instead. A document in Helvetica is a document; a blank one is not.

## What is NOT here, and why

**No serif.** The three OFL families this product already owns are two sans faces and a
monospace. A serif is what makes a document read as a document, and adding one means
vendoring one more OFL file — EB Garamond, Source Serif or Libre Baskerville are the
obvious candidates. **The machinery is now the cheap part**: drop the `woff2` or `ttf` in,
add a line to `BUILD` in the vendoring tool, and a family to `EMBEDDED` in `_faces.py`.

**No italic**, and that is the font's fault rather than a shortcut. Both sources carry a
single `wght` axis, so there is no slanted design to instance. Italic resolves to the
upright face rather than being faked with a text-matrix skew — a synthetic oblique is a
different typeface wearing this one's name, and a reader would meet it in the same
document as a real `Times-Italic`.
