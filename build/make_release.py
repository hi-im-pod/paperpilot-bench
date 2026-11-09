"""Build the Phase 3 zip: everything another team needs, minus the held-back answers."""
import argparse
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INCLUDED = ["corpus/", "tools/", "tasks/dev.jsonl", "tasks/test.jsonl", "tasks/schemas/",
            "gold/dev_gold.jsonl", "scoring/", "baselines/", "prompts/agent.md",
            "prompts/judge.md", "requirements.txt", "README.md"]
# Test gold and the S2 edge list are answer keys; drafts, provenance and items
# carry trap flags; the judge cache holds scored test outputs.
EXCLUDED = ["gold/test_gold.jsonl", "gold/citations_s2.jsonl", "gold/drafts/", "gold/provenance.csv",
            "tasks/items.jsonl", "build/", "scoring/.judge_cache.jsonl"]
SKIP_PARTS = {"__pycache__", ".pytest_cache"}


def strip_clusters(text):
    # Cluster tags hint at find_papers relevance.
    out = []
    for line in text.splitlines():
        if line.strip():
            rec = json.loads(line)
            rec.pop("clusters", None)
            out.append(json.dumps(rec, ensure_ascii=False))
    return "\n".join(out) + "\n"


def build_release(repo, out_zip):
    repo, out_zip = Path(repo), Path(out_zip)
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    files = []
    for entry in INCLUDED:
        p = repo / entry
        if entry.endswith("/"):
            files += [f for f in sorted(p.rglob("*")) if f.is_file()] if p.exists() else []
        elif p.exists():
            files.append(p)
        else:
            print(f"warning: {entry} not found, not shipped")
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            rel = f.relative_to(repo).as_posix()
            if rel.startswith(tuple(EXCLUDED)) or SKIP_PARTS & set(f.parts):
                continue
            if rel == "corpus/papers.jsonl":
                z.writestr(rel, strip_clusters(f.read_text(encoding="utf-8")))
            else:
                z.write(f, rel)
    with zipfile.ZipFile(out_zip) as z:
        names = z.namelist()
        leaked = [n for n in names if n.startswith(tuple(EXCLUDED))]
        if "corpus/papers.jsonl" in names and '"clusters"' in z.read("corpus/papers.jsonl").decode("utf-8"):
            leaked.append("corpus/papers.jsonl (clusters field)")
    if leaked:
        out_zip.unlink()
        raise SystemExit(f"release would leak held-back files, aborted: {leaked}")
    return out_zip


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ROOT / "release" / "paperpilot-bench-v1.zip"))
    args = ap.parse_args()
    z = build_release(ROOT, args.out)
    with zipfile.ZipFile(z) as zf:
        print(f"wrote {z}: {len(zf.namelist())} files")


if __name__ == "__main__":
    sys.exit(main())
