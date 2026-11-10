"""Turn verified drafts into the task and gold files the scorer reads.

py build/assemble_gold.py
py build/assemble_gold.py --perfect-preds gold/dev_perfect_preds.jsonl --split dev

--perfect-preds writes predictions that copy the gold, quotes included. Scoring
them must give 1.0 on every deterministic metric; anything less means a gold
quote doesn't match the corpus text, and the label needs fixing.
"""
import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from common import ROOT, read_jsonl, write_jsonl

DRAFTS = ROOT / "gold" / "drafts"


def gold_for(item, d):
    t = item["type"]
    if t == "find_papers":
        grades = d["grades"]
        missing = [g["paper_id"] for g in grades if g.get("grade") is None]
        if missing:
            raise ValueError(f"{item['id']}: ungraded papers {missing}")
        relevant = {g["paper_id"]: int(g["grade"]) for g in grades if int(g["grade"]) > 0}
        if not relevant:
            # nDCG is undefined with no relevant papers; such an item is a trap and should be marked one.
            raise ValueError(f"{item['id']}: no relevant papers; mark it trap=true or rewrite the topic")
        return {"relevant": relevant, "pooled": [g["paper_id"] for g in grades]}
    if t == "comparison_table":
        rows = {pid: {col: cell["value"] for col, cell in cells.items()} for pid, cells in d["rows"].items()}
        bad = [(pid, c) for pid, r in rows.items() for c, v in r.items() if v is None]
        if bad:
            raise ValueError(f"{item['id']}: empty cells {bad}")
        return {"rows": rows, "row_set_required": item["input"].get("paper_ids") is None}
    if t == "citation_links":
        undecided = [(e["citing"], e["cited"]) for e in d["edges"] if e.get("keep") is None]
        if undecided:
            raise ValueError(f"{item['id']}: edges still need keep=true/false: {undecided}")
        return {"edges": [[e["citing"], e["cited"]] for e in d["edges"] if e["keep"]]}
    if t == "grounded_claims":
        ids = sorted({s["paper_id"] for s in d["supporting"]})
        if not ids:
            raise ValueError(f"{item['id']}: no supporting papers; mark it trap=true or rewrite the question")
        return {"supporting_ids": ids}
    if t == "followup_questions":
        return {"gap_notes": d.get("gap_notes", "")}
    raise ValueError(f"unknown type {t}")


def perfect_pred(item, d):
    t = item["type"]
    if item.get("trap"):
        return {"id": item["id"], "abstain": True, "output": {"reason": "trap"}}
    if t == "find_papers":
        g = sorted(d["grades"], key=lambda g: -int(g["grade"]))
        out = {"ranked_ids": [x["paper_id"] for x in g if int(x["grade"]) > 0]}
    elif t == "comparison_table":
        out = {"rows": [{"paper_id": pid, "cells": {c: cell["value"] for c, cell in cells.items()},
                         "evidence": {c: cell.get("quote", "") for c, cell in cells.items()}}
                        for pid, cells in d["rows"].items()]}
    elif t == "citation_links":
        out = {"edges": [[e["citing"], e["cited"]] for e in d["edges"] if e["keep"]]}
    elif t == "grounded_claims":
        out = {"answer": d.get("draft_answer", ""),
               "claims": [{"text": s.get("why", ""), "paper_id": s["paper_id"], "quote": s.get("quote", "")}
                          for s in d["supporting"]]}
    else:
        out = {"questions": []}
    return {"id": item["id"], "abstain": False, "output": out}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--perfect-preds", help="also write gold-copy predictions to this path")
    ap.add_argument("--split", default="dev", help="split for --perfect-preds")
    ap.add_argument("--items", default=str(ROOT / "tasks" / "items.jsonl"))
    ap.add_argument("--drafts", default=str(DRAFTS))
    ap.add_argument("--out", default=str(ROOT), help="root folder for the tasks/ and gold/ outputs")
    ap.add_argument("--track", choices=["v1", "hard"], default="v1",
                    help="hard writes to tasks/hard/ and gold/hard/ under --out")
    args = ap.parse_args()

    items = read_jsonl(args.items)
    drafts_dir, out = Path(args.drafts), Path(args.out)
    sub = "hard" if args.track == "hard" else ""
    tasks_out, gold_out = out / "tasks" / sub, out / "gold" / sub
    drafts = {}
    for item in items:
        if item.get("trap"):
            continue
        path = drafts_dir / f"{item['id']}.json"
        if not path.exists():
            raise SystemExit(f"{item['id']}: no draft; run draft_labels.py first")
        d = json.loads(path.read_text(encoding="utf-8"))
        if not d.get("verified_by"):
            raise SystemExit(f"{item['id']}: draft not verified (set verified_by in {path.name})")
        drafts[item["id"]] = d

    by_split = {"dev": ([], []), "test": ([], [])}
    prov, changed, reviewed = [], 0, 0
    for item in items:
        task = {k: item[k] for k in ("id", "type", "input")}
        if item.get("trap"):
            gold = {"id": item["id"], "trap": True}
        else:
            d = drafts[item["id"]]
            try:
                gold = {"id": item["id"], "trap": False, **gold_for(item, d)}
            except ValueError as e:
                raise SystemExit(f"cannot assemble: {e}")
            if item["type"] == "citation_links":
                for e in d["edges"]:
                    if e.get("needs_review"):
                        reviewed += 1
                        changed += e["keep"] != e["in_s2"]
        by_split[item["split"]][0].append(task)
        by_split[item["split"]][1].append(gold)
        d = drafts.get(item["id"], {})
        prov.append([item["id"], item["type"], item["split"], d.get("drafting_model", "hand-written"),
                     d.get("verified_by", ""), d.get("checked_by", "")])

    for split, (tasks, golds) in by_split.items():
        write_jsonl(tasks_out / f"{split}.jsonl", tasks)
        write_jsonl(gold_out / f"{split}_gold.jsonl", golds)
    with open(gold_out / "provenance.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "type", "split", "drafting_model", "verified_by", "checked_by"])
        w.writerows(prov)

    counts = Counter((i["split"], "trap" if i.get("trap") else i["type"]) for i in items)
    for split in ("dev", "test"):
        print(f"{split}: " + ", ".join(f"{t}={n}" for (s, t), n in sorted(counts.items()) if s == split))
    if reviewed:
        print(f"citation edges needing review: {reviewed}; the verifier overrode S2 on {changed} ({changed / reviewed:.0%})")
    print(f"wrote tasks/dev.jsonl, tasks/test.jsonl, gold/dev_gold.jsonl, gold/test_gold.jsonl, gold/provenance.csv under {out}")

    if args.perfect_preds:
        preds = [perfect_pred(i, drafts.get(i["id"], {})) for i in items if i["split"] == args.split]
        write_jsonl(args.perfect_preds, preds)
        print(f"wrote {args.perfect_preds}: {len(preds)} gold-copy predictions for {args.split}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
