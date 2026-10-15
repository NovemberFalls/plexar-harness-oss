"""**One chart, three renderers, and the geometry decided in exactly one place.**

T81. Len asked for a chart of one row of a 376-row P&L and got three identical
tool refusals and a confabulation, because no format this product writes could
carry a chart at all. The `image` block re-uses a photograph out of a file
somebody uploaded; there was nothing that DRAWS.

══ WHY THE CONTRACT IS ITS OWN MODULE ══════════════════════════════════════════

Three renderers have to agree, and they share no code otherwise:

    PDF     `re f` fills and `m`/`l`/`S` strokes, points, origin bottom-left
    SVG     markup, pixels, origin TOP-left
    xlsx    OOXML `chart1.xml`, no geometry at all — Excel draws it

**If each computed its own axis, the same chart would have three different
y-ranges and the PDF and the spreadsheet would disagree about what the data
says.** So the ticks are computed here, once, and every renderer is handed the
same numbers. The xlsx renderer ignores the geometry and uses only the data —
that is fine, and it is exactly why the two are separated in this file.

══ EVERY REFUSAL NAMES THE FIELD AND THE FIX ═══════════════════════════════════

`BadChart` messages go back to the MODEL, which will retry. T2's lesson in the
other direction: *"a wrong diagnosis handed to a model is a retry loop."* Len's
session burned its whole tool budget on three identical refusals that were
correct about the cause and silent about the alternative. So each message here
says which field was wrong, what arrived, and what to send instead.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


class BadChart(ValueError):
    """A chart spec the model must fix. Its text goes to the model verbatim."""


#: What shapes exist. **A closed set, and the refusal lists it** — a model that
#: asks for a pie chart must be told what it CAN have, not merely told no.
CHART_SHAPES = ("line", "bar")

#: Ceilings. **A chart is a picture, not a data dump.** 24 categories is a
#: two-year monthly series, which is the case this row was built for; past that
#: the axis labels collide and the picture stops carrying information (C56.3's
#: reasoning about width, applied to density).
MAX_SERIES = 8
MAX_POINTS = 400


@dataclass(frozen=True)
class Series:
    """One line or one set of bars.

    `values` may hold `None` — **a gap is not a zero.** INVARIANT-ENVELOPE, in
    a chart: a missing month plotted at the baseline is a claim that revenue was
    nothing, which is a lie the reader cannot see. A line skips the gap; a bar
    is simply absent.
    """

    name: str = ""
    values: tuple[float | None, ...] = ()
    #: An RGB triple in 0..1, or `None` to take the palette's nth colour. Same
    #: rule as `Block.colour` (T72): `None` means "the renderer decides".
    colour: tuple[float, float, float] | None = None


@dataclass(frozen=True)
class Chart:
    """A chart, format-independent — the only thing the three renderers share."""

    shape: str = "line"
    title: str = ""
    #: One label per category, along the x axis.
    labels: tuple[str, ...] = ()
    series: tuple[Series, ...] = ()
    #: Axis captions. Empty means unlabelled, which is honest; a guessed unit
    #: ("USD") on somebody else's numbers is not.
    x_title: str = ""
    y_title: str = ""

    @property
    def points(self) -> int:
        return len(self.labels)

    @property
    def text(self) -> str:
        """What a text-only reader sees. **A chart announces itself and its
        data**, the way T52 numbered the images rather than letting them be
        silently absent — so `Document.text`, the search index and the
        attachment block all carry the chart instead of a blank.
        """
        out = [f"[chart: {self.shape}"
               + (f" — {self.title}" if self.title else "") + "]"]
        if self.labels:
            out.append("\t".join(("",) + self.labels))
        for s in self.series:
            cells = ["" if v is None else _plain(v) for v in s.values]
            out.append("\t".join([s.name or "series"] + cells))
        return "\n".join(out)


def _plain(value: float) -> str:
    """A number as a human would write it, without a locale or a currency."""
    if value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return f"{value:.6g}"


# ══ PARSING ═════════════════════════════════════════════════════════════════════

def parse_chart(raw: Any) -> Chart:
    """A model-authored `{"type": "chart", …}` dict into a `Chart`.

    Raises `BadChart` with text the model can act on. **Never returns a chart
    with nothing in it** — an empty chart renders as an empty box, and a blank
    rectangle that the model then describes as the answer is the defect this
    whole row exists to end.
    """
    if not isinstance(raw, dict):
        raise BadChart("a chart block must be an object with 'labels' and "
                       "'series'.")

    shape = str(raw.get("chart") or raw.get("shape") or "line").strip().lower()
    if shape in ("column", "bars", "histogram"):
        shape = "bar"
    if shape in ("lines", "linechart"):
        shape = "line"
    if shape not in CHART_SHAPES:
        raise BadChart(
            f"{shape!r} is not a chart shape Plexar can draw, so no file was "
            f"created. Supported: {', '.join(CHART_SHAPES)}.")

    labels = _labels(raw.get("labels"))
    series = _series(raw.get("series"), raw.get("values"), len(labels))

    # ══ THE TWO LENGTHS MUST AGREE, AND SILENCE HERE IS A WRONG PICTURE ══════
    # Zipping the shorter of the two is the tempting repair and it draws a
    # chart that is confidently mislabelled — January's bar under February's
    # tick. **A picture that is wrong in a way the reader cannot detect is
    # worse than a refusal**, so the lengths are checked and named.
    for s in series:
        if len(s.values) != len(labels):
            raise BadChart(
                f"series {s.name or '(unnamed)'!r} has {len(s.values)} "
                f"value(s) but there are {len(labels)} label(s), so no file "
                f"was created. Send one value per label — use null for a gap.")

    if not any(v is not None for s in series for v in s.values):
        raise BadChart("every value in this chart is empty, so there is "
                       "nothing to draw and no file was created.")

    return Chart(
        shape=shape,
        title=_line(raw.get("title")),
        labels=labels,
        series=series,
        x_title=_line(raw.get("x_title") or raw.get("xTitle")),
        y_title=_line(raw.get("y_title") or raw.get("yTitle")),
    )


def _line(value: Any) -> str:
    """A single-line caption. **Control characters are flattened**, for C57's
    reason: this text is drawn into a document and, for the html kind, into
    markup — a newline in an axis title is how a caption becomes two."""
    text = "" if value is None else str(value)
    return " ".join(text.split())[:200]


def _labels(raw: Any) -> tuple[str, ...]:
    if raw is None:
        raise BadChart("a chart needs 'labels': an array of category names "
                       "along the x axis, one per value.")
    if isinstance(raw, str) or not isinstance(raw, (list, tuple)):
        raise BadChart("'labels' must be an array of strings, not "
                       f"{type(raw).__name__}.")
    labels = tuple(_line(v) for v in raw)
    if len(labels) < 2:
        raise BadChart(f"a chart needs at least 2 labels; got {len(labels)}. "
                       "One point is a number, not a chart — write it as a "
                       "sentence instead.")
    if len(labels) > MAX_POINTS:
        raise BadChart(f"a chart may have at most {MAX_POINTS} points; got "
                       f"{len(labels)}. Summarise, or send a table instead.")
    return labels


def _series(raw: Any, bare: Any, width: int) -> tuple[Series, ...]:
    # **A single unnamed series may be written as a bare `values` array.** The
    # model reaches for that shape constantly and refusing it would be a
    # refusal about punctuation, not about the data.
    if raw is None and bare is not None:
        raw = [{"values": bare}]
    if raw is None:
        raise BadChart("a chart needs 'series': an array of "
                       "{'name': …, 'values': [numbers]} objects.")
    if isinstance(raw, dict):
        raw = [raw]
    if isinstance(raw, str) or not isinstance(raw, (list, tuple)):
        raise BadChart("'series' must be an array of objects, each with "
                       "'name' and 'values'.")
    if not raw:
        raise BadChart("'series' is empty, so there is nothing to draw.")
    if len(raw) > MAX_SERIES:
        raise BadChart(f"a chart may show at most {MAX_SERIES} series; got "
                       f"{len(raw)}. Pick the ones that answer the question.")

    from ._colour import parse_colour

    out: list[Series] = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, (list, tuple)):
            item = {"values": item}
        if not isinstance(item, dict):
            raise BadChart(f"series {index} must be an object with 'name' and "
                           f"'values'; got {type(item).__name__}.")
        values = item.get("values", item.get("data"))
        if values is None:
            raise BadChart(f"series {index} has no 'values'. Send an array of "
                           f"{width} number(s), using null for a gap.")
        if isinstance(values, str) or not isinstance(values, (list, tuple)):
            raise BadChart(f"series {index}'s 'values' must be an array of "
                           f"numbers, not {type(values).__name__}.")
        out.append(Series(
            name=_line(item.get("name") or item.get("label")),
            values=tuple(_number(v, index) for v in values),
            colour=parse_colour(item.get("color", item.get("colour"))),
        ))
    return tuple(out)


def _number(value: Any, series: int) -> float | None:
    """One data point, or `None` for a gap.

    **Strings are accepted and stripped of the things a spreadsheet puts in
    them.** The numbers in this row's own case arrived as `$936,205` and
    `10.15%` — read out of a P&L by a model that was quoting what it saw.
    Refusing those would be refusing the actual use case; parsing them is the
    whole reason this helper is not `float(value)`.
    """
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        # **A bool is not a data point.** `True` is 1 in Python and plotting it
        # would be silent nonsense.
        raise BadChart(f"series {series} has a true/false where a number "
                       f"belongs. Send numbers, or null for a gap.")
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).strip()
        negative = text.startswith("(") and text.endswith(")")
        cleaned = "".join(c for c in text if c.isdigit() or c in ".-+e")
        percent = text.endswith("%")
        try:
            number = float(cleaned)
        except ValueError:
            raise BadChart(
                f"series {series} has {value!r} where a number belongs, so no "
                f"file was created. Send numbers without units, or null for a "
                f"gap.") from None
        if percent:
            # **A percentage stays the number it reads as.** 10.15% plots at
            # 10.15 against an axis of percents, NOT at 0.1015 against an axis
            # of dollars — the model that typed the % sign meant the former,
            # and dividing here would silently flatten the series to zero.
            pass
        if negative and number > 0:
            number = -number
    if not math.isfinite(number):
        raise BadChart(f"series {series} has a value that is not a finite "
                       f"number ({value!r}). Send numbers, or null for a gap.")
    return number


# ══ GEOMETRY — COMPUTED ONCE, SHARED BY EVERY RENDERER THAT DRAWS ═══════════════

@dataclass(frozen=True)
class Axis:
    """A y axis: where it starts, where it ends, and where the ticks go."""

    lo: float
    hi: float
    ticks: tuple[float, ...] = ()

    @property
    def span(self) -> float:
        # **Never zero.** A flat series (every value identical) would otherwise
        # divide by zero in every renderer; `nice_axis` widens it instead.
        return self.hi - self.lo


def nice_axis(chart: Chart, *, target_ticks: int = 5) -> Axis:
    """A y axis with round numbers, from the data alone.

    **Bars start at zero and lines do not, and that is not a style choice.** A
    bar's LENGTH encodes its value, so a truncated baseline exaggerates every
    difference — the standard chart lie. A line encodes CHANGE, so forcing zero
    on a series that varies between 936,204 and 972,929 flattens it into a
    straight line and hides the answer. So the rule follows the mark.
    """
    values = [v for s in chart.series for v in s.values if v is not None]
    if not values:
        # `parse_chart` refuses this, so reaching here means a caller built a
        # `Chart` by hand. Still answer rather than raising: a renderer must
        # not be the thing that crashes.
        return Axis(0.0, 1.0, (0.0, 1.0))

    lo, hi = min(values), max(values)
    if chart.shape == "bar":
        lo = min(0.0, lo)
        hi = max(0.0, hi)
    if lo == hi:
        # A single flat value: give it room on both sides so the mark lands in
        # the middle of the plot rather than on its edge.
        pad = abs(lo) * 0.1 or 1.0
        lo, hi = lo - pad, hi + pad

    step = _tick_step((hi - lo) / max(1, target_ticks))
    lo = math.floor(lo / step) * step
    hi = math.ceil(hi / step) * step
    ticks: list[float] = []
    # Integer counting rather than repeated addition: accumulating `step`
    # 40 times drifts, and a drifted tick prints as `-0` or `1.0000000001`.
    count = int(round((hi - lo) / step))
    for i in range(count + 1):
        ticks.append(lo + i * step)
    return Axis(lo, hi, tuple(ticks))


def _tick_step(rough: float) -> float:
    """The 1 / 2 / 5 / 10 ladder — the reason axis labels read as round."""
    if rough <= 0:
        return 1.0
    power = math.floor(math.log10(rough))
    base = 10.0 ** power
    for multiple in (1.0, 2.0, 2.5, 5.0, 10.0):
        if rough <= multiple * base:
            return multiple * base
    return 10.0 * base


def tick_labels(axis: Axis) -> tuple[str, ...]:
    """Every tick's text, in one call — **because the unit is a property of the
    AXIS, not of a tick.**

    Thousands are abbreviated because `936204.81` does not fit under a 468pt
    plot. The first draft of this chose the suffix per tick from its own
    magnitude and produced an axis reading `600k · 700k · 800k · 900k · 1M ·
    1.1M` — which is the exact defect the docstring claimed to prevent, on the
    row that wrote it. **A reader who sees `900k` next to `1M` has to notice
    that the unit changed mid-axis to avoid mis-reading the scale by a factor
    of a thousand.** So the divisor is picked once, from the largest tick, and
    every label on the axis is written in it.
    """
    if not axis.ticks:
        return ()
    biggest = max(abs(t) for t in axis.ticks)
    step = axis.ticks[1] - axis.ticks[0] if len(axis.ticks) > 1 else 1.0

    divisor, suffix = 1.0, ""
    for limit, mark, div in ((1e9, "B", 1e9), (1e6, "M", 1e6), (1e3, "k", 1e3)):
        if biggest >= limit:
            divisor, suffix = div, mark
            break

    # ══ ENOUGH DECIMALS THAT THE STEP IS EXACTLY REPRESENTABLE ══════════════
    # **Found by reading the output, not by reasoning about it.** The first
    # rule here was `-floor(log10(step))`, which gives ONE decimal for a step
    # of 0.25M and prints the 2.5 rung of the tick ladder as
    #
    #     0.0M · 0.2M · 0.5M · 0.8M · 1.0M · 1.2M
    #
    # — six evenly spaced gridlines labelled with unevenly spaced numbers,
    # because 0.25 rounds to 0.2 and 0.75 to 0.8. A reader takes the LABELS as
    # the scale, so that axis misstates every interval on it.
    #
    # So the count is chosen by asking what it produces: the fewest decimals
    # for which the labels are distinct AND consecutive gaps are equal. That
    # question cannot be got wrong by a rounding rule, because it inspects the
    # rounding.
    scaled = [v / divisor for v in axis.ticks]
    decimals = 6
    for candidate in range(0, 7):
        rendered = [round(v, candidate) for v in scaled]
        if len(set(rendered)) != len(rendered):
            continue
        gaps = {round(b - a, candidate + 3)
                for a, b in zip(rendered, rendered[1:])}
        if len(gaps) <= 1:
            decimals = candidate
            break

    # **Every label gets the same number of decimals, deliberately.** Trimming
    # each one's trailing zeros yields `1.1M` beside `1.15M`, and ragged
    # decimals down an axis read as noise rather than as a scale.
    return tuple(f"{v / divisor:.{decimals}f}{suffix}" for v in axis.ticks)


def fraction(value: float, axis: Axis) -> float:
    """Where a value sits in the plot, 0 at the bottom and 1 at the top."""
    return (value - axis.lo) / axis.span if axis.span else 0.0
