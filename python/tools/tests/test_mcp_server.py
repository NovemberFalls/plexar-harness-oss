"""The plexar-tools MCP server, driven as a real subprocess over stdio (chat-DEC-397).

Chat builds its MCP client against this wire and deletes its in-process tools
only when its own suite passes against the server, so the descriptions, the
200,000-character extraction cap and the per-outcome sentences are pinned here:
a change to any of them must be told to Chat first.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile

import pytest

from plexar_tools import office
from plexar_tools._serve import _post
from plexar_tools._serve._extract import (MAX_INDEXED_CHARS_PER_FILE,
                                          _extract_text, _sniff)
from plexar_tools.office import xlsx_bytes
from plexar_tools.tools import (CONVERT_DOCUMENT, CREATE_DOCUMENT, FIND_IN_FILE,
                                QUERY_SHEET, READ_FILE, Registry, ToolCall)

TOOLS_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = TOOLS_ROOT / "src"
PACKAGE = SRC / "plexar_tools"
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
NAMES = ["read_file", "find_in_file", "query_sheet", "convert_document",
         "extract_document", "create_document"]


class Server:
    """One `python -m plexar_tools.mcp` child and a request counter."""

    def __init__(self, cwd: pathlib.Path | None = None,
                 env: dict[str, str] | None = None) -> None:
        full = dict(os.environ)
        full["PYTHONPATH"] = str(SRC)
        full["PYTHONDONTWRITEBYTECODE"] = "1"
        full.update(env or {})
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "plexar_tools.mcp"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=str(cwd or TOOLS_ROOT), env=full)
        self.next_id = 0

    def send_raw(self, line: bytes) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(line + b"\n")
        self.proc.stdin.flush()

    def receive(self) -> dict:
        assert self.proc.stdout is not None
        line = self.proc.stdout.readline()
        assert line, self.proc.stderr.read().decode() if self.proc.stderr else "EOF"
        return json.loads(line)

    def request(self, method: str, params: dict | None = None) -> dict:
        self.next_id += 1
        message = {"jsonrpc": "2.0", "id": self.next_id, "method": method}
        if params is not None:
            message["params"] = params
        self.send_raw(json.dumps(message).encode())
        reply = self.receive()
        assert reply["id"] == self.next_id
        return reply

    def call(self, name: str, arguments: dict) -> dict:
        reply = self.request("tools/call", {"name": name, "arguments": arguments})
        assert "result" in reply, reply
        return reply["result"]

    def close(self) -> int:
        assert self.proc.stdin is not None
        self.proc.stdin.close()
        code = self.proc.wait(timeout=30)
        for stream in (self.proc.stdout, self.proc.stderr):
            if stream is not None:
                stream.close()
        return code


@pytest.fixture
def server():
    running = Server()
    running.request("initialize", {"protocolVersion": "2025-06-18",
                                   "capabilities": {},
                                   "clientInfo": {"name": "test", "version": "0"}})
    running.send_raw(json.dumps({"jsonrpc": "2.0",
                                 "method": "notifications/initialized"}).encode())
    yield running
    if running.proc.poll() is None:
        running.close()


def _file(name: str, body: bytes) -> dict:
    return {"name": name, "data_base64": base64.b64encode(body).decode()}


def _pnl() -> bytes:
    return xlsx_bytes([
        ["R365 P&L Projection"],
        [],
        ["Line Item", "Jan 2025 Result", "Feb 2025 Result", "Total"],
        ["Dine In", "936204.81", "700529.00", "1636733.81"],
        ["Beverage", "1000", "1200", "2200"],
    ], sheet="PNL Projection")


def _direct(tool, args: dict, name: str, text: str):
    """The in-process path Chat's App runs: registry validation, then the
    post-resolution step on already-resolved text."""
    result = Registry((tool,)).run(ToolCall(index=0, id="", name=tool.name,
                                            arguments=json.dumps(args)))
    step = {"read_file": _post.read, "find_in_file": _post.find,
            "query_sheet": _post.query}[tool.name]
    return step(result, name, text) if result.ok else result


# ── 1. initialize + tools/list ─────────────────────────────────────────────

#: sha256 of each description. A failure here means a model-facing text changed:
#: tell Chat before updating the pin.
DESCRIPTION_SHA256 = {
    "read_file": "112b057456a7fd5a1b734d8009d4ff6dc3003d7c6ab8af15429df49fba9fa195",
    "find_in_file": "70c2707b4b083f6102118804e25a93f09ea927501666039462edd90e75b71df5",
    "query_sheet": "340171b8ab88eb7827db002d5eeef65d96bdbd2d24ba6a156e13b209e6930303",
    "convert_document": "a64057af268cf291d60c64b99be45533ab5420b512e095c8555257a4421e6677",
    "extract_document": "e7f8e4c54be17e78415a1f4c0bb3d6b1bfa4838fab2cf3c8bb6de764f2739cdf",
    "create_document": "c7944afba5a6e80e53486ad03d289cb7e26021066eb0193638dd3a4b16ad1259",
}


def test_initialize_answers_the_pinned_server_info():
    running = Server()
    reply = running.request("initialize", {"protocolVersion": "2025-06-18"})
    result = reply["result"]
    assert result["protocolVersion"] == "2025-06-18"
    assert result["capabilities"] == {"tools": {}}
    assert result["serverInfo"]["name"] == "plexar-tools"
    assert result["serverInfo"]["version"] == "0.0.0.dev0"
    assert running.request("ping")["result"] == {}
    assert running.close() == 0


def test_tools_list_is_exactly_six_tools_with_chats_texts(server):
    tools = server.request("tools/list")["result"]["tools"]
    assert [t["name"] for t in tools] == NAMES
    by_name = {t["name"]: t for t in tools}
    for tool in (READ_FILE, FIND_IN_FILE, QUERY_SHEET, CONVERT_DOCUMENT,
                 CREATE_DOCUMENT):
        listed = by_name[tool.name]
        assert listed["description"] == tool.description
        for key, schema in tool.parameters["properties"].items():
            assert listed["inputSchema"]["properties"][key] == schema
        assert set(tool.parameters["required"]) <= set(listed["inputSchema"]["required"])
    for name in ("read_file", "find_in_file", "query_sheet"):
        assert "document" in by_name[name]["inputSchema"]["required"]
        assert "file" not in by_name[name]["inputSchema"]["properties"]
    for name in ("convert_document", "extract_document"):
        assert "file" in by_name[name]["inputSchema"]["required"]
    create = by_name["create_document"]["inputSchema"]
    assert create["required"] == CREATE_DOCUMENT.parameters["required"]
    assert create["properties"]["sources"] == {
        "type": "object",
        "additionalProperties": {
            "type": "object", "required": ["name", "data_base64"],
            "properties": {"name": {"type": "string"},
                           "media_type": {"type": "string"},
                           "data_base64": {"type": "string"}}}}
    digests = {t["name"]: hashlib.sha256(t["description"].encode()).hexdigest()
               for t in tools}
    assert digests == DESCRIPTION_SHA256


# ── 2. boundary ────────────────────────────────────────────────────────────

_FORBIDDEN = ("sub", "bucket", "r2", "conversation", "user", "owner", "tenant",
              "principal")


def _property_names(schema, found: list[str]) -> list[str]:
    if isinstance(schema, dict):
        for key, value in (schema.get("properties") or {}).items():
            found.append(key)
            _property_names(value, found)
        for value in schema.values():
            if isinstance(value, (dict, list)):
                _property_names(value, found)
    elif isinstance(schema, list):
        for value in schema:
            _property_names(value, found)
    return found


def test_no_schema_names_an_owner_concept(server):
    tools = server.request("tools/list")["result"]["tools"]
    for tool in tools:
        names = set(_property_names(tool["inputSchema"], []))
        for name in names:
            assert not any(bad in name.lower() for bad in _FORBIDDEN), (tool["name"], name)
        extra = names - set(_property_names(
            {"properties": {"file_id": 0, "to": 0, "name": 0, "source": 0, "start": 0,
                            "length": 0, "query": 0, "row": 0, "headings": 0,
                            "sheet": 0}}, []))
        extra -= set(_property_names(CREATE_DOCUMENT.parameters, []))
        assert extra <= {"file", "document", "media_type", "data_base64", "text",
                         "sources"}


# ── 3. parity ──────────────────────────────────────────────────────────────

def _extract_over_mcp(server, name: str, body: bytes) -> dict:
    return server.call("extract_document", {"file": _file(name, body)})


@pytest.mark.parametrize("name,body", [
    ("pnl.xlsx", None),
    ("illustrated.docx", "fixture"),
    ("len-carriers.html", "fixture"),
    ("rows.csv", office.csv_bytes([["a", "b"], ["1", "2"]])),
])
def test_extract_equals_chats_upload_extraction(server, name, body):
    if body is None:
        body = _pnl()
    elif body == "fixture":
        body = (FIXTURES / name).read_bytes()
    result = _extract_over_mcp(server, name, body)
    text, state, reason = _extract_text(body, name, _sniff(body, name))
    assert result["structuredContent"]["extra"] == {
        "text": text, "state": state, "reason": reason,
        "convertible": office.kind_of(name) in office.READERS,
        "sniffed": _sniff(body, name),
        "kind": "ok" if state == "indexed" else state}
    assert result["content"][0]["text"] == text
    assert result["isError"] is (state != "indexed")
    if name.endswith((".xlsx", ".docx")):
        assert text == office.read(body, name).text[:MAX_INDEXED_CHARS_PER_FILE]


def test_extraction_cap_is_pinned_at_200_000(server):
    assert MAX_INDEXED_CHARS_PER_FILE == 200_000
    result = _extract_over_mcp(server, "long.txt", b"x" * 250_000)
    assert len(result["structuredContent"]["extra"]["text"]) == 200_000


@pytest.mark.parametrize("tool,args", [
    (READ_FILE, {"source": "pnl.xlsx", "start": 10, "length": 50}),
    (READ_FILE, {"source": "other name", "start": 0}),
    (FIND_IN_FILE, {"source": "pnl.xlsx", "query": "dine in"}),
    (FIND_IN_FILE, {"source": "pnl.xlsx", "query": "Nowhere Row"}),
    (QUERY_SHEET, {"source": "pnl.xlsx", "row": "Dine In"}),
    (QUERY_SHEET, {"source": "pnl.xlsx", "row": "R4"}),
    (QUERY_SHEET, {"source": "pnl.xlsx", "row": "Dine In", "sheet": "Nope"}),
    (READ_FILE, {"source": "pnl.xlsx", "start": "middle"}),
])
def test_text_reads_match_the_in_process_path(server, tool, args):
    text = _extract_over_mcp(server, "pnl.xlsx", _pnl())["structuredContent"]["extra"]["text"]
    over_mcp = server.call(tool.name, {**args, "document": {"name": "pnl.xlsx",
                                                             "text": text}})
    direct = _direct(tool, args, "pnl.xlsx", text)
    structured = over_mcp["structuredContent"]
    assert structured == {"ok": direct.ok, "content": direct.content,
                          "detail": direct.detail, "extra": direct.extra}
    assert over_mcp["content"] == [{"type": "text", "text": direct.content}]
    assert over_mcp["isError"] is (not direct.ok)


def test_query_sheet_pairs_values_with_headings(server):
    text = _extract_over_mcp(server, "pnl.xlsx", _pnl())["structuredContent"]["extra"]["text"]
    result = server.call("query_sheet", {"source": "pnl.xlsx", "row": "Dine In",
                                         "document": {"name": "pnl.xlsx", "text": text}})
    assert "Jan 2025 Result | 936204.81" in result["content"][0]["text"]


def test_convert_matches_office_convert(server):
    body = _pnl()
    result = server.call("convert_document", {"file_id": "pnl.xlsx", "to": "csv",
                                              "file": _file("pnl.xlsx", body)})
    data, kind, _ = office.convert(body, "pnl.xlsx", "csv")
    output = result["structuredContent"]["output"]
    assert base64.b64decode(output["data_base64"]) == data
    produced = office.safe_name("pnl.xlsx", kind)
    assert output == {"name": produced, "media_type": office.KINDS[kind][1],
                      "data_base64": output["data_base64"]}
    assert result["content"][0]["text"] == (
        f"Converted to {produced}, a CSV file, {len(data)} bytes.")
    assert result["structuredContent"]["extra"] == {"kind": "ok"}


# ── 4. the three outcomes ──────────────────────────────────────────────────

def test_couldnt_read_is_chats_extraction_refusal(server):
    corrupt = _extract_over_mcp(server, "broken.xlsx", b"PK\x03\x04 not a zip")
    assert corrupt["isError"] is True
    assert corrupt["structuredContent"]["extra"] == {
        "text": "", "state": "not_extractable",
        "reason": "the .xlsx file could not be read", "convertible": True,
        "sniffed": _sniff(b"PK\x03\x04 not a zip", "broken.xlsx"),
        "kind": "not_extractable"}
    garbled = _extract_over_mcp(server, "notes.txt", b"\xff\xfe\xfa bad")
    assert garbled["structuredContent"]["extra"] == {
        "text": "", "state": "failed",
        "reason": "the file is not valid UTF-8 text", "convertible": True,
        "sniffed": _sniff(b"\xff\xfe\xfa bad", "notes.txt"),
        "kind": "failed"}


def test_found_nothing_is_an_ok_fact(server):
    result = server.call("find_in_file", {
        "source": "a.txt", "query": "zebra",
        "document": {"name": "a.txt", "text": "alpha beta"}})
    assert result["isError"] is False
    assert result["structuredContent"] == {
        "ok": True,
        "content": ("a.txt — 'zebra' does not appear anywhere in its 10 "
                    "characters. The file IS attached and readable; this is a "
                    "fact about the text, not a failure. Try a shorter or "
                    "differently-spelled phrase, or read part of the file to see "
                    "what the labels actually are."),
        "detail": "searched a.txt — no match for 'zebra'",
        "extra": {"kind": "no_match"}}


def test_refused_on_a_bound_names_the_length(server):
    result = server.call("read_file", {
        "source": "a.txt", "start": 50,
        "document": {"name": "a.txt", "text": "alpha beta"}})
    assert result["isError"] is True
    assert result["structuredContent"] == {
        "ok": False,
        "content": ("a.txt has 10 characters of text in total, so there is "
                    "nothing at character 50. Read a start below 10."),
        "detail": "nothing read — past the end of 10",
        "extra": {"kind": "bound"}}


def test_one_call_is_bounded_to_the_read_window(server):
    result = server.call("read_file", {
        "source": "a.txt", "start": 0, "length": 999_999,
        "document": {"name": "a.txt", "text": "y" * 20_000}})
    assert result["structuredContent"]["extra"]["read_span"] == {
        "start": 0, "end": 6_000, "total": 20_000}


# ── 5. convert writes nothing ──────────────────────────────────────────────

def _listing(root: pathlib.Path) -> list[tuple[str, int, int]]:
    return sorted((str(p.relative_to(root)), p.stat().st_size, p.stat().st_mtime_ns)
                  for p in root.rglob("*"))


def test_convert_writes_nothing_to_disk():
    with tempfile.TemporaryDirectory() as scratch:
        empty = pathlib.Path(scratch)
        before = (_listing(empty), _listing(PACKAGE))
        running = Server(cwd=empty, env={"TMP": scratch, "TEMP": scratch,
                                         "TMPDIR": scratch})
        result = running.call("convert_document", {
            "file_id": "pnl.xlsx", "to": "pdf", "file": _file("pnl.xlsx", _pnl())})
        assert running.close() == 0
        assert (_listing(empty), _listing(PACKAGE)) == before
    assert base64.b64decode(result["structuredContent"]["output"]["data_base64"]
                            ).startswith(b"%PDF-")


# ── 6. kill switch and EOF ─────────────────────────────────────────────────

def test_a_killed_server_leaves_nothing_behind():
    rows = [["Line Item", "Jan", "Feb"]] + [[f"Item {i}", str(i), str(2 * i)]
                                           for i in range(40_000)]
    big = xlsx_bytes(rows, sheet="Big")
    doomed = Server()
    doomed.send_raw(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                "params": {"name": "extract_document",
                                           "arguments": {"file": _file("big.xlsx", big)}}
                                }).encode())
    doomed.proc.kill()
    doomed.proc.wait(timeout=30)
    fresh = Server()
    result = fresh.call("extract_document", {"file": _file("big.xlsx", big)})
    assert result["structuredContent"]["extra"]["state"] == "indexed"
    assert fresh.close() == 0


def test_eof_exits_zero():
    assert Server().close() == 0


# ── 7. malformed input ─────────────────────────────────────────────────────

def test_a_malformed_line_is_a_parse_error_and_serving_continues(server):
    server.send_raw(b"{not json")
    reply = server.receive()
    assert reply == {"jsonrpc": "2.0", "id": None,
                     "error": {"code": -32700, "message": "Parse error"}}
    assert server.request("ping")["result"] == {}


def test_an_unknown_method_is_method_not_found(server):
    assert server.request("resources/list")["error"]["code"] == -32601
