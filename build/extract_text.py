"""Download each selected paper's PDF and split its text into sections.

Reads build/selected.jsonl, writes corpus/papers.jsonl.
"""
import argparse
import re
import sys
import unicodedata
from collections import Counter

import pymupdf as fitz

from common import ROOT, arxiv_client, read_jsonl, write_jsonl

sys.path.insert(0, str(ROOT / "tools"))
from corpus_tools import corpus_sha256  # noqa: E402

KNOWN = ["abstract", "introduction", "related work", "related works", "background", "preliminaries",
         "method", "methods", "methodology", "approach", "our approach", "experiments", "experimental setup",
         "experimental results", "results", "evaluation", "analysis", "discussion", "limitations",
         "conclusion", "conclusions", "conclusion and future work", "conclusions and future work",
         "future work", "broader impact", "broader impacts", "ethics statement", "acknowledgments",
         "acknowledgements", "references", "bibliography", "appendix", "appendices", "supplementary material"]
REFERENCE_NAMES = {"references", "bibliography"}
ROMAN = {r: i for i, r in enumerate(["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"], 1)}
TITLE_LIKE = r"[A-Z][\w ,:;&()'/+\-–—?!]{1,80}"
# Once a paper numbers its sections, only these may appear without a number;
# a bare "Method" or "Results" line is then a table header, not a section.
UNNUMBERED_OK = {"abstract", "references", "bibliography", "acknowledgments", "acknowledgements",
                 "broader impact", "broader impacts", "ethics statement", "impact statement",
                 "reproducibility statement", "limitations", "appendix", "appendices", "supplementary material"}


def title_cased(title):
    """Headings are Title Case or ALL CAPS, or short. Figure text and list items mostly aren't."""
    words = title.split()
    if len(words) <= 4 or title.isupper():
        return True
    long_words = [w for w in words if len(w) > 3 and w[0].isalpha()]
    return not long_words or sum(w[0].isupper() for w in long_words) / len(long_words) >= 0.5


def page_lines(doc):
    pages = []
    for page in doc:
        text = unicodedata.normalize("NFKC", page.get_text("text"))
        pages.append([ln.strip() for ln in text.splitlines()])
    # Running headers and footers repeat on most pages ("Published as a conference
    # paper at ...") and would otherwise land in the middle of every section.
    counts = Counter(ln for p in pages for ln in set(p) if ln and not ln.isdigit())
    repeated = {ln for ln, c in counts.items() if len(pages) >= 4 and c >= len(pages) / 2}
    lines = []
    for p in pages:
        for ln in p:
            if ln in repeated or re.match(r"^arXiv:\d{4}\.\d{4,5}v\d+", ln):
                continue
            lines.append(ln)
    return lines


def followed_by_prose(window):
    """Real headings lead into body text or a subsection within a few lines; table cells don't."""
    return any(len(ln.split()) >= 7 or re.match(r"^\d+\.\d+\.?(\s|$)", ln) for ln in window)


def heading_name(line, ahead, state):
    """Return (section name, lines consumed) if `line` starts a section, else None."""
    nxt = ahead[0] if ahead else ""
    clean = line.rstrip(":").strip()
    low = clean.lower()
    words = clean.split()
    if not clean or len(words) > 10 or clean.endswith((".", ",")):
        if not re.match(r"^abstract\b", low):
            return None
    if re.match(r"^abstract\b", low) and not state["seen_abstract"]:
        state["seen_abstract"] = True
        return "Abstract", 1
    if low in KNOWN and (low in UNNUMBERED_OK or (state["num"] == 0 and state["roman"] == 0)):
        if low in REFERENCE_NAMES:
            state["in_refs"] = True
        return clean.title() if clean.isupper() else clean, 1
    # "1 Introduction" / "1. Introduction"; top-level numbers only, in order, so
    # numbered list items and table rows aren't mistaken for headings.
    m = re.match(rf"^(\d{{1,2}})\.?\s+({TITLE_LIKE})$", clean)
    if m and not state["in_refs"] and int(m.group(1)) == state["num"] + 1 and len(words) <= 9 \
            and title_cased(m.group(2)) and followed_by_prose(ahead[:3]):
        state["num"] += 1
        return clean, 1
    # The number and the title often extract as two lines: "3" then "Method".
    if re.fullmatch(r"\d{1,2}\.?", clean) and nxt and not state["in_refs"] \
            and int(clean.rstrip(".")) == state["num"] + 1 and re.fullmatch(TITLE_LIKE, nxt) \
            and len(nxt.split()) <= 9 and not nxt.endswith(".") and title_cased(nxt) \
            and followed_by_prose(ahead[1:4]):
        state["num"] += 1
        return f"{clean.rstrip('.')} {nxt}", 2
    m = re.match(r"^([IVX]{1,4})\.\s+([A-Z][A-Z0-9 ,&\-]{2,60})$", clean)
    if m and not state["in_refs"] and ROMAN.get(m.group(1)) == state["roman"] + 1:
        state["roman"] += 1
        return clean, 1
    # Appendices come after References and use letters: "A Additional Results".
    m = re.match(rf"^([A-H])(\.\d+)?\.?\s+({TITLE_LIKE})$", clean)
    if m and state["in_refs"] and "," not in clean and len(words) <= 8 and not m.group(2) \
            and ord(m.group(1)) == state["appendix"] + 1:
        state["appendix"] += 1
        return clean, 1
    if re.fullmatch(r"[A-H]\.?", clean) and state["in_refs"] and ord(clean[0]) == state["appendix"] + 1 \
            and re.fullmatch(TITLE_LIKE, nxt) and "," not in nxt and len(nxt.split()) <= 10 and title_cased(nxt):
        state["appendix"] += 1
        return f"{clean[0]} {nxt}", 2
    return None


def split_sections(lines):
    state = {"num": 0, "roman": 0, "appendix": ord("A") - 1, "in_refs": False, "seen_abstract": False}
    sections = [{"name": "Front matter", "lines": []}]
    i = 0
    while i < len(lines):
        ln = lines[i]
        h = heading_name(ln, lines[i + 1:i + 5], state)
        if h:
            name, used = h
            body = []
            if name == "Abstract" and len(ln) > len("abstract") + 2:
                body = [re.sub(r"^abstract[\s.:\-—]*", "", ln, flags=re.I)]
            sections.append({"name": name, "lines": body})
            i += used
            continue
        if not re.fullmatch(r"\d{1,3}", ln):  # drop bare page numbers
            sections[-1]["lines"].append(ln)
        i += 1
    out = []
    for s in sections:
        text = "\n".join(s["lines"]).strip()
        # Rejoin words that the PDF hyphenated across a line break.
        text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
        if text:
            out.append({"name": s["name"], "text": text})
    if len(out) <= 1:
        return [{"name": "body", "text": "\n\n".join(s["text"] for s in out)}]
    return out


def check_checksum(path, ref):
    """Compare a rebuilt corpus with the published one, or record it on the first build."""
    digest = corpus_sha256(path)
    if not ref.exists():
        ref.write_text(f"{digest}  papers.jsonl\n", encoding="utf-8")
        print(f"recorded corpus checksum {digest[:16]}... in {ref.relative_to(ROOT)}")
    elif ref.read_text(encoding="utf-8").split()[0] == digest:
        print(f"corpus matches the published checksum ({digest[:16]}...)")
    else:
        print(f"WARNING: corpus differs from the published checksum. Gold quotes may no longer match. "
              f"Got {digest[:16]}..., expected {ref.read_text(encoding='utf-8').split()[0][:16]}...")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", nargs="*", help="re-extract just these IDs (for debugging)")
    ap.add_argument("--track", choices=["v1", "hard"], default="v1",
                    help="v1: the frozen 138-paper corpus; hard: the recent-papers track")
    args = ap.parse_args()
    build_dir = ROOT / "build" / ("hard" if args.track == "hard" else "")
    corpus_dir = ROOT / "corpus" / ("hard" if args.track == "hard" else "")
    corpus_dir.mkdir(parents=True, exist_ok=True)
    selected = read_jsonl(build_dir / "selected.jsonl")
    if args.only:
        selected = [r for r in selected if r["id"] in set(args.only)]
    ax = arxiv_client()
    papers, failed, flagged = [], [], []
    no_abstract = 0
    for n, rec in enumerate(selected, 1):
        pdf = ax.request("GET", f"https://arxiv.org/pdf/{rec['id']}{rec.get('arxiv_version', '')}", binary=True)
        if not pdf or not pdf.startswith(b"%PDF"):
            print(f"[{n}/{len(selected)}] {rec['id']}: no PDF, skipping")
            failed.append(rec["id"])
            continue
        try:
            with fitz.open(stream=pdf, filetype="pdf") as doc:
                sections = split_sections(page_lines(doc))
        except Exception as e:  # a corrupt PDF shouldn't stop the whole build
            print(f"[{n}/{len(selected)}] {rec['id']}: extraction failed ({e}), skipping")
            failed.append(rec["id"])
            continue
        words = sum(len(s["text"].split()) for s in sections)
        if len(sections) < 3 or words < 2000:
            flagged.append((rec["id"], len(sections), words, rec["title"][:60]))
        abstract = rec["abstract"]
        if not abstract:
            # S2 withholds some abstracts; the PDF's own Abstract section is the next best source.
            pdf_abs = next((s["text"] for s in sections if s["name"] == "Abstract"), "")
            abstract = " ".join(pdf_abs.split())[:2000]
            no_abstract += not abstract
        papers.append({"id": rec["id"], "title": rec["title"], "authors": rec["authors"], "year": rec["year"],
                       "abstract": abstract, "clusters": rec["clusters"], "sections": sections})
        if n % 10 == 0:
            print(f"[{n}/{len(selected)}] extracted")
    out = corpus_dir / ("papers.only.jsonl" if args.only else "papers.jsonl")
    write_jsonl(out, papers)
    if not args.only:
        check_checksum(out, corpus_dir / "papers.sha256")
    print(f"wrote {out.relative_to(ROOT)}: {len(papers)} papers; {len(failed)} failed {failed}")
    if no_abstract:
        print(f"{no_abstract} papers have no abstract from S2 or the PDF")
    print(f"flagged for a manual check (<3 sections or <2000 words): {len(flagged)}")
    for f in flagged:
        print(f"  {f[0]}  sections={f[1]}  words={f[2]}  {f[3]}")


if __name__ == "__main__":
    main()
