"""Upload-time text extraction, copied from Chat (chat-DEC-397).

Copied verbatim from `plexar-chat/chat/store/_projects.py` (`INDEXED`,
`NOT_EXTRACTABLE`, `FAILED`, `MAX_INDEXED_CHARS_PER_FILE`, `TEXT_SUFFIXES`,
`suffix_of`, `_sniff`, `MAX_DOCX_XML_BYTES`, `_DOCX_BREAKS`, `_XML_ENTITIES`,
`_docx_text`, `_extract_text`). No edits were needed: the relative imports
`..office` resolve to `plexar_tools.office` from here. These
functions take bytes and a name and return `(text, state, reason)`; they do
no ownership resolution and no storage.

Chat must be told before `MAX_INDEXED_CHARS_PER_FILE` changes.
"""

from __future__ import annotations

#: Extraction states. Three, never a boolean — see the module docstring.
INDEXED = "indexed"
NOT_EXTRACTABLE = "not_extractable"
FAILED = "failed"


#: How much extracted text the index keeps FOR ONE FILE. Bounds any single
#: upload's contribution to the search index.
MAX_INDEXED_CHARS_PER_FILE = 200_000

#: machinery as a PDF. **Refusing the upload would make a search limit look like
#: a storage limit**, which is the conflation this whole row exists to undo.
MAX_INDEXED_CHARS_PER_PROJECT = 20_000_000

#: Kinds we can honestly read as text. **An ALLOW-LIST, not a deny-list**: a deny
#: list is a list of the formats someone thought of, and the default for an
#: unknown kind must be "we cannot read this" rather than "try it and see".
TEXT_SUFFIXES = frozenset({
    "txt", "md", "markdown", "csv", "tsv", "json", "yaml", "yml", "toml", "ini",
    "log", "rst", "xml", "html", "htm", "css", "js", "ts", "py", "rb", "go",
    "rs", "java", "c", "h", "cpp", "cs", "sh", "bash", "sql", "env", "cfg", "conf",
})

def suffix_of(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""

def _sniff(body: bytes, name: str) -> str:
    """What WE think this is. **Never merged with what the browser claimed.**

    Deliberately shallow: a handful of magic numbers and otherwise a text/binary
    determination. This is NOT a format parser and must not become one — the
    moment it parses a container to identify it, it is doing the thing this whole
    module exists not to do.
    """
    head = body[:16]
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"GIF8"):
        return "image/gif"
    if head.startswith(b"PK\x03\x04"):
        # A zip container. docx/xlsx/jar all live here, and we deliberately do
        # NOT open it to find out which — unpacking an archive to classify it is
        # a parser with an attacker-controlled input.
        return "application/zip"
    if b"\x00" in head:
        return "application/octet-stream"
    if suffix_of(name) in TEXT_SUFFIXES:
        return "text/plain"
    return "application/octet-stream"


#: The most `word/document.xml` we will read out of a .docx. A ZIP member
#: declares its own uncompressed size, and that declaration is written by
#: whoever made the file — so this bounds the READ as well as trusting the
#: header, and a bomb is refused rather than expanded.
MAX_DOCX_XML_BYTES = 24 * 1024 * 1024

#: `<w:p>` ends a paragraph, `<w:br/>` a line, `<w:tab/>` a tab. Everything else
#: is dropped. Kept as one literal so a reader sees exactly which tags carry
#: meaning to us and how few there are.
_DOCX_BREAKS = (
    ("</w:p>", "\n"),
    ("<w:br/>", "\n"),
    ("<w:br />", "\n"),
    ("<w:tab/>", "\t"),
    ("<w:tab />", "\t"),
)

#: The five predefined XML entities and NOTHING ELSE. Numeric and custom
#: entities are left as written rather than expanded — expansion is the whole
#: mechanism of a billion-laughs attack, and a `&#65;` rendered literally is a
#: cosmetic wart where an expander is a denial of service.
_XML_ENTITIES = (("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'),
                 ("&apos;", "'"), ("&amp;", "&"))


def _docx_text(body: bytes) -> tuple[str, str, str]:
    """Text out of a .docx. **Unzipped, never parsed, never executed.**

    ══ THIS IS A DELIBERATE EXCEPTION TO THIS MODULE'S OWN RULE ═════════════
    The module docstring says *"never unpacks an archive, never parses a
    document — every one of those is a parser, and a parser is where
    file-handling code gets its vulnerabilities."* That sentence was right and
    it is now qualified rather than quietly broken, because Len asked for the
    thing it forbade: *"Im trying to have the model look at a docx and it
    cant."* A `.docx` is the single most common document a person attaches, and
    refusing every one of them is a real cost paid for a general principle.

    **What is conceded and what is not:**

      * `zipfile` IS used. It is stdlib, it decompresses, and it executes
        nothing. One member is read — `word/document.xml` — by exact name, so
        a crafted archive full of other entries yields nothing.
      * **NO XML PARSER.** `xml.etree` would be the obvious choice and it is
        the dangerous one: Python's own docs warn it is vulnerable to entity
        expansion. The tags we care about are replaced by hand and the rest are
        stripped, so there is no parser to attack and no entity to expand.
      * **A ZIP BOMB IS REFUSED, NOT EXPANDED.** The declared uncompressed size
        is checked AND the read is capped, because the declaration is written
        by whoever made the file.

    Everything else the module promised holds: nothing is executed, no other
    member is opened, and a file we cannot read is still `NOT_EXTRACTABLE`
    **with a reason the UI shows**.
    """
    import io
    import re
    import zipfile

    try:
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            try:
                entry = archive.getinfo("word/document.xml")
            except KeyError:
                return "", NOT_EXTRACTABLE, "this .docx has no document body we can read"
            if entry.file_size > MAX_DOCX_XML_BYTES:
                return "", NOT_EXTRACTABLE, "that document is too large to read as text"
            with archive.open(entry) as member:
                # **CAPPED READ, not a trusting one.** `file_size` above is the
                # archive's own claim about itself.
                raw = member.read(MAX_DOCX_XML_BYTES + 1)
            if len(raw) > MAX_DOCX_XML_BYTES:
                return "", NOT_EXTRACTABLE, "that document is too large to read as text"
    except (zipfile.BadZipFile, OSError, EOFError, ValueError):
        return "", FAILED, "that .docx could not be opened"

    try:
        xml = raw.decode("utf-8", errors="replace")
    except Exception:  # pragma: no cover - decode with errors= does not raise
        return "", FAILED, "that .docx could not be read as text"

    for tag, char in _DOCX_BREAKS:
        xml = xml.replace(tag, char)
    text = re.sub(r"<[^>]*>", "", xml)
    for entity, char in _XML_ENTITIES:
        text = text.replace(entity, char)
    # Collapse the blank runs a stripped document leaves behind, without
    # touching intentional single breaks.
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return "", NOT_EXTRACTABLE, "that .docx holds no readable text"
    return text[:MAX_INDEXED_CHARS_PER_FILE], INDEXED, ""


def _extract_text(body: bytes, name: str, sniffed: str) -> tuple[str, str, str]:
    """``(text, state, reason)``. **Three-state, never a boolean.**

    Two operations are performed on an uploaded byte in this product:
    `bytes.decode`, and — for a `.docx` only — a bounded unzip of one named
    member with no XML parser behind it (see `_docx_text`, which records why
    that exception exists). Nothing is executed. A kind we have no extractor
    for is `NOT_EXTRACTABLE` **with a reason the UI shows** — not an empty
    string that would make it look searched.
    """
    suffix = suffix_of(name)
    # ══ THE OFFICE READER FIRST, AND IT ANNOUNCES PICTURES (T41) ════════════
    # `_docx_text` returns the words and nothing else, which is why Michael's
    # eight photographs were invisible: the model saw 330 characters of a
    # 728 KB document and no sign that any image existed, so it could not have
    # preserved what it was never shown. `chat/office/` walks the same file in
    # body order and emits `[image: …]` where each picture sits.
    #
    # **This is a text extractor and stays one.** The bytes of the images do
    # not enter the index — only the fact and the position of them, which is
    # what lets the model say "put photo 3 back after step 2" without seeing it.
    # ══ WHY THERE IS NO WALL-CLOCK CEILING AROUND THIS CALL (T84) ═══════════
    # A security audit of the two hand-written binary readers found six
    # denial-of-service paths and framed the amplifier as THIS SEAM: extraction
    # runs synchronously on the upload request thread, one thread per request
    # (T3), single process, no admission cap by design (INVARIANT-NOQUEUE) — and
    # `MAX_INDEXED_CHARS_PER_FILE` below trims a string that has ALREADY been
    # paid for in full. The obvious cure is a timeout here.
    #
    # **IT IS NOT IMPLEMENTABLE IN-PROCESS, AND THAT IS MEASURED RATHER THAN
    # ASSUMED.** On this platform:
    #
    #     signal.alarm       absent
    #     signal.setitimer   absent
    #
    # so there is no way to interrupt the running thread from a timer. And
    # CPython cannot kill a thread: a `Thread.join(timeout=…)` that gives up
    # leaves the work RUNNING, which was confirmed by abandoning one mid-scan
    # and watching it keep burning a core. A `re` scan or a `zlib` loop holds no
    # bytecode boundary for an exception to be delivered at either.
    #
    # Measured on the actual shape, so the size of the problem is on record —
    # `re.findall(r"<row .*?</row>", …)` against unclosed openers:
    #
    #      2,000 openers   0.095s
    #      4,000 openers   0.374s
    #      8,000 openers   1.500s
    #     16,000 openers   6.413s      <- exactly 4x per doubling
    #     200,000 openers  did not finish inside 120 seconds
    #
    # **So every bound must live INSIDE the readers, and a subprocess is the
    # only thing that could ever bound them from out here.** That is a real
    # option and a real cost — serialising the bytes to a child, an IPC hop on
    # every upload, and a refusal that can no longer name WHICH bound it hit —
    # and it is deliberately not this row. It is recorded so the next person
    # does not add a `join(timeout=…)`, watch the request return promptly, and
    # conclude the box is protected while a thread keeps spinning behind it.
    if suffix in ("docx", "xlsx", "pptx", "pdf"):
        # **`read_failed` distinguishes "the reader threw" from "we never had a
        # reader"**, and without it the `application/pdf` branch below tells the
        # user to rename a file that is already named correctly. See there.
        read_failed = False
        try:
            from ..office import read as _office_read
            from ..office.pdf import PDFRefused as _PDFRefused

            document = _office_read(body, name)
            text = document.text
            if text.strip():
                return text[:MAX_INDEXED_CHARS_PER_FILE], INDEXED, ""
        except _PDFRefused as exc:
            # ══ THE PDF READER'S REASON IS THE ONE THE USER GETS (T78) ══════
            # A scan and an encrypted file and a damaged file are three
            # different things to be told, and the fall-through below would
            # flatten all three into `no text extractor for application/pdf` —
            # which is now FALSE as well as unhelpful, since there is one.
            # INVARIANT-ENVELOPE: the reason travels or it does not exist.
            return "", NOT_EXTRACTABLE, str(exc)
        except Exception:
            # **A reader that throws must not lose the file.** `.docx` falls
            # back to the old stripper, which has been correct for months;
            # the other two have no fallback and say so honestly below.
            read_failed = True
    else:
        read_failed = False
    if suffix == "docx":
        return _docx_text(body)
    if suffix in ("xlsx", "pptx"):
        return "", NOT_EXTRACTABLE, f"the .{suffix} file could not be read"
    if sniffed.startswith("image/"):
        return "", NOT_EXTRACTABLE, f"no text extractor for {sniffed}"
    if sniffed == "application/pdf":
        # ══ THE COMMENT HERE SAID THIS WAS UNREACHABLE FOR A `.pdf` (T84) ════
        # It read: *"Reached only when the suffix is not `.pdf` — the reader
        # above owns every file that names itself one."* **False for every
        # exception the reader can raise that is not `PDFRefused`**, and it can
        # raise several: an unguarded `int()` on a token of 5,000 digits, a
        # `chr()` above U+10FFFF from a hostile CMap, an `int()` on a
        # non-numeric `/Columns`, a `MemoryError` from an inflate bomb.
        #
        # The consequence was advice that is both untrue and impossible to act
        # on — *"rename it and attach it again"* for a file already named
        # `budget.pdf`. **That is T77's defect one branch along**: a model, or a
        # person, told something false about our storage in our own voice. T77's
        # sentence was *"never say the file is missing"*; this one was *"the name
        # is wrong"*, and both send the user to fix something that is correct.
        if read_failed or suffix == "pdf":
            return "", NOT_EXTRACTABLE, (
                "this PDF could not be read — it may be damaged, or built in a "
                "way Plexar's reader does not handle. The file IS stored and "
                "the name is correct; nothing needs renaming or re-uploading")
        return "", NOT_EXTRACTABLE, (
            "this file's contents are a PDF but it is not named .pdf, so it "
            "was not read; rename it and attach it again")
    if sniffed in ("application/zip", "application/octet-stream"):
        return "", NOT_EXTRACTABLE, f"no text extractor for {sniffed}"
    if suffix and suffix not in TEXT_SUFFIXES:
        return "", NOT_EXTRACTABLE, f"no text extractor for .{suffix} files"
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return "", FAILED, "the file is not valid UTF-8 text"
    return text[:MAX_INDEXED_CHARS_PER_FILE], INDEXED, ""
