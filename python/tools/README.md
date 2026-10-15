English | [中文](README.zh.md)

# plexar-tools

Host-free document and file tools, shared between DeepSeek Harness and Chat under decision chat-DEC-397 (Chat and Harness stay separate products; the Harness team owns every tool that touches no host, and Chat consumes them over MCP).

## What this package is

`plexar_tools` is a stdlib-only Python package with two parts:

- `plexar_tools.office` — the document model and format readers/writers (Word, Excel, PowerPoint, PDF, HTML, CSV, plain text) copied from Chat's `chat/office/`. It parses and renders bytes; it has no knowledge of a user, a store, a bucket, or a conversation.
- `plexar_tools.tools` — exactly five tools built on `office`: `read_file`, `find_in_file`, `query_sheet`, `convert_document`, `create_document`. Each tool receives only bytes/text and arguments and returns a `ToolResult`. None of them import a user, store, bucket, R2, conversation, sub, `App`, or `chat.api`/`chat.store` concept (INVARIANT-OWNSCOPE, binding on the harness side per chat-DEC-397).

## The chat-DEC-397 boundary

Chat has no host access and serves many users; the Harness has host access and serves one user, and nobody hosts it for other people. Tools that touch no host — document parsing, format conversion, in-memory search — are shared through this package and consumed over MCP. The agent loop, personas, and model-facing prompts are not shared, and never move here.

A shared tool in this package receives only bytes/text and arguments. Ownership resolution (naming a file, resolving it to a stored object, checking who owns it) stays in the consumer — historically `chat/api`'s `App._resolve_attached`, and the harness's own MCP server for `dsh`. This package holds the `ToolResult` envelope (`available`/`reason`/`action`) and the T84 read/search bounds; it never resolves a name to a stored file itself.

Code in `office/` and `tools/` is copied byte-for-byte from `plexar-chat/chat/office/` and `plexar-chat/chat/tools/`, with only the minimum import rewrites (`chat.office` → `plexar_tools.office`, `chat.tools` → `plexar_tools.tools`); relative imports are unchanged. Tool names stay `read_file` / `find_in_file` / `query_sheet` / `convert_document` / `create_document` byte-exact. Chat keeps its own in-tree copy until an MCP server built on this package (tracked separately) passes Chat's existing test suite, and deletes its copy then, so there is one implementation rather than two that drift.

## The MCP server

`python -m plexar_tools.mcp` serves the tools over MCP stdio: newline-delimited JSON-RPC 2.0, protocol version `2025-06-18`, server name `plexar-tools`, methods `initialize`, `notifications/initialized`, `ping`, `tools/list` and `tools/call`. An unknown method returns -32601; a line that is not JSON returns -32700 and the server keeps serving; a missing or malformed `document`/`file` returns -32602. The server keeps no state between calls, writes nothing to disk, exits 0 on stdin EOF, and can be killed at any point.

`tools/list` returns six tools in this order:

- `read_file`, `find_in_file`, `query_sheet` take Chat's description and argument schema verbatim plus a required `document` (`{name, text}`): the text `extract_document` returned at upload. The server runs the window, search or heading pairing on that text exactly as Chat's `App` does after it resolves the file.
- `convert_document` takes Chat's schema plus a required `file` (`{name, media_type?, data_base64}`) and returns the produced file in `structuredContent.output` (`{name, media_type, data_base64}`); its content reads `Converted to {name}, a {EXT} file, {n} bytes.` and the consumer writes its own attached wording after storing.
- `extract_document` takes `file` and returns Chat's upload extraction (`_extract_text`, copied into `plexar_tools/_serve/_extract.py`): `extra` holds `text`, `state` (`indexed`, `not_extractable`, `failed`), `reason`, `sniffed` (`_sniff`'s value, which Chat stores as `FileRecord.sniffed_type`) and `convertible` (Chat's `office.kind_of(name) in office.READERS` check), and the text is cut at `MAX_INDEXED_CHARS_PER_FILE` (200,000 characters).
- `create_document` takes Chat's description and argument schema verbatim plus an optional `sources` object keyed by the reference exactly as an image block (or `header.image`) names it — a file name, a partial name or a file id — each value `{name, media_type?, data_base64}` where `name` is the file's real name and selects the reader; the consumer supplies only the files the spec names. The server validates with Chat's `_document.py` and builds the file as Chat's `App._attach_generated` does after resolving sources (`image_refs`, `furniture_refs`, `office.read`, `resolve_images`, `resolve_furniture`, `build`). It returns the file in `structuredContent.output`; its content reads `Created {name}, a {EXT} file, {n} bytes.` (Chat's own sentence says the file was attached, so the consumer writes that after storing), and `extra.literal_markup` carries the count Chat's `_markup_note` reads. A source that is absent from `sources`, unreadable, or lacks the referenced image is refused with Chat's sentence for that case and `extra.kind` `missing_image`; the absent-source sentence lists the `sources` keys instead of Chat's `name (file id)` catalogue, and that refusal adds `extra.needed_sources`, the sorted references the spec names that `sources` does not supply. A spec with no picture or header-logo references never refuses on `sources`.

A `tools/call` result is `{"content": [{"type": "text", "text": content}], "isError": not ok, "structuredContent": {ok, content, detail, extra}}`, the `ToolResult` fields verbatim. `extra.kind` tags the outcome as `ok`, `no_match`, `bound`, `failed`, `not_extractable` or `missing_image` without changing `content` or `detail`; argument refusals from the tool modules carry no `kind`.

The server enforces only per-call bounds: `READ_WINDOW` (6,000 characters) per `read_file` call, the find and sheet limits, and the T84 reader bounds. `READ_BUDGET_PER_TURN` counts characters across every call in a turn, so it belongs to the conversation and the consumer enforces it. Because the file id never reaches the server, `read_file`'s substitution notice compares `source` with the document name and its stem only, and `extra.read_span` carries no `file_id`.

Chat's `App` also reads three `office` helpers directly; none gets its own tool. `office.kind_of` + `READERS` (the "can this be converted" check) is `extract_document`'s `extra.convertible`. `office._model.parse_sheets` is covered by `query_sheet`, which parses the sheets back out of the document text on the server. `FORMULA_UNSET` (`=?`) is covered by the text itself: `extract_document` returns the markers in `text` and `query_sheet` states their meaning, while the per-slice count Chat adds to its attachment preamble depends on Chat's own truncation and stays in Chat.

The server tests pin every description, the 200,000-character cap and the per-outcome sentences; tell Chat before changing any of them.

## Running the tests

```sh
cd python/tools
python -m pip install -e ".[test]"
python -m pytest -q
```

The test suite is a trimmed copy of `plexar-chat/tests`' office/tools coverage: files that exercise only `office/` or the four tools directly are copied whole; files that also exercise `chat.api.App`, `chat.store`, a `sub`, or a browser keep only their office/tools-only arms, or stay in Chat entirely when no arm qualifies.

Some tests double-check written files with independent readers (openpyxl, pypdf, pdfminer.six, python-docx, python-pptx, fonttools). Those tests skip when the readers are not installed; install them to run the full set.
