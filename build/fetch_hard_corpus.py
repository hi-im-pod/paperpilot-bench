"""Select the hard-track corpus: recent arXiv papers a model trained before mid-2026 can't have memorized.

Writes build/hard/selected.jsonl and corpus/hard/licenses.csv. Then run
  py build/extract_text.py --track hard
to download the PDFs and build corpus/hard/papers.jsonl.

The v1 corpus is famous 2017-2023 work that frontier models know by heart: in
the v1 baselines, Claude with paper titles alone scored 0.93 against 0.97 with
the tools. This track draws only on papers first submitted from July to
October 2026, grouped into narrow subtopics so items can be written against
coherent sets of papers.
"""
import argparse
import csv
import json
import xml.etree.ElementTree as ET

from common import ROOT, arxiv_client, bare_arxiv_id, write_jsonl
from fetch_corpus import abs_page

ATOM = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
WINDOW = "submittedDate:[202607010000 TO 202610312359]"
EARLIEST = "2026-07-01"

# Subtopic -> (field, arXiv query). Kept narrow so a subtopic's papers really belong together.
SUBTOPICS = {
    "pi-defenses": ("llm_security", 'abs:"prompt injection" AND (abs:defense OR abs:defend)'),
    "reasoning-jailbreaks": ("llm_security", 'abs:jailbreak AND abs:"reasoning model"'),
    "mcp-security": ("llm_security", 'abs:"model context protocol" AND (abs:attack OR abs:security)'),
    "graph-rag": ("rag", 'abs:"graph" AND abs:"retrieval-augmented generation" AND abs:"knowledge graph"'),
    "rag-poisoning": ("rag", 'abs:"retrieval-augmented generation" AND (abs:poisoning OR abs:poisoned)'),
    "deep-research": ("rag", 'abs:"deep research" AND abs:agent'),
    "gui-agents": ("llm_agents", 'abs:"GUI agent" OR abs:"computer-use agent" OR abs:"computer use agent"'),
    "agent-memory": ("llm_agents", 'abs:memory AND abs:"LLM agents" AND abs:long-term'),
    "multi-agent": ("llm_agents", 'abs:"multi-agent" AND abs:"large language model" AND abs:collaboration'),
}
CATEGORIES = {"cs.CL", "cs.CR", "cs.AI", "cs.LG", "cs.IR", "cs.MA", "cs.HC", "cs.SE"}


def search(ax, query, n):
    text = ax.request("GET", "https://export.arxiv.org/api/query",
                      params={"search_query": f"({query}) AND {WINDOW}", "start": 0, "max_results": n,
                              "sortBy": "relevance", "sortOrder": "descending"})
    out = []
    for e in ET.fromstring(text or "<feed xmlns='http://www.w3.org/2005/Atom'/>").findall("a:entry", ATOM):
        cat = e.find("arxiv:primary_category", ATOM)
        out.append({"id": bare_arxiv_id(e.findtext("a:id", "", ATOM)),
                    "published": e.findtext("a:published", "", ATOM)[:10],
                    "primary": cat.get("term") if cat is not None else "",
                    "title": " ".join(e.findtext("a:title", "", ATOM).split())})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--per-subtopic", type=int, default=11)
    ap.add_argument("--pool", type=int, default=40, help="search results considered per subtopic")
    args = ap.parse_args()
    if (ROOT / "corpus" / "hard" / "FREEZE.json").exists():
        raise SystemExit("the hard corpus is frozen (corpus/hard/FREEZE.json); rebuild text with extract_text.py --track hard")
    ax = arxiv_client()
    chosen = {}
    for sub, (field, query) in SUBTOPICS.items():
        hits = [h for h in search(ax, query, args.pool)
                if h["published"] >= EARLIEST and h["primary"] in CATEGORIES and h["id"] not in chosen]
        for h in hits[:args.per_subtopic]:
            chosen[h["id"]] = {"subtopic": sub, "field": field}
        print(f"[{sub}] {len(hits)} eligible, kept {min(len(hits), args.per_subtopic)}")

    records, licenses, dropped = [], [], []
    print(f"fetching {len(chosen)} abstract pages (3 s apart)")
    for aid, tag in chosen.items():
        meta = abs_page(ax, aid)
        if not meta:
            dropped.append(aid)
            continue
        licenses.append((aid, meta.pop("license")))
        records.append({"id": aid, **meta, "clusters": [tag["field"]], "subtopic": tag["subtopic"]})
    out = ROOT / "build" / "hard" / "selected.jsonl"
    write_jsonl(out, records)
    (ROOT / "corpus" / "hard").mkdir(parents=True, exist_ok=True)
    with open(ROOT / "corpus" / "hard" / "licenses.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([("id", "license"), *licenses])
    print(f"wrote {out.relative_to(ROOT)}: {len(records)} papers; dropped {dropped}")


if __name__ == "__main__":
    main()
