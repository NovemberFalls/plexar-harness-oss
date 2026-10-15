"""The harness-facing `path`-argument MCP server (N90).

Runs `python -m plexar_tools.harness_mcp` as a real subprocess and checks it
against `plexar_tools.mcp`: same tool names and descriptions, `path` in place
of inline `document`/`file`/`sources` bytes, and root enforcement for every
path argument.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

from plexar_tools.mcp import tool_list as _base_tool_list

TOOLS_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = TOOLS_ROOT / "src"
NAMES = ["read_file", "find_in_file", "query_sheet", "convert_document",
         "extract_document", "create_document"]


class Server:
    """One `python -m plexar_tools.harness_mcp` child and a request counter."""

    def __init__(self, root: pathlib.Path, env: dict[str, str] | None = None) -> None:
        full = dict(os.environ)
        full["PYTHONPATH"] = str(SRC)
        full["PYTHONDONTWRITEBYTECODE"] = "1"
        full["PLEXAR_TOOLS_ROOT"] = str(root)
        full.update(env or {})
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "plexar_tools.harness_mcp"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=str(root), env=full)
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
def workspace(tmp_path: pathlib.Path) -> pathlib.Path:
    (tmp_path / "a.txt").write_text("alpha beta", encoding="utf-8")
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir(exist_ok=True)
    (outside / "secret.txt").write_text("nope", encoding="utf-8")
    return tmp_path


@pytest.fixture
def server(workspace):
    running = Server(workspace)
    running.request("initialize", {"protocolVersion": "2025-06-18",
                                   "capabilities": {},
                                   "clientInfo": {"name": "test", "version": "0"}})
    running.send_raw(json.dumps({"jsonrpc": "2.0",
                                 "method": "notifications/initialized"}).encode())
    yield running
    if running.proc.poll() is None:
        running.close()


def test_tools_list_is_the_same_six_tools_with_path_in_place_of_bytes(server):
    tools = server.request("tools/list")["result"]["tools"]
    assert [t["name"] for t in tools] == NAMES
    base_by_name = {t["name"]: t for t in _base_tool_list()}
    for tool in tools:
        base = base_by_name[tool["name"]]
        assert tool["description"] == base["description"]
        if tool["name"] != "create_document":
            assert tool["inputSchema"]["properties"]["path"]["type"] == "string"
            assert "path" in tool["inputSchema"]["required"]
        assert "document" not in tool["inputSchema"]["properties"]
        assert "file" not in tool["inputSchema"]["properties"]
    create = next(t for t in tools if t["name"] == "create_document")
    assert create["inputSchema"]["properties"]["sources"]["additionalProperties"]["type"] == "string"


def test_read_file_resolves_a_relative_path_inside_the_root(server):
    result = server.call("read_file", {"source": "a.txt", "start": 0, "path": "a.txt"})
    assert result["isError"] is False
    assert "alpha beta" in result["content"][0]["text"]


def test_a_path_escaping_the_root_is_refused(server, workspace):
    outside = workspace.parent / f"{workspace.name}-outside" / "secret.txt"
    reply = server.request("tools/call", {"name": "read_file",
                                          "arguments": {"source": "secret.txt", "start": 0,
                                                        "path": str(outside)}})
    assert reply["error"]["code"] == -32602
    assert "outside the workspace root" in reply["error"]["message"]


def test_a_parent_traversal_relative_path_is_refused(server):
    reply = server.request("tools/call", {"name": "read_file",
                                          "arguments": {"source": "secret.txt", "start": 0,
                                                        "path": "../secret.txt"}})
    assert reply["error"]["code"] == -32602
    assert "outside the workspace root" in reply["error"]["message"]


def test_a_missing_file_is_refused_not_a_traceback(server):
    reply = server.request("tools/call", {"name": "read_file",
                                          "arguments": {"source": "nope.txt", "start": 0,
                                                        "path": "nope.txt"}})
    assert reply["error"]["code"] == -32602
    assert "does not name a readable file" in reply["error"]["message"]


def test_extract_document_reads_the_file_from_disk(server):
    result = server.call("extract_document", {"path": "a.txt"})
    assert result["structuredContent"]["extra"]["text"] == "alpha beta"
    assert result["structuredContent"]["extra"]["state"] == "indexed"


def test_find_in_file_over_a_path(server):
    result = server.call("find_in_file", {"source": "a.txt", "query": "beta", "path": "a.txt"})
    assert result["isError"] is False
    assert "beta" in result["content"][0]["text"]


def test_missing_workspace_root_is_refused(workspace):
    running = Server(workspace, env={"PLEXAR_TOOLS_ROOT": ""})
    reply = running.request("tools/call", {"name": "read_file",
                                           "arguments": {"source": "a.txt", "start": 0,
                                                         "path": "a.txt"}})
    assert reply["error"]["code"] == -32602
    assert "PLEXAR_TOOLS_ROOT is not set" in reply["error"]["message"]
    assert running.close() == 0


def test_eof_exits_zero(server):
    assert server.close() == 0
