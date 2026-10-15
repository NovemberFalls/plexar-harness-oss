"""`create_document` — the model can hand back a real file (T40).

══ THIS TOOL WRITES NOTHING TO STORAGE, AND THAT IS THE DESIGN ═════════════
It returns BYTES on the result. `api/` uploads them. `store/` remains the only
package that knows a bucket exists, and `tools/` remains a pure registry with
no principal, no session and no conversation — which is what lets every tool be
driven by a gate with nothing mocked.

**The alternative was threading a `Principal` through `ToolBox.run`**, which
would have put an ownership check inside a package whose job is dispatch, one
layer away from the store that already enforces it. INVARIANT-OWNSCOPE is not
improved by a second place that could get it wrong.

══ `does_io = False`, AND THAT IS TRUE ═════════════════════════════════════
Building a zip in memory touches nothing outside the process. The upload that
FOLLOWS does, and it is `api/`'s, recorded there. T1's rule holds: `does_io` is
declared about what the handler does, not inferred from what happens next.
"""

from __future__ import annotations

from typing import Any

from .. import office
from ._contract import ToolResult
from ._registry import Tool

#: How many blocks or rows one call may carry. **A bound, because the argument
#: string is model-authored and unbounded input is how a tool becomes a way to
#: spend memory.** Generous enough that a real contract fits: the Olo amendment
#: that started this row is ~120 blocks.
MAX_BLOCKS = 2000
MAX_ROWS = 5000
MAX_CELLS = 50_000
#: A deck is a presentation, not a book. The bound is generous for a real one
#: and still refuses a model that decided to emit a slide per paragraph.
MAX_SLIDES = 300

PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "kind": {
            "type": "string",
            "enum": sorted(office.KINDS),
            # ══ THE PROSE MUST NAME EVERY MEMBER OF THE ENUM (T83) ══════════
            # The enum is `sorted(office.KINDS)` and T81e added `html` to it;
            # this sentence was not updated, so the one kind that draws a
            # chart the reader can hover was the one kind the description did
            # not mention. **The schema is the vocabulary** — Len's standing
            # rule — and a member the prose omits is a member the model will
            # not reach for.
            "description": ("docx for a Word document, pdf for a PDF, xlsx "
                            "for a spreadsheet, pptx for a slide deck, csv for "
                            "plain rows, html for a self-contained web page "
                            "whose charts are inline SVG with a native tooltip "
                            "on every mark. If the user names a format, use "
                            "THAT one."),
        },
        "name": {
            "type": "string",
            "description": "File name without a path. The extension is added for you.",
        },
        "blocks": {
            "type": "array",
            "description": (
                "For kind=docx, kind=pdf or kind=html. Ordered content. Each item is an object with "
                "'type' and 'text'. type is one of: heading1, heading2, "
                "heading3, paragraph, bullet, callout, spacer, table, image, or chart. "
                "A CALLOUT item is a tinted band with a coloured bar down its left "
                "edge, for a warning or a rule that must not be missed -- use it for "
                "safety notices, \"always/never\" rules and key reminders. Give it "
                "'tone': 'warning', 'caution', 'success' or 'note'. A table item "
                "uses 'rows' (array of arrays of strings) instead of 'text'; "
                "its first row is treated as the header. Inside 'text' you may "
                "use **bold** and *italics* and they become real Word "
                "formatting. "
                # ══ THE ONE THAT DRAWS (T81) ═════════════════════════════════
                # Len asked for *"a chart for the Dine in"* off an attached
                # P&L. The model reached for an `image` block three times,
                # because `image` was the only thing in this list that put a
                # picture on a page — and `image` can only re-use a photograph
                # somebody uploaded. It burned the tool budget and then told him
                # it had failed. **The capability was missing, not the prompt.**
                "A CHART item DRAWS a chart from numbers you supply — this is "
                "how you plot data out of an attached spreadsheet, and you do "
                "NOT need an image to do it: {\"type\": \"chart\", \"chart\": "
                "\"line\" or \"bar\", \"title\": \"Dine In revenue\", "
                "\"labels\": [\"Jan\", \"Feb\", \"Mar\"], \"series\": "
                "[{\"name\": \"2025 Actual\", \"values\": [936205, 646796, "
                "972929]}, {\"name\": \"2026 Result\", \"values\": [1031231, "
                "711846, 1073259]}]}. One value per label; use null for a gap "
                "rather than 0, which would plot as a real measurement of "
                "nothing. Up to 8 series. A series may carry its own \"color\". "
                "You may also set \"y_title\" and \"x_title\". "
                "In kind=xlsx the chart becomes a REAL Excel chart the user can "
                "click and re-point; in pdf and html it is drawn as a picture. "
                # ══ THE ONE THAT LETS A STYLED DOCUMENT KEEP ITS PHOTOGRAPHS ══
                # Written in the second person and with the exact literal the
                # model has already been shown, because a parameter it cannot
                # map to something on screen is a parameter it will not use —
                # T43's lesson, and the reason this row exists at all.
                # ══ THE NAME COMES FIRST NOW (T70) ══════════════════
                # The model copied a 24-hex id and dropped two characters out
                # of the middle, which cost an otherwise perfect document. It
                # is asked for the FILE NAME first because that is the string
                # it can carry — the id still works, and `resolve_source`
                # accepts either.
                "An IMAGE item re-uses a picture from a file already in this "
                "conversation: {\"type\": \"image\", \"source\": \"<the "
                "file's NAME, exactly as listed above>\", "
                "\"index\": 2} where index is the number printed beside the "
                "picture in the attached file's text, like [image 2: photo.jpg]. "
                "This is how you write a NEW, styled document that still "
                "contains the user's original photographs — lay out your own "
                "headings and prose, and place their pictures between them by "
                "number. You never need to see a picture to place it. "
                # ══ COLOUR AND ALIGNMENT PER BLOCK (T72) ═════════════════
                # Len: *"Theres no color variations in the header, is this a
                # model limitation or a harness limitation?"* Ours. The model
                # described colour-coded step headings three times and there
                # was no field through which one could arrive.
                # ══ THE WHOLE TYPOGRAPHIC VOCABULARY (T75) ═══════════
                # Len: *"it should choose the more prestine fonts… it should
                # know what to bold, what to center, what to right align, it
                # should know what to color main headers / sub headers. It
                # should know all of this."* He is right that the model knows
                # what a good document looks like; every one of these was a
                # constant in the writer, so it could describe one and had no
                # way to ask for one.
                "TYPESET IT YOURSELF. Any item may also carry \"color\" (hex, "
                "e.g. \"#1f77b4\"), \"size\" (points, 5 to 96), \"bold\" "
                "(true/false), \"italic\" (true/false), \"align\" "
                "(\"left\", \"center\" or \"right\") and \"font\" "
                "(\"serif\", \"sans\", \"mono\", \"figtree\" or \"jetbrains\"). "
                "Use them the way you "
                "would set a real document: a large title, section headings "
                "that are clearly bigger than the body, a date or a reference "
                "ranged right, a caption smaller and italic, colour used to "
                "separate main headings from sub-headings. "
                "A very pale colour is refused and falls back to the "
                "document's, because pale text on white paper cannot be read."
            ),
            "items": {"type": "object"},
        },
        "style": {
            "type": "object",
            "description": (
                # **NAMED AS A PALETTE, NOT AS "STYLING".** A vague field
                # invites a vague value; four named colours are four things
                # the model can decide and this package can draw.
                # ══ NAMED PER FORMAT, BECAUSE THEY DIFFER (T73) ══════
                # Len: *"what if they want to style a docx or excel or power
                # point?"* Saying only "the palette" would leave the model to
                # discover by experiment that a csv ignores it — and a field
                # that is silently dropped is the same lie as a control that
                # does nothing.
                "The document's palette — every field optional, each a hex "
                "colour, and anything you leave out keeps Plexar's default. "
                "\"accent\" colours the headings and the rules under them, "
                "\"heading\" colours the headings alone if you want them "
                "different from the rules, \"subheading\" colours heading2 and "
                "heading3 differently from heading1 -- a document whose numbered "
                "sections are one colour and whose step headings are another is "
                "ordinary and this is how to ask for it -- \"ink\" is the body "
                "text and "
                "\"rule\" is the hairlines, and \"rule_width\" is their "
                "thickness in points (0.7 is the default hairline; 2 to 4 "
                "reads as a bold divider). "
                "\"font\" sets the body face and \"heading_font\" the "
                "headings. Choose from \"serif\", \"sans\", \"mono\", and two real "
                "typefaces carried inside the file: \"figtree\" (a modern "
                "humanist sans, the product's own) and \"jetbrains\" (a "
                "monospace). "
                "**A sans heading over a serif body is the classic pairing "
                "for a report**; all-sans reads as a slide, all-serif as a "
                "book. Named typefaces are accepted and mapped to the closest "
                "of the three, so \"Times\" gives you a serif and \"Arial\" "
                "a sans. "
                "It applies to pdf (headings, body, rules), docx (the same), "
                "pptx (slide titles and bullets) and xlsx (the header row is "
                "filled with the accent). A csv has nowhere to put a colour "
                "and ignores it. "
                "Choose a palette that suits what the document IS — a safety "
                "procedure, a financial summary and a menu do not want the "
                "same one. Dark, saturated tones read on paper; pale ones do "
                "not and will be refused."
            ),
        },
        "slides": {
            "type": "array",
            "description": (
                "For kind=pptx. One object per slide with 'title' (string) and "
                "'bullets' (array of strings). Keep bullets short — a slide is "
                "not a paragraph. **bold** and *italics* work inside both. "
                "A slide may carry \"color\" to give its title its own hex "
                "colour, and \"align\": \"center\" or \"left\"."
            ),
            "items": {"type": "object"},
        },
        "rows": {
            "type": "array",
            "description": "For kind=xlsx or csv. An array of arrays of cell strings.",
            "items": {"type": "array", "items": {"type": "string"}},
        },
        # ══ PAGE FURNITURE, WHICH THE MODEL COULD NOT ASK FOR (C77) ═══════
        # The writer grew a running header and footer, and a capability the
        # model cannot ADDRESS is not a capability -- T43, and the exact
        # reason the chart block and the callout above it are described here
        # rather than only implemented.
        "header": {
            "type": "object",
            "description": (
                "For kind=pdf. A running header repeated on EVERY page, outside "
                "the text. 'right' is the document class or reference (e.g. "
                "'SOP'), 'left' a short label. Use it for procedures, policies "
                "and anything with a document number. 'image' puts a LOGO at the "
                "top left of every page and takes the same {'source', 'index'} a "
                "picture block takes, so a letterhead comes from a file already "
                "in the conversation."),
        },
        "footer": {
            "type": "object",
            "description": (
                "For kind=pdf. A running footer repeated on EVERY page. 'right' "
                "for a confidentiality notice or revision date, and 'pages' for "
                "a page stamp -- write it as 'Page {n} of {of}' and the real "
                "numbers are substituted after the document is paginated."),
        },
        # ══ A SHAPE, NOT ADVICE ABOUT A SHAPE (C78) ═══════════════════════
        # Everything this supplies was ALREADY expressible after C77 and the
        # model produced none of it -- expressible is not reached. Naming the
        # template RUNS the transformation, so the numbering, the furniture and
        # the second heading tier happen whether or not it remembered to ask.
        "template": {
            "type": "string",
            "enum": ["sop"],
            "description": (
                "For kind=pdf, kind=docx or kind=html. Optional. 'sop' shapes "
                "the file as a controlled procedure: heading2 blocks are NUMBERED "
                "for you as sections (1., 2., 3.), heading3 blocks stay unnumbered "
                "as steps and are set in a second colour, and a running header and "
                "page footer are added. Write the content normally -- typically "
                "Purpose, Scope, Procedure and Key Reminders as heading2, each step "
                "as heading3, and safety rules as callout blocks. Anything you set "
                "yourself wins: the template only fills in what you left out."),
        },
        "sheet": {"type": "string", "description": "For kind=xlsx: the sheet name."},
    },
    "required": ["kind", "name"],
}

DESCRIPTION = (
    "Create a downloadable file of NEW content you write (Word .docx, PDF, "
    "Excel .xlsx, PowerPoint .pptx, .html, or .csv) and attach "
    "it to this conversation so the user can download it. Use this whenever the "
    "user asks for a document, a report, a spreadsheet or a file they can open "
    "or keep — do not paste a long document into the chat instead. It writes a "
    "NEW file from the content you supply. "
    # ══ THE OTHER HALF OF T81's ROUTING RULE ═════════════════════════════════
    # **This description is why the model chose a PDF for a chart.** The
    # sentence above says "use this whenever the user asks for a document, a
    # report… " and there was no competing rule anywhere, so a request for a
    # chart landed here and then found only `image` blocks. Both halves of the
    # rule now exist; `chat/upstream/_preamble.py`'s RUNTIME_FACTS carries the
    # artifact half, and neither may be edited without the other.
    "IT CAN DRAW A CHART from numbers you supply — see the chart block in "
    "'blocks'. Use kind=pdf or kind=html for a chart the user wants as a file, "
    "and kind=xlsx when they want the underlying numbers too, where the chart "
    "becomes a real Excel chart they can click and re-point. "
    "**If they just want to LOOK at a chart rather than keep a file, write an "
    "artifact instead** — a fenced html block in your reply, which renders "
    "live beside the conversation and needs no tool at all. "
    # ══ THIS SENTENCE USED TO FORBID THE THING THE ROW JUST BUILT (T52) ══════
    # It read: *"writing its content out by hand here loses every photograph,
    # because you cannot see them."* That was TRUE and is now false, and a
    # stale prohibition is worse than a missing permission — the model would
    # have read the new image parameter and been told, two sentences later,
    # not to use it. C53's warn copy, one layer in: the description understated
    # the product in one direction and hid the new capability in the other.
    "It CAN re-use pictures from a file already in this conversation: give a "
    "block {\"type\": \"image\", \"source\": \"<the file's name>\", "
    "\"index\": 2}, "
    "using the number shown beside the picture in that file's text. That is "
    "how you produce a restyled, reorganised version of somebody's document "
    "that still contains their photographs. "
    "**When the user wants the SAME document in another format with nothing "
    "changed, use convert_document instead** — it is exact and needs no "
    "retyping. Use this tool when they want the content laid out differently. "
    "Neither tool edits an uploaded file in place or preserves its original "
    "fonts, colours or headers."
)


#: Block types the model may name. **Read from the writers' vocabulary, not
#: re-typed here** — a second hand-written list is how a schema comes to
#: promise something no writer implements, which is the pair of states T1's
#: registry was built to make unconstructible.
_ALIASES = {"title": "heading1", "heading": "heading1",
            "list": "bullet", "listitem": "bullet", "item": "bullet",
            "break": "spacer"}


def _check_blocks(blocks: Any, key: str) -> "ToolResult | None":
    """Refuse a block the writers would silently typeset as an empty paragraph.

    Returns `None` when every block is sound. **Charts are PARSED here**, so a
    malformed one is named before any file exists — `office.build` would
    otherwise draw an empty box and report success.
    """
    if not isinstance(blocks, list):
        return None
    for position, block in enumerate(blocks, start=1):
        if not isinstance(block, dict):
            continue          # `from_blocks` turns these into text, honestly
        raw = str(block.get("type") or block.get("kind") or "paragraph")
        kind = _ALIASES.get(raw.strip().lower(), raw.strip().lower())
        if kind not in office.BLOCK_KINDS:
            return ToolResult(
                name="", ok=False,
                content=(f"block {position} has type {raw!r}, which is not a "
                         f"block Plexar can write, so no file was created. "
                         f"Supported: "
                         f"{', '.join(sorted(office.BLOCK_KINDS - {'sheet', 'slide'}))}."),
                detail="no file created — unknown block type")
        if kind != "chart":
            continue
        if key not in _CHART_KINDS:
            return ToolResult(
                name="", ok=False,
                content=(f"A chart can be drawn in "
                         f"{', '.join(sorted(_CHART_KINDS))}, not in a {key}. "
                         f"No file was created."),
                detail="no file created — chart needs pdf, html or xlsx")
        try:
            office.parse_chart(block)
        except office.BadChart as exc:
            # The message already names the field and the fix; prefixing the
            # position is what makes it actionable in a document with several.
            return ToolResult(
                name="", ok=False,
                content=f"block {position}: {exc}",
                detail="no file created — bad chart")
    return None


#: Tags that mean the model was trying to RENDER something rather than write
#: about it. **Deliberately not a general HTML detector.** A `<p>` or an `<h2>`
#: in prose is almost always somebody discussing markup, and a tutorial on HTML
#: is a document this product should be able to write — Len's standing rule is
#: that we do not constrain the model. These eight are the ones that only
#: appear when the intent was for a browser to execute or lay something out.
_RENDER_TAGS = ("<script", "<canvas", "<iframe", "<style",
                "<object", "<embed", "<svg", "<div")


def _markup_blocks(spec: dict) -> int:
    """How many text-bearing blocks carry markup that will be typeset literally.

    **A count, not a refusal.** Refusing was the first design and it is wrong:
    a PDF explaining Chart.js legitimately contains `<script src=…>`, and a
    refusal there would break a document the product should write. What was
    actually missing is that the model had no way to learn what became of its
    markup — so it assumed the best and told the user the file was interactive.
    """
    seen = 0
    for block in spec.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        if _looks_rendered(str(block.get("text") or "")):
            seen += 1
    for slide in spec.get("slides") or []:
        if not isinstance(slide, dict):
            continue
        joined = (str(slide.get("title") or "") + " "
                  + " ".join(str(b) for b in (slide.get("bullets") or [])))
        if _looks_rendered(joined):
            seen += 1
    return seen


def _looks_rendered(text: str) -> bool:
    """**Closing tags count, and that is not pedantry.**

    Measured against the two-page PDF Len was handed: page 1 carried
    `<div>…<canvas>…<script src=…>` and page 2 carried the rest of the
    Chart.js body, ending in `</script>` — a block with **no opening tag in
    it at all.** A detector matching only `<script` saw one block of two and
    reported half the problem, which for a count that a model reads is a
    quieter version of reporting none.
    """
    lowered = text.lower()
    return any(tag in lowered or tag.replace("<", "</") in lowered
               for tag in _RENDER_TAGS)


def _has_chart(blocks: Any) -> bool:
    return isinstance(blocks, list) and any(
        isinstance(b, dict)
        and str(b.get("type") or b.get("kind") or "").strip().lower() == "chart"
        for b in blocks)


#: Where a chart can actually be drawn. **docx and pptx are absent on purpose
#: and the refusal above says so** — T81 built three renderers, and a fourth
#: that silently produced a chartless document would be the same lie one
#: format along.
_CHART_KINDS = frozenset({"pdf", "html", "xlsx"})


def _run(args: dict) -> ToolResult:
    # The registry has already parsed and refused unreadable arguments, so a
    # non-dict cannot reach here — but the guard stays: a tool that assumes
    # its caller validated is a tool that breaks when a second caller appears.
    if not isinstance(args, dict):
        # **The model never finished writing the arguments.** Distinct from bad
        # arguments, and it must not become an empty document with a plausible
        # name — that is a file the model will then describe as the answer.
        return ToolResult(
            name="", ok=False,
            content="The arguments for create_document were incomplete, so no "
                    "file was created. Send the call again.",
            detail="no file created — incomplete arguments",
        )

    kind = args.get("kind")
    # ══ THE KIND IS VALIDATED BEFORE THE CONTENT, AND THE ORDER IS THE FIX ══
    # **Found by the gate.** With the content check first, an unknown kind fell
    # through to `expected = "rows"`, found none, and was reported as *"no
    # content was supplied for a odt file"* — which is false and, worse, sends
    # the model off to supply rows for a format that will never exist. A wrong
    # diagnosis handed to a model is a retry loop; name the actual fault.
    key = str(kind or "").strip().lower().lstrip(".")
    if key not in office.KINDS:
        return ToolResult(
            name="", ok=False,
            content=(f"{key or '(none)'} is not a document kind Plexar can "
                     f"write, and no file was created. Supported: "
                     f"{', '.join(sorted(office.KINDS))}."),
            detail="no file created — unsupported kind")

    spec: dict[str, Any] = {}
    blocks = args.get("blocks")
    rows = args.get("rows")
    if isinstance(blocks, list):
        spec["blocks"] = blocks[:MAX_BLOCKS]
    slides = args.get("slides")
    if isinstance(slides, list):
        spec["slides"] = [s for s in slides[:MAX_SLIDES] if isinstance(s, dict)]
    if isinstance(rows, list):
        spec["rows"] = [r for r in rows[:MAX_ROWS] if isinstance(r, (list, tuple))]
        if sum(len(r) for r in spec["rows"]) > MAX_CELLS:
            return ToolResult(
                name="", ok=False,
                content=f"That is more than {MAX_CELLS} cells. No file was "
                        f"created. Split it into several files.",
                detail="no file created — too many cells",
            )
    if args.get("sheet"):
        spec["sheet"] = args["sheet"]
    # ══ THE PALETTE RIDES WITH THE SPEC, INCLUDING ON THE COMPOSE HOP (T72) ═
    # **This assignment is above the `image_refs` branch on purpose.** That
    # branch hands `spec` to `api/` to finish, so a style added after it would
    # reach every plain document and silently vanish from every document with
    # a picture in it — which is precisely the kind Len asks to be made
    # presentable. One dict, one hop, no second place to remember.
    #
    # Not validated here: `office.theme_from` refuses what it does not
    # recognise, and a second opinion in this file is a second rule.
    if isinstance(args.get("style"), dict):
        spec["style"] = args["style"]

    # Passed through unexamined, like `style` and for its reason: the writer
    # keeps only the slots it knows (`office._furniture`) and reserves a band
    # only when something will be drawn in it, so a second opinion here would
    # be a second rule about the same field.
    for slot in ("header", "footer"):
        if isinstance(args.get(slot), (dict, str)) and args[slot]:
            spec[slot] = args[slot]

    # ABSENT and EMPTY are different here, which is why this is not folded
    # into the loop above: `office._template` reads `"header" in spec` to tell
    # "the model said nothing" from "the model said no header", so an empty
    # dict must survive the copy that a truthiness test would swallow.
    for slot in ("header", "footer"):
        if slot not in spec and isinstance(args.get(slot), dict):
            spec[slot] = args[slot]
    if isinstance(args.get("template"), str) and args["template"].strip():
        spec["template"] = args["template"]

    # ══ THE CONTENT FIELD IS CHECKED PER KIND, NOT "ANY OF THE THREE" ══════
    # **Found by the gate**: `kind=pptx` with `blocks` passed an any-of check
    # and produced a one-slide EMPTY DECK with a plausible name, which the
    # model would then announce as ready. An empty document is a refusal, not
    # a file — a zero-content .docx opens fine and says nothing.
    # ══ AN UNKNOWN BLOCK TYPE IS REFUSED NOW, NOT SILENTLY TYPESET (T81) ═════
    # **Every writer's dispatch ends in `else: paragraph`, and `Block.__post_
    # init__` coerces the same way.** That is RIGHT for a reader — a converter
    # meeting a kind we do not have must not lose the text — and wrong for a
    # model, which gets a successful-looking file with an empty paragraph where
    # it asked for something. A typo'd type failed open, and this row adds a
    # kind, so the next one added would have failed open too.
    #
    # Checked here rather than in `_model.py` because THIS is the layer with
    # somebody to refuse: the model will read the message and retry.
    refusal = _check_blocks(spec.get("blocks"), key)
    if refusal is not None:
        return refusal

    # A chart is content, so a spreadsheet built to carry one is not empty even
    # with no `rows` — the writer materialises the chart's own numbers as cells.
    expected = {"docx": "blocks", "pdf": "blocks", "pptx": "slides",
                "html": "blocks"}.get(key, "rows")
    if key == "xlsx" and _has_chart(spec.get("blocks")):
        expected = "blocks" if not spec.get("rows") else "rows"
    if not spec.get(expected):
        return ToolResult(
            name="", ok=False,
            content=f"No content was supplied for a {kind} file, so none was "
                    f"created. Send '{expected}' — 'blocks' for a docx, "
                    f"'slides' for a pptx, 'rows' for xlsx or csv.",
            detail="no file created — no content",
        )

    # ══ A DOCUMENT THAT REUSES PICTURES CANNOT BE BUILT HERE (T52) ═════════
    # The pictures are in the STORE, and this package holds no principal and no
    # bucket — deliberately, and the module docstring above says why. So a spec
    # carrying image references is handed BACK for `api/` to resolve and build:
    # it is the only layer with both the caller's identity and the store.
    #
    # **The boundary is kept rather than widened.** Threading a `Principal`
    # into `ToolBox.run` to fetch the bytes here would put an ownership check
    # inside a package whose job is dispatch, which is the exact trade this
    # tool's docstring already refused once.
    if office.image_refs(spec.get("blocks")):
        if key not in ("docx", "pdf"):
            return ToolResult(
                name="", ok=False,
                content=(f"Pictures can only be placed in a docx or a pdf, not "
                         f"in a {key}. No file was created."),
                detail="no file created — pictures need docx or pdf")
        return ToolResult(
            name="", ok=True,
            content="Composing…",
            detail="composing",
            extra={"compose": {"kind": key, "name": args.get("name"),
                               "spec": spec}},
        )

    try:
        built = office.build(kind, args.get("name"), spec)
    except office.UnsupportedKind as exc:
        return ToolResult(name="", ok=False, content=str(exc),
                          detail="no file created — unsupported kind")
    except Exception:
        # The message is deliberately not the exception text: it is written by
        # a package the model's own input reaches, and it goes back to a model.
        return ToolResult(
            name="", ok=False,
            content="The file could not be built from that content and no file "
                    "was created.",
            detail="no file created — build failed")

    # ══ `ok` IS NOT SET HERE, AND THAT IS THE POINT ══════════════════════
    # The bytes exist; the FILE does not until `api/` stores it. Reporting
    # success now would let the model tell the user about a download that was
    # never created — the same class as the empty bubble under a banner
    # claiming an answer (T39), one layer up. `api/` finishes this result.
    return ToolResult(
        name="", ok=True,
        content=f"Built {built.name} ({built.size:,} bytes). Attaching…",
        detail=f"created {built.name}",
        # ══ WHAT HAPPENED TO ANY MARKUP IT WROTE, AS A FACT (T81b) ═══════════
        # Len's model wrote a `<div>`, a `<canvas>` and a full Chart.js
        # `<script>` into paragraph blocks; the PDF writer typeset all of it as
        # prose across two pages, and the model then told him the document
        # contained *"a fully interactive line chart"* on which *"hovering over
        # a point will display the exact sales value"*. **The tool result was
        # true and the sentence above it was not** — T40's shape exactly, and a
        # guard on the RESULT could not catch it because nothing in the result
        # mentioned the markup at all.
        #
        # So the COUNT rides back. It is a fact, not an instruction: T60 —
        # a tool result is data the model may quote, and Len has already been
        # shown our own briefing pasted into an answer. What to do instead
        # lives in the preamble with every other ambient rule.
        extra={"file": built, "literal_markup": _markup_blocks(spec)},
    )


CREATE_DOCUMENT = Tool(
    name="create_document",
    description=DESCRIPTION,
    parameters=PARAMETERS,
    handler=_run,
    does_io=False,
)
