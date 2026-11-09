"""Build the documents the label-review page shows: gold drafts marked for a second check, plus judge decisions.

py build/review_items.py --out <dir>

Writes one JSON file per review item into <dir>, ready to load into the review
page's `items` collection. Gold items carry Claude's label for the reviewer to
confirm or fix. Judge items leave the judge's answer out so the reviewer labels blind.
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

from common import ROOT, read_jsonl

sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "scoring")]
import corpus_tools  # noqa: E402
from normalize import normalize  # noqa: E402

ABSTRACT_CHARS = 1200
PASSAGE_CHARS = 1600


def arxiv(pid):
    return f"https://arxiv.org/abs/{pid}"


def paper_card(papers, pid, abstract=True):
    p = papers[pid]
    card = {"paper_id": pid, "title": p["title"], "url": arxiv(pid), "year": p.get("year")}
    if abstract:
        card["abstract"] = (p.get("abstract") or "")[:ABSTRACT_CHARS]
    return card


def reference_line(citing, cited, papers):
    """The stretch of the citing paper's reference list that names the cited paper, if any."""
    try:
        refs = " ".join(corpus_tools.read(citing, "References").split())
    except KeyError:
        return ""
    m = re.search(rf"(?<![\d.]){re.escape(cited)}(?!\d)", refs)
    if not m:
        key = papers[cited]["title"].split(":")[0][:40]
        i = refs.lower().find(key.lower())
        if i < 0:
            return ""
        return refs[max(0, i - 160):i + 220]
    return refs[max(0, m.start() - 220):m.end() + 60]


def gold_items(papers, drafts_dir, tasks):
    out = []
    for path in sorted(drafts_dir.glob("*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        if not d.get("second_check_requested"):
            continue
        t, inp = d["type"], d["input"]
        base = {"id": f"gold-{d['id']}", "source": "gold", "item_id": d["id"], "task_type": t, "input": inp}
        if t == "find_papers":
            base["papers"] = [{**paper_card(papers, g["paper_id"]), "claude": g["grade"]} for g in d["grades"]]
        elif t == "comparison_table":
            cols = {c["name"]: c for c in inp["columns"]}
            base["cells"] = [{"paper_id": pid, "title": papers[pid]["title"], "url": arxiv(pid), "column": col,
                              "type": cols[col]["type"], "setting": cols[col].get("setting", ""),
                              "allowed": cols[col].get("allowed"), "claude": c["value"], "quote": c.get("quote", ""),
                              "note": c.get("note", "")}
                             for pid, row in d["rows"].items() for col, c in row.items()]
        elif t == "citation_links":
            base["papers"] = [paper_card(papers, pid, abstract=False) for pid in inp["paper_ids"]]
            base["edges"] = [{"citing": e["citing"], "cited": e["cited"], "claude": e["keep"],
                              "in_s2": e["in_s2"], "in_reference_list": e["in_reference_list"],
                              "evidence": reference_line(e["citing"], e["cited"], papers)} for e in d["edges"]]
        elif t == "grounded_claims":
            base["supporting"] = [{**paper_card(papers, s["paper_id"], abstract=False), "quote": s["quote"],
                                   "why": s.get("why", ""), "claude": True} for s in d["supporting"]]
            base["draft_answer"] = d.get("draft_answer", "")
        elif t == "followup_questions":
            base["papers"] = [paper_card(papers, pid) for pid in inp["paper_ids"]]
            base["gap_notes"] = d.get("gap_notes", "")
            base["gaps"] = d.get("gaps", [])
        out.append(base)
    return out


def judge_items(csv_path):
    out = []
    for i, r in enumerate(csv.DictReader(open(csv_path, encoding="utf-8"))):
        x = json.loads(r["inputs"])
        item = {"id": f"judge-{i:02d}", "source": "judge", "kind": r["kind"], "csv_row": i}
        if r["kind"] == "claim_support":
            item.update(claim=x["claim"], passage=x["passage"][:PASSAGE_CHARS])
        elif r["kind"] == "text_equiv":
            item.update(column=x["column"], setting=x.get("setting", ""), gold=x["gold"], pred=x["pred"])
        else:
            item.update(topic=x["topic"], paper_titles=x["paper_titles"], gap_notes=x["gap_notes"], question=x["question"])
        out.append(item)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--drafts", default=str(ROOT / "gold" / "drafts"))
    ap.add_argument("--judge-csv", default=str(ROOT / "docs" / "judge_validation.csv"))
    args = ap.parse_args()
    papers = corpus_tools._state()[0]
    tasks = {t["id"]: t for t in read_jsonl(ROOT / "tasks" / "items.jsonl")}
    items = gold_items(papers, Path(args.drafts), tasks) + judge_items(args.judge_csv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for n, item in enumerate(items):
        item["order"] = n
        (out / f"{item['id']}.json").write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(items)} review items to {out} "
          f"({sum(i['source'] == 'gold' for i in items)} gold, {sum(i['source'] == 'judge' for i in items)} judge)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
