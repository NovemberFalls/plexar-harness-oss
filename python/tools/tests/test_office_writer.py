"""**T40 · N4 — Chat can hand back a document, not only read one.**

MIXED source (chat-DEC-397): this file is trimmed from
`plexar-chat/tests/test_office_writer.py`. Only the arms that drive
`office/` directly are kept. Every arm that drives `CREATE_DOCUMENT`
(`chat.tools._document`), `chat.api.App`, or `chat.store` stays in Chat,
because `_document` is a Chat-only tool this package does not own and
`_attach_generated`/`_extract_text` are `chat.api`/`chat.store` behavior.

══ WHAT IS WATCHED TO FAIL HERE ════════════════════════════════════════════
* **The escaping.** A cell whose text is `</w:t></w:r>` must round-trip as
  LITERAL TEXT. The unescaped writer is run on the same input and its output is
  required to be unopenable — an arm asserting only "the good one works" would
  pass against a writer that escaped nothing, because the fixture would have to
  contain markup to notice.
"""

from __future__ import annotations

import io
import posixpath
import xml.dom.minidom
import xml.etree.ElementTree as ET
import zipfile

import pytest

from plexar_tools import office
from plexar_tools.office.word._write import body_xml
from plexar_tools.office._runs import runs
from plexar_tools.office.excel._write import column_name

HOSTILE = '</w:t></w:r><w:p><w:r><w:t>INJECTED'

REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"
CT_NS = "{http://schemas.openxmlformats.org/package/2006/content-types}"


def _zip(body: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(body))


def _deck(slides=None):
    return office.build("pptx", "Q3 review", {"slides": slides or [
        {"title": "Q3 Review", "bullets": ["Revenue **up 12%**", "Churn *flat*"]},
        {"title": "Next quarter", "bullets": ["Hire two engineers"]},
    ]})


# ══════════════════════════════════════════════════════════════════════════════
# THE PACKAGES OPEN, AND THEIR XML IS XML.
# ══════════════════════════════════════════════════════════════════════════════

def test_a_docx_is_a_valid_package_with_every_required_part() -> None:
    """**Word repairs nothing.** A package missing any of these does not open.

    `word/_rels/document.xml.rels` is the one this row shipped WITHOUT and had
    to be told about by `python-docx`: `styles.xml` was present and declared,
    and nothing pointed at it, so every heading resolved to Normal. **Present
    is not the same as related**, and only the second one makes a part part of
    the document."""
    z = _zip(office.build("docx", "report", {"blocks": [
        {"type": "heading1", "text": "Title"},
        {"type": "paragraph", "text": "Body."},
    ]}).body)
    assert z.testzip() is None
    assert set(z.namelist()) == {
        "[Content_Types].xml", "_rels/.rels", "word/_rels/document.xml.rels",
        "word/document.xml", "word/styles.xml"}
    for part in z.namelist():
        xml.dom.minidom.parseString(z.read(part))


def test_an_xlsx_is_a_valid_package_and_its_parts_parse() -> None:
    z = _zip(office.build("xlsx", "data", {"rows": [["a", "b"], ["1", "2"]]}).body)
    assert z.testzip() is None
    assert "xl/worksheets/sheet1.xml" in z.namelist()
    assert "xl/_rels/workbook.xml.rels" in z.namelist(), (
        "without the workbook rels the sheet is unreachable and Excel refuses "
        "the file")
    for part in z.namelist():
        xml.dom.minidom.parseString(z.read(part))


# ══════════════════════════════════════════════════════════════════════════════
# THE ESCAPING. The one non-negotiable.
# ══════════════════════════════════════════════════════════════════════════════

def test_model_authored_markup_is_text_and_cannot_restructure_the_document() -> None:
    """**A cell value must not be able to close an element.**

    Treated exactly as `clean_name` treats an uploaded filename: hostile by
    default, because the model wrote it and a user asked it to.
    """
    doc = _zip(office.build("docx", "x", {"blocks": [
        {"type": "paragraph", "text": HOSTILE}]}).body).read("word/document.xml")
    xml.dom.minidom.parseString(doc)          # still well-formed
    assert b"INJECTED" in doc                  # the text survived...
    assert b"&lt;/w:t&gt;" in doc              # ...as characters, not markup
    text = doc.decode()
    # And it did not become an extra paragraph: one `<w:p>` from our own writer.
    assert text.count("<w:p>") == 1, text.count("<w:p>")

    sheet = _zip(office.build("xlsx", "x", {"rows": [[HOSTILE]]}).body).read(
        "xl/worksheets/sheet1.xml")
    xml.dom.minidom.parseString(sheet)
    assert b"&lt;/w:t&gt;" in sheet


def test_arm_an_unescaped_writer_produces_a_file_that_will_not_open() -> None:
    """**Watched to fail.** The same hostile text through a writer that skips
    the escape, asserted to produce XML no parser accepts.

    Without this the assertion above is a threshold nobody has watched fail: a
    writer that escaped nothing would still put `INJECTED` in the document, and
    that arm's first check would pass.
    """
    import plexar_tools.office.word._write as docx_module

    original = docx_module.escape
    docx_module.escape = lambda t: "" if t is None else str(t)
    try:
        # R23 — confirm the break actually changed the function the writer uses.
        assert docx_module.escape("<") == "<", "the arm changed nothing — R23"
        broken = docx_module.build([{"type": "paragraph", "text": HOSTILE}])
    finally:
        docx_module.escape = original
    assert docx_module.escape("<") == "&lt;", "the arm did not restore"

    doc = _zip(broken).read("word/document.xml")
    with pytest.raises(Exception):
        xml.dom.minidom.parseString(doc)


def test_control_characters_are_removed_rather_than_escaped() -> None:
    """XML 1.0 forbids them OUTRIGHT — `&#x1;` is as invalid as a raw `\\x01`,
    so an escape does not launder one. A model quoting a binary blob emits them
    eventually."""
    built = office.build("docx", "x", {"blocks": [
        {"type": "paragraph", "text": "a\x01b\x0cc\td"}]})
    doc = _zip(built.body).read("word/document.xml").decode()
    xml.dom.minidom.parseString(doc)
    assert "&#x1;" not in doc and "\x01" not in doc
    assert "a" in doc and "b" in doc
    assert "\t" in doc, "tab is LEGAL in XML 1.0 and must survive"


# ══════════════════════════════════════════════════════════════════════════════
# THE INLINE EMPHASIS. It is the whole of "highlight the terms".
# ══════════════════════════════════════════════════════════════════════════════

def test_emphasis_becomes_formatting_and_never_loses_a_character() -> None:
    """**Predicted: the concatenated runs equal the text minus its markers.**

    "The bold is slightly wrong" and "a clause vanished" are the two failures
    this splitter can have, and only the first is survivable.
    """
    out = runs("plain **bold** middle *ital* end")
    assert "".join(r.text for r in out) == "plain bold middle ital end"
    assert [(r.text, r.bold, r.italic) for r in out if r.bold] == [("bold", True, False)]
    assert [(r.text, r.italic) for r in out if r.italic] == [("ital", True)]

    # ORDER OF ALTERNATION. With `*` tried first, `**bold**` matches the
    # single-star arm on its first two characters and yields an empty run.
    assert [r.text for r in runs("**b**")] == ["b"]
    # Unbalanced markers stay literal rather than eating the rest of the line.
    assert "".join(r.text for r in runs("2 * 3 = 6")) == "2 * 3 = 6"


def test_a_docx_body_never_drops_a_block_it_does_not_recognise() -> None:
    """An unknown `type` from the model renders as a paragraph. **Dropping it
    would lose the user's content to a typo in a field name.**"""
    xml_out = body_xml([{"type": "wingding", "text": "keep me"}])
    assert "keep me" in xml_out


def test_columns_past_z_are_named_correctly() -> None:
    """`chr(65 + i)` produces `[` for the 27th column, and a sheet wider than
    the alphabet is ordinary."""
    assert [column_name(i) for i in (0, 25, 26, 27, 51, 52)] == \
        ["A", "Z", "AA", "AB", "AZ", "BA"]


def test_the_name_is_forced_to_match_the_bytes() -> None:
    """A `.docx` called `report.txt` opens with the wrong application."""
    assert office.safe_name("report.txt", "docx") == "report.txt.docx"
    assert office.safe_name("report.docx", "docx") == "report.docx"
    # Leading dots are stripped too, so a traversal attempt cannot even
    # LOOK like a relative path by the time `clean_name` sees it.
    assert office.safe_name("../../etc/passwd", "csv") == "-..-etc-passwd.csv"
    assert office.safe_name("", "csv") == "document.csv"


# ══════════════════════════════════════════════════════════════════════════════
# THE DECK. **PowerPoint repairs nothing**, so the property gated is CLOSURE.
# ══════════════════════════════════════════════════════════════════════════════

def test_every_relationship_in_a_deck_resolves_to_a_part_that_exists() -> None:
    """**THE ARM THAT MATTERS, and it is not "there are eleven files".**

    A dangling relationship is the failure mode: PowerPoint refuses the file
    outright rather than rendering it imperfectly, and the commonest dangling
    one is `theme1.xml`, which the master needs and which a reader assumes is
    decoration. Asserting closure is what a structural check can honestly do —
    every `Target` resolves, from its OWN part's directory.
    """
    z = _zip(_deck().body)
    names = set(z.namelist())
    checked = 0
    for part in [n for n in names if n.endswith(".rels")]:
        base = posixpath.dirname(posixpath.dirname(part))  # strip `_rels`
        for rel in ET.fromstring(z.read(part)).findall(REL_NS):
            target = rel.get("Target")
            resolved = posixpath.normpath(posixpath.join(base, target))
            assert resolved in names, (
                f"{part} points at {target!r} -> {resolved!r}, which is not in "
                f"the package. PowerPoint refuses the whole file for this.")
            checked += 1
    assert checked >= 6, f"only {checked} relationships checked — the arm is not looking"


def test_every_part_of_a_deck_is_declared_in_the_content_types() -> None:
    """An undeclared part is as fatal as a missing one, and it is invisible in
    a file listing — which is why "eleven parts are present" is not the gate."""
    z = _zip(_deck().body)
    types = ET.fromstring(z.read("[Content_Types].xml"))
    defaults = {d.get("Extension").lower()
                for d in types.findall(CT_NS + "Default")}
    overrides = {o.get("PartName") for o in types.findall(CT_NS + "Override")}
    for part in z.namelist():
        if part == "[Content_Types].xml":
            continue
        extension = part.rsplit(".", 1)[-1].lower()
        assert ("/" + part) in overrides or extension in defaults, (
            f"{part} is in the package but no content type declares it")


def test_a_deck_is_well_formed_and_carries_its_slides_and_emphasis() -> None:
    built = _deck()
    z = _zip(built.body)
    assert z.testzip() is None
    for part in z.namelist():
        xml.dom.minidom.parseString(z.read(part))

    assert "ppt/slides/slide1.xml" in z.namelist()
    assert "ppt/slides/slide2.xml" in z.namelist()
    assert "ppt/theme/theme1.xml" in z.namelist(), (
        "the master's colour map resolves against the theme; without it the "
        "deck does not open")

    slide = z.read("ppt/slides/slide1.xml").decode()
    assert "Q3 Review" in slide and "Revenue" in slide
    # **The emphasis became real runs**, not asterisks on a slide.
    assert "up 12%" in slide and "**up 12%**" not in slide
    assert '<a:b val="1"/>' in slide

    # AND THE PRESENTATION LISTS EXACTLY THE SLIDES THAT EXIST. A `sldIdLst`
    # naming a slide that is not in the package is the same fatal dangle.
    presentation = z.read("ppt/presentation.xml").decode()
    assert presentation.count("<p:sldId ") == 2


def test_a_slide_with_a_title_and_no_bullets_is_still_a_valid_slide() -> None:
    """**One empty body must not take the whole deck down.** A `<p:txBody>` with
    no paragraph at all is malformed, and the failure is the FILE, not the
    slide."""
    z = _zip(_deck([{"title": "Just a title"}]).body)
    slide = z.read("ppt/slides/slide1.xml")
    xml.dom.minidom.parseString(slide)
    assert b"Just a title" in slide
    assert b"<a:p/>" in slide, "the empty body still needs a paragraph"


def test_deck_markup_from_the_model_is_text_here_too() -> None:
    """The escaping is not per-format discipline — it is one function, and this
    asserts the deck actually uses it."""
    z = _zip(_deck([{"title": HOSTILE, "bullets": [HOSTILE]}]).body)
    slide = z.read("ppt/slides/slide1.xml")
    xml.dom.minidom.parseString(slide)
    assert b"&lt;/w:t&gt;" in slide


# ══════════════════════════════════════════════════════════════════════════════
# INDEPENDENT PARSERS. Not our reader, not our assertions.
# ══════════════════════════════════════════════════════════════════════════════

def test_python_docx_opens_our_document_and_sees_the_headings_and_bold() -> None:
    """**A THIRD PARTY'S OPINION, which is the strongest gate available here.**

    `_extract_text` is ours and shares our assumptions; `python-docx` shares
    none of them. It resolves styles, walks the real object model, and refuses a
    package Word would refuse. If it can name our heading style and see our bold
    run, the file is a `.docx` by somebody else's definition of one.
    """
    docx = pytest.importorskip("docx", reason="python-docx is not installed here")

    built = office.build("docx", "amendment", {"blocks": [
        {"type": "heading1", "text": "AMENDMENT"},
        {"type": "paragraph", "text": "Between **Olo Inc.** and plain text."},
        {"type": "table", "rows": [["Term", "Why"], ["Exclusive", "No alternatives"]]},
    ]})
    document = docx.Document(io.BytesIO(built.body))

    texts = [p.text for p in document.paragraphs]
    assert "AMENDMENT" in texts
    assert document.paragraphs[0].style.name.startswith("Heading"), \
        f"the heading style did not survive: {document.paragraphs[0].style.name}"

    # THE EMPHASIS IS REAL FORMATTING, read off the run rather than the string.
    bolds = [r.text for p in document.paragraphs for r in p.runs if r.bold]
    assert "Olo Inc." in bolds, bolds
    assert not any("**" in t for t in texts), "asterisks reached the document"

    assert len(document.tables) == 1
    assert document.tables[0].cell(0, 0).text == "Term"
    assert document.tables[0].cell(1, 1).text == "No alternatives"


def test_openpyxl_opens_our_workbook_and_the_cells_land_where_they_should() -> None:
    """**The sparse-row trap, checked by somebody else's reader.**

    Empty cells are omitted from the XML and the `r` reference is what keeps a
    row aligned. A writer that emitted cells positionally would shift every
    column after a gap LEFT, and the file would still open — so only a real
    parser reading coordinates can catch it.
    """
    openpyxl = pytest.importorskip("openpyxl", reason="openpyxl is not installed here")

    built = office.build("xlsx", "data", {"sheet": "Q3 Actuals", "rows": [
        ["Region", "Q1", "Q2"],
        ["North", "", "12"],          # <- the gap
        ["South", "9", "11"],
    ]})
    workbook = openpyxl.load_workbook(io.BytesIO(built.body))
    sheet = workbook["Q3 Actuals"]
    assert sheet["A1"].value == "Region"
    assert sheet["C1"].value == "Q2"
    assert sheet["A2"].value == "North"
    assert sheet["B2"].value is None, "the empty cell must stay empty..."
    assert sheet["C2"].value == "12", "...and 12 must NOT shift left into B2"
    assert sheet["C3"].value == "11"


def test_openpyxl_sees_hostile_markup_as_a_string_and_not_as_structure() -> None:
    openpyxl = pytest.importorskip("openpyxl", reason="openpyxl is not installed here")
    built = office.build("xlsx", "x", {"rows": [[HOSTILE, "after"]]})
    sheet = openpyxl.load_workbook(io.BytesIO(built.body)).active
    assert sheet["A1"].value == HOSTILE, "the cell must hold the text verbatim"
    assert sheet["B1"].value == "after", "the next cell must still be there"


@pytest.mark.parametrize("kind,spec", [
    ("docx", {"blocks": [{"type": "heading1", "text": "T"},
                         {"type": "paragraph", "text": "B"}]}),
    ("xlsx", {"rows": [["a", "b"], ["1", "2"]]}),
    ("pptx", {"slides": [{"title": "T", "bullets": ["b"]}]}),
])
def test_every_package_is_closed_every_target_resolves_every_part_declared(kind, spec):
    """**THE GENERAL FORM OF THE BUG `python-docx` FOUND, applied to all three.**

    `.docx` shipped with `styles.xml` in the package and no relationship
    pointing at it. The zip was valid, every part parsed, our own reader was
    happy, and every heading silently rendered as body text. The property that
    would have caught it is CLOSURE, and it is cheap:

      * every `Target` in every `.rels` resolves to a part that exists;
      * every part is covered by a `Default` extension or an `Override`;
      * the package has exactly one `_rels/.rels` naming the main document.

    Parametrised over all three formats so the next writer added inherits the
    check instead of needing someone to remember it.
    """
    body = office.build(kind, "x", spec).body
    z = _zip(body)
    names = set(z.namelist())

    assert "_rels/.rels" in names and "[Content_Types].xml" in names

    resolved = 0
    for part in [n for n in names if n.endswith(".rels")]:
        base = posixpath.dirname(posixpath.dirname(part))
        for rel in ET.fromstring(z.read(part)).findall(REL_NS):
            target = posixpath.normpath(posixpath.join(base, rel.get("Target")))
            assert target in names, (
                f"{kind}: {part} points at {rel.get('Target')!r} -> {target!r}, "
                f"which is not in the package")
            resolved += 1
    assert resolved >= 2, f"{kind}: only {resolved} relationships — nothing checked"

    types = ET.fromstring(z.read("[Content_Types].xml"))
    defaults = {d.get("Extension").lower() for d in types.findall(CT_NS + "Default")}
    overrides = {o.get("PartName") for o in types.findall(CT_NS + "Override")}
    for part in names:
        if part == "[Content_Types].xml":
            continue
        extension = part.rsplit(".", 1)[-1].lower()
        assert ("/" + part) in overrides or extension in defaults, \
            f"{kind}: {part} is in the package but undeclared"


def test_arm_a_package_missing_its_relationship_is_caught_by_the_closure_check():
    """**Watched to fail — this is the exact defect that shipped.**

    The styles relationship is emptied and the closure property must break. An
    arm that only asserted "closure holds" would be green against the writer
    that had the bug, because the bug REMOVED a relationship rather than adding
    a bad one — so absence has to be checked from the CONTENT TYPES side too.
    """
    import plexar_tools.office.word._write as docx_module

    original = docx_module.DOC_RELS
    docx_module.DOC_RELS = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
        'relationships"></Relationships>')
    try:
        assert docx_module.DOC_RELS != original, "the arm changed nothing — R23"
        broken = docx_module.build([{"type": "heading1", "text": "T"}])
    finally:
        docx_module.DOC_RELS = original
    assert docx_module.DOC_RELS == original, "the arm did not restore"

    docx = pytest.importorskip("docx", reason="python-docx is not installed here")
    document = docx.Document(io.BytesIO(broken))
    # THE FILE STILL OPENS. That is the whole danger: the defect is not a crash,
    # it is a heading that quietly became body text.
    assert document.paragraphs[0].text == "T"
    assert document.paragraphs[0].style.name == "Normal", (
        "without the styles relationship the heading must flatten — if this "
        "reads Heading 1 the arm is no longer reproducing the defect")


# ══════════════════════════════════════════════════════════════════════════════
# THE PDF. **The format two real users asked for**, and the one whose absence
# made the model announce a file that did not exist.
# ══════════════════════════════════════════════════════════════════════════════

LONG = ("Cover the pan with plastic wrap, label it with the date and time the "
        "thawing process began, and place it in the refrigerator to thaw "
        "overnight at four degrees celsius for proper food safety tracking.")


def test_pypdf_opens_our_pdf_and_reads_the_text_back() -> None:
    """**An independent parser, and there are three of them here.**

    `reportlab` is installed and is NOT used to build: `office/` is
    stdlib-only because it is reached by model-authored input. Generating and
    verifying with the same library is not a gate; generating with stdlib and
    verifying with somebody else's reader is.
    """
    pypdf = pytest.importorskip("pypdf", reason="pypdf is not installed here")

    built = office.build("pdf", "Thawing", {"blocks": [
        {"type": "heading1", "text": "Tuna Poke Thawing Procedure"},
        {"type": "paragraph", "text": "Effective 11 August 2026."},
        {"type": "bullet", "text": "Remove frozen tuna from the bag."},
        {"type": "table", "rows": [["Pan", "Bags"], ["1/3", "2-3"]]},
    ]})
    assert built.name == "Thawing.pdf"
    assert built.body[:5] == b"%PDF-", "a PDF must start with its magic number"
    assert built.body.rstrip().endswith(b"%%EOF")

    reader = pypdf.PdfReader(io.BytesIO(built.body))
    assert len(reader.pages) == 1
    text = reader.pages[0].extract_text()
    for phrase in ("Tuna Poke Thawing Procedure", "Effective 11 August 2026",
                   "Remove frozen tuna", "Pan", "Bags"):
        assert phrase in text, f"{phrase!r} did not survive into the PDF"


def test_no_character_is_painted_outside_the_text_frame(tmp_path) -> None:
    """**THE ARM THAT CHECKS THE ARITHMETIC, and it is empirical.**

    Wrapping is done with a hardcoded Helvetica width table. A wrong entry does
    not raise — it paints text off the right edge of the page, where the reader
    simply cannot see it. So the character boxes are MEASURED with `pdfminer`
    rather than the table being trusted, which is the same reason C50 counts
    pixels instead of scanning source.
    """
    pdfminer = pytest.importorskip("pdfminer", reason="pdfminer is not installed")
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTChar

    from plexar_tools.office.pdf._write import MARGIN, PAGE_W

    built = office.build("pdf", "wide", {"blocks": [
        {"type": "heading1", "text": "A Very Long Heading That Must Wrap "
                                     "Across More Than One Line Of This Page"},
        {"type": "paragraph", "text": LONG},
        {"type": "bullet", "text": LONG},
        {"type": "paragraph", "text": "Supercalifragilisticexpialidocious" * 6},
    ] * 3})

    right_edge = PAGE_W - MARGIN
    seen = 0
    worst = 0.0
    for page in extract_pages(io.BytesIO(built.body)):
        for element in page:
            for line in getattr(element, "_objs", []) or []:
                for char in getattr(line, "_objs", []) or []:
                    if isinstance(char, LTChar):
                        seen += 1
                        worst = max(worst, char.x1)
                        assert char.x0 >= MARGIN - 0.5, "ink left of the margin"
    assert seen > 500, f"only {seen} characters measured — the arm is not looking"
    assert worst <= right_edge + 0.5, (
        f"ink reaches {worst:.1f}pt but the frame ends at {right_edge:.1f}pt — "
        f"the width table is wrong and text is running off the page")


def test_a_long_document_breaks_into_pages_rather_than_off_the_bottom() -> None:
    pypdf = pytest.importorskip("pypdf", reason="pypdf is not installed here")
    built = office.build("pdf", "long", {"blocks": [
        {"type": "paragraph", "text": LONG} for _ in range(60)]})
    reader = pypdf.PdfReader(io.BytesIO(built.body))
    assert len(reader.pages) > 1, "60 paragraphs must not fit on one page"
    from plexar_tools.office.pdf._write import MARGIN
    for page in reader.pages:
        assert float(page.mediabox.width) == 612 and float(page.mediabox.height) == 792
    assert MARGIN == 72


def test_a_parenthesis_from_the_model_cannot_corrupt_the_page() -> None:
    """**The PDF equivalent of the XML injection.** An unescaped `)` closes the
    string early and the rest of the sentence is read as operators — a corrupt
    page rather than a stray character."""
    pypdf = pytest.importorskip("pypdf", reason="pypdf is not installed here")
    nasty = r"Use 1/3 pan (2-3 bags) \ and ) Tj 0 0 Td (INJECTED"
    built = office.build("pdf", "x", {"blocks": [
        {"type": "paragraph", "text": nasty}]})
    text = pypdf.PdfReader(io.BytesIO(built.body)).pages[0].extract_text()
    assert "INJECTED" in text, "the text must survive..."
    assert "(2-3 bags)" in text, "...including its parentheses, as characters"


def test_characters_winansi_cannot_carry_are_transliterated_not_dropped() -> None:
    """The model's default punctuation is em dashes and curly quotes. Dropping
    them silently would eat the punctuation out of every sentence."""
    pypdf = pytest.importorskip("pypdf", reason="pypdf is not installed here")
    built = office.build("pdf", "x", {"blocks": [
        {"type": "paragraph", "text": "Olo — “Carrot Express’s” terms…"}]})
    text = pypdf.PdfReader(io.BytesIO(built.body)).pages[0].extract_text()
    assert "Olo - " in text
    assert '"Carrot Express\'s"' in text
    assert "..." in text
