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
