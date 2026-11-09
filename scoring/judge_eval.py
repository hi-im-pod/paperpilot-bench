"""Compare candidate judge models on cases with known answers.

py scoring/judge_eval.py --models qwen3.5:9b gemma4:12b

Cases are in scoring/judge_eval_cases.jsonl. Claim-support passages are verbatim
from four seed-paper abstracts. The expected labels were drafted by Claude while
building the harness and still need a teammate's review. Treat this as a check
that a judge is fit to use, not as a replacement for validating it against human
labels on real benchmark outputs.
"""
import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from judge import Judge, cohen_kappa  # noqa: E402
from score import SUPPORT_SCORE, claim_numbers_backed  # noqa: E402

CASES = Path(__file__).resolve().parent / "judge_eval_cases.jsonl"


def mean3(r):
    vals = [r.get(k) for k in ("specific", "grounded", "novel")]
    return sum(vals) / 3 if all(isinstance(v, int) for v in vals) else None


def run_pass(judge, cases):
    out = {}
    for c in cases:
        i = c["inputs"]
        if c["kind"] == "claim_support":
            out[c["id"]] = judge.claim_support(i["claim"], i["passage"]).get("label")
        elif c["kind"] == "text_equiv":
            out[c["id"]] = judge.text_equiv(i["column"], i["setting"], i["gold"], i["pred"]).get("equivalent")
        else:
            better = judge.followup_score(i["topic"], i["paper_titles"], i["better"], i["gap_notes"])
            worse = judge.followup_score(i["topic"], i["paper_titles"], i["worse"], i["gap_notes"])
            out[c["id"]] = (better, worse)
    return out


def claim_stats(cs, labels):
    exp = [c["expected"] for c in cs]
    err = sum(abs(SUPPORT_SCORE[e] - SUPPORT_SCORE.get(g, 0.0)) for e, g in zip(exp, labels))
    return {"accuracy": sum(e == g for e, g in zip(exp, labels)) / len(cs), "kappa": cohen_kappa(exp, labels),
            "binary_accuracy": sum((e == "supported") == (g == "supported") for e, g in zip(exp, labels)) / len(cs),
            "score_error": err,
            "errors": dict(Counter(f"{e}->{g}" for e, g in zip(exp, labels) if e != g))}


def summarize(cases, res):
    cs = [c for c in cases if c["kind"] == "claim_support"]
    raw = [str(res[c["id"]]) for c in cs]
    # What the scorer actually awards: a claim whose numbers aren't in the passage is
    # unsupported before the judge is asked.
    checked = [lab if claim_numbers_backed(c["inputs"]["claim"], c["inputs"]["passage"]) else "unsupported"
               for c, lab in zip(cs, raw)]
    judge_only, with_check = claim_stats(cs, raw), claim_stats(cs, checked)
    te = [c for c in cases if c["kind"] == "text_equiv"]
    fq = [c for c in cases if c["kind"] == "followup_pair"]
    gaps = []
    for c in fq:
        b, w = (mean3(x) for x in res[c["id"]])
        gaps.append(None if b is None or w is None else b - w)
    return {
        **{f"claim_{k}": v for k, v in judge_only.items()},
        **{f"claim_{k}_with_number_check": v for k, v in with_check.items()},
        "false_support": [c["id"] for c, g in zip(cs, raw) if c["expected"] == "unsupported" and g == "supported"],
        "equiv_accuracy": sum(res[c["id"]] == c["expected"] for c in te) / len(te),
        "equiv_misses": [c["id"] for c in te if res[c["id"]] != c["expected"]],
        "followup_pairs_ordered": sum(g is not None and g > 0 for g in gaps) / len(fq),
        "followup_mean_gap": sum(g for g in gaps if g is not None) / max(1, sum(g is not None for g in gaps)),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", nargs="+", default=["qwen3.5:9b", "gemma4:12b"])
    ap.add_argument("--passes", type=int, default=2, help="repeat runs, to check the judge is deterministic")
    ap.add_argument("--out", default="judge_eval_results.json")
    args = ap.parse_args()
    cases = [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines() if line.strip()]

    report = {}
    for model in args.models:
        judge = Judge(model, use_cache=False)
        passes, times = [], []
        for _ in range(args.passes):
            t0 = time.time()
            passes.append(run_pass(judge, cases))
            times.append(time.time() - t0)
        first = passes[0]
        stable = sum(all(p[c["id"]] == first[c["id"]] for p in passes) for c in cases) / len(cases)
        report[model] = {"digest": judge.digest, **summarize(cases, first), "stable_across_passes": stable,
                         "json_errors": judge.errors, "seconds_per_call": round(sum(times) / judge.calls, 2),
                         "answers": {k: v for k, v in first.items()}}
        print(f"{model}: done in {sum(times):.0f}s")

    keys = ["claim_accuracy", "claim_kappa", "claim_binary_accuracy", "claim_score_error",
            "claim_accuracy_with_number_check", "claim_kappa_with_number_check",
            "claim_binary_accuracy_with_number_check", "claim_score_error_with_number_check",
            "equiv_accuracy", "followup_pairs_ordered", "followup_mean_gap", "stable_across_passes",
            "json_errors", "seconds_per_call"]
    print(f"\n{'metric':<40}" + "".join(f"{m:>16}" for m in args.models))
    for k in keys:
        row = [report[m][k] for m in args.models]
        print(f"{k:<40}" + "".join(f"{v:>16.3f}" if isinstance(v, float) else f"{v:>16}" for v in row))
    for m in args.models:
        print(f"\n{m}: false support (unsupported judged supported): {report[m]['false_support']}")
        print(f"{m}: claim errors {report[m]['claim_errors']}; with number check {report[m]['claim_errors_with_number_check']}")
        print(f"{m}: equivalence misses {report[m]['equiv_misses']}")
    Path(args.out).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
