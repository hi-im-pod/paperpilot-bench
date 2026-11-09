import copy
import json
import subprocess
import sys
import zipfile

from conftest import A, B, C, FIXTURE_CORPUS, GOLD, QUOTE_A, ROOT, TASKS, perfect_preds
from score import score_all


def run(preds, corpus, tasks=TASKS, gold=GOLD):
    return score_all(tasks, gold, preds, corpus, judge=None)


def item(results, item_id):
    return next(r for r in results["items"] if r["id"] == item_id)


def with_output(item_id, output, abstain=False):
    preds = perfect_preds()
    for p in preds:
        if p["id"] == item_id:
            p["output"], p["abstain"] = output, abstain
    return preds


def test_perfect_predictions_score_one(corpus):
    res = run(perfect_preds(), corpus)
    fp = item(res, "fp-1")["metrics"]
    assert fp["recall@10"] == fp["ndcg@10"] == 1.0
    assert item(res, "ct-1")["metrics"]["cell_accuracy"] == 1.0
    assert item(res, "ct-1")["metrics"]["evidence_match_rate"] == 1.0
    assert item(res, "cl-1")["metrics"]["f1"] == 1.0
    gc = item(res, "gc-1")["metrics"]
    assert gc["valid_id_rate"] == gc["quote_match_rate"] == gc["supporting_recall"] == 1.0
    assert gc["support_rate"] is None  # judge-only, skipped with --judge none
    assert item(res, "trap-1")["primary"] == 1.0
    assert res["hallucination_rate"] == 0.0


def test_empty_predictions_score_zero(corpus):
    empty = [{"id": t["id"], "abstain": False, "output": {}} for t in TASKS]
    res = run(empty, corpus)
    for r in res["items"]:
        if r["id"] in ("fu-1", "trap-1"):
            continue
        assert r["primary"] in (0.0, None), r
    assert item(res, "fp-1")["primary"] == 0.0
    assert item(res, "cl-1")["primary"] == 0.0


def test_missing_prediction_scores_zero(corpus):
    preds = [p for p in perfect_preds() if p["id"] != "fp-1"]
    assert item(run(preds, corpus), "fp-1")["primary"] == 0.0


def test_made_up_id_counts_as_hallucination(corpus):
    preds = with_output("cl-1", {"edges": [[A, B], [C, A], [C, "9999.99999"]]})
    res = run(preds, corpus)
    assert res["hallucination_rate"] > 0
    cl = item(res, "cl-1")
    assert cl["hallucinated_ids"] == ["9999.99999"]
    assert cl["metrics"]["f1"] < 1.0


def test_trap_abstain_scores_one_and_returned_id_scores_zero(corpus):
    assert item(run(perfect_preds(), corpus), "trap-1")["primary"] == 1.0
    empty_list = with_output("trap-1", {"ranked_ids": []})
    assert item(run(empty_list, corpus), "trap-1")["primary"] == 1.0
    answered = with_output("trap-1", {"ranked_ids": [B]})
    assert item(run(answered, corpus), "trap-1")["primary"] == 0.0


def claim_preds(quote, paper_id=A):
    return with_output("gc-1", {"answer": "x", "claims": [
        {"text": "The attack works.", "paper_id": paper_id, "quote": quote}]})


def test_quote_with_ligature_and_line_break_matches(corpus):
    # The paper text has "modiﬁcation" and "adver-\nsarial".
    quote = "The adversarial suffix transfers across models without any modification to the prompt."
    res = run(claim_preds(quote), corpus)
    assert item(res, "gc-1")["metrics"]["quote_match_rate"] == 1.0


def test_four_word_quote_fails(corpus):
    res = run(claim_preds("greedy coordinate search ."), corpus)
    assert item(res, "gc-1")["metrics"]["quote_match_rate"] == 0.0


def test_one_changed_digit_fails(corpus):
    res = run(claim_preds(QUOTE_A.replace("88.0", "83.0")), corpus)
    assert item(res, "gc-1")["metrics"]["quote_match_rate"] == 0.0


def test_quote_from_wrong_paper_fails(corpus):
    res = run(claim_preds(QUOTE_A, paper_id=B), corpus)
    gc = item(res, "gc-1")["metrics"]
    assert gc["valid_id_rate"] == 1.0 and gc["quote_match_rate"] == 0.0


def test_bare_number_row_evidence_passes(corpus):
    preds = perfect_preds()
    preds[1]["output"]["rows"][0]["cells"]["headline_number"] = "45.1"
    preds[1]["output"]["rows"][0]["evidence"]["headline_number"] = "72.3 45.1 12.0"
    res = run(preds, corpus)
    ct = item(res, "ct-1")["metrics"]
    assert ct["evidence_match_rate"] == 1.0
    assert ct["cell_accuracy"] == 0.75  # 45.1 is not the gold 88.0


def test_numeric_tolerance(corpus):
    def acc(value):
        preds = perfect_preds()
        preds[1]["output"]["rows"][0]["cells"]["headline_number"] = value
        return item(run(preds, corpus), "ct-1")["metrics"]["cell_accuracy"]
    assert acc("89.5") == 1.0   # 1.7% off
    assert acc("90.7") == 0.75  # 3.1% off
    assert acc("88.0%") == 1.0


def test_find_papers_metrics(corpus):
    preds = with_output("fp-1", {"ranked_ids": [A, B, B]})
    fp = item(run(preds, corpus), "fp-1")["metrics"]
    assert fp["recall@10"] == 0.5
    assert fp["precision@10"] == 0.1
    assert 0 < fp["ndcg@10"] < 1


def test_citation_edges_outside_set_are_false_positives(corpus):
    tasks = copy.deepcopy(TASKS)
    tasks[2]["input"]["paper_ids"] = [A, B]
    gold = copy.deepcopy(GOLD)
    gold[2]["edges"] = [[A, B]]
    preds = with_output("cl-1", {"edges": [[A, B], [C, A], [A, A]]})
    cl = item(run(preds, corpus, tasks, gold), "cl-1")["metrics"]
    assert cl["precision"] == 0.5 and cl["recall"] == 1.0


def test_aggregates_have_bootstrap_ci(corpus):
    res = run(perfect_preds(), corpus)
    fp = res["per_type"]["find_papers"]
    assert fp["primary_mean"] == 1.0 and fp["primary_ci95"] == [1.0, 1.0]
    assert res["per_type"]["traps"]["primary_mean"] == 1.0


def test_cli_end_to_end(tmp_path):
    def dump(name, rows):
        p = tmp_path / name
        p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
        return p
    out = tmp_path / "results.json"
    cmd = [sys.executable, str(ROOT / "scoring" / "score.py"),
           "--tasks", str(dump("t.jsonl", TASKS)), "--gold", str(dump("g.jsonl", GOLD)),
           "--preds", str(dump("p.jsonl", perfect_preds())), "--corpus", str(FIXTURE_CORPUS),
           "--judge", "none", "--out", str(out)]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(out.read_text(encoding="utf-8"))["hallucination_rate"] == 0.0


def test_release_zip_excludes_held_back_files(tmp_path):
    from make_release import EXCLUDED, build_release
    repo = tmp_path / "repo"
    files = {
        "corpus/papers.jsonl": FIXTURE_CORPUS.read_text(encoding="utf-8"),
        "tools/corpus_tools.py": "", "scoring/score.py": "", "baselines/llm.py": "",
        "tasks/dev.jsonl": "", "tasks/test.jsonl": "", "tasks/items.jsonl": "secret",
        "tasks/schemas/find_papers.json": "{}",
        "gold/dev_gold.jsonl": "", "gold/test_gold.jsonl": "secret",
        "gold/citations_s2.jsonl": "secret", "gold/provenance.csv": "secret",
        "gold/drafts/fp-1.json": "secret", "build/seeds.json": "secret",
        "scoring/.judge_cache.jsonl": "secret",
        "prompts/agent.md": "", "prompts/judge.md": "", "prompts/builder.md": "",
        "requirements.txt": "", "README.md": "",
    }
    for rel, text in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")
    zpath = build_release(repo, tmp_path / "out.zip")
    with zipfile.ZipFile(zpath) as z:
        names = set(z.namelist())
        assert not any(n.startswith(tuple(EXCLUDED)) for n in names), names
        assert "gold/dev_gold.jsonl" in names and "corpus/papers.jsonl" in names
        assert '"clusters"' not in z.read("corpus/papers.jsonl").decode("utf-8")


class AlwaysSupported:
    """Stub judge that approves everything, so any rejection comes from the scorer."""

    def __init__(self):
        self.decisions = []

    def claim_support(self, claim, passage):
        self.decisions.append(claim)
        return {"label": "supported"}

    def info(self):
        return {"model": "stub"}


def claim_with_text(text):
    return with_output("gc-1", {"answer": "x", "claims": [{"text": text, "paper_id": A, "quote": QUOTE_A}]})


def test_claim_with_number_missing_from_passage_scores_zero_without_asking_judge(corpus):
    judge = AlwaysSupported()
    res = score_all(TASKS[3:4], GOLD[3:4], claim_with_text("The attack reaches 83.0% attack success rate."),
                    corpus, judge=judge)
    gc = item(res, "gc-1")["metrics"]
    assert gc["quote_match_rate"] == 1.0  # the quote itself is fine
    assert gc["unbacked_number_claims"] == 1 and gc["support_rate"] == 0.0
    assert judge.decisions == []


def test_claim_with_backed_numbers_goes_to_judge(corpus):
    judge = AlwaysSupported()
    res = score_all(TASKS[3:4], GOLD[3:4], claim_with_text("The attack reaches 88% attack success rate."),
                    corpus, judge=judge)
    gc = item(res, "gc-1")["metrics"]
    assert gc["unbacked_number_claims"] == 0 and gc["support_rate"] == 1.0
    assert len(judge.decisions) == 1
