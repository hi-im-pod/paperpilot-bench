"""Fold reviews from the label-review page back into the repo.

1. Export the page's data with Claude Code's ArtifactData tool:
   list collection "reviews" (and "items") with out_dir=<dir>
2. py build/apply_reviews.py --export <dir> [--names names.json]

Judge labels go into docs/judge_validation.csv, one row per reviewer per
decision, with the reviewer in `labeler`. Gold verdicts are compared with
Claude's labels: an item a reviewer confirmed unchanged gets `checked_by`, and
every change is listed in docs/review_report.md for a person to apply. Gold
isn't edited automatically, because two reviewers can disagree.

--names maps reviewer ids to display names (from ArtifactData's profiles action).
"""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from common import ROOT

CSV_PATH = ROOT / "docs" / "judge_validation.csv"
REPORT = ROOT / "docs" / "review_report.md"
DRAFTS = ROOT / "gold" / "drafts"


def load_docs(folder):
    docs = {}
    for p in sorted(Path(folder).glob("*.json")):
        raw = json.loads(p.read_text(encoding="utf-8"))
        # ArtifactData's out_dir files hold the document body; tolerate a {"data": ...} wrapper too.
        docs[p.stem] = raw.get("data", raw) if isinstance(raw, dict) else raw
    return docs


def gold_changes(item, v):
    """List the reviewer's departures from Claude's label for one gold item."""
    t, out = item["task_type"], []
    if t == "find_papers":
        claude = {p["paper_id"]: p["claude"] for p in item["papers"]}
        out = [f"{pid}: grade {claude[pid]} -> {g}" for pid, g in (v.get("grades") or {}).items() if claude.get(pid) != g]
    elif t == "comparison_table":
        claude = {f"{c['paper_id']}|{c['column']}": c["claude"] for c in item["cells"]}
        out = [f"{k}: {claude[k]!r} -> {val!r}" for k, val in (v.get("cells") or {}).items() if str(claude.get(k)) != val]
    elif t == "citation_links":
        claude = {f"{e['citing']}>{e['cited']}": e["claude"] for e in item["edges"]}
        out = [f"{k}: {'cites' if claude[k] else 'no'} -> {'cites' if val else 'no'}" for k, val in (v.get("edges") or {}).items() if claude.get(k) != val]
    elif t == "grounded_claims":
        out = [f"{pid}: drop from supporting" for pid, keep in (v.get("supporting") or {}).items() if not keep]
    elif t == "followup_questions" and v.get("ok") == "no":
        out = ["gap notes need changes"]
    if v.get("missing"):
        out.append(f"missing: {v['missing']}")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export", required=True, help="the out_dir ArtifactData wrote; holds items/ and reviews/")
    ap.add_argument("--names", help="JSON map of reviewer id -> display name")
    args = ap.parse_args()
    export = Path(args.export)
    items = load_docs(export / "items")
    reviews = load_docs(export / "reviews")
    names = json.loads(Path(args.names).read_text(encoding="utf-8")) if args.names else {}
    who = lambda rid: names.get(rid) or rid

    # Judge labels: replace any earlier rows from the same reviewer, keep everything else.
    rows = list(csv.DictReader(open(CSV_PATH, encoding="utf-8")))
    base = {}
    for r in rows:
        base.setdefault((r["kind"], r["inputs"]), r)
    by_row = list(dict.fromkeys((r["kind"], r["inputs"]) for r in rows))
    reviewers = {who(rid) for rid in reviews}
    kept = [r for r in rows if r.get("labeler", "") not in reviewers]
    added = 0
    for rid, doc in reviews.items():
        for item_id, v in (doc.get("verdicts") or {}).items():
            item = items.get(item_id)
            if not item or item.get("source") != "judge" or not v.get("label"):
                continue
            key = by_row[item["csv_row"]]
            kept.append({**base[key], "human_label": v["label"], "labeler": who(rid)})
            added += 1
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["kind", "inputs", "judge_label", "human_label", "labeler"])
        w.writeheader()
        w.writerows(kept)

    # Gold: confirmations become checked_by; changes go to the report.
    lines = ["# Label review report", "", f"Reviewers: {', '.join(sorted(reviewers)) or 'none yet'}.", ""]
    confirmed = defaultdict(list)
    for item_id, item in sorted(items.items()):
        if item.get("source") != "gold":
            continue
        verdicts = {who(rid): d["verdicts"][item_id] for rid, d in reviews.items() if item_id in (d.get("verdicts") or {})}
        lines.append(f"## {item['item_id']} ({item['task_type']})")
        if not verdicts:
            lines += ["Not reviewed yet.", ""]
            continue
        for name, v in verdicts.items():
            changes = gold_changes(item, v)
            if changes:
                lines.append(f"- **{name}** changed {len(changes)}: " + "; ".join(changes))
            else:
                lines.append(f"- **{name}** confirmed Claude's label.")
                confirmed[item["item_id"]].append(name)
            if v.get("note"):
                lines.append(f"  - Note: {v['note']}")
        lines.append("")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for item_id, people in confirmed.items():
        path = DRAFTS / f"{item_id}.json"
        d = json.loads(path.read_text(encoding="utf-8"))
        d["checked_by"] = ", ".join(sorted(set(people)))
        path.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"judge labels added: {added}; gold items confirmed: {len(confirmed)}; report: {REPORT}")
    print("next: py scoring/judge.py --agreement docs/judge_validation.csv --labeler <name>")


if __name__ == "__main__":
    main()
