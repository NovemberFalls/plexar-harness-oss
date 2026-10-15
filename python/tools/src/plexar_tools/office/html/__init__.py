"""HTML. **Write only, and self-contained by construction (T81).**

A generated `.html` is DOWNLOADED. It is served `application/octet-stream` off
Chat's origin and then opened off the user's own disk, possibly with no network
at all — so a document that reaches for a stylesheet, a font or a script is a
document that renders as a blank box on the machine it was made for. C50's
vendored `/lib/chart.umd.js` shelf resolves ONLY on the artifact origin, which
makes Chart.js exactly the wrong tool here even though it is the right one two
directories away.

**So the charts are inline SVG and there is no other resource of any kind.** No
`<script>`, no `<link>`, no `@import`, no `src=`, no `http`. `_write.py` holds
the drawing; `tests/test_chart_html.py` gates the absence, because
"self-contained" is a property that decays the first time somebody adds a
convenience.
"""

from ._write import build

__all__ = ["build"]
