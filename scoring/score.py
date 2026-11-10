"""Score PaperPilot-Bench predictions.

py scoring/score.py --tasks tasks/test.jsonl --gold gold/test_gold.jsonl \
    --preds preds.jsonl --judge ollama:qwen3.5:9b --out results.json
"""
import argparse
import json
import math
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from normalize import normalize, numbers_in, parse_number, quote_match  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TYPES = ["find_papers", "comparison_table", "citation_links", "grounded_claims", "followup_questions"]
MAX_CLAIMS, MAX_QUESTIONS, MIN_QUOTE_WORDS = 10, 5, 6
NUMERIC_TOL = 0.02
SUPPORT_SCORE = {"supported": 1.0, "partial": 0.5, "unsupported": 0.0, "error": 0.0}


def corpus_path(explicit=None):
    return Path(explicit or os.environ.get("PAPERPILOT_CORPUS") or ROOT / "corpus" / "papers.jsonl")


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class Corpus:
    def __init__(self, papers):
        self.papers = {p["id"]: p for p in papers}
        self._norm = {}

    def __contains__(self, pid):
        return pid in self.papers

    def norm_text(self, pid):
        """Normalized abstract + all sections; quotes may come from any of them.

        The title is left out: on the hard track, a titles-only agent scored 0.97
        on grounded claims by quoting titles, which proves nothing about the paper.
        """
        if pid not in self._norm:
            p = self.papers[pid]
            # "Front matter" repeats the title and author list, so it's left out too.
            parts = [p.get("abstract", "")] + [s["text"] for s in p.get("sections", []) if s["name"] != "Front matter"]
            self._norm[pid] = normalize("\n\n".join(parts))
        return self._norm[pid]


def load_corpus(path=None):
    return Corpus(read_jsonl(corpus_path(path)))


def output_ids(task_type, out):
    if task_type == "find_papers":
        return [i for i in out.get("ranked_ids") or [] if isinstance(i, str)]
    if task_type == "comparison_table":
        return [r.get("paper_id") for r in out.get("rows") or [] if isinstance(r, dict)]
    if task_type == "citation_links":
        return [i for e in out.get("edges") or [] if isinstance(e, list) for i in e]
    if task_type == "grounded_claims":
        return [c.get("paper_id") for c in out.get("claims") or [] if isinstance(c, dict)]
    return []


def answer_list(task_type, out):
    key = {"find_papers": "ranked_ids", "comparison_table": "rows", "citation_links": "edges",
           "grounded_claims": "claims", "followup_questions": "questions"}[task_type]
    return out.get(key) or []


# ---------- per-type scoring ----------

def score_find_papers(task, gold, out, ctx):
    seen, ranked = set(), []
    for pid in out.get("ranked_ids") or []:
        if pid not in seen:
            seen.add(pid)
            ranked.append(pid)
    top = ranked[:10]
    rel = {k: v for k, v in gold["relevant"].items() if v > 0}
    if not rel:
        raise ValueError(f"{task['id']}: non-trap find_papers gold has no relevant papers")
    hits = [p for p in top if p in rel]
    dcg = sum(rel.get(p, 0) / math.log2(i + 2) for i, p in enumerate(top))
    ideal = sorted(rel.values(), reverse=True)[:10]
    idcg = sum(g / math.log2(i + 2) for i, g in enumerate(ideal))
    m = {"recall@10": len(hits) / len(rel), "precision@10": len(hits) / 10, "ndcg@10": dcg / idcg}
    return m, m["ndcg@10"]


def cell_correct(col, gold_val, pred_val, setting, judge):
    """True/False, or None when only the judge could decide and it's off."""
    if pred_val is None:
        return False
    g, p = str(gold_val), str(pred_val)
    if normalize(g) in ("not_reported", "not reported"):
        return normalize(p) in ("not_reported", "not reported")
    if col["type"] == "numeric":
        gv, pv = parse_number(g), parse_number(p)
        if gv is None or pv is None:
            return False
        return pv == gv if gv == 0 else abs(pv - gv) <= NUMERIC_TOL * abs(gv)
    if normalize(g) == normalize(p):
        return True
    if col["type"] == "enum":
        return False
    if judge is None:
        return None
    return judge.text_equiv(col["name"], col.get("setting", ""), g, p).get("equivalent") is True


def score_comparison_table(task, gold, out, ctx):
    cols = {c["name"]: c for c in task["input"]["columns"]}
    pred_rows = {}
    for r in out.get("rows") or []:
        if isinstance(r, dict) and r.get("paper_id") not in pred_rows:
            pred_rows[r.get("paper_id")] = r
    correct, total, skipped = 0, 0, 0
    ev_ok, ev_total = 0, 0
    for pid, gold_cells in gold["rows"].items():
        row = pred_rows.get(pid) or {}
        cells, evidence = row.get("cells") or {}, row.get("evidence") or {}
        for name, gval in gold_cells.items():
            verdict = cell_correct(cols[name], gval, cells.get(name), cols[name].get("setting", ""), ctx["judge"])
            if verdict is None:
                skipped += 1
                continue
            total += 1
            correct += verdict
            # Evidence is checked on numeric cells only: that's where a quote can
            # be verified against the value without a judge.
            pval = cells.get(name)
            if cols[name]["type"] == "numeric" and pval is not None and parse_number(pval) is not None:
                ev_total += 1
                ev = evidence.get(name)
                if ev and pid in ctx["corpus"]:
                    text = ctx["corpus"].norm_text(pid)
                    span = quote_match(ev, text)
                    if span and parse_number(pval) in {float(n) for n in numbers_in(text[span[0]:span[1]])}:
                        ev_ok += 1
    m = {"cell_accuracy": correct / total if total else None,
         "evidence_match_rate": ev_ok / ev_total if ev_total else None,
         "text_cells_skipped": skipped}
    if gold.get("row_set_required"):
        m["row_recall"] = len(set(pred_rows) & set(gold["rows"])) / len(gold["rows"])
    return m, m["cell_accuracy"]


def score_citation_links(task, gold, out, ctx):
    allowed = set(task["input"]["paper_ids"])
    pred = {tuple(e) for e in out.get("edges") or []
            if isinstance(e, list) and len(e) == 2 and e[0] != e[1]}
    gold_edges = {tuple(e) for e in gold["edges"]}
    tp = len(pred & gold_edges)  # edges outside the input set can't be in gold, so they're FPs
    if not gold_edges:
        f1 = 1.0 if not pred else 0.0
        return {"precision": f1, "recall": f1, "f1": f1}, f1
    p = tp / len(pred) if pred else 0.0
    r = tp / len(gold_edges)
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": p, "recall": r, "f1": f1, "edges_outside_set": sum(
        1 for a, b in pred if a not in allowed or b not in allowed)}, f1


def claim_numbers_backed(claim, passage):
    """Every number in the claim appears in the passage the judge would see."""
    have = {float(n) for n in numbers_in(passage)}
    return all(float(n) in have for n in numbers_in(claim))


def score_grounded_claims(task, gold, out, ctx):
    claims = [c for c in out.get("claims") or [] if isinstance(c, dict)][:MAX_CLAIMS]
    corpus, judge = ctx["corpus"], ctx["judge"]
    valid = matched = unbacked = 0
    support = []
    for c in claims:
        pid, quote = c.get("paper_id"), c.get("quote") or ""
        if pid not in corpus:
            support.append(0.0)
            continue
        valid += 1
        text = corpus.norm_text(pid)
        span = quote_match(quote, text) if len(normalize(quote).split()) >= MIN_QUOTE_WORDS else None
        if span is None:
            support.append(0.0)
            continue
        matched += 1
        # The judge reads the paper's own text, never the agent's quote,
        # which could have been edited to fit the claim.
        passage = text[max(0, span[0] - 500):span[1] + 500]
        if not claim_numbers_backed(c.get("text", ""), passage):
            # Both candidate judges gave half credit to claims with a wrong
            # number (docs/judge_comparison.md), so numbers are checked here.
            unbacked += 1
            support.append(0.0)
        elif judge is not None:
            label = judge.claim_support(c.get("text", ""), passage).get("label", "error")
            support.append(SUPPORT_SCORE.get(label, 0.0))
    n = len(claims)
    cited = {c.get("paper_id") for c in claims}
    sup_ids = set(gold["supporting_ids"])
    m = {"n_claims": n,
         "valid_id_rate": valid / n if n else 0.0,
         "quote_match_rate": matched / n if n else 0.0,
         "unbacked_number_claims": unbacked,
         "supporting_recall": len(cited & sup_ids) / len(sup_ids) if sup_ids else None,
         "support_rate": (sum(support) / n if n else 0.0) if judge is not None else None}
    primary = None
    if m["support_rate"] is not None and m["supporting_recall"] is not None:
        primary = 0.5 * m["support_rate"] + 0.5 * m["supporting_recall"]
    return m, primary


def score_followup_questions(task, gold, out, ctx):
    qs = [q for q in out.get("questions") or [] if isinstance(q, str)][:MAX_QUESTIONS]
    judge = ctx["judge"]
    if judge is None:
        return {"n_questions": len(qs), "rubric": None}, None
    if not qs:
        return {"n_questions": 0, "rubric": 0.0}, 0.0
    titles = [ctx["corpus"].papers[p]["title"] for p in task["input"].get("paper_ids") or [] if p in ctx["corpus"]]
    scores = []
    for q in qs:
        r = judge.followup_score(task["input"].get("topic", ""), titles, q, gold.get("gap_notes", ""))
        crit = [r.get(k) for k in ("specific", "grounded", "novel")]
        scores.append(sum(crit) / 15 if all(isinstance(x, (int, float)) for x in crit) else 0.0)
    return {"n_questions": len(qs), "rubric": sum(scores) / len(scores)}, sum(scores) / len(scores)


SCORERS = {"find_papers": score_find_papers, "comparison_table": score_comparison_table,
           "citation_links": score_citation_links, "grounded_claims": score_grounded_claims,
           "followup_questions": score_followup_questions}


# ---------- aggregation ----------

def bootstrap_ci(values, n=1000, seed=0):
    if not values:
        return None
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(values) for _ in values) / len(values) for _ in range(n))
    return [round(means[int(0.025 * n)], 4), round(means[int(0.975 * n) - 1], 4)]


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def score_all(tasks, golds, preds, corpus, judge=None):
    gold_by = {g["id"]: g for g in golds}
    pred_by = {p["id"]: p for p in preds}
    ctx = {"corpus": corpus, "judge": judge}
    items = []
    for task in tasks:
        gold = gold_by[task["id"]]
        pred = pred_by.get(task["id"])
        rec = {"id": task["id"], "type": task["type"], "trap": bool(gold.get("trap")),
               "missing": pred is None, "abstained": False, "hallucinated_ids": [], "metrics": {}}
        if pred is not None:
            out = pred.get("output") or {}
            rec["abstained"] = bool(pred.get("abstain"))
            ids = [] if rec["abstained"] else output_ids(task["type"], out)
            rec["hallucinated_ids"] = sorted({i for i in ids if i not in corpus}, key=str)
        if rec["trap"]:
            empty = pred is not None and (rec["abstained"] or not answer_list(task["type"], pred.get("output") or {}))
            rec["primary"] = 1.0 if empty and not rec["hallucinated_ids"] else 0.0
        elif pred is None or rec["abstained"]:
            rec["primary"] = 0.0
        else:
            rec["metrics"], rec["primary"] = SCORERS[task["type"]](task, gold, pred.get("output") or {}, ctx)
        rec["trace"] = (pred or {}).get("trace")
        items.append(rec)

    per_type = {}
    buckets = {t: [r for r in items if r["type"] == t and not r["trap"]] for t in TYPES}
    buckets["traps"] = [r for r in items if r["trap"]]
    for name, rs in buckets.items():
        if not rs:
            continue
        prim = [r["primary"] for r in rs if r["primary"] is not None]
        keys = sorted({k for r in rs for k in r["metrics"]})
        per_type[name] = {"n": len(rs), "primary_mean": mean(prim), "primary_ci95": bootstrap_ci(prim),
                          "metrics": {k: mean([r["metrics"].get(k) for r in rs]) for k in keys}}
    traces = [r["trace"] for r in items if r["trace"]]
    trace_means = {k: mean([t.get(k) for t in traces]) for k in ("steps", "input_tokens", "output_tokens", "cost_usd")}
    return {
        "n_items": len(items),
        "hallucination_rate": sum(1 for r in items if r["hallucinated_ids"]) / len(items) if items else 0.0,
        "per_type": per_type,
        "trace_means": trace_means if traces else None,
        "macro_avg": mean([v["primary_mean"] for v in per_type.values()]),
        "judge": judge.info() if judge is not None else None,
        "items": items,
        "judge_decisions": judge.decisions if judge is not None else None,
    }


def print_table(res):
    print(f"{'bucket':<20}{'n':>4}{'primary':>10}   95% CI")
    for name, v in res["per_type"].items():
        pm = "n/a" if v["primary_mean"] is None else f"{v['primary_mean']:.3f}"
        ci = v["primary_ci95"] or "n/a"
        print(f"{name:<20}{v['n']:>4}{pm:>10}   {ci}")
    print(f"hallucination_rate: {res['hallucination_rate']:.3f}")
    if res["trace_means"]:
        print("trace means:", {k: round(v, 3) for k, v in res["trace_means"].items() if v is not None})
    if res["judge"]:
        print("judge:", res["judge"])
    ma = res["macro_avg"]
    print(f"macro_avg (secondary): {'n/a' if ma is None else f'{ma:.3f}'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--gold", required=True)
    ap.add_argument("--preds", required=True)
    ap.add_argument("--corpus", help="default: $PAPERPILOT_CORPUS, then corpus/papers.jsonl")
    ap.add_argument("--judge", default="none", help="ollama:<tag>, or none to skip judge metrics")
    ap.add_argument("--out", default="results.json")
    args = ap.parse_args()

    judge = None
    if args.judge != "none":
        from judge import Judge
        judge = Judge.from_spec(args.judge)
    res = score_all(read_jsonl(args.tasks), read_jsonl(args.gold), read_jsonl(args.preds),
                    load_corpus(args.corpus), judge)
    Path(args.out).write_text(json.dumps(res, indent=2), encoding="utf-8")
    print_table(res)
    print(f"wrote {args.out}: {res['n_items']} items")


if __name__ == "__main__":
    main()
