"""`.csv` and `.xlsx`, from rows.

CSV ships first and is not a throwaway: it exercises the whole path — tool ->
bytes -> `Projects.upload` -> the existing download route — with a format that
cannot be malformed. **If the file does not arrive, the fault is in the plumbing
and not in an OOXML package**, and that separation is worth one small module.

══ `inlineStr` AND NO `sharedStrings.xml` ══════════════════════════════════
Shared strings are an indirection: cells hold an INDEX into a separate part.
That is smaller for a real spreadsheet and is a second place to be wrong for
ours — an off-by-one there puts the wrong word in every cell, and the file still
opens, so nothing looks broken. Inline strings cost bytes we do not care about
and remove the indirection entirely.

**Every cell is a string, deliberately.** Guessing that "0123" is a number
loses the leading zero, and guessing that "1/2" is a date turns a fraction into
January 2nd — the handoff's warning about serial dates, met by declining to
infer rather than by inferring carefully.

══ T81 — THE INVARIANT IS NARROWED, NOT DROPPED, FOR ONE PURPOSE ═══════════
A chart plots a range of CELLS, and Excel recomputes a chart's plotted values
from the sheet every time the workbook opens — a `c:numCache` is a hint for a
viewer that never recalculates, not a source of truth. A chart pointed at
`t="inlineStr"` cells therefore plots every point as zero, silently, on the
one machine that matters: the reader's copy of Excel.

So there is exactly one place in this module that ever writes a numeric cell:
the data grid this module builds FOR a chart, below any rows the caller
supplied. Every other cell in the workbook — every caller-supplied row,
including the chart's own category (label) column — is still `t="inlineStr"`,
unchanged, for the reasons above. The narrowing lives entirely in
`_sheet_xml`: a cell is written numeric if and only if the Python value handed
to it is a real `int`/`float` (never `bool`), and the only code path that ever
puts a bare float into a row is the chart-grid builder in `xlsx_bytes`. No
caller-supplied string is ever reinterpreted as a number.
"""

from __future__ import annotations

import io
import zipfile

from .._model import Document
from .._colour import hex_of
from .._xml import clean, escape

XL_CONTENT_TYPES_BASE = (
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
)

XL_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

# ══ T81 — `xl/styles.xml` SHIPPED WITH NO RELATIONSHIP (PRE-EXISTING BUG) ═══
# `xl/_rels/workbook.xml.rels` named the worksheet and never named the styles
# part it sits beside — every generated workbook has been missing this
# relationship since the module existed. Excel tolerates it because it also
# finds `xl/styles.xml` by its well-known part name, which is exactly the
# "the file still opens, so nothing looks broken" trap this module's own
# docstring warns about for shared strings. Fixed here as `rId2`, `rId1`
# unchanged so nothing that already depends on the worksheet's id moves.
WB_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>
<fills count="1"><fill><patternFill patternType="none"/></fill></fills>
<borders count="1"><border/></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>
</styleSheet>"""

_HEAD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'

# ══ NAMESPACES — SHARED BY THE DRAWING AND THE CHART PART ═══════════════════
_RELT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
REL_DRAWING = _RELT + "drawing"
REL_CHART = _RELT + "chart"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
C_NS = "http://schemas.openxmlformats.org/drawingml/2006/chart"
XDR_NS = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CHART_CT = "application/vnd.openxmlformats-officedocument.drawingml.chart+xml"
DRAWING_CT = "application/vnd.openxmlformats-officedocument.drawing+xml"


def styles_xml(accent: str = "") -> str:
    """The workbook's style table — one extra style when a palette is given.

    ══ A SPREADSHEET'S STYLING IS ITS HEADER ROW, AND THAT IS NOT A SHORTCUT ═
    Len: *"what if they want to style a docx or excel or power point?"* A `.pdf`
    and a `.docx` are read as prose, so colour lands on headings and body text.
    **A sheet is read as a grid**, and the one piece of formatting that changes
    how it is read is the header: bold, filled, and legible against the fill.
    Colouring arbitrary cells would need a style per distinct colour, a
    `cellXfs` index threaded through every cell, and a way for the model to say
    which cells — three things whose absence is not what makes a spreadsheet
    look unfinished.

    **`fillId` 0 and 1 are RESERVED BY THE FORMAT** — `none` and `gray125` —
    and Excel silently mis-renders a workbook whose fills do not start with
    them. So the accent is fill index 2, not 1, and the first two are written
    even though nothing uses `gray125`.

    **The header's text is WHITE**, because the accent is required to be dark
    enough to read black text ON — which is exactly the colour black text
    cannot be read against.
    """
    if not accent:
        return STYLES
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="2">'
        '<font><sz val="11"/><name val="Calibri"/></font>'
        '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>'
        "</fonts>"
        '<fills count="3">'
        '<fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill>'
        f'<fill><patternFill patternType="solid"><fgColor rgb="FF{accent}"/>'
        f'<bgColor indexed="64"/></patternFill></fill>'
        "</fills>"
        "<borders count=\"1\"><border/></borders>"
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>'
        "</cellStyleXfs>"
        '<cellXfs count="2">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" '
        'applyFont="1" applyFill="1"/>'
        "</cellXfs>"
        "</styleSheet>"
    )


def column_name(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA. **Not `chr(65 + i)`** — that silently produces
    `[` for the 27th column, and a sheet wider than the alphabet is ordinary."""
    name = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        name = chr(65 + rem) + name
    return name


def _num(value: float) -> str:
    """A float as OOXML wants it: no locale, no thousands separator, and an
    integer-valued float written without a trailing `.0`."""
    if value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return repr(float(value))


def _rels(entries: list[tuple[str, str, str]]) -> str:
    body = "".join(
        f'<Relationship Id="{rid}" Type="{typ}" Target="{target}"/>'
        for rid, typ, target in entries)
    return f'{_HEAD}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{body}</Relationships>'


def _sheet_xml(rows: list[list], header: bool = False,
               drawing_rid: str | None = None) -> str:
    body = []
    for r, row in enumerate(rows or [], start=1):
        cells = []
        # `s="1"` is the styled cell format from `styles_xml`. **Row 1 only**,
        # and only when a palette was given — a sheet with no style keeps
        # writing cells with no `s` attribute at all, which is the pre-T73 file
        # byte for byte.
        style = ' s="1"' if header and r == 1 else ""
        for c, value in enumerate(row or []):
            # ══ THE ONE NUMERIC BRANCH IN THIS MODULE (T81) ══════════════════
            # A bare Python `int`/`float` reaches here ONLY from the chart data
            # grid `xlsx_bytes` builds — every caller-supplied row is still
            # `list[list[str]]` by contract, so this branch cannot fire on
            # ordinary content. `bool` is excluded because it is an `int`
            # subclass and is not a data point.
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                ref = f"{column_name(c)}{r}"
                cells.append(f'<c r="{ref}"{style}><v>{_num(value)}</v></c>')
                continue
            text = clean(value)
            if text == "":
                # AN EMPTY CELL IS OMITTED, and the `r` reference on its
                # neighbours is what keeps the row aligned. This is the exact
                # trap the handoff named for the READER; the writer has to
                # honour the same rule or a sparse row shifts left. `None`
                # (a chart gap) reaches here too and is omitted the same way.
                continue
            ref = f"{column_name(c)}{r}"
            cells.append(f'<c r="{ref}"{style} t="inlineStr">'
                         f'<is><t xml:space="preserve">'
                         f"{escape(text)}</t></is></c>")
        body.append(f'<row r="{r}">{"".join(cells)}</row>')
    ns_r = (f' xmlns:r="{R_NS}"' if drawing_rid else "")
    drawing_tag = f'<drawing r:id="{drawing_rid}"/>' if drawing_rid else ""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"{ns_r}>'
        f'<sheetData>{"".join(body)}</sheetData>{drawing_tag}</worksheet>'
    )


def _quoted_sheet(name: str) -> str:
    """A sheet name as a formula wants it — always quoted, because a caller
    may have left spaces or punctuation in it and an unquoted formula breaks
    at the first one."""
    return "'" + name.replace("'", "''") + "'"


def _range(name: str, col: str, r1: int, r2: int) -> str:
    q = _quoted_sheet(name)
    return f"{q}!${col}${r1}:${col}${r2}"


def _series_label(series, index: int) -> str:
    return series.name or f"Series {index + 1}"


def _series_xml(index: int, series, cat_range: str, labels: tuple[str, ...],
                 val_range: str, shape: str) -> str:
    name_val = _series_label(series, index)
    colour_xml = ""
    if series.colour is not None:
        rgb = hex_of(series.colour)
        if shape == "line":
            colour_xml = (f'<c:spPr><a:ln w="28575"><a:solidFill>'
                          f'<a:srgbClr val="{rgb}"/></a:solidFill></a:ln>'
                          f'</c:spPr>')
        else:
            colour_xml = (f'<c:spPr><a:solidFill><a:srgbClr val="{rgb}"/>'
                          f'</a:solidFill></c:spPr>')
    cat_pts = "".join(
        f'<c:pt idx="{i}"><c:v>{escape(v)}</c:v></c:pt>'
        for i, v in enumerate(labels))
    val_pts = "".join(
        f'<c:pt idx="{i}"><c:v>{_num(v)}</c:v></c:pt>'
        for i, v in enumerate(series.values) if v is not None)
    smooth = '<c:smooth val="0"/>' if shape == "line" else ""
    return (
        f'<c:ser><c:idx val="{index}"/><c:order val="{index}"/>'
        f'<c:tx><c:v>{escape(name_val)}</c:v></c:tx>'
        f'{colour_xml}'
        f'<c:cat><c:strRef><c:f>{escape(cat_range)}</c:f>'
        f'<c:strCache><c:ptCount val="{len(labels)}"/>{cat_pts}</c:strCache>'
        f'</c:strRef></c:cat>'
        f'<c:val><c:numRef><c:f>{escape(val_range)}</c:f>'
        f'<c:numCache><c:formatCode>General</c:formatCode>'
        f'<c:ptCount val="{len(series.values)}"/>{val_pts}</c:numCache>'
        f'</c:numRef></c:val>{smooth}</c:ser>'
    )


def _title_xml(text: str) -> str:
    return (f'<c:title><c:tx><c:rich><a:bodyPr/><a:lstStyle/>'
            f'<a:p><a:r><a:t>{escape(text)}</a:t></a:r></a:p>'
            f'</c:rich></c:tx><c:overlay val="0"/></c:title>')


def _chart_xml(chart, sheet_name: str, start_row: int) -> str:
    """One chart's `chart{n}.xml`.

    **Geometry is not computed here.** `_chart.nice_axis` and `tick_labels`
    exist for the PDF and SVG renderers, which have to draw their own axis;
    Excel draws its own from the cell ranges the `c:f` formulas point at, so
    importing either would be dead code pretending to matter.
    """
    label_r1 = start_row + 1
    label_r2 = start_row + len(chart.labels)
    cat_range = _range(sheet_name, "A", label_r1, label_r2)

    sers = []
    for i, series in enumerate(chart.series):
        col = column_name(i + 1)
        val_range = _range(sheet_name, col, label_r1, label_r2)
        sers.append(_series_xml(i, series, cat_range, chart.labels,
                                 val_range, chart.shape))
    body = "".join(sers)

    ax_cat, ax_val = "111111111", "222222222"
    if chart.shape == "bar":
        plot = (f'<c:barChart><c:barDir val="col"/>'
                f'<c:grouping val="clustered"/><c:varyColors val="0"/>'
                f'{body}<c:axId val="{ax_cat}"/><c:axId val="{ax_val}"/>'
                f'</c:barChart>')
    else:
        plot = (f'<c:lineChart><c:grouping val="standard"/>'
                f'<c:varyColors val="0"/>{body}<c:marker val="1"/>'
                f'<c:axId val="{ax_cat}"/><c:axId val="{ax_val}"/>'
                f'</c:lineChart>')

    title_xml = _title_xml(chart.title) if chart.title else '<c:autoTitleDeleted val="1"/>'
    cat_title = _title_xml(chart.x_title) if chart.x_title else ""
    val_title = _title_xml(chart.y_title) if chart.y_title else ""

    return (
        f'{_HEAD}<c:chartSpace xmlns:c="{C_NS}" xmlns:a="{A_NS}" xmlns:r="{R_NS}">'
        '<c:chart>'
        f'{title_xml}'
        '<c:plotArea><c:layout/>'
        f'{plot}'
        f'<c:catAx><c:axId val="{ax_cat}"/><c:scaling>'
        f'<c:orientation val="minMax"/></c:scaling><c:delete val="0"/>'
        f'<c:axPos val="b"/>{cat_title}<c:crossAx val="{ax_val}"/></c:catAx>'
        f'<c:valAx><c:axId val="{ax_val}"/><c:scaling>'
        f'<c:orientation val="minMax"/></c:scaling><c:delete val="0"/>'
        f'<c:axPos val="l"/>{val_title}<c:crossAx val="{ax_cat}"/></c:valAx>'
        '</c:plotArea>'
        '<c:legend><c:legendPos val="b"/><c:overlay val="0"/></c:legend>'
        '<c:plotVisOnly val="1"/>'
        '</c:chart></c:chartSpace>'
    )


def _anchor_xml(index: int, row0: int) -> str:
    """One chart's placement, stacked below the previous one so multiple
    charts on the same sheet do not overlap."""
    col_from, col_to = 10, 20
    row_to = row0 + 18
    return (
        '<xdr:twoCellAnchor>'
        f'<xdr:from><xdr:col>{col_from}</xdr:col><xdr:colOff>0</xdr:colOff>'
        f'<xdr:row>{row0}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from>'
        f'<xdr:to><xdr:col>{col_to}</xdr:col><xdr:colOff>0</xdr:colOff>'
        f'<xdr:row>{row_to}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:to>'
        '<xdr:graphicFrame macro="">'
        '<xdr:nvGraphicFramePr>'
        f'<xdr:cNvPr id="{index + 1}" name="Chart {index}"/>'
        '<xdr:cNvGraphicFramePr/>'
        '</xdr:nvGraphicFramePr>'
        '<xdr:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/></xdr:xfrm>'
        '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/chart">'
        f'<c:chart xmlns:c="{C_NS}" xmlns:r="{R_NS}" r:id="rId{index}"/>'
        '</a:graphicData></a:graphic>'
        '</xdr:graphicFrame><xdr:clientData/></xdr:twoCellAnchor>'
    )


def _drawing_xml(anchors: list[str]) -> str:
    return (
        f'{_HEAD}<xdr:wsDr xmlns:xdr="{XDR_NS}" xmlns:a="{A_NS}">'
        f'{"".join(anchors)}</xdr:wsDr>'
    )


def xlsx_bytes(rows: list[list[str]], *, sheet: str = "Sheet1",
               theme: dict | None = None, charts: list[dict] | None = None) -> bytes:
    theme = theme if isinstance(theme, dict) else {}
    accent = hex_of(theme.get("accent") or theme.get("heading"))
    name = clean(sheet).strip() or "Sheet1"
    # Excel refuses these in a sheet name and refuses names over 31 characters.
    for bad in "[]:*?/\\":
        name = name.replace(bad, "-")
    name = name[:31]

    # ══ T81 — THE CHART'S DATA IS MATERIALISED INTO THE SHEET, NOT THE CACHE ═
    # A chart formula (`c:f`) points at a real range, so the chart stays live
    # if a person edits a cell later — the whole reason this shape was chosen
    # over dropping a rendered picture into the sheet. Each chart gets its own
    # header row (series names) and one row per label, separated from the
    # caller's own rows — and from each other — by a blank row.
    all_rows: list[list] = list(rows or [])
    chart_specs: list[tuple[object, int]] = []
    if charts:
        from .._chart import parse_chart
        for raw in charts:
            chart = parse_chart(raw)
            all_rows.append([])
            start_row = len(all_rows) + 1
            header = [""] + [_series_label(s, i) for i, s in enumerate(chart.series)]
            all_rows.append(header)
            for li, label in enumerate(chart.labels):
                row: list = [label]
                for s in chart.series:
                    row.append(s.values[li])
                all_rows.append(row)
            chart_specs.append((chart, start_row))

    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets><sheet name="{escape(name)}" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )

    drawing_rid = "rId1" if chart_specs else None
    parts: dict[str, str] = {
        "_rels/.rels": XL_RELS,
        "xl/workbook.xml": workbook,
        "xl/_rels/workbook.xml.rels": WB_RELS,
        "xl/styles.xml": styles_xml(accent),
        "xl/worksheets/sheet1.xml": _sheet_xml(all_rows, bool(accent), drawing_rid),
    }

    overrides = [
        ("/xl/workbook.xml",
         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"),
        ("/xl/worksheets/sheet1.xml",
         "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"),
        ("/xl/styles.xml",
         "application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"),
    ]

    if chart_specs:
        parts["xl/worksheets/_rels/sheet1.xml.rels"] = _rels(
            [("rId1", REL_DRAWING, "../drawings/drawing1.xml")])

        anchors = []
        chart_rels = []
        for i, (chart, start_row) in enumerate(chart_specs, start=1):
            parts[f"xl/charts/chart{i}.xml"] = _chart_xml(chart, name, start_row)
            overrides.append((f"/xl/charts/chart{i}.xml", CHART_CT))
            chart_rels.append((f"rId{i}", REL_CHART, f"../charts/chart{i}.xml"))
            anchors.append(_anchor_xml(i, (i - 1) * 20))

        parts["xl/drawings/drawing1.xml"] = _drawing_xml(anchors)
        parts["xl/drawings/_rels/drawing1.xml.rels"] = _rels(chart_rels)
        overrides.append(("/xl/drawings/drawing1.xml", DRAWING_CT))

    parts["[Content_Types].xml"] = (
        f'{_HEAD}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        f'{XL_CONTENT_TYPES_BASE}'
        + "".join(f'<Override PartName="{p}" ContentType="{c}"/>' for p, c in overrides)
        + "</Types>"
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for part, data in parts.items():
            info = zipfile.ZipInfo(part, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, data.encode("utf-8"))
    return buffer.getvalue()


def write(document: Document) -> bytes:
    """Document -> `.xlsx`. Sheets become sheets; prose becomes one column.

    **A document with no tabular content is not an error.** It becomes a
    single-column sheet of its lines, because refusing would mean a user who
    asked for "this as a spreadsheet" gets nothing and no reason.
    """
    sheets = [b for b in document.blocks if b.kind in ("sheet", "table")]
    if sheets:
        first = sheets[0]
        rows = list(first.rows)
        for extra in sheets[1:]:
            rows.append([])
            if extra.name:
                rows.append([extra.name])
            rows.extend(extra.rows)
        return xlsx_bytes(rows, sheet=first.name or "Sheet1")
    rows = [[b.text] for b in document.blocks if b.text]
    return xlsx_bytes(rows or [[""]], sheet=document.title[:31] or "Sheet1")
