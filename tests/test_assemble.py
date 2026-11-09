import json
import subprocess
import sys

from conftest import A, B, C, FIXTURE_CORPUS, QUOTE_A, ROOT

ITEMS = [
    {"id": "fp-1", "type": "find_papers", "split": "dev", "trap": False, "input": {"topic": "retrieval"}},
    {"id": "ct-1", "type": "comparison_table", "split": "dev", "trap": False, "input": {
        "topic": "t", "paper_ids": [A], "columns": [{"name": "asr", "type": "numeric", "unit": "percent", "setting": "s"}]}},
    {"id": "cl-1", "type": "citation_links", "split": "dev", "trap": False, "input": {"paper_ids": [A, B, C]}},
    {"id": "gc-1", "type": "grounded_claims", "split": "test", "trap": False, "input": {"question": "q"}},
    {"id": "trap-1", "type": "find_papers", "split": "dev", "trap": True, "input": {"topic": "protein folding"}},
]
DRAFTS = {
    "fp-1": {"grades": [{"paper_id": B, "grade": 2}, {"paper_id": C, "grade": 1}, {"paper_id": A, "grade": 0}]},
    "ct-1": {"rows": {A: {"asr": {"value": "88.0", "quote": QUOTE_A}}}},
    "cl-1": {"edges": [
        {"citing": A, "cited": B, "in_s2": True, "in_reference_list": True, "needs_review": False, "keep": True},
        {"citing": C, "cited": A, "in_s2": False, "in_reference_list": True, "needs_review": True, "keep": True},
        {"citing": C, "cited": B, "in_s2": True, "in_reference_list": False, "needs_review": True, "keep": False}]},
    "gc-1": {"supporting": [{"paper_id": A, "quote": QUOTE_A, "why": "The attack reaches 88.0%."}]},
}


def setup(tmp_path, verified=True):
    items = tmp_path / "items.jsonl"
    items.write_text("\n".join(json.dumps(i) for i in ITEMS), encoding="utf-8")
    drafts = tmp_path / "drafts"
    drafts.mkdir()
    for item in ITEMS:
        if item["id"] in DRAFTS:
            d = {"id": item["id"], "type": item["type"], "input": item["input"], **DRAFTS[item["id"]],
                 "drafting_model": "fixture", "verified_by": "tester" if verified else None, "checked_by": None}
            (drafts / f"{item['id']}.json").write_text(json.dumps(d), encoding="utf-8")
    return items, drafts


def assemble(tmp_path, items, drafts, *extra):
    cmd = [sys.executable, str(ROOT / "build" / "assemble_gold.py"), "--items", str(items),
           "--drafts", str(drafts), "--out", str(tmp_path / "out"), *extra]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")


def test_unverified_drafts_are_refused(tmp_path):
    items, drafts = setup(tmp_path, verified=False)
    proc = assemble(tmp_path, items, drafts)
    assert proc.returncode != 0 and "not verified" in (proc.stdout + proc.stderr)


def test_assembled_gold_and_gold_copy_predictions_score_one(tmp_path):
    items, drafts = setup(tmp_path)
    preds = tmp_path / "perfect.jsonl"
    proc = assemble(tmp_path, items, drafts, "--perfect-preds", str(preds), "--split", "dev")
    assert proc.returncode == 0, proc.stderr
    out = tmp_path / "out"
    tasks = [json.loads(line) for line in (out / "tasks" / "dev.jsonl").read_text(encoding="utf-8").splitlines()]
    assert all("trap" not in t and "split" not in t for t in tasks)
    gold = {g["id"]: g for g in map(json.loads, (out / "gold" / "dev_gold.jsonl").read_text(encoding="utf-8").splitlines())}
    assert gold["fp-1"]["relevant"] == {B: 2, C: 1}
    assert gold["cl-1"]["edges"] == [[A, B], [C, A]]
    assert gold["trap-1"] == {"id": "trap-1", "trap": True}
    assert "gc-1" not in gold  # it's in test

    sys.path.insert(0, str(ROOT / "scoring"))
    from score import load_corpus, read_jsonl, score_all
    res = score_all(read_jsonl(out / "tasks" / "dev.jsonl"), read_jsonl(out / "gold" / "dev_gold.jsonl"),
                    read_jsonl(preds), load_corpus(FIXTURE_CORPUS), judge=None)
    for r in res["items"]:
        assert r["primary"] == 1.0, r
        assert r["metrics"].get("evidence_match_rate") in (None, 1.0), r
