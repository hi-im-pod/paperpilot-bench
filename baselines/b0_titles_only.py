"""Baseline B0: no tools, only the list of corpus IDs and titles. One call per item.

It measures how far a model gets from titles and memory alone, and how often it
invents IDs or quotes. B1 minus B0 is what reading the papers adds.

py baselines/b0_titles_only.py --tasks tasks/dev.jsonl --out preds_b0.jsonl --provider anthropic
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "baselines")]
import agent_prompts  # noqa: E402
from llm import Agent, add_provider_args  # noqa: E402

NO_TOOLS = ("You have no tools in this run. The library's full list of papers is below "
            "(ID: title). Answer from this list and what you know. Follow the same rules "
            "and the same output format.\n\n")


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--corpus", help="default: $PAPERPILOT_CORPUS, then corpus/papers.jsonl")
    ap.add_argument("--only", nargs="*")
    add_provider_args(ap)
    args = ap.parse_args()

    corpus = Path(args.corpus or os.environ.get("PAPERPILOT_CORPUS") or ROOT / "corpus" / "papers.jsonl")
    titles = "\n".join(f"{p['id']}: {p['title']}" for p in read_jsonl(corpus))
    system, templates = agent_prompts.load()
    agent = Agent(args.provider, args.model, args.effort)
    tasks = [t for t in read_jsonl(args.tasks) if not args.only or t["id"] in args.only]
    with open(args.out, "w", encoding="utf-8") as f:
        for n, task in enumerate(tasks, 1):
            t0 = time.time()
            # The title list goes first and stays identical across items, so it caches.
            user = NO_TOOLS + titles + "\n\n---\n\n" + agent_prompts.task_prompt(templates, task)
            text, trace = agent.run(system, user)
            trace["seconds"] = round(time.time() - t0, 1)
            pred = agent_prompts.to_prediction(task["id"], text, trace)
            f.write(json.dumps(pred, ensure_ascii=False) + "\n")
            f.flush()
            print(f"[{n}/{len(tasks)}] {task['id']}: tokens={trace['input_tokens']}+{trace['output_tokens']}"
                  f" cost={trace['cost_usd']} parse_error={pred['trace']['parse_error']}")
    print(f"wrote {args.out}: {len(tasks)} predictions")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
