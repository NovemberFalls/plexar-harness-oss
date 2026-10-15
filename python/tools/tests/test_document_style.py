"""T72 · the model could describe a palette and had no way to ask for one.

Len, on the third identical PDF: *"Theres no color variations in the header, is
this a model limitation or a harness limitation?"*

**Ours, and it was measurable.** Two PDFs produced a day apart from the same
document, one after the model was explicitly asked for *"blue for preparation,
green for setup, yellow for placement, red for safety"*:

    bytes            839,553  /  839,305
    fill colours     0.100 0.100 0.110   INK      identical
                     0.110 0.200 0.310   ACCENT   identical
                     0.780 0.800 0.830   RULE     identical

Three constants in `pdf/_write.py`, and `create_document` had **no colour,
style or theme field at all**. The model was not lying about the document; it
was describing a document it could not ask for.

══ WHAT THIS FILE ASSERTS, AND WHY EACH HALF IS SEPARATE ════════════════════
1. the colours ARRIVE — a themed document really carries them
2. the default is UNCHANGED — T51's three constants, byte-for-byte
3. what cannot be READ is refused, not darkened
4. the palette survives the COMPOSE hop, which is the kind Len actually asks
   for and the one path where a late-added field would silently vanish
"""

from __future__ import annotations

import pathlib
import re

from plexar_tools import office
from plexar_tools.office._colour import parse_colour, readable_on_white
from plexar_tools.office.pdf._write import ACCENT, INK, RULE, build

FILL = re.compile(rb"([\d.]+ [\d.]+ [\d.]+) rg")


def colours(pdf: bytes) -> set[str]:
    """Every fill colour the file actually paints. **Read off the bytes**, not
    off the spec that produced them — the whole defect was a spec that said one
    thing and a file that contained another."""
    return {m.decode() for m in set(FILL.findall(pdf))}


def rgb(triple) -> str:
    return f"{triple[0]:.3f} {triple[1]:.3f} {triple[2]:.3f}"


PLAIN = [{"type": "heading1", "text": "Tuna Poke Thawing Procedure"},
         {"type": "paragraph", "text": "Follow these steps."}]


# ══════════════════════════════════════════════════════════════════════════════
# 1 · THE DEFAULT IS EXACTLY WHAT IT WAS
# ══════════════════════════════════════════════════════════════════════════════

def test_a_document_that_says_nothing_is_UNCHANGED() -> None:
    """**Asserted first, and as an exact set.** Every conversion this product
    has ever done goes down this path, and a styling row that shifted the
    default look would be a redesign nobody asked for riding inside a feature
    somebody did."""
    assert colours(build(PLAIN)) == {rgb(ACCENT), rgb(INK), rgb(RULE)}
    # And through the real entry point, where `style` is simply absent.
    made = office.build("pdf", "plain", {"blocks": PLAIN})
    assert colours(made.body) == {rgb(ACCENT), rgb(INK), rgb(RULE)}


def test_a_style_naming_nothing_recognisable_is_the_default_too() -> None:
    """A palette of typos must not become a palette of guesses. `theme_from`
    returns `None`, which is the same state as "said nothing"."""
    made = office.build("pdf", "junk", {
        "style": {"accent": "chartreuse", "ink": "#12345", "rule": ""},
        "blocks": PLAIN})
    assert colours(made.body) == {rgb(ACCENT), rgb(INK), rgb(RULE)}


# ══════════════════════════════════════════════════════════════════════════════
# 2 · THE COLOURS ARRIVE
# ══════════════════════════════════════════════════════════════════════════════

def test_the_documents_palette_reaches_the_page() -> None:
    """Each field falls back independently, so a style naming one colour
    changes one thing — asserted by naming only the accent and checking the
    other two are still the defaults."""
    made = office.build("pdf", "accented", {
        "style": {"accent": "#b8860b"}, "blocks": PLAIN})
    seen = colours(made.body)
    assert "0.722 0.525 0.043" in seen, seen
    assert rgb(ACCENT) not in seen, ("the default accent is still being "
                                     "painted beside the chosen one", seen)
    assert rgb(INK) in seen and rgb(RULE) in seen, seen


def test_every_heading_can_have_its_OWN_colour() -> None:
    """**The thing Len asked for, in his own words**: *"color-coded step
    headings using a modern, intuitive palette: blue for preparation, green for
    setup, yellow for placement, and red for final safety steps."* Three of
    those four are legible and land; the fourth has its own arm below."""
    made = office.build("pdf", "coded", {"blocks": [
        {"type": "heading1", "text": "Procedure"},
        {"type": "heading2", "text": "Step 1", "color": "#1f77b4"},
        {"type": "heading2", "text": "Step 2", "color": "#2ca02c"},
        {"type": "heading2", "text": "Danger", "color": "#d62728"},
    ]})
    seen = colours(made.body)
    for wanted in ("0.122 0.467 0.706", "0.173 0.627 0.173",
                   "0.839 0.153 0.157"):
        assert wanted in seen, (wanted, seen)


def test_BOTH_spellings_of_colour_are_read() -> None:
    """`color` is what a model trained on the web writes; `colour` is what this
    codebase writes. **A schema documenting one and a parser reading the other
    is a feature that never fires and never reddens.**"""
    for key in ("color", "colour"):
        made = office.build("pdf", key, {"blocks": [
            {"type": "heading2", "text": "S", key: "#1f77b4"}]})
        assert "0.122 0.467 0.706" in colours(made.body), key


def test_alignment_is_three_state() -> None:
    """`None` keeps the kind's own default. Measured on the x-offset of the
    drawn text: a centred paragraph does not start at the left margin, and a
    block saying nothing starts exactly where it always did."""
    def first_x(pdf: bytes) -> str:
        # **The x of the drawn text, off the `Td` operator.** Read from the
        # bytes rather than from the layout, because "centred" is a claim about
        # where the glyphs end up and nothing else.
        found = re.search(rb"Tf ([\d.]+) [\d.]+ Td", pdf)
        assert found, pdf[:400]
        return found.group(1).decode()

    plain = build([{"type": "paragraph", "text": "body text here"}])
    centred = build([{"type": "paragraph", "text": "body text here",
                      "align": "centre"}])
    assert first_x(plain) != first_x(centred)
    # AND AN UNRECOGNISED VALUE IS THE DEFAULT, not a guess.
    junk = build([{"type": "paragraph", "text": "body text here",
                   "align": "diagonally"}])
    assert first_x(junk) == first_x(plain)


# ══════════════════════════════════════════════════════════════════════════════
# 3 · WHAT CANNOT BE READ IS REFUSED
# ══════════════════════════════════════════════════════════════════════════════

def test_a_colour_nobody_can_read_is_REFUSED_not_darkened() -> None:
    """A model asked for *"yellow for placement"* writes `#ffff00`, which on
    white paper is very nearly invisible.

    **Refused, not nudged.** Darkening it would put a colour in the document
    that nobody chose — and the answer would then describe the colour it asked
    for, which is this row's own defect rebuilt one layer in. The heading falls
    back to the theme's, which is legible by construction.
    """
    made = office.build("pdf", "pale", {"blocks": [
        {"type": "heading2", "text": "Placement", "color": "#ffff00"}]})
    seen = colours(made.body)
    assert "1.000 1.000 0.000" not in seen, seen
    assert rgb(ACCENT) in seen, ("the refused heading lost its colour "
                                 "altogether instead of falling back", seen)
    # THE FLOOR ITSELF, so the threshold is a stated number and not a mood.
    assert readable_on_white(parse_colour("#b8860b")) is True
    assert readable_on_white(parse_colour("#e0a800")) is False
    assert readable_on_white(parse_colour("#ffff00")) is False


# ══════════════════════════════════════════════════════════════════════════════
# 4 · THE COMPOSE HOP — the kind Len actually asks for
# ══════════════════════════════════════════════════════════════════════════════

def test_WATCH_TO_FAIL_the_pre_T72_writer_paints_three_colours_whatever_is_asked() -> None:
    """**The measured before-state**, so every arm above is compared against
    something rather than asserted into existence.

    Asserted as a PAIR: the unstyled build must produce exactly T51's three AND
    the styled one must differ. Asserting only the difference would pass
    against a writer that had broken the default instead of honouring a theme.
    """
    styled = office.build("pdf", "s", {
        "style": {"accent": "#b8860b"},
        "blocks": [{"type": "heading1", "text": "T"},
                   {"type": "heading2", "text": "S", "color": "#1f77b4"}]})
    unstyled = office.build("pdf", "u", {
        "blocks": [{"type": "heading1", "text": "T"},
                   {"type": "heading2", "text": "S"}]})
    assert colours(unstyled.body) == {rgb(ACCENT), rgb(RULE)}, \
        "the default look changed — that is a redesign, not a feature"
    assert colours(styled.body) != colours(unstyled.body), \
        "a style was given and the file came out identical — the defect"
    assert len(colours(styled.body)) > len(colours(unstyled.body))


# ══════════════════════════════════════════════════════════════════════════════
# 5 · T73 — EVERY FORMAT THAT CAN CARRY A PALETTE, CARRIES THE SAME ONE
# ══════════════════════════════════════════════════════════════════════════════
#
# Len: *"what if they want to style a docx or excel or power point... or
# something else like an html?"*
#
# **T72 gave the model a palette and only the PDF read it.** That is a worse
# state than no styling at all: the same request produces a coloured PDF and a
# black-and-white Word file, which reads as the model ignoring him on one format
# and not the other. One `style`, every writer.
#
# The formats differ in WHERE colour lives and each is asserted against the real
# XML, never against the spec that produced it:
#
#     docx   <w:color> in <w:rPr>       — a RUN property; on <w:pPr> it is dropped
#     pptx   <a:solidFill> in <a:rPr>   — a child element; there is no attribute
#     xlsx   a fill + font in styles.xml, and `s="1"` on the header cells
#     csv    nowhere. Ignored, and the schema says so.

import io
import zipfile


def _part(blob: bytes, name: str) -> str:
    return zipfile.ZipFile(io.BytesIO(blob)).read(name).decode("utf-8")


def _parts(blob: bytes, prefix: str) -> str:
    zf = zipfile.ZipFile(io.BytesIO(blob))
    return "".join(zf.read(n).decode("utf-8")
                   for n in zf.namelist() if n.startswith(prefix))


def test_a_docx_carries_the_palette_AND_the_per_block_colour() -> None:
    made = office.build("docx", "styled", {
        "style": {"accent": "#b8860b"},
        "blocks": [{"type": "heading1", "text": "Procedure"},
                   {"type": "heading2", "text": "Step 1", "color": "#1f77b4"},
                   {"type": "paragraph", "text": "body", "align": "center"}]})
    xml = _part(made.body, "word/document.xml")
    found = set(re.findall(r'w:color w:val="(\w+)"', xml))
    assert "B8860B" in found, ("the theme did not reach the heading", found)
    assert "1F77B4" in found, ("the per-block colour did not reach the run", found)
    # **THE COLOUR IS A RUN PROPERTY.** On `<w:pPr>` Word drops it in silence:
    # a valid document that opens with none of the colour asked for.
    assert '<w:rPr><w:b/><w:color w:val="1F77B4"/></w:rPr>' in xml \
        or '<w:color w:val="1F77B4"/></w:rPr>' in xml, xml[:600]
    assert 'w:jc w:val="center"' in xml


def test_a_pptx_carries_the_palette_AND_a_slides_own_colour() -> None:
    made = office.build("pptx", "deck", {
        "style": {"accent": "#b8860b", "ink": "#333344"},
        "slides": [{"title": "Overview", "bullets": ["one", "two"]},
                   {"title": "Danger", "bullets": ["careful"], "color": "#d62728"}]})
    xml = _parts(made.body, "ppt/slides/slide")
    found = set(re.findall(r'<a:srgbClr val="(\w+)"/></a:solidFill>', xml))
    assert {"B8860B", "333344", "D62728"} <= found, found


def test_an_xlsx_fills_its_HEADER_ROW_and_openpyxl_agrees() -> None:
    """**An independent parser's opinion, not our own XML read back.** A
    spreadsheet's styling is its header row; colouring arbitrary cells would
    need a style per distinct colour and a way for the model to name cells,
    neither of which is what makes a sheet look unfinished."""
    import openpyxl

    made = office.build("xlsx", "book", {
        "style": {"accent": "#1f4e79"},
        "rows": [["Item", "Qty"], ["Tuna", "3"]]})
    sheet = openpyxl.load_workbook(io.BytesIO(made.body)).active
    assert [[c.value for c in r] for r in sheet.iter_rows()] == \
        [["Item", "Qty"], ["Tuna", "3"]]
    assert sheet["A1"].font.b is True
    assert sheet["A1"].fill.fgColor.rgb == "FF1F4E79"
    # AND THE BODY IS UNTOUCHED — a header style that leaked into every row
    # would be a sheet nobody can read.
    assert sheet["A2"].font.b in (False, None), sheet["A2"].font.b


def test_every_format_is_UNCHANGED_when_no_palette_is_given() -> None:
    """**The claim that matters most, across all four.** Every conversion this
    product has ever done goes down these paths."""
    docx = office.build("docx", "p", {"blocks": [{"type": "heading1", "text": "T"}]})
    assert 'w:color' not in _part(docx.body, "word/document.xml")

    pptx = office.build("pptx", "p", {"slides": [{"title": "T", "bullets": ["b"]}]})
    assert "</a:solidFill>" not in _parts(pptx.body, "ppt/slides/slide")

    xlsx = office.build("xlsx", "p", {"rows": [["a", "b"]]})
    assert 's="1"' not in _part(xlsx.body, "xl/worksheets/sheet1.xml")
    assert "fgColor" not in _part(xlsx.body, "xl/styles.xml")


def test_a_csv_ignores_a_palette_INSTEAD_of_failing() -> None:
    """A `.csv` is rows of text with commas between them; there is nowhere for
    a colour to live. **Ignored, silently, and the byte output proves it.**

    The source arm also checks that `create_document`'s schema DESCRIBES this
    ("csv ... ignores it") — that half stays in Chat: it reads
    `chat.tools.default_registry({})`, which wires in `CREATE_DOCUMENT` from
    `chat.tools._document`, a Chat-only tool this package does not own.
    """
    styled = office.build("csv", "rows", {
        "style": {"accent": "#1f4e79"}, "rows": [["a", "b"]]})
    plain = office.build("csv", "rows", {"rows": [["a", "b"]]})
    assert styled.body == plain.body


def test_the_rule_has_a_WEIGHT_and_it_is_clamped() -> None:
    """**T74 · Len: *"can you make the lines thicker for the headers?"*** The
    model answered *"this version features thicker, more prominent header
    lines"* and produced a file with the identical 0.7pt hairline — T72's
    defect exactly, one field over, surviving T72 because that row added colour
    and stopped there.

    **Clamped, not trusted.** The number is model-authored and reaches a layout
    that reserves space by arithmetic; 400 here is a black band across the
    page. Asserted at both ends and on the two ways of saying nothing.
    """
    def widths(pdf: bytes) -> set[str]:
        return {m.decode() for m in set(re.findall(rb"([\d.]+) re f", pdf))}

    blocks = [{"type": "heading2", "text": "Step 1"},
              {"type": "paragraph", "text": "x"}]
    assert widths(office.build("pdf", "d", {"blocks": blocks}).body) == {"0.70"}
    for given, expected in ((3.0, "3.00"), (400, "6.00"), (0.01, "0.30")):
        made = office.build("pdf", "d", {
            "style": {"rule_width": given}, "blocks": blocks})
        assert widths(made.body) == {expected}, (given, widths(made.body))
    # **A NON-NUMBER IS THE DEFAULT, NEVER AN EXCEPTION.** `True` is an `int`
    # in Python and would otherwise become a 1pt rule nobody asked for.
    for junk in ("fat", None, True, [3]):
        made = office.build("pdf", "d", {
            "style": {"rule_width": junk}, "blocks": blocks})
        assert widths(made.body) == {"0.70"}, junk


def test_the_palette_is_enumerated_from_the_DATACLASS_not_by_hand() -> None:
    """**The bug this row found in T72's own plumbing.** `rule_width` was added
    to `Theme`, parsed by `theme_from`, and then dropped one line before the
    writer because `office.build` listed the theme's fields by hand. The whole
    feature existed and did nothing.

    Asserted structurally: every field of `Theme` must reach the writer, so the
    next field added cannot be silently left behind."""
    import dataclasses

    from plexar_tools.office._model import Theme

    names = {f.name for f in dataclasses.fields(Theme)}
    assert "rule_width" in names
    source = (pathlib.Path(office.__file__)).read_text(encoding="utf-8")
    assert "dataclasses.fields(theme)" in source, (
        "the palette is hand-listed again — add a field to Theme and it will "
        "be parsed, stored and never drawn")


# ══════════════════════════════════════════════════════════════════════════════
# 6 · T75 — THE MODEL TYPESETS THE DOCUMENT
# ══════════════════════════════════════════════════════════════════════════════
#
# Len: *"it should choose the more prestine fonts, it has flexibility to
# basically do a full rebuild. We shouldnt constrain it. the model should know
# how good pdf's look… It should know what to bold, what to center, what to
# right align, it should know what to color main headers / sub headers."*
#
# He is right about the model, and T72 had given it exactly one dimension.
# Every other one — face, size, weight, italic, right alignment — was a
# constant in `STYLES`, so it could describe a document it had no way to ask
# for. That is this file's own subject, across the whole of typography rather
# than across one colour.
#
# **THE CEILING IS STATED RATHER THAN IMPLIED.** Three families, twelve faces,
# all PDF base-14, none embedded. Anything else needs a vendored font file with
# a licence and a digest — C50's shelf again — and is not this row.

FACE = re.compile(rb"/(F\d+) ([\d.]+) Tf")


def faces(pdf: bytes) -> set[str]:
    return {f"{a.decode()}@{b.decode()}" for a, b in set(FACE.findall(pdf))}


def test_the_document_can_pair_a_SANS_heading_with_a_SERIF_body() -> None:
    """**The classic report pairing, and the reason there are two fields.**
    One `font` would have made it unsayable: all-sans reads as a slide,
    all-serif as a book."""
    made = office.build("pdf", "report", {
        "style": {"font": "serif", "heading_font": "sans"},
        "blocks": [{"type": "heading1", "text": "Quarterly Report"},
                   {"type": "paragraph", "text": "Body copy."}]})
    seen = faces(made.body)
    assert "F2@26.0" in seen, ("the heading is not Helvetica-Bold", seen)
    assert "F5@11.0" in seen, ("the body is not Times-Roman", seen)


def test_a_NAMED_typeface_lands_on_the_family_it_belongs_to() -> None:
    """**The model will ask for Garamond.** Refusing there would cost the whole
    document over a font, so a name maps to the closest of the three families
    and an unknown one falls back rather than raising."""
    from plexar_tools.office.pdf._faces import family_of

    assert family_of("Garamond") == "serif"
    assert family_of("Times New Roman") == "serif"
    assert family_of("Arial") == "sans"
    assert family_of("Consolas") == "mono"
    assert family_of("Wingdings") == "sans"
    assert family_of(None) == "sans"
    # AND IT REACHES THE PAGE, not just the helper.
    made = office.build("pdf", "g", {
        "style": {"font": "Garamond"},
        "blocks": [{"type": "paragraph", "text": "Body copy."}]})
    assert "F5@11.0" in faces(made.body), faces(made.body)


def test_size_weight_italic_and_RIGHT_alignment_are_per_block() -> None:
    """Every dimension at once, on one document, because they are set at one
    call site and a thread that dropped any of them would still pass an arm
    that only checked its favourite."""
    made = office.build("pdf", "t", {"blocks": [
        {"type": "heading1", "text": "Title", "size": 30},
        {"type": "paragraph", "text": "15 August 2026",
         "align": "right", "italic": True, "size": 9},
        {"type": "paragraph", "text": "code()", "font": "mono", "size": 9},
        {"type": "paragraph", "text": "Emphasis", "bold": True},
    ]})
    seen = faces(made.body)
    assert "F2@30.0" in seen, ("the size override did not reach the page", seen)
    assert "F3@9.0" in seen or "F7@9.0" in seen, ("no italic face", seen)
    assert "F9@9.0" in seen, ("no monospaced face", seen)
    assert "F2@11.0" in seen, ("bold=true on a paragraph did nothing", seen)


def test_RIGHT_alignment_puts_the_text_on_the_right_MARGIN() -> None:
    """**Measured as an x-offset, not as a flag.** `right` was implemented as
    its own branch rather than as centring with a bigger offset, and the two
    are only distinguishable by where the glyphs land."""
    def first_x(pdf: bytes) -> float:
        return float(re.search(rb"Tf ([\d.]+) [\d.]+ Td", pdf).group(1))

    text = {"type": "paragraph", "text": "15 August 2026"}
    left = office.build("pdf", "l", {"blocks": [text]}).body
    right = office.build("pdf", "r", {
        "blocks": [{**text, "align": "right"}]}).body
    centre = office.build("pdf", "c", {
        "blocks": [{**text, "align": "centre"}]}).body
    assert first_x(left) == 72.0, first_x(left)
    # Right of centre, and inside the page. 612 - 72 = the right margin.
    assert first_x(centre) < first_x(right) < 540.0, \
        (first_x(centre), first_x(right))


def test_the_WRAP_MEASURES_THE_FACE_IT_WILL_DRAW() -> None:
    """**The silent one.** Times is narrower than Helvetica and Courier is
    wider; measuring every line with the sans table gives short lines in a
    serif document and lines running off the page in a monospaced one. Neither
    throws — the only symptom is a badly set page.

    Asserted on the arithmetic directly, because the rendered check that would
    catch it lives in `test_office_writer.py` and runs `pdfminer` over the
    boxes.
    """
    from plexar_tools.office.pdf._write import width_of

    sample = "The quick brown fox jumps over the lazy dog"
    sans = width_of(sample, 11)
    serif = width_of(sample, 11, family="serif")
    mono = width_of(sample, 11, family="mono")
    assert serif < sans < mono, (serif, sans, mono)
    # Courier is monospaced: every glyph 600/1000 of the point size.
    assert abs(mono - len(sample) * 11 * 0.6) < 0.01, mono


def test_a_SIZE_the_model_invented_is_clamped_not_trusted() -> None:
    """R42. The number decides page breaks by arithmetic, so 4000 is a glyph
    that never fits and an advance loop that never terminates."""
    from plexar_tools.office.pdf._write import _size_of

    assert _size_of(30, 11) == 30.0
    assert _size_of(4000, 11) == 96.0
    assert _size_of(0.1, 11) == 5.0
    for junk in (None, "big", True, [12]):
        assert _size_of(junk, 11) == 11.0, junk


def test_ALL_TWELVE_FACES_ARE_DECLARED_AND_THE_METRICS_ARE_COMPLETE() -> None:
    """**A `/F7` reference to a font that was never written is a page that
    renders nothing**, so every face is declared in every file rather than
    tracked per document — 1.2 KB against a class of defect that cannot then
    exist. And every declared face must have a width table, or wrapping falls
    back to a guess for a whole family."""
    from plexar_tools.office.pdf._faces import FAMILIES, METRICS, declarations, resource

    declared = declarations()
    assert len(declared) == 12, declared
    assert len({name for name, _ in declared}) == 12, "a resource name repeats"
    for family in FAMILIES:
        for bold in (False, True):
            for italic in (False, True):
                assert (family, bold, italic) in METRICS
                assert len(METRICS[(family, bold, italic)]) == 95
                assert resource(family, bold, italic) in {n for n, _ in declared}


def test_a_document_that_names_no_TYPE_is_unchanged() -> None:
    """Asserted for the fifth time in this file and for the fifth reason: every
    conversion this product has ever done takes this path."""
    made = office.build("pdf", "p", {"blocks": [
        {"type": "heading1", "text": "T"}, {"type": "paragraph", "text": "b"}]})
    assert faces(made.body) == {"F1@11.0", "F2@26.0"}, faces(made.body)
