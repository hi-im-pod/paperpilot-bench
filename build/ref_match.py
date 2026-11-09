"""Decide whether paper A cites paper B by reading A's reference list.

Used to cross-check Semantic Scholar's edges for citation_links gold. Matches on
B's arXiv ID first, then on B's title. A paper can change title between arXiv
versions (2302.12173 was first "More than you've asked for..."), and the ID
still matches when the title doesn't.

py build/ref_match.py 2307.02483 2302.12173
"""
import re
import sys

from rapidfuzz import fuzz

from common import ROOT

sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "scoring")]
import corpus_tools  # noqa: E402
from normalize import normalize  # noqa: E402

TITLE_THRESHOLD = 92


def _squash(text):
    """Lowercase alphanumerics only: references break titles across lines and hyphens."""
    return re.sub(r"[^a-z0-9]+", " ", normalize(text)).strip()


def references(pid):
    try:
        return corpus_tools.read(pid, "References")
    except KeyError:
        return ""


def cites(a, b, papers):
    """(True/False, evidence) for 'paper a cites paper b'."""
    refs = references(a)
    if not refs:
        return False, "no References section"
    if re.search(rf"(?<![\d.]){re.escape(b)}(?!\d)", refs):
        return True, f"arXiv ID {b} in reference list"
    title = _squash(papers[b]["title"].split(":")[0] if len(papers[b]["title"].split(":")[0].split()) >= 3
                    else papers[b]["title"])
    flat = _squash(refs)
    if len(title.split()) < 3:
        return (f" {title} " in f" {flat} "), "short title, exact match only"
    score = fuzz.partial_ratio(title, flat)
    return score >= TITLE_THRESHOLD, f"title match {score:.0f}"


def main():
    papers, _, _ = corpus_tools._state()
    a, b = sys.argv[1], sys.argv[2]
    print(cites(a, b, papers))


if __name__ == "__main__":
    main()
