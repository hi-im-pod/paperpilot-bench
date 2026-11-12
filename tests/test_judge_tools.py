import csv
import json

from conftest import ROOT  # noqa: F401  (puts scoring/ on sys.path)
from judge import agreement, cohen_kappa, export_sample


def test_kappa_is_undefined_when_every_label_is_one_class():
    assert cohen_kappa(["supported"] * 5, ["supported"] * 5) is None
    assert cohen_kappa(["a", "b", "a", "b"], ["a", "b", "a", "b"]) == 1.0


def decision(claim, label):
    return {"kind": "claim_support", "inputs": {"claim": claim, "passage": "p"}, "result": {"label": label}}


def test_export_sample_merges_files_and_drops_duplicates(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps({"judge_decisions": [decision("x", "supported"), decision("y", "partial")]}))
    b.write_text(json.dumps({"judge_decisions": [decision("x", "supported"), decision("z", "unsupported")]}))
    out = tmp_path / "s.csv"
    export_sample([a, b], 10, out)
    rows = list(csv.DictReader(open(out, encoding="utf-8")))
    assert sorted(json.loads(r["inputs"])["claim"] for r in rows) == ["x", "y", "z"]
    assert set(rows[0]) == {"kind", "inputs", "judge_label", "human_label", "labeler"}


def test_agreement_filters_by_labeler(tmp_path, capsys):
    out = tmp_path / "s.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["kind", "inputs", "judge_label", "human_label", "labeler"])
        w.writerow(["claim_support", "{}", "supported", "supported", "alice"])
        w.writerow(["claim_support", "{}", "partial", "unsupported", "bob"])
    agreement(out, "alice")
    assert "agreement=1.00" in capsys.readouterr().out


def test_followup_caps():
    from judge import apply_followup_caps
    # Two questions in one can't be one experiment; no stated gap can't be fully grounded.
    assert apply_followup_caps({"gap": "none", "parts": 2, "specific": 5, "grounded": 5, "novel": 5}) == \
        {"gap": "none", "parts": 2, "specific": 3, "grounded": 3, "novel": 5}
    kept = {"gap": "reader saturates before recall", "parts": 1, "specific": 5, "grounded": 4, "novel": 4}
    assert apply_followup_caps(kept) == kept
    assert apply_followup_caps({"gap": "x", "parts": 1, "specific": 2, "grounded": 2, "novel": 2})["specific"] == 2
    err = {"specific": None, "grounded": None, "novel": None, "error": True}
    assert apply_followup_caps(err) == err


def test_prompts_load_with_notes_under_headings():
    from judge import load_prompts
    p = load_prompts()
    assert p["followup_score"].startswith("You rate one follow-up research question")
    assert '"parts"' in p["followup_score"] and p["claim_support"].startswith("You check whether a passage")
