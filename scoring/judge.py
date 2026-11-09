"""Local LLM judge for the three things string math can't score.

Prompts are read verbatim from prompts/judge.md. Every decision is cached by
(model digest, prompt version, prompt name, filled prompt), so reruns are free
and give the same answers.

Validation:
  py scoring/judge.py --sample 30 --results results.json --out judge_sample.csv
  (a teammate fills in human_label)
  py scoring/judge.py --agreement judge_sample.csv
"""
import argparse
import csv
import hashlib
import json
import os
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPTS_FILE = ROOT / "prompts" / "judge.md"
CACHE_FILE = Path(__file__).resolve().parent / ".judge_cache.jsonl"
# Bump on any edit to prompts/judge.md: the version is part of the cache key.
JUDGE_PROMPT_VERSION = 1
DEFAULT_MODEL = "qwen3.5:9b"


def load_prompts(path=PROMPTS_FILE):
    text = path.read_text(encoding="utf-8")
    prompts = {}
    for name in ("claim_support", "text_equiv", "followup_score"):
        m = re.search(rf"## \d+\. {name}\s*\n+```\n(.*?)\n```", text, re.S)
        if not m:
            raise ValueError(f"prompt {name} not found in {path}")
        prompts[name] = m.group(1)
    return prompts


def fill(template, **values):
    # str.format would trip over the JSON braces in the prompts.
    for k, v in values.items():
        template = template.replace("{" + k + "}", str(v))
    return template


def _valid(name, obj):
    if name == "claim_support":
        return obj.get("label") in ("supported", "partial", "unsupported")
    if name == "text_equiv":
        return isinstance(obj.get("equivalent"), bool)
    return all(isinstance(obj.get(k), int) and 1 <= obj[k] <= 5 for k in ("specific", "grounded", "novel"))


ERROR_RESULT = {"claim_support": {"label": "error"}, "text_equiv": {"equivalent": False, "error": True},
                "followup_score": {"specific": None, "grounded": None, "novel": None, "error": True}}


def ollama_host():
    # OLLAMA_HOST=0.0.0.0 is a common server bind setting, but a client can't
    # connect to 0.0.0.0 on Windows, so point it at loopback instead.
    host = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434")
    return host.replace("0.0.0.0", "127.0.0.1")


class Judge:
    def __init__(self, model=DEFAULT_MODEL, host=None, use_cache=True):
        import ollama
        self.client = ollama.Client(host=host or ollama_host())
        self.model = model
        tags = {m.model: m.digest for m in self.client.list().models}
        if model not in tags:
            raise SystemExit(f"judge model {model!r} is not pulled; run: ollama pull {model}")
        self.digest = tags[model]
        self.prompts = load_prompts()
        # Off only for judge_eval.py, which reruns each case to check the model is deterministic.
        self.use_cache = use_cache
        self.cache = {}
        if use_cache and CACHE_FILE.exists():
            for line in CACHE_FILE.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    self.cache[rec["key"]] = rec["result"]
        self.calls = self.cache_hits = self.errors = 0
        self.decisions = []

    @classmethod
    def from_spec(cls, spec):
        provider, _, model = spec.partition(":")
        if provider != "ollama" or not model:
            raise SystemExit(f"--judge must be ollama:<tag> or none, got {spec!r}")
        return cls(model)

    def info(self):
        return {"model": self.model, "digest": self.digest, "prompt_version": JUDGE_PROMPT_VERSION,
                "calls": self.calls, "cache_hits": self.cache_hits, "errors": self.errors}

    def _chat(self, prompt):
        kwargs = dict(model=self.model, messages=[{"role": "user", "content": prompt}], format="json",
                      options={"temperature": 0, "seed": 0})
        try:
            # Qwen 3.5 thinks by default; thinking is slower and adds nothing to a one-label decision.
            resp = self.client.chat(**kwargs, think=False)
        except Exception:
            resp = self.client.chat(**kwargs)
        return resp.message.content

    def _ask(self, name, inputs):
        prompt = fill(self.prompts[name], **inputs)
        key = hashlib.sha256(json.dumps([self.digest, JUDGE_PROMPT_VERSION, name, prompt]).encode()).hexdigest()
        if key in self.cache:
            self.cache_hits += 1
            result = self.cache[key]
        else:
            result = None
            for _ in range(2):  # one retry on bad JSON
                self.calls += 1
                try:
                    obj = json.loads(self._chat(prompt))
                    if isinstance(obj, dict) and _valid(name, obj):
                        result = obj
                        break
                except json.JSONDecodeError:
                    pass
            if result is None:
                self.errors += 1
                result = ERROR_RESULT[name]
            elif self.use_cache:
                self.cache[key] = result
                with open(CACHE_FILE, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"key": key, "name": name, "result": result}) + "\n")
        self.decisions.append({"kind": name, "inputs": inputs, "result": result})
        return result

    def claim_support(self, claim, passage):
        return self._ask("claim_support", {"claim": claim, "passage": passage})

    def text_equiv(self, column, setting, gold, pred):
        return self._ask("text_equiv", {"column": column, "setting": setting, "gold": gold, "pred": pred})

    def followup_score(self, topic, paper_titles, question, gap_notes):
        return self._ask("followup_score", {"topic": topic, "paper_titles": "; ".join(paper_titles),
                                            "question": question, "gap_notes": gap_notes or "(none)"})


# ---------- validation against human labels ----------

def judge_label(d):
    r = d["result"]
    if d["kind"] == "claim_support":
        return r.get("label")
    if d["kind"] == "text_equiv":
        return str(r.get("equivalent")).lower()
    return "/".join(str(r.get(k)) for k in ("specific", "grounded", "novel"))


def export_sample(results_path, n, out_path, seed=0):
    decisions = json.loads(Path(results_path).read_text(encoding="utf-8")).get("judge_decisions") or []
    if not decisions:
        raise SystemExit("no judge_decisions in results; score with --judge ollama:<tag> first")
    sample = random.Random(seed).sample(decisions, min(n, len(decisions)))
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["kind", "inputs", "judge_label", "human_label"])
        for d in sample:
            w.writerow([d["kind"], json.dumps(d["inputs"], ensure_ascii=False), judge_label(d), ""])
    print(f"wrote {out_path}: {len(sample)} decisions. Fill human_label without looking at judge_label.")
    print("  claim_support: supported|partial|unsupported   text_equiv: true|false   followup_score: s/g/n, e.g. 4/2/5")


def cohen_kappa(a, b):
    labels = sorted(set(a) | set(b))
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(lab) / n) * (b.count(lab) / n) for lab in labels)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def agreement(csv_path):
    rows = [r for r in csv.DictReader(open(csv_path, encoding="utf-8")) if r["human_label"].strip()]
    if not rows:
        raise SystemExit("no human_label filled in yet")
    for kind in ("claim_support", "text_equiv"):
        rs = [r for r in rows if r["kind"] == kind]
        if rs:
            a = [r["judge_label"].strip().lower() for r in rs]
            b = [r["human_label"].strip().lower() for r in rs]
            agree = sum(x == y for x, y in zip(a, b)) / len(rs)
            print(f"{kind}: n={len(rs)} agreement={agree:.2f} kappa={cohen_kappa(a, b):.2f}")
    rs = [r for r in rows if r["kind"] == "followup_score" and "None" not in r["judge_label"]]
    if rs:
        diffs = [[abs(int(x) - int(y)) for x, y in zip(r["judge_label"].split("/"), r["human_label"].split("/"))]
                 for r in rs]
        mae = [sum(d[i] for d in diffs) / len(diffs) for i in range(3)]
        print(f"followup_score: n={len(rs)} mean abs diff specific={mae[0]:.2f} grounded={mae[1]:.2f} novel={mae[2]:.2f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sample", type=int)
    ap.add_argument("--results")
    ap.add_argument("--out", default="judge_sample.csv")
    ap.add_argument("--agreement")
    ap.add_argument("--smoke", metavar="MODEL", help="run one decision of each kind against a pulled model")
    args = ap.parse_args()
    if args.agreement:
        agreement(args.agreement)
    elif args.sample:
        export_sample(args.results, args.sample, args.out)
    elif args.smoke:
        j = Judge(args.smoke)
        print(j.claim_support("The defense cuts attack success to under 5% on every model tested.",
                              "our defense lowers attack success rate to 3.1% on llama-2 and 4.4% on vicuna, "
                              "but on gpt-3.5 it remains at 21%."))
        print(j.text_equiv("base_model", "main table", "Llama-2-7B-Chat", "LLaMA 2 7B chat"))
        print(j.followup_score("jailbreak defenses", ["A paper on suffix attacks"],
                               "How can LLMs be made safer?", "No adaptive-attack evaluation."))
        print(j.info())
    else:
        ap.print_help()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
