"""Scratch helpers for writing items and gold in this session. Not part of the repo."""
import json
import re
import sys
from pathlib import Path

REPO = Path(r"C:\Users\redro\paperpilot-bench")
sys.path[:0] = [str(REPO / "build"), str(REPO / "tools"), str(REPO / "scoring"), str(REPO / "baselines")]
import corpus_tools as ct  # noqa: E402
from normalize import normalize, quote_match  # noqa: E402

PAPERS = ct._state()[0]


class _NoAgent:
    model = "none"


def drafter():
    from draft_labels import Drafter
    d = Drafter.__new__(Drafter)
    d.papers, d._emb, d.agent = PAPERS, None, _NoAgent()
    return d


def pool(topic, n=20):
    d = drafter()
    b, e = d.bm25_papers(topic, n), d.emb_papers(topic, n)
    return {pid: [s for s, ids in (("bm25", b), ("emb", e)) if pid in ids] for pid in dict.fromkeys(b + e)}


def title(pid):
    return PAPERS[pid]["title"]


def grep(pid, pattern, width=160, limit=6):
    text = " ".join(ct.read(pid).split())
    out = []
    for m in re.finditer(pattern, text, re.I):
        out.append(text[max(0, m.start() - width):m.end() + width])
        if len(out) >= limit:
            break
    return out


def check_quote(pid, quote):
    return quote_match(quote, normalize("\n\n".join(
        [PAPERS[pid]["title"], PAPERS[pid].get("abstract", "")] + [s["text"] for s in PAPERS[pid]["sections"]]))) is not None


def raw_find(pid, pattern):
    """Exact verbatim span from the paper (whitespace collapsed), for building quotes."""
    text = " ".join(ct.read(pid).split())
    m = re.search(pattern, text, re.I | re.S)
    return m.group(0) if m else None
