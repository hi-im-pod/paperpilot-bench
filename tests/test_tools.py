import json

import pytest
from conftest import A, B, C, ROOT

import corpus_tools as ct


def test_search_finds_the_right_paper():
    hits = ct.search("dual encoder dense index wikipedia passages", k=3)
    assert hits[0]["paper_id"] == B
    assert set(hits[0]) == {"paper_id", "title", "section", "snippet", "score"}


def test_search_skips_references_sections():
    # "Unrelated Book" only appears in reference lists.
    assert ct.search("unrelated book") == []


def test_read_section_and_unknown_id():
    assert "88.0%" in ct.read(A, "Results")
    assert "88.0%" in ct.read(A, "4 Results")
    assert "FIXTURE: Paper B" in ct.read(A, "References")
    with pytest.raises(KeyError):
        ct.read("9999.99999")
    with pytest.raises(KeyError):
        ct.read(A, "No Such Section")


def test_metadata_has_no_references_or_clusters():
    meta = ct.get_metadata(C)
    assert set(meta) == {"paper_id", "title", "authors", "year", "abstract"}


def test_list_sections():
    assert ct.list_sections(B) == ["Abstract", "3 Method", "References"]


def test_call_tool_returns_errors_as_text():
    assert ct.call_tool("read", {"paper_id": "9999.99999"}).startswith("error:")
    assert json.loads(ct.call_tool("get_metadata", {"paper_id": A}))["paper_id"] == A


def test_tool_schemas_match_functions():
    schemas = json.loads((ROOT / "tools" / "tool_schemas.json").read_text(encoding="utf-8"))
    assert {s["name"] for s in schemas} == set(ct.TOOLS)


def test_corpus_checksum_ignores_line_endings(tmp_path):
    # A Windows build wrote CRLF; Linux and Docker write LF. Same text, same checksum.
    from corpus_tools import corpus_sha256
    lf, crlf = tmp_path / "lf.jsonl", tmp_path / "crlf.jsonl"
    lf.write_bytes(b'{"id": "a"}\n{"id": "b"}\n')
    crlf.write_bytes(b'{"id": "a"}\r\n{"id": "b"}\r\n')
    assert corpus_sha256(lf) == corpus_sha256(crlf)
    other = tmp_path / "other.jsonl"
    other.write_bytes(b'{"id": "a"}\n{"id": "c"}\n')
    assert corpus_sha256(other) != corpus_sha256(lf)


def test_build_writes_lf(tmp_path):
    import sys
    sys.path.insert(0, str(ROOT / "build"))
    from common import write_jsonl
    write_jsonl(tmp_path / "x.jsonl", [{"id": "a"}, {"id": "b"}])
    assert b"\r" not in (tmp_path / "x.jsonl").read_bytes()
