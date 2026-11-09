import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_CORPUS = ROOT / "tests" / "fixtures" / "papers.jsonl"
# The tools and the scorer resolve the corpus from this variable, so tests never touch the real one.
os.environ["PAPERPILOT_CORPUS"] = str(FIXTURE_CORPUS)
for sub in ("scoring", "tools", "build"):
    sys.path.insert(0, str(ROOT / sub))

A, B, C = "0000.00001", "0000.00002", "0000.00003"

TASKS = [
    {"id": "fp-1", "type": "find_papers", "input": {"topic": "retrieval augmented generation"}},
    {"id": "ct-1", "type": "comparison_table", "input": {
        "topic": "fixture headline numbers", "paper_ids": [A, B],
        "columns": [
            {"name": "headline_number", "type": "numeric", "unit": "as reported", "setting": "main result"},
            {"name": "family", "type": "enum", "allowed": ["attack", "retrieval", "agent"]},
        ]}},
    {"id": "cl-1", "type": "citation_links", "input": {"paper_ids": [A, B, C]}},
    {"id": "gc-1", "type": "grounded_claims", "input": {"question": "How well does the fixture suffix attack work?"}},
    {"id": "fu-1", "type": "followup_questions", "input": {"topic": "fixture attacks", "paper_ids": [A]}},
    {"id": "trap-1", "type": "find_papers", "input": {"topic": "protein folding with diffusion models"}},
]

GOLD = [
    {"id": "fp-1", "trap": False, "relevant": {B: 2, C: 1}, "pooled": [A, B, C]},
    {"id": "ct-1", "trap": False, "row_set_required": False, "rows": {
        A: {"headline_number": "88.0", "family": "attack"},
        B: {"headline_number": "21", "family": "retrieval"}}},
    {"id": "cl-1", "trap": False, "edges": [[A, B], [C, A], [C, B]]},
    {"id": "gc-1", "trap": False, "supporting_ids": [A]},
    {"id": "fu-1", "trap": False, "gap_notes": "Fixture gap: no defenses evaluated."},
    {"id": "trap-1", "trap": True},
]

QUOTE_A = "the attack reaches an attack success rate of 88.0% against the fixture chat model"


def perfect_preds():
    return [
        {"id": "fp-1", "abstain": False, "output": {"ranked_ids": [B, C]}},
        {"id": "ct-1", "abstain": False, "output": {"rows": [
            {"paper_id": A, "cells": {"headline_number": "88.0", "family": "attack"},
             "evidence": {"headline_number": QUOTE_A}},
            {"paper_id": B, "cells": {"headline_number": "21", "family": "retrieval"},
             "evidence": {"headline_number": "a wikipedia index of 21 million passages"}}]}},
        {"id": "cl-1", "abstain": False, "output": {"edges": [[A, B], [C, A], [C, B]]}},
        {"id": "gc-1", "abstain": False, "output": {"answer": "It reaches 88.0%.", "claims": [
            {"text": "The suffix attack reaches 88.0% attack success rate.", "paper_id": A, "quote": QUOTE_A}]}},
        {"id": "fu-1", "abstain": False, "output": {"questions": ["Does the fixture defense hold under adaptive attacks?"]}},
        {"id": "trap-1", "abstain": True, "output": {"reason": "No paper in the library covers protein folding."}},
    ]


@pytest.fixture
def corpus():
    from score import load_corpus
    return load_corpus(FIXTURE_CORPUS)
