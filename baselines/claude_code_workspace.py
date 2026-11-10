"""Run a Claude Code session (or any coding agent) as the agent under test, blind to the gold.

  py baselines/claude_code_workspace.py make  --tasks tasks/test.jsonl --types find_papers --out <dir>
  py baselines/claude_code_workspace.py make  --tasks tasks/test.jsonl --titles-only --out <dir>
  py baselines/claude_code_workspace.py collect --out <dir> --preds preds.jsonl

`make` builds a folder holding only what the agent may see: the corpus, the task
items, prompts/agent.md, and tool.py, which logs every call and stops answering
an item after the tool budget. Put the folder outside this repo so the gold
isn't one directory away. `collect` turns the agent's answers/<id>.json files
into a predictions file, with tool-call counts as trace.steps.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUDGET = 15
CLIP = 30000

TOOL_PY = r'''"""The only way to look at the library. Every call is logged.

python tool.py <item_id> search "<query>" [k]
python tool.py <item_id> read <paper_id> [section name...]
python tool.py <item_id> sections <paper_id>
python tool.py <item_id> meta <paper_id>
"""
import json, os, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
os.environ["PAPERPILOT_CORPUS"] = str(HERE / "corpus" / "papers.jsonl")
sys.path.insert(0, str(HERE / "lib"))
import corpus_tools as ct
BUDGET, CLIP = {budget}, {clip}

def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 4:
        print(__doc__); return
    item, cmd, args = sys.argv[1], sys.argv[2], sys.argv[3:]
    log = HERE / "calls.jsonl"
    used = sum(1 for l in log.open(encoding="utf-8") if json.loads(l)["item"] == item) if log.exists() else 0
    if used >= BUDGET:
        print(f"Tool budget used up for {{item}} ({{BUDGET}} calls). Write your final answer now."); return
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps({{"item": item, "cmd": cmd, "args": args}}) + "\n")
    try:
        if cmd == "search":
            out = ct.search(args[0], int(args[1]) if len(args) > 1 else 10)
        elif cmd == "read":
            out = ct.read(args[0], " ".join(args[1:]) if len(args) > 1 else None)
        elif cmd == "sections":
            out = ct.list_sections(args[0])
        elif cmd == "meta":
            out = ct.get_metadata(args[0])
        else:
            print("unknown command; see python tool.py"); return
    except KeyError as e:
        print(f"error: {{e}}"); return
    text = out if isinstance(out, str) else json.dumps(out, indent=1, ensure_ascii=False)
    if len(text) > CLIP:
        text = text[:CLIP] + f"\n[truncated at {{CLIP}} characters; read one section at a time]"
    print(text)
    print(f"\n[{{used + 1}}/{{BUDGET}} tool calls used for {{item}}]")

main()
'''

README = """# You are the agent under test

You're being evaluated on a research-literature benchmark. Answer each task in
`tasks.jsonl` using only the paper library in this folder.

Rules:
- Read `agent.md`. Its system prompt and the template for each task type are your
  instructions, and its JSON shapes are the required output.
- Learn about papers only through `{tool}` (run `{python} tool.py` for usage).
  Every call names the task ID it is for. Each task has a budget of {budget} calls;
  after that, tool.py refuses and you must answer with what you have.
- Don't open any file outside this folder, don't open corpus/ or lib/ directly,
  and don't use the web. Answer from what the tools return, not from memory.
- For each task, write exactly one JSON object to `answers/<task id>.json`, in the
  shape agent.md gives: {{"abstain": false, "output": {{...}}}} or
  {{"abstain": true, "output": {{"reason": "..."}}}}.
- Some tasks may have no answer in the library. Abstaining is then correct.
"""

README_TITLES = """# You are the agent under test (titles only)

You're being evaluated on a research-literature benchmark, with no access to the
papers themselves. `titles.txt` lists every paper in the library (ID: title).

Rules:
- Read `agent.md`. Its system prompt and task templates are your instructions and
  its JSON shapes are the required output. The tools it mentions are not available.
- Don't open any file outside this folder and don't use the web.
- For each task in `tasks.jsonl`, write one JSON object to `answers/<task id>.json`:
  {"abstain": false, "output": {...}} or {"abstain": true, "output": {"reason": "..."}}.
"""


def make(args):
    out = Path(args.out)
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty")
    if ROOT in out.resolve().parents or out.resolve() == ROOT:
        raise SystemExit("put the workspace outside the repo, so the gold isn't next to it")
    tasks = [json.loads(line) for line in open(args.tasks, encoding="utf-8") if line.strip()]
    if args.types:
        tasks = [t for t in tasks if t["type"] in args.types]
    for t in tasks:
        if set(t) - {"id", "type", "input"}:
            raise SystemExit(f"{t['id']} carries fields beyond id/type/input; use tasks/*.jsonl, not items")
    (out / "answers").mkdir(parents=True)
    (out / "tasks.jsonl").write_text("".join(json.dumps(t, ensure_ascii=False) + "\n" for t in tasks), encoding="utf-8")
    shutil.copy(ROOT / "prompts" / "agent.md", out / "agent.md")
    corpus = Path(args.corpus)
    if args.titles_only:
        titles = [json.loads(line) for line in corpus.open(encoding="utf-8")]
        (out / "titles.txt").write_text("".join(f"{p['id']}: {p['title']}\n" for p in titles), encoding="utf-8")
        (out / "README.md").write_text(README_TITLES, encoding="utf-8")
    else:
        (out / "corpus").mkdir()
        (out / "lib").mkdir()
        # A stripped copy: no cluster tags, which hint at relevance.
        with corpus.open(encoding="utf-8") as src, (out / "corpus" / "papers.jsonl").open("w", encoding="utf-8") as dst:
            for line in src:
                rec = json.loads(line)
                rec.pop("clusters", None)
                dst.write(json.dumps(rec, ensure_ascii=False) + "\n")
        shutil.copy(ROOT / "tools" / "corpus_tools.py", out / "lib" / "corpus_tools.py")
        (out / "tool.py").write_text(TOOL_PY.format(budget=BUDGET, clip=CLIP), encoding="utf-8")
        python = args.python or sys.executable
        (out / "README.md").write_text(README.format(tool="tool.py", python=f'"{python}"', budget=BUDGET),
                                       encoding="utf-8")
    print(f"wrote workspace {out}: {len(tasks)} tasks ({'titles only' if args.titles_only else 'tools'})")


def collect(args):
    out = Path(args.out)
    calls = {}
    if (out / "calls.jsonl").exists():
        for line in (out / "calls.jsonl").open(encoding="utf-8"):
            item = json.loads(line)["item"]
            calls[item] = calls.get(item, 0) + 1
    tasks = [json.loads(line) for line in (out / "tasks.jsonl").open(encoding="utf-8")]
    preds, missing = [], []
    for t in tasks:
        path = out / "answers" / f"{t['id']}.json"
        trace = {"steps": calls.get(t["id"], 0), "agent": args.agent}
        if not path.exists():
            missing.append(t["id"])
            continue
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            preds.append({"id": t["id"], "abstain": False, "output": {}, "trace": {**trace, "parse_error": True}})
            continue
        if "output" not in obj and "abstain" not in obj:
            obj = {"abstain": False, "output": obj}
        preds.append({"id": t["id"], "abstain": bool(obj.get("abstain")), "output": obj.get("output") or {},
                      "trace": trace})
    with open(args.preds, "a" if args.append else "w", encoding="utf-8") as f:
        for p in preds:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"wrote {args.preds}: {len(preds)} predictions; missing answers: {missing}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make")
    m.add_argument("--tasks", required=True)
    m.add_argument("--types", nargs="*")
    m.add_argument("--titles-only", action="store_true")
    m.add_argument("--corpus", default=str(ROOT / "corpus" / "papers.jsonl"), help="corpus to copy in (the hard track: corpus/hard/papers.jsonl)")
    m.add_argument("--python", help="python that has rank_bm25 installed (default: this one)")
    m.add_argument("--out", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--out", required=True)
    c.add_argument("--preds", required=True)
    c.add_argument("--agent", default="claude-code-subagent")
    c.add_argument("--append", action="store_true")
    args = ap.parse_args()
    make(args) if args.cmd == "make" else collect(args)


if __name__ == "__main__":
    main()
