"""Baseline B1: search, read, answer. The agent gets the four corpus tools and up to 15 calls per item.

py baselines/b1_search_read.py --tasks tasks/dev.jsonl --out preds_b1.jsonl --provider anthropic
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "baselines"), str(ROOT / "tools")]
import agent_prompts  # noqa: E402
import corpus_tools  # noqa: E402
from llm import Agent, add_provider_args  # noqa: E402


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-tool-calls", type=int, default=15)
    ap.add_argument("--only", nargs="*", help="run just these task IDs")
    add_provider_args(ap)
    args = ap.parse_args()

    system, templates = agent_prompts.load()
    schemas = json.loads((ROOT / "tools" / "tool_schemas.json").read_text(encoding="utf-8"))
    agent = Agent(args.provider, args.model, args.effort)
    tasks = [t for t in read_jsonl(args.tasks) if not args.only or t["id"] in args.only]
    with open(args.out, "w", encoding="utf-8") as f:
        for n, task in enumerate(tasks, 1):
            t0 = time.time()
            text, trace = agent.run(system, agent_prompts.task_prompt(templates, task), schemas,
                                    corpus_tools.call_tool, args.max_tool_calls)
            trace["seconds"] = round(time.time() - t0, 1)
            pred = agent_prompts.to_prediction(task["id"], text, trace)
            f.write(json.dumps(pred, ensure_ascii=False) + "\n")
            f.flush()
            print(f"[{n}/{len(tasks)}] {task['id']}: steps={trace['steps']} tokens={trace['input_tokens']}+"
                  f"{trace['output_tokens']} cost={trace['cost_usd']} parse_error={pred['trace']['parse_error']}")
    print(f"wrote {args.out}: {len(tasks)} predictions")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
