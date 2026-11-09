import csv
import json
import sys

from conftest import ROOT

sys.path.insert(0, str(ROOT / "build"))
import apply_reviews  # noqa: E402


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def test_reviews_become_labels_report_and_checked_by(tmp_path, monkeypatch):
    csv_path, report, drafts = tmp_path / "jv.csv", tmp_path / "report.md", tmp_path / "drafts"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["kind", "inputs", "judge_label", "human_label", "labeler"])
        w.writerow(["claim_support", '{"claim": "c"}', "supported", "supported", "claude-session (stand-in, not human)"])
    write(drafts / "fp-01.json", {"id": "fp-01", "checked_by": None})
    write(drafts / "ct-01.json", {"id": "ct-01", "checked_by": None})
    monkeypatch.setattr(apply_reviews, "CSV_PATH", csv_path)
    monkeypatch.setattr(apply_reviews, "REPORT", report)
    monkeypatch.setattr(apply_reviews, "DRAFTS", drafts)

    export = tmp_path / "export"
    write(export / "items" / "judge-00.json", {"source": "judge", "kind": "claim_support", "csv_row": 0})
    write(export / "items" / "gold-fp-01.json", {"source": "gold", "item_id": "fp-01", "task_type": "find_papers",
                                                  "papers": [{"paper_id": "A", "claude": 2}, {"paper_id": "B", "claude": 0}]})
    write(export / "items" / "gold-ct-01.json", {"source": "gold", "item_id": "ct-01", "task_type": "comparison_table",
                                                  "cells": [{"paper_id": "A", "column": "x", "claude": "88"}]})
    write(export / "reviews" / "u_alice.json", {"verdicts": {
        "judge-00": {"label": "partial"},
        "gold-fp-01": {"grades": {"A": 2, "B": 0}},
        "gold-ct-01": {"cells": {"A|x": "56"}, "note": "Table 1, individual column"}}})
    names = tmp_path / "names.json"
    names.write_text(json.dumps({"u_alice": "Alice"}), encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["apply_reviews.py", "--export", str(export), "--names", str(names)])
    apply_reviews.main()

    rows = list(csv.DictReader(open(csv_path, encoding="utf-8")))
    assert [(r["labeler"], r["human_label"]) for r in rows] == [
        ("claude-session (stand-in, not human)", "supported"), ("Alice", "partial")]
    assert json.loads((drafts / "fp-01.json").read_text())["checked_by"] == "Alice"
    assert json.loads((drafts / "ct-01.json").read_text())["checked_by"] is None
    text = report.read_text(encoding="utf-8")
    assert "'88' -> '56'" in text and "confirmed Claude's label" in text

    # Running again replaces Alice's rows instead of duplicating them.
    apply_reviews.main()
    assert len(list(csv.DictReader(open(csv_path, encoding="utf-8")))) == 2
