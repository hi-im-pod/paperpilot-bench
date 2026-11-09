"""The four tools an agent under test may use. They are its only view of the corpus.

CLI for manual poking:
  py tools/corpus_tools.py search "prompt injection defenses"
  py tools/corpus_tools.py read 2302.12173 Introduction
  py tools/corpus_tools.py sections 2302.12173
  py tools/corpus_tools.py meta 2302.12173
"""
import json
import os
import re
import sys
from functools import lru_cache
from pathlib import Path

from rank_bm25 import BM25Okapi

ROOT = Path(__file__).resolve().parent.parent
CHUNK_WORDS = 300
SNIPPET_CHARS = 300
_STOP = set("a an the of and or to in on for with by from is are was were be as at that this these "
            "those it its we our their they which can using use used via into than then also".split())


def _corpus_path():
    return Path(os.environ.get("PAPERPILOT_CORPUS") or ROOT / "corpus" / "papers.jsonl")


def _tokens(text):
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOP]


def _is_references(name):
    return _section_key(name).startswith(("reference", "bibliograph"))


@lru_cache(maxsize=None)
def _load(path_str):
    papers = {}
    with open(path_str, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                p = json.loads(line)
                papers[p["id"]] = p
    chunks = []  # (paper_id, section, text)
    for pid, p in papers.items():
        chunks.append((pid, "Title and abstract", f"{p['title']}. {p.get('abstract', '')}"))
        for s in p.get("sections", []):
            # References are left out of search: a query would otherwise match
            # titles in other papers' bibliographies. read(id, "References") still works.
            if _is_references(s["name"]):
                continue
            words = s["text"].split()
            for i in range(0, len(words), CHUNK_WORDS):
                chunks.append((pid, s["name"], " ".join(words[i:i + CHUNK_WORDS])))
    bm25 = BM25Okapi([_tokens(c[2]) for c in chunks])
    return papers, chunks, bm25


def _state():
    return _load(str(_corpus_path()))


def _paper(paper_id):
    papers = _state()[0]
    if paper_id not in papers:
        raise KeyError(f"paper not in corpus: {paper_id}")
    return papers[paper_id]


def _snippet(text, query_tokens):
    low = text.lower()
    hits = [low.find(t) for t in query_tokens if low.find(t) >= 0]
    start = max(0, min(hits) - SNIPPET_CHARS // 3) if hits else 0
    return text[start:start + SNIPPET_CHARS]


def search(query, k=10):
    """BM25 over ~300-word section chunks. Returns [{paper_id, title, section, snippet, score}]."""
    papers, chunks, bm25 = _state()
    q = _tokens(query)
    if not q:
        return []
    scores = bm25.get_scores(q)
    order = sorted(range(len(chunks)), key=lambda i: -scores[i])[:max(1, int(k))]
    return [{"paper_id": chunks[i][0], "title": papers[chunks[i][0]]["title"], "section": chunks[i][1],
             "snippet": _snippet(chunks[i][2], q), "score": round(float(scores[i]), 3)}
            for i in order if scores[i] > 0]


def _section_key(name):
    # "4 Results", "IV. RESULTS" and "Results" all name the same section.
    return re.sub(r"^([\dIVX]+(\.\d+)*\.?|[A-H]\.?)\s+", "", name.strip()).lower()


def read(paper_id, section=None):
    """One section's text, or the whole paper (all sections) if section is None."""
    p = _paper(paper_id)
    sections = p.get("sections", [])
    if section is None:
        return "\n\n".join(f"## {s['name']}\n{s['text']}" for s in sections)
    for match in (lambda s: s["name"] == section,
                  lambda s: s["name"].lower() == section.lower(),
                  lambda s: _section_key(s["name"]) == _section_key(section)):
        found = [s for s in sections if match(s)]
        if found:
            return "\n\n".join(s["text"] for s in found)
    raise KeyError(f"no section {section!r} in {paper_id}; sections: {[s['name'] for s in sections]}")


def list_sections(paper_id):
    return [s["name"] for s in _paper(paper_id).get("sections", [])]


def get_metadata(paper_id):
    """Title, authors, year, abstract. Never references, clusters or citation edges."""
    p = _paper(paper_id)
    return {"paper_id": paper_id, "title": p["title"], "authors": p.get("authors", []),
            "year": p.get("year"), "abstract": p.get("abstract", "")}


TOOLS = {"search": search, "read": read, "list_sections": list_sections, "get_metadata": get_metadata}


def call_tool(name, arguments):
    """Dispatch a tool call by name; errors come back as text so the agent can recover."""
    try:
        result = TOOLS[name](**arguments)
    except (KeyError, TypeError) as e:
        return f"error: {e}"
    return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("search", "read", "sections", "meta"):
        print(__doc__)
        return
    cmd, arg = sys.argv[1], sys.argv[2]
    if cmd == "search":
        for r in search(arg, int(sys.argv[3]) if len(sys.argv) > 3 else 10):
            print(f"{r['score']:>7}  {r['paper_id']}  [{r['section']}]  {r['title'][:60]}\n         {r['snippet'][:160]}")
    elif cmd == "read":
        print(read(arg, sys.argv[3] if len(sys.argv) > 3 else None))
    elif cmd == "sections":
        print("\n".join(list_sections(arg)))
    else:
        print(json.dumps(get_metadata(arg), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
