"""Harness-facing plexar-tools MCP server: `path` arguments, not inline bytes (N90).

Run with ``python -m plexar_tools.harness_mcp``. Wraps `plexar_tools.mcp`
verbatim — tool names, descriptions and the 200,000-character extraction cap
stay pinned there (chat-DEC-397); only the argument surface changes. Where the
base server takes `document` ({name, text}) or `file` ({name, data_base64})
inline, this server takes a `path` string and reads the file itself; where it
takes `sources` (image references to inline files), this server takes the
same references mapped to path strings.

Every path — `path`, an entry in `sources` — must resolve inside
`PLEXAR_TOOLS_ROOT` (an absolute directory read from the environment once at
startup). A path outside that root, or naming something that is not a
readable file, is refused with a plain message; it never reaches disk I/O
outside the root. `PLEXAR_TOOLS_ROOT` is required: a call made without it set
is refused the same way, so a caller sees why the tool cannot run.

This server requires Python 3.12 or newer, like the rest of `plexar_tools`
(pyproject `requires-python`). `main()` checks the interpreter first and
exits 1 with one line on stderr before serving, so a caller invoking the
wrong interpreter gets one readable line instead of an import-time traceback.
"""

from __future__ import annotations

import base64
import copy
import json
import os
import pathlib
import sys
from typing import Any, BinaryIO

from . import mcp as _base
from ._serve._extract import INDEXED, _extract_text, _sniff

#: Env var naming the absolute directory every `path`/`sources` entry must resolve inside.
ROOT_ENV = "PLEXAR_TOOLS_ROOT"

PATH_SCHEMA: dict[str, Any] = {
    "type": "string",
    "description": "A file path, absolute or relative to the workspace root.",
}

_DOCUMENT_TOOLS = ("read_file", "find_in_file", "query_sheet")
_FILE_TOOLS = ("convert_document", "extract_document")


class _Refused(Exception):
    """A `path`/`sources` entry outside the workspace root, missing, or unreadable."""


def _root() -> pathlib.Path:
    """The configured workspace root.

    @returns: The resolved, absolute root directory.
    @raises _Refused: When `PLEXAR_TOOLS_ROOT` is unset, relative, or not a directory.
    """
    value = os.environ.get(ROOT_ENV)
    if not value:
        raise _Refused(f"{ROOT_ENV} is not set; the harness must configure it")
    root = pathlib.Path(value)
    if not root.is_absolute():
        raise _Refused(f"{ROOT_ENV} must be an absolute path, got {value!r}")
    root = root.resolve()
    if not root.is_dir():
        raise _Refused(f"{ROOT_ENV} does not name a directory: {value!r}")
    return root


def _resolve(root: pathlib.Path, raw: Any, label: str) -> pathlib.Path:
    """One path argument, checked against `root`.

    @param root: The resolved workspace root.
    @param raw: The caller-supplied path value.
    @param label: What the argument is called, for the refusal message.
    @returns: The resolved absolute path, guaranteed to be inside `root`.
    @raises _Refused: When `raw` is not a string, escapes `root`, or is not a readable file.
    """
    if not isinstance(raw, str) or not raw:
        raise _Refused(f"{label} must be a non-empty string")
    candidate = pathlib.Path(raw)
    target = (candidate if candidate.is_absolute() else root / candidate).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise _Refused(f"{label} {raw!r} resolves outside the workspace root") from None
    if not target.is_file():
        raise _Refused(f"{label} {raw!r} does not name a readable file")
    return target


def tool_list() -> list[dict[str, Any]]:
    """The `tools/list` entries, `document`/`file`/inline `sources` swapped for paths.

    @returns: One `{name, description, inputSchema}` per tool, in the base server's order.
    """
    tools = copy.deepcopy(_base.tool_list())
    for tool in tools:
        schema = tool["inputSchema"]
        props, required = schema["properties"], schema["required"]
        for key in ("document", "file"):
            if key in props:
                del props[key]
                if key in required:
                    required.remove(key)
        if "sources" in props:
            props["sources"] = {
                "type": "object",
                "additionalProperties": PATH_SCHEMA,
                "description": ("Image references, keyed exactly as the document spec "
                                "names them, to file paths inside the workspace root."),
            }
        if tool["name"] != "create_document":
            props["path"] = copy.deepcopy(PATH_SCHEMA)
            required.append("path")
    return tools


def _path_arg(arguments: dict[str, Any]) -> str:
    raw = arguments.get("path")
    if not isinstance(raw, str):
        raise _Refused("path must be a string")
    return raw


def _document_arguments(root: pathlib.Path, arguments: dict[str, Any]) -> dict[str, Any]:
    target = _resolve(root, _path_arg(arguments), "path")
    body = target.read_bytes()
    text, state, reason = _extract_text(body, target.name, _sniff(body, target.name))
    if state != INDEXED:
        raise _Refused(f"{target.name}: {reason}")
    return {**{k: v for k, v in arguments.items() if k != "path"},
            "document": {"name": target.name, "text": text}}


def _file_arguments(root: pathlib.Path, arguments: dict[str, Any]) -> dict[str, Any]:
    target = _resolve(root, _path_arg(arguments), "path")
    encoded = base64.b64encode(target.read_bytes()).decode("ascii")
    return {**{k: v for k, v in arguments.items() if k != "path"},
            "file": {"name": target.name, "data_base64": encoded}}


def _sources_arguments(root: pathlib.Path, arguments: dict[str, Any]) -> dict[str, Any]:
    given = arguments.get("sources", {})
    if not isinstance(given, dict):
        raise _Refused("sources must be an object keyed by image reference")
    resolved: dict[str, Any] = {}
    for ref, raw in given.items():
        target = _resolve(root, raw, f"sources[{ref!r}]")
        encoded = base64.b64encode(target.read_bytes()).decode("ascii")
        resolved[ref] = {"name": target.name, "data_base64": encoded}
    return {**{k: v for k, v in arguments.items() if k != "sources"}, "sources": resolved}


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Resolve `path`/`sources` against the workspace root, then run the base tool.

    @param name: The tool name.
    @param arguments: The call arguments, including `path` and/or `sources`.
    @returns: The MCP `CallToolResult` object, from `plexar_tools.mcp.call_tool`.
    @raises _Refused: When a path argument is missing, escapes the root, or is unreadable.
    """
    root = _root()
    if name in _DOCUMENT_TOOLS:
        base_arguments = _document_arguments(root, arguments)
    elif name in _FILE_TOOLS:
        base_arguments = _file_arguments(root, arguments)
    elif name == _base.CREATE_DOCUMENT.name:
        base_arguments = _sources_arguments(root, arguments)
    else:
        raise _base._BadParams(f"unknown tool: {name}")  # noqa: SLF001 - same module family
    return _base.call_tool(name, base_arguments)


def handle(message: Any) -> dict[str, Any] | None:
    """Answer one decoded JSON-RPC message, same wire shape as `plexar_tools.mcp.handle`.

    @param message: The decoded line.
    @returns: The response object, or `None` for a notification.
    """
    if not isinstance(message, dict) or not isinstance(message.get("method"), str):
        return _base._error(message.get("id") if isinstance(message, dict) else None,  # noqa: SLF001
                            -32600, "Invalid Request")
    method = message["method"]
    if "id" not in message:
        return None
    id_ = message["id"]
    params = message.get("params") or {}
    if method == "initialize":
        result: Any = {"protocolVersion": _base.PROTOCOL_VERSION,
                       "capabilities": {"tools": {}},
                       "serverInfo": {"name": _base.SERVER_NAME, "version": _base._version()}}  # noqa: SLF001
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": tool_list()}
    elif method == "tools/call":
        arguments = params.get("arguments") if isinstance(params, dict) else None
        if not isinstance(params, dict) or not isinstance(params.get("name"), str):
            return _base._error(id_, -32602, "tools/call needs a string name")  # noqa: SLF001
        try:
            result = call_tool(params["name"], arguments if isinstance(arguments, dict) else {})
        except (_base._BadParams, _Refused) as exc:  # noqa: SLF001
            return _base._error(id_, -32602, str(exc))  # noqa: SLF001
    else:
        return _base._error(id_, -32601, f"Method not found: {method}")  # noqa: SLF001
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def serve(stdin: BinaryIO, stdout: BinaryIO) -> int:
    """Serve until EOF, same loop as `plexar_tools.mcp.serve`.

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
            reply: dict[str, Any] | None = _base._error(None, -32700, "Parse error")  # noqa: SLF001
        else:
            try:
                reply = handle(message)
            except Exception as exc:  # noqa: BLE001 - one bad call must not end the server
                reply = _base._error(  # noqa: SLF001
                    message.get("id") if isinstance(message, dict) else None,
                    -32603, f"Internal error: {type(exc).__name__}: {exc}")
        if reply is not None:
            stdout.write(json.dumps(reply, ensure_ascii=False).encode("utf-8") + b"\n")
            stdout.flush()
    return 0


def main() -> int:
    """Entry point for ``python -m plexar_tools.harness_mcp``.

    @returns: The process exit code. 1, with one line on stderr, below Python 3.12.
    """
    if sys.version_info < (3, 12):
        print("Plexar document tools need Python 3.12 or newer; set PLEXAR_PYTHON to its path",
              file=sys.stderr)
        return 1
    return serve(sys.stdin.buffer, sys.stdout.buffer)


if __name__ == "__main__":
    sys.exit(main())
