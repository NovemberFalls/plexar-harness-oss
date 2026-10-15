"""The plexar-tools MCP server: stdio, newline-delimited JSON-RPC 2.0 (chat-DEC-397).

Run with ``python -m plexar_tools.mcp``. Stdlib only. One request is handled at a
time; nothing is kept between calls and nothing is written to disk. Stdin EOF
exits 0; the process holds no state that a SIGKILL could corrupt.

Methods: ``initialize``, ``notifications/initialized``, ``ping``, ``tools/list``,
``tools/call``. An unknown method is error -32601, a line that is not JSON is
-32700 (and the server keeps serving), and a call whose `document`/`file`
argument is missing or malformed is -32602.

Tools, in order: ``read_file``, ``find_in_file``, ``query_sheet``,
``convert_document``, ``extract_document``, ``create_document``. Chat's tools
keep Chat's description and argument schema verbatim; `read_file`, `find_in_file` and
`query_sheet` add a required `document` ({name, text}: the text
`extract_document` returned at upload), `convert_document` and
`extract_document` a required `file` ({name, media_type?, data_base64}), and
`create_document` an optional `sources` (reference as the spec names it ->
{name, media_type?, data_base64}) holding the files its image blocks name.

A `tools/call` result is ``{"content": [{"type": "text", "text": content}],
"isError": not ok, "structuredContent": {"ok", "content", "detail", "extra"}}``,
the `ToolResult` fields verbatim; `convert_document` and `create_document` add
``structuredContent.output = {"name", "media_type", "data_base64"}``.
"""

from __future__ import annotations

import base64
import binascii
import copy
import json
import sys
from typing import Any, BinaryIO

from .tools import CONVERT_DOCUMENT, FIND_IN_FILE, QUERY_SHEET, READ_FILE
from .tools import CREATE_DOCUMENT, Registry, ToolCall, ToolResult
from ._serve import _post

PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "plexar-tools"

DOCUMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["name", "text"],
    "properties": {"name": {"type": "string"}, "text": {"type": "string"}},
}
FILE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["name", "data_base64"],
    "properties": {
        "name": {"type": "string"},
        "media_type": {"type": "string"},
        "data_base64": {"type": "string"},
    },
}

SOURCES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": {
        "type": "object",
        "required": ["name", "data_base64"],
        "properties": {"name": {"type": "string"},
                       "media_type": {"type": "string"},
                       "data_base64": {"type": "string"}},
    },
}

EXTRACT_DESCRIPTION = (
    "Extract a file's text exactly as Plexar Chat stores it at upload. Returns "
    "the text, the extraction state (indexed, not_extractable or failed) and "
    "the reason when there is no text."
)

_REGISTRY = Registry((READ_FILE, FIND_IN_FILE, QUERY_SHEET, CONVERT_DOCUMENT,
                      CREATE_DOCUMENT))
_TEXT_TOOLS = {READ_FILE.name: _post.read, FIND_IN_FILE.name: _post.find,
               QUERY_SHEET.name: _post.query}


def _version() -> str:
    """The installed package version, or pyproject's when run from source."""
    from importlib import metadata

    try:
        return metadata.version("plexar-tools")
    except metadata.PackageNotFoundError:
        import pathlib
        import tomllib

        pyproject = pathlib.Path(__file__).resolve().parents[2] / "pyproject.toml"
        return tomllib.loads(pyproject.read_text("utf-8"))["project"]["version"]


def _with(parameters: dict[str, Any], key: str, schema: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(parameters)
    merged["properties"][key] = copy.deepcopy(schema)
    merged["required"] = [*merged.get("required", []), key]
    return merged


def tool_list() -> list[dict[str, Any]]:
    """The `tools/list` entries, in wire order.

    @returns: One `{name, description, inputSchema}` per tool.
    """
    tools = [{"name": t.name, "description": t.description,
              "inputSchema": _with(t.parameters, "document", DOCUMENT_SCHEMA)}
             for t in (READ_FILE, FIND_IN_FILE, QUERY_SHEET)]
    tools.append({"name": CONVERT_DOCUMENT.name,
                  "description": CONVERT_DOCUMENT.description,
                  "inputSchema": _with(CONVERT_DOCUMENT.parameters, "file",
                                       FILE_SCHEMA)})
    tools.append({"name": "extract_document", "description": EXTRACT_DESCRIPTION,
                  "inputSchema": {"type": "object", "required": ["file"],
                                  "properties": {"file": copy.deepcopy(FILE_SCHEMA)}}})
    create_schema = copy.deepcopy(CREATE_DOCUMENT.parameters)
    create_schema["properties"]["sources"] = copy.deepcopy(SOURCES_SCHEMA)
    tools.append({"name": CREATE_DOCUMENT.name,
                  "description": CREATE_DOCUMENT.description,
                  "inputSchema": create_schema})
    return tools


class _BadParams(Exception):
    """A `tools/call` whose server-side argument (`document`/`file`) is unusable."""


def _document(arguments: dict[str, Any]) -> tuple[str, str]:
    doc = arguments.get("document")
    if not (isinstance(doc, dict) and isinstance(doc.get("name"), str)
            and isinstance(doc.get("text"), str)):
        raise _BadParams("document must be an object with string name and text")
    return doc["name"], doc["text"]


def _file(arguments: dict[str, Any]) -> tuple[str, bytes]:
    given = arguments.get("file")
    if not (isinstance(given, dict) and isinstance(given.get("name"), str)
            and isinstance(given.get("data_base64"), str)):
        raise _BadParams("file must be an object with string name and data_base64")
    try:
        body = base64.b64decode(given["data_base64"], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise _BadParams(f"file.data_base64 is not base64: {exc}") from exc
    return given["name"], body


def _sources(arguments: dict[str, Any]) -> dict[str, tuple[str, bytes]]:
    given = arguments.get("sources", {})
    if not isinstance(given, dict):
        raise _BadParams("sources must be an object keyed by image reference")
    out: dict[str, tuple[str, bytes]] = {}
    for named, entry in given.items():
        if not (isinstance(entry, dict) and isinstance(entry.get("name"), str)
                and isinstance(entry.get("data_base64"), str)):
            raise _BadParams(f"sources[{named!r}] must be an object with string "
                             f"name and data_base64")
        try:
            out[named] = (entry["name"],
                          base64.b64decode(entry["data_base64"], validate=True))
        except (binascii.Error, ValueError) as exc:
            raise _BadParams(f"sources[{named!r}].data_base64 is not base64: {exc}") from exc
    return out


def _encoded(generated: Any) -> dict[str, str]:
    return {"name": generated.name, "media_type": generated.declared_type,
            "data_base64": base64.b64encode(generated.body).decode("ascii")}


def _structured(result: ToolResult) -> dict[str, Any]:
    return {"ok": result.ok, "content": result.content, "detail": result.detail,
            "extra": result.extra}


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Run one tool and build the `tools/call` result.

    @param name: The tool name.
    @param arguments: The call arguments, including `document`, `file` or `sources`.
    @returns: The MCP `CallToolResult` object.
    @raises _BadParams: When `document`/`file`/`sources` is missing or malformed.
    """
    output = None
    if name == "extract_document":
        result = _post.extract(*_file(arguments))
    elif name == CREATE_DOCUMENT.name:
        sources = _sources(arguments)
        model_args = {k: v for k, v in arguments.items() if k != "sources"}
        result = _REGISTRY.run(ToolCall(index=0, id="", name=name,
                                        arguments=json.dumps(model_args)))
        generated = None
        if result.ok:
            result, generated = _post.create(result, sources)
        if generated is not None:
            output = _encoded(generated)
    else:
        model_args = {k: v for k, v in arguments.items()
                      if k not in ("document", "file")}
        handler = _TEXT_TOOLS.get(name)
        loaded = (_document(arguments) if handler is not None else
                  _file(arguments) if name == CONVERT_DOCUMENT.name else None)
        result = _REGISTRY.run(ToolCall(index=0, id="", name=name,
                                        arguments=json.dumps(model_args)))
        if result.ok and handler is not None:
            result = handler(result, *loaded)
        elif result.ok and loaded is not None:
            result, generated = _post.convert(result, *loaded)
            if generated is not None:
                output = _encoded(generated)
    structured = _structured(result)
    if output is not None:
        structured["output"] = output
    return {"content": [{"type": "text", "text": result.content}],
            "isError": not result.ok, "structuredContent": structured}


def _error(id_: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def handle(message: Any) -> dict[str, Any] | None:
    """Answer one decoded JSON-RPC message.

    @param message: The decoded line.
    @returns: The response object, or `None` for a notification.
    """
    if not isinstance(message, dict) or not isinstance(message.get("method"), str):
        return _error(message.get("id") if isinstance(message, dict) else None,
                      -32600, "Invalid Request")
    method = message["method"]
    if "id" not in message:
        return None
    id_ = message["id"]
    params = message.get("params") or {}
    if method == "initialize":
        result: Any = {"protocolVersion": PROTOCOL_VERSION,
                       "capabilities": {"tools": {}},
                       "serverInfo": {"name": SERVER_NAME, "version": _version()}}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": tool_list()}
    elif method == "tools/call":
        arguments = params.get("arguments") if isinstance(params, dict) else None
        if not isinstance(params, dict) or not isinstance(params.get("name"), str):
            return _error(id_, -32602, "tools/call needs a string name")
        try:
            result = call_tool(params["name"], arguments if isinstance(arguments, dict) else {})
        except _BadParams as exc:
            return _error(id_, -32602, str(exc))
    else:
        return _error(id_, -32601, f"Method not found: {method}")
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def serve(stdin: BinaryIO, stdout: BinaryIO) -> int:
    """Serve until EOF.

    @param stdin: Newline-delimited JSON-RPC requests.
    @param stdout: Where responses are written, one per line.
    @returns: 0 at EOF.
    """
    for line in stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except ValueError:
            reply: dict[str, Any] | None = _error(None, -32700, "Parse error")
        else:
            try:
                reply = handle(message)
            except Exception as exc:  # noqa: BLE001 - one bad call must not end the server
                reply = _error(message.get("id") if isinstance(message, dict) else None,
                               -32603, f"Internal error: {type(exc).__name__}: {exc}")
        if reply is not None:
            stdout.write(json.dumps(reply, ensure_ascii=False).encode("utf-8") + b"\n")
            stdout.flush()
    return 0


def main() -> int:
    """Entry point for ``python -m plexar_tools.mcp``.

    @returns: The process exit code.
    """
    return serve(sys.stdin.buffer, sys.stdout.buffer)


if __name__ == "__main__":
    sys.exit(main())
