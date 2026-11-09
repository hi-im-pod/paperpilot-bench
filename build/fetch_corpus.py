"""Select the corpus by growing each cluster outward from its seed papers.

Writes build/selected.jsonl (metadata for extract_text.py), gold/citations_s2.jsonl
(the citation answer key), and corpus/licenses.csv.
"""
import argparse
import html
import csv
import json
import re
from collections import defaultdict

from common import ROOT, arxiv_client, bare_arxiv_id, read_jsonl, s2_client, write_jsonl

S2 = "https://api.semanticscholar.org/graph/v1"
NEIGHBOR_FIELDS = "externalIds,title,year,citationCount"


def arxiv_of(paper):
    ext = (paper or {}).get("externalIds") or {}
    return bare_arxiv_id(ext["ArXiv"]) if ext.get("ArXiv") else None


def neighbors(s2, arxiv_id, kind, pages):
    """References or citations of one paper, as (arxiv_id, citationCount) pairs."""
    key = "citedPaper" if kind == "references" else "citingPaper"
    out = []
    for page in range(pages):
        text = s2.request("GET", f"{S2}/paper/arXiv:{arxiv_id}/{kind}",
                          params={"fields": NEIGHBOR_FIELDS, "limit": 1000, "offset": page * 1000})
        if not text:
            break
        body = json.loads(text)
        for row in body.get("data") or []:
            p = row.get(key) or {}
            aid = arxiv_of(p)
            if aid:
                out.append((aid, p.get("citationCount") or 0))
        if body.get("next") is None:
            break
    return out


def batch_references(s2, ids, chunk=100):
    """arXiv references of many papers via the batch endpoint, {id: set(ids)}."""
    refs = {}
    for i in range(0, len(ids), chunk):
        part = ids[i:i + chunk]
        text = s2.request("POST", f"{S2}/paper/batch",
                          params={"fields": "externalIds,citationCount,references.externalIds"},
                          json_body={"ids": [f"arXiv:{a}" for a in part]})
        if not text:
            continue
        for aid, paper in zip(part, json.loads(text)):
            if paper is None:
                print(f"  S2 has no record for {aid}; skipping")
                continue
            refs[aid] = {arxiv_of(r) for r in paper.get("references") or []} - {None}
    return refs


def abs_page(ax, aid):
    """Title, authors, year, abstract and license from the paper's arxiv.org/abs page.

    The arXiv query API (HTTP 429) and the S2 batch endpoint (429 for ten minutes
    straight) both throttled metadata requests during the first build; the abs
    pages kept working, and one page carries the license too.
    """
    text = ax.request("GET", f"https://arxiv.org/abs/{aid}")
    if not text:
        return None

    def metas(name):
        return [html.unescape(m) for m in re.findall(rf'<meta name="{name}" content="([^"]*)"', text)]

    title = metas("citation_title")
    if not title:
        return None
    date = metas("citation_date") or metas("citation_online_date")
    lic = re.search(r'class="abs-license"><a href="([^"]+)"', text)
    # arxiv.org/pdf/<id> serves whatever version is newest, so a later rebuild
    # could extract different text; record the version to pin the download.
    versions = [int(v) for v in re.findall(rf"arXiv:{re.escape(aid)}v(\d+)", text)]
    return {"title": " ".join(title[0].split()),
            "authors": [" ".join(reversed(x.split(", ", 1))) for x in metas("citation_author")],
            "year": int(date[0][:4]) if date else None,
            "abstract": " ".join((metas("citation_abstract") or [""])[0].split()),
            "license": lic.group(1) if lic else "unknown",
            "arxiv_version": f"v{max(versions)}" if versions else ""}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--per-cluster", type=int, default=50)
    ap.add_argument("--pool", type=int, default=150,
                    help="candidates per cluster whose references are fetched to score connectivity")
    ap.add_argument("--min-citers-citations", type=int, default=20)
    ap.add_argument("--citation-pages", type=int, default=2)
    args = ap.parse_args()

    seeds_cfg = json.loads((ROOT / "build" / "seeds.json").read_text())
    exclude = set(seeds_cfg.pop("_exclude", []))
    seeds_cfg.pop("_comment", None)
    clusters = {k: v for k, v in seeds_cfg.items() if not k.startswith("_")}
    s2, ax = s2_client(), arxiv_client()

    # 1. Candidate pools: seeds' arXiv references and well-cited arXiv citers.
    pools, popularity = {}, {}
    for name, seeds in clusters.items():
        links = defaultdict(int)
        for seed in seeds:
            print(f"[{name}] neighbors of {seed}")
            for aid, cc in neighbors(s2, seed, "references", 1):
                links[aid] += 1
                popularity[aid] = cc
            for aid, cc in neighbors(s2, seed, "citations", args.citation_pages):
                if cc >= args.min_citers_citations:
                    links[aid] += 1
                    popularity[aid] = cc
        for aid in list(links):
            if aid in seeds or aid in exclude:
                del links[aid]
        # Prefilter before the expensive connectivity step: papers tied to more
        # seeds first, then more-cited ones.
        ranked = sorted(links, key=lambda a: (links[a], popularity.get(a, 0)), reverse=True)
        pools[name] = list(seeds) + ranked[:args.pool]
        print(f"[{name}] {len(links)} candidates, pool {len(pools[name])}")

    # 2. References of everything in any pool, in bulk.
    all_ids = sorted({a for p in pools.values() for a in p})
    print(f"fetching references for {len(all_ids)} pool papers")
    refs = batch_references(s2, all_ids)

    # 3. Score by in-cluster degree and keep the top papers per cluster.
    selected = defaultdict(set)
    for name, pool in pools.items():
        members = set(pool) & set(refs)
        degree = defaultdict(int)
        for a in members:
            for b in refs[a] & members:
                if a != b:
                    degree[a] += 1
                    degree[b] += 1
        seeds = [s for s in clusters[name] if s in members]
        rest = sorted((a for a in members if a not in seeds),
                      key=lambda a: (degree[a], popularity.get(a, 0)), reverse=True)
        kept = seeds + rest[:args.per_cluster - len(seeds)]
        for a in kept:
            selected[a].add(name)
        print(f"[{name}] kept {len(kept)} (lowest kept degree {min(degree[a] for a in kept)})")

    ids = sorted(selected)
    print(f"fetching {len(ids)} arXiv abstract pages (3 s apart)")
    meta = {}
    for n, aid in enumerate(ids, 1):
        m = abs_page(ax, aid)
        if m:
            meta[aid] = m
        if n % 25 == 0:
            print(f"  {n}/{len(ids)}")
    missing = [x for x in ids if x not in meta]
    if missing:
        print(f"no abs page for {len(missing)} papers, dropping: {missing}")
    ids = [x for x in ids if x in meta]
    corpus = set(ids)

    records = [{"id": a, **{k: v for k, v in meta[a].items() if k != "license"}, "clusters": sorted(selected[a]),
                "s2_citation_count": popularity.get(a)} for a in ids]
    write_jsonl(ROOT / "build" / "selected.jsonl", records)

    edges = sorted({(a, b) for a in ids for b in refs.get(a, set()) & corpus if a != b})
    write_jsonl(ROOT / "gold" / "citations_s2.jsonl", [{"citing": a, "cited": b} for a, b in edges])

    with open(ROOT / "corpus" / "licenses.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "license"])
        for a in ids:
            w.writerow([a, meta[a]["license"]])

    cross = [r for r in records if len(r["clusters"]) > 1]
    per = {n: sum(n in r["clusters"] for r in records) for n in clusters}
    print(f"wrote build/selected.jsonl: {len(records)} papers {per}, {len(cross)} cross-cluster")
    print(f"wrote gold/citations_s2.jsonl: {len(edges)} in-corpus edges")
    top = sorted(records, key=lambda r: -(r["s2_citation_count"] or 0))[:12]
    print("most-cited papers (check these are on-topic; add off-topic ones to _exclude in seeds.json):")
    for r in top:
        print(f"  {r['id']}  {r['s2_citation_count']:>6}  {r['title'][:70]}  {r['clusters']}")


if __name__ == "__main__":
    main()
