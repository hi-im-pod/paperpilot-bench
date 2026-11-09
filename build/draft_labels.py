"""Draft gold labels with an LLM, one file per item in gold/drafts/, for a person to verify.

py build/draft_labels.py --type find_papers --provider anthropic
py build/draft_labels.py --sample-check          # pick the 20% second-check sample

A draft is not gold. The verifier edits the draft in place and sets "verified_by".
"""
import argparse
import hashlib
import json
import os
import random
import re
import sys
from collections import Counter
from pathlib import Path

from common import ROOT, read_jsonl

sys.path[:0] = [str(ROOT / "baselines"), str(ROOT / "tools"), str(ROOT / "scoring")]
import corpus_tools  # noqa: E402
from agent_prompts import parse_final  # noqa: E402
from llm import Agent, add_provider_args  # noqa: E402

DRAFTS = ROOT / "gold" / "drafts"
ITEMS = ROOT / "tasks" / "items.jsonl"
EMBED_MODEL = "nomic-embed-text"
SYSTEM = "You draft gold labels for a research-paper benchmark. Follow the instructions exactly and return JSON only."
TYPES = ["find_papers", "comparison_table", "citation_links", "grounded_claims", "followup_questions"]
GAP_SECTIONS = ("limitation", "discussion", "conclusion", "future work")


def load_prompts():
    md = (ROOT / "prompts" / "label_draft.md").read_text(encoding="utf-8")
    out = {}
    for t in TYPES:
        m = re.search(rf"^## \d+\. {t}:[^\n]*\n.*?```\n(.*?)\n```", md, re.S | re.M)
        if not m:
            raise SystemExit(f"no drafting prompt for {t} in prompts/label_draft.md")
        out[t] = m.group(1)
    return out


def fill(template, pattern, value):
    """Replace one {placeholder ...} in a drafting prompt; patterns are loose on purpose."""
    return re.sub(pattern, lambda _: value, template, count=1)


class Drafter:
    def __init__(self, agent):
        self.agent = agent
        self.prompts = load_prompts()
        self.papers, _, _ = corpus_tools._state()
        self._emb = None

    def ask(self, prompt):
        text, trace = self.agent.run(SYSTEM, prompt)
        obj = parse_final(text)
        if obj is None:
            print(f"  could not parse the model's JSON; first 300 chars: {text[:300]!r}")
        return obj or {}, trace

    # ---- candidate pools ----

    def bm25_papers(self, query, n):
        seen = []
        for hit in corpus_tools.search(query, k=n * 8):
            if hit["paper_id"] not in seen:
                seen.append(hit["paper_id"])
        return seen[:n]

    def embeddings(self):
        import numpy as np
        import ollama
        ids = sorted(self.papers)
        key = hashlib.sha256(json.dumps(ids).encode()).hexdigest()[:12]
        path = ROOT / "build" / "cache" / f"emb_{key}.npy"
        if path.exists():
            return ids, np.load(path)
        client = ollama.Client(host=os.environ.get("OLLAMA_HOST", "127.0.0.1:11434").replace("0.0.0.0", "127.0.0.1"))
        texts = [f"search_document: {self.papers[i]['title']}. {self.papers[i].get('abstract', '')}" for i in ids]
        vecs = []
        for i in range(0, len(texts), 32):
            vecs += client.embed(model=EMBED_MODEL, input=texts[i:i + 32]).embeddings
        arr = np.array(vecs, dtype="float32")
        arr /= np.linalg.norm(arr, axis=1, keepdims=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(path, arr)
        return ids, arr

    def emb_papers(self, query, n):
        import numpy as np
        import ollama
        ids, arr = self._emb or self.embeddings()
        self._emb = (ids, arr)
        client = ollama.Client(host=os.environ.get("OLLAMA_HOST", "127.0.0.1:11434").replace("0.0.0.0", "127.0.0.1"))
        q = np.array(client.embed(model=EMBED_MODEL, input=[f"search_query: {query}"]).embeddings[0], dtype="float32")
        order = np.argsort(-(arr @ (q / np.linalg.norm(q))))
        return [ids[i] for i in order[:n]]

    def llm_papers(self, query, n):
        listing = "\n".join(f"{i}: {p['title']}" for i, p in sorted(self.papers.items()))
        obj, _ = self.ask(f"Topic: {query}\n\nFrom the paper list below, pick the {n} papers most relevant to the "
                          f"topic, best first. Return JSON only: {{\"ids\": [\"<id>\", ...]}}\n\n{listing}")
        return [i for i in obj.get("ids", []) if i in self.papers][:n]

    def paper_line(self, pid):
        p = self.papers[pid]
        return f"{pid} | {p['title']} | {p.get('abstract', '')}"

    # ---- per type ----

    def find_papers(self, item):
        topic = item["input"]["topic"]
        sources = {"bm25": self.bm25_papers(topic, 20), "embedding": self.emb_papers(topic, 20),
                   "llm": self.llm_papers(topic, 20)}
        pool = list(dict.fromkeys(sources["bm25"] + sources["embedding"] + sources["llm"]))
        grades = []
        for i in range(0, len(pool), 10):
            batch = pool[i:i + 10]
            prompt = fill(self.prompts["find_papers"], r"\{topic\}", topic)
            prompt = fill(prompt, r"\{for each paper:[^}]*\}", "\n".join(self.paper_line(p) for p in batch))
            obj, _ = self.ask(prompt)
            got = {g.get("paper_id"): g for g in obj.get("grades", []) if isinstance(g, dict)}
            for pid in batch:
                g = got.get(pid, {"grade": None, "evidence": "MODEL DID NOT GRADE THIS PAPER"})
                grades.append({"paper_id": pid, "title": self.papers[pid]["title"], "grade": g.get("grade"),
                               "evidence": g.get("evidence", ""),
                               "found_by": [s for s, ids in sources.items() if pid in ids]})
        grades.sort(key=lambda g: -(g["grade"] or 0))
        return {"grades": grades, "how_to_verify": "Check every grade 1 and 2, spot-check the 0s. "
                "Set any null grade by hand. Gold relevant = papers with grade 1 or 2."}

    def comparison_table(self, item):
        inp = item["input"]
        pids = inp.get("paper_ids") or self.bm25_papers(inp["topic"], 3) + \
            [p for p in self.emb_papers(inp["topic"], 6) if p not in self.bm25_papers(inp["topic"], 3)][:3]
        cols = "\n".join(f"- {c['name']} | {c['type']} | {c.get('unit') or ', '.join(c.get('allowed', []))} | "
                         f"{c.get('setting', '')}" for c in inp["columns"])
        rows = {}
        for pid in pids:
            # Paper text goes in last so a brace inside it can't be mistaken for a placeholder.
            prompt = fill(self.prompts["comparison_table"], r"\{paper_id\}", pid)
            prompt = fill(prompt, r"\{one line per column:[^}]*\}", cols)
            prompt = fill(prompt, r"\{full text\}", corpus_tools.read(pid))
            obj, _ = self.ask(prompt)
            rows[pid] = {c["name"]: (obj.get("cells") or {}).get(c["name"],
                         {"value": None, "quote": "", "section": "", "note": "MODEL DID NOT FILL THIS CELL"})
                         for c in inp["columns"]}
        return {"rows": rows, "rows_were_searched": inp.get("paper_ids") is None,
                "how_to_verify": "Find each quote in the paper (Ctrl+F) and check the setting matches. "
                "Every non-empty note needs a second look. Remove rows that don't belong."}

    def citation_links(self, item):
        ids = item["input"]["paper_ids"]
        s2 = {(e["citing"], e["cited"]) for e in read_jsonl(ROOT / "gold" / "citations_s2.jsonl")
              if e["citing"] in ids and e["cited"] in ids}
        llm = set()
        for pid in ids:
            try:
                refs = corpus_tools.read(pid, "References")
            except KeyError:
                print(f"  {pid} has no References section; only S2 edges for it")
                continue
            others = "\n".join(f"{o} | {self.papers[o]['title']} | {(self.papers[o].get('authors') or ['?'])[0]} | "
                               f"{self.papers[o].get('year')}" for o in ids if o != pid)
            prompt = fill(self.prompts["citation_links"], r"\{paper_id\}", pid)
            prompt = fill(prompt, r"\{for each other paper in the set:[^}]*\}", others)
            prompt = fill(prompt, r"\{References section text\}", refs)
            obj, _ = self.ask(prompt)
            for c in obj.get("cited", []):
                if isinstance(c, dict) and c.get("paper_id") in ids and c["paper_id"] != pid:
                    llm.add((pid, c["paper_id"]))
        edges = []
        for a, b in sorted(s2 | llm):
            agree = (a, b) in s2 and (a, b) in llm
            edges.append({"citing": a, "cited": b, "in_s2": (a, b) in s2, "in_reference_list": (a, b) in llm,
                          "needs_review": not agree, "keep": True if agree else None})
        return {"edges": edges, "how_to_verify": "Set keep to true or false on every edge with needs_review, "
                "by checking the citing paper's References section."}

    def grounded_claims(self, item):
        q = item["input"]["question"]
        cands = list(dict.fromkeys(self.bm25_papers(q, 10) + self.emb_papers(q, 10)))[:15]
        prompt = fill(self.prompts["grounded_claims"], r"\{question\}", q)
        prompt = fill(prompt, r"\{candidate papers\}", "\n".join(self.paper_line(p) for p in cands))
        obj, _ = self.ask(prompt)
        return {"candidates": cands, "supporting": [s for s in obj.get("supporting", []) if isinstance(s, dict)],
                "draft_answer": obj.get("draft_answer", ""),
                "how_to_verify": "Delete supporting entries that don't help answer the question; add any missing."}

    def followup_questions(self, item):
        parts = []
        for pid in item["input"]["paper_ids"]:
            secs = [s for s in corpus_tools.list_sections(pid) if any(k in s.lower() for k in GAP_SECTIONS)]
            text = "\n".join(corpus_tools.read(pid, s) for s in secs) or "(no limitations, discussion or conclusion section found)"
            parts.append(f"{pid} | {self.papers[pid]['title']} | {text}")
        prompt = fill(self.prompts["followup_questions"], r"\{for each paper:[^}]*\}", "\n\n".join(parts))
        obj, _ = self.ask(prompt)
        return {"gaps": obj.get("gaps", []), "gap_notes": obj.get("gap_notes", ""),
                "how_to_verify": "Remove any gap whose quote isn't in the paper; tighten gap_notes."}


def sample_check(drafts_dir, fraction=0.2, seed=0):
    drafts = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(drafts_dir.glob("*.json"))]
    rng = random.Random(seed)
    picked = []
    for t in TYPES:
        of_type = sorted(d["id"] for d in drafts if d["type"] == t)
        k = max(1, round(fraction * len(of_type))) if of_type else 0
        picked += rng.sample(of_type, k)
    for pid in picked:
        path = drafts_dir / f"{pid}.json"
        d = json.loads(path.read_text(encoding="utf-8"))
        d["second_check_requested"] = True
        path.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"marked {len(picked)} drafts for a second check: {picked}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--type", choices=TYPES)
    ap.add_argument("--only", nargs="*", help="draft just these item IDs")
    ap.add_argument("--force", action="store_true", help="overwrite existing drafts")
    ap.add_argument("--sample-check", action="store_true")
    ap.add_argument("--items", default=str(ITEMS), help="task items file (default tasks/items.jsonl)")
    ap.add_argument("--drafts", default=str(DRAFTS), help="draft folder (default gold/drafts)")
    add_provider_args(ap)
    args = ap.parse_args()
    drafts_dir = Path(args.drafts)
    if args.sample_check:
        return sample_check(drafts_dir)
    if not args.type:
        ap.error("--type is required unless --sample-check")
    items = [i for i in read_jsonl(args.items) if i["type"] == args.type and not i.get("trap")
             and (not args.only or i["id"] in args.only)]
    drafts_dir.mkdir(parents=True, exist_ok=True)
    drafter = Drafter(Agent(args.provider, args.model, args.effort))
    written = Counter()
    for item in items:
        path = drafts_dir / f"{item['id']}.json"
        if path.exists() and not args.force:
            print(f"{item['id']}: draft exists, skipping (use --force to redo)")
            continue
        print(f"{item['id']}: drafting")
        body = getattr(drafter, args.type)(item)
        draft = {"id": item["id"], "type": item["type"], "input": item["input"], **body,
                 "drafting_model": drafter.agent.model, "verified_by": None, "checked_by": None}
        path.write_text(json.dumps(draft, indent=2, ensure_ascii=False), encoding="utf-8")
        written[args.type] += 1
    print(f"wrote {sum(written.values())} drafts to {drafts_dir}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
