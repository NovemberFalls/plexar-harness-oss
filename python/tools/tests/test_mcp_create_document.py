"""`create_document` and extract_document's `convertible` over the real stdio server (chat-DEC-397).

The server builds what Chat's `App._attach_generated` builds for a created
document, from the caller's `sources` instead of the store, and returns the
bytes in `structuredContent.output`. These tests pin the per-kind round trip
through `extract_document`, the picture path, the distinct missing-image
refusal and the no-disk rule.
"""

from __future__ import annotations

import base64
import pathlib
import tempfile

import pytest

from plexar_tools import office
from plexar_tools._serve._extract import _sniff
from test_mcp_server import FIXTURES, PACKAGE, Server, _file, _listing, server  # noqa: F401

_SPECS = {
    "docx": {"blocks": [{"type": "heading1", "text": "Thaw Procedure"},
                        {"type": "paragraph", "text": "Keep below 5C marker"}]},
    "pdf": {"blocks": [{"type": "heading1", "text": "Thaw Procedure"},
                       {"type": "paragraph", "text": "Keep below 5C marker"}]},
    "html": {"blocks": [{"type": "heading1", "text": "Thaw Procedure"},
                        {"type": "paragraph", "text": "Keep below 5C marker"}]},
    "pptx": {"slides": [{"title": "Thaw Procedure",
                         "bullets": ["Keep below 5C marker"]}]},
    "xlsx": {"rows": [["Item", "Note"], ["Tuna", "Keep below 5C marker"]]},
    "csv": {"rows": [["Item", "Note"], ["Tuna", "Keep below 5C marker"]]},
}


def _source(name: str, body: bytes) -> dict:
    return {"name": name, "data_base64": base64.b64encode(body).decode()}


def _decoded(result: dict) -> tuple[str, bytes]:
    output = result["structuredContent"]["output"]
    return output["name"], base64.b64decode(output["data_base64"])


@pytest.mark.parametrize("kind", sorted(office.KINDS))
def test_each_kind_builds_a_file_that_extracts_again(server, kind):
    result = server.call("create_document", {"kind": kind, "name": "Thaw",
                                             **_SPECS[kind]})
    assert result["isError"] is False, result
    name, body = _decoded(result)
    assert name == office.safe_name("Thaw", kind)
    assert result["structuredContent"]["output"]["media_type"] == office.KINDS[kind][1]
    suffix = name.rsplit(".", 1)[-1].upper()
    assert result["structuredContent"]["content"] == (
        f"Created {name}, a {suffix} file, {len(body)} bytes.")
    assert result["structuredContent"]["extra"] == {"literal_markup": 0, "kind": "ok"}
    extracted = server.call("extract_document", {"file": _file(name, body)})
    assert extracted["structuredContent"]["extra"]["state"] == "indexed"
    assert "Keep below 5C marker" in extracted["structuredContent"]["extra"]["text"]


def test_an_image_source_supplied_by_name_is_placed(server):
    photo = (FIXTURES / "illustrated.docx").read_bytes()
    result = server.call("create_document", {
        "kind": "docx", "name": "Illustrated SOP",
        "blocks": [{"type": "heading1", "text": "Step one"},
                   {"type": "image", "source": "illustrated.docx", "index": 1}],
        "sources": {"illustrated.docx": _source("illustrated.docx", photo)}})
    assert result["isError"] is False, result
    name, body = _decoded(result)
    assert len(office.read(body, name).images) == 1


def test_a_missing_image_source_is_the_distinct_refusal(server):
    result = server.call("create_document", {
        "kind": "docx", "name": "Illustrated SOP",
        "blocks": [{"type": "image", "source": "photos.docx", "index": 1}],
        "sources": {}})
    assert result["isError"] is True
    assert "output" not in result["structuredContent"]
    assert result["structuredContent"] == {
        "ok": False,
        "content": ("There is no file photos.docx in this conversation, so "
                    "nothing was created. The files here are: none. Use one of "
                    "those as the image source and send it again — do NOT tell "
                    "the user their file is missing."),
        "detail": "no file — a source is missing",
        "extra": {"needed_sources": ["photos.docx"], "kind": "missing_image"}}


def test_an_image_index_past_the_source_is_chats_missing_image_sentence(server):
    photo = (FIXTURES / "illustrated.docx").read_bytes()
    result = server.call("create_document", {
        "kind": "pdf", "name": "SOP",
        "blocks": [{"type": "image", "source": "illustrated.docx", "index": 9}],
        "sources": {"illustrated.docx": _source("illustrated.docx", photo)}})
    assert result["structuredContent"] == {
        "ok": False,
        "content": ("That document could not be assembled: that file has 2 "
                    "image(s), so image 9 does not exist. No file was created — "
                    "check the image numbers against the file's own text and "
                    "send it again."),
        "detail": "no file — an image reference did not resolve",
        "extra": {"kind": "missing_image"}}


def test_create_writes_nothing_to_disk():
    photo = (FIXTURES / "illustrated.docx").read_bytes()
    with tempfile.TemporaryDirectory() as scratch:
        empty = pathlib.Path(scratch)
        before = (_listing(empty), _listing(PACKAGE))
        running = Server(cwd=empty, env={"TMP": scratch, "TEMP": scratch,
                                         "TMPDIR": scratch})
        plain = running.call("create_document", _SPECS["pdf"] | {"kind": "pdf",
                                                                "name": "a"})
        pictured = running.call("create_document", {
            "kind": "pdf", "name": "b",
            "blocks": [{"type": "image", "source": "illustrated.docx", "index": 1}],
            "sources": {"illustrated.docx": _source("illustrated.docx", photo)}})
        assert running.close() == 0
        assert (_listing(empty), _listing(PACKAGE)) == before
    for result in (plain, pictured):
        assert _decoded(result)[1].startswith(b"%PDF-")


def test_malformed_sources_are_invalid_params(server):
    reply = server.request("tools/call", {"name": "create_document", "arguments": {
        "kind": "docx", "name": "x", "blocks": [{"type": "paragraph", "text": "y"}],
        "sources": {"a.docx": {"name": "a.docx", "data_base64": "!!not base64!!"}}}})
    assert reply["error"]["code"] == -32602
    nameless = server.request("tools/call", {"name": "create_document", "arguments": {
        "kind": "docx", "name": "x", "blocks": [{"type": "paragraph", "text": "y"}],
        "sources": {"a.docx": {"data_base64": ""}}}})
    assert nameless["error"]["code"] == -32602


def test_an_unreadable_source_is_named_by_its_real_name(server):
    result = server.call("create_document", {
        "kind": "docx", "name": "SOP",
        "blocks": [{"type": "image", "source": "65a3f0c9", "index": 1}],
        "sources": {"65a3f0c9": _source("photos.docx", b"PK not a zip")}})
    assert result["structuredContent"] == {
        "ok": False,
        "content": ("photos.docx could not be read, so its pictures could not "
                    "be re-used and no file was created."),
        "detail": "no file — a source could not be read",
        "extra": {"kind": "missing_image"}}


@pytest.mark.parametrize("real_name", ["photos.pdf", "photos.docx"])
def test_a_file_id_reference_reads_by_the_sources_real_name(server, real_name):
    photo = (FIXTURES / "illustrated.docx").read_bytes()
    if real_name.endswith(".pdf"):
        photo = office.convert(photo, "illustrated.docx", "pdf")[0]
    result = server.call("create_document", {
        "kind": "pdf", "name": "SOP",
        "header": {"text": "Kitchen", "image": {"source": "65a3f0c9", "index": 2}},
        "blocks": [{"type": "heading1", "text": "Step one"},
                   {"type": "image", "source": "65a3f0c9", "index": 1}],
        "sources": {"65a3f0c9": _source(real_name, photo)}})
    assert result["isError"] is False, result
    assert _decoded(result)[1].startswith(b"%PDF-")


def test_needed_sources_lists_every_unsupplied_reference(server):
    photo = (FIXTURES / "illustrated.docx").read_bytes()
    spec = {"kind": "docx", "name": "SOP",
            "blocks": [{"type": "image", "source": "zeta-ref", "index": 1},
                       {"type": "image", "source": "alpha-ref", "index": 1}]}
    one = server.call("create_document", {
        **spec, "sources": {"zeta-ref": _source("z.docx", photo)}})
    assert one["structuredContent"]["extra"] == {
        "needed_sources": ["alpha-ref"], "kind": "missing_image"}
    none = server.call("create_document", spec)
    assert none["structuredContent"]["extra"] == {
        "needed_sources": ["alpha-ref", "zeta-ref"], "kind": "missing_image"}
    assert none["structuredContent"]["detail"] == "no file — a source is missing"


def test_a_spec_without_pictures_ignores_sources(server):
    result = server.call("create_document", {
        "kind": "docx", "name": "Plain", **_SPECS["docx"]})
    assert result["isError"] is False


@pytest.mark.parametrize("name,body,convertible", [
    ("rows.xlsx", office.xlsx_bytes([["a"], ["1"]]), True),
    ("illustrated.docx", "fixture", True),
    ("sop.pdf", office.build("pdf", "sop", _SPECS["pdf"]).body, True),
    ("len-carriers.html", "fixture", False),
    ("diagram.bin", b"\x00\x01\x02 opaque", False),
])
def test_extract_reports_convertible_and_sniffed(server, name, body, convertible):
    if body == "fixture":
        body = (FIXTURES / name).read_bytes()
    extra = server.call("extract_document", {"file": _file(name, body)}
                        )["structuredContent"]["extra"]
    assert extra["convertible"] is convertible
    assert extra["convertible"] is (office.kind_of(name) in office.READERS)
    assert extra["sniffed"] == _sniff(body, name)
