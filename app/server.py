"""PaperPilot-Bench run console: connect an HTTP agent, run a split, see scores.

py app/server.py                      # http://127.0.0.1:8765
py app/server.py --port 9000 --judge ollama:qwen3.5:9b

The agent contract (see README, "Connect your agent"):
  GET  <agent>/health             -> 200, optional {"name": "..."}
  POST <agent>/solve              <- {"task": {...}, "tools_url": "...", "run_id": "...", "item_id": "..."}
                                  -> {"abstain": bool, "output": {...}, "trace": {...}}
  POST <tools_url>/<tool>         <- the tool's arguments as JSON  -> {"result": ...} or {"error": "..."}
     tools: search {query, k}, read {paper_id, section}, list_sections {paper_id}, get_metadata {paper_id}

Uses only the standard library, so it runs wherever the scorer runs.
"""
import argparse
import json
import os
import re
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "scoring"), str(ROOT / "tools")]
import corpus_tools  # noqa: E402
import score as scoring  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
RUNS_DIR = Path(__file__).resolve().parent / "runs"
TOOL_NAMES = set(corpus_tools.TOOLS)


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def http_json(method, url, body=None, timeout=10):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return json.loads(raw) if raw.strip() else {}


class Run:
    def __init__(self, bench, agent_url, split, judge_spec, timeout, workers, budget, item_ids):
        self.id = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        self.bench, self.split, self.agent_url = bench, split, agent_url.rstrip("/")
        self.judge_spec, self.timeout, self.workers, self.budget = judge_spec, timeout, workers, budget
        tasks = bench.splits[split]["tasks"]
        self.tasks = [t for t in tasks if not item_ids or t["id"] in item_ids]
        self.items = {t["id"]: {"id": t["id"], "type": t["type"], "status": "queued", "steps": 0,
                                "seconds": None, "error": None, "primary": None} for t in self.tasks}
        self.preds = {}
        self.status, self.error, self.results, self.agent_name = "running", None, None, None
        self.started, self.finished = time.time(), None
        self.lock = threading.Lock()

    @classmethod
    def load(cls, bench, d):
        """Rebuild a finished run from app/runs/<id>, so history survives a restart."""
        st = json.loads((d / "state.json").read_text(encoding="utf-8"))
        if st.get("split") not in bench.splits:
            return None
        run = cls.__new__(cls)
        run.id, run.bench, run.split, run.agent_url = st["id"], bench, st["split"], st["agent_url"]
        run.judge_spec, run.budget, run.agent_name = st.get("judge"), st.get("budget"), st.get("agent_name")
        run.timeout, run.workers, run.lock = None, 1, threading.Lock()
        run.items = {i["id"]: i for i in st["items"]}
        run.tasks = [t for t in bench.splits[run.split]["tasks"] if t["id"] in run.items]
        run.preds = {p["id"]: p for p in read_jsonl(d / "preds.jsonl")} if (d / "preds.jsonl").exists() else {}
        run.results = json.loads((d / "results.json").read_text(encoding="utf-8")) if (d / "results.json").exists() else None
        run.status, run.error = st["status"], st.get("error")
        if run.status in ("running", "scoring"):
            run.status, run.error = "error", "the console stopped before this run finished"
        run.started, run.finished = 0.0, float(st.get("elapsed") or 0)
        return run

    def tools_url(self, item_id):
        return f"{self.bench.base_url}/runs/{self.id}/items/{item_id}/tools"

    def call_tool(self, item_id, name, args):
        with self.lock:
            item = self.items.get(item_id)
            if item is None:
                return {"error": f"unknown item {item_id}"}
            if self.budget and item["steps"] >= self.budget:
                return {"error": f"tool budget of {self.budget} calls used up for {item_id}; return your answer"}
            item["steps"] += 1
        with corpus_tools.using_corpus(self.bench.splits[self.split]["corpus_path"]):
            out = corpus_tools.call_tool(name, args if isinstance(args, dict) else {})
        if isinstance(out, str) and out.startswith("error:"):
            return {"error": out[len("error: "):]}
        return {"result": out if name == "read" else json.loads(out)}

    def solve(self, task):
        item = self.items[task["id"]]
        item["status"] = "running"
        t0 = time.time()
        try:
            pred = http_json("POST", f"{self.agent_url}/solve",
                             {"task": task, "tools_url": self.tools_url(task["id"]), "run_id": self.id,
                              "item_id": task["id"]}, timeout=self.timeout)
            if not isinstance(pred, dict) or not ("output" in pred or "abstain" in pred):
                raise ValueError("response has neither 'output' nor 'abstain'")
            trace = {**(pred.get("trace") or {}), "tool_calls": item["steps"], "seconds": round(time.time() - t0, 1)}
            self.preds[task["id"]] = {"id": task["id"], "abstain": bool(pred.get("abstain")),
                                      "output": pred.get("output") or {}, "trace": trace}
            item["status"] = "answered"
        except Exception as e:  # any agent failure is that item's failure, not the run's
            item["status"], item["error"] = "failed", f"{type(e).__name__}: {e}"[:300]
        item["seconds"] = round(time.time() - t0, 1)

    def run(self):
        try:
            try:
                health = http_json("GET", f"{self.agent_url}/health", timeout=5)
                self.agent_name = health.get("name") if isinstance(health, dict) else None
            except Exception:
                pass
            with ThreadPoolExecutor(max_workers=self.workers) as pool:
                list(pool.map(self.solve, self.tasks))
            self.score()
        except Exception as e:
            self.status, self.error = "error", f"{type(e).__name__}: {e}"
            traceback.print_exc()
        self.finished = time.time()
        self.save()

    def score(self):
        gold = self.bench.splits[self.split]["gold"]
        if gold is None:
            self.status = "no_gold"
            return
        self.status = "scoring"
        judge = None
        if self.judge_spec and self.judge_spec != "none":
            from judge import Judge
            judge = Judge.from_spec(self.judge_spec)
        corpus = self.bench.corpora[self.bench.splits[self.split]["corpus_path"]]["corpus"]
        res = scoring.score_all(self.tasks, gold, list(self.preds.values()), corpus, judge)
        for rec in res["items"]:
            self.items[rec["id"]]["primary"] = rec["primary"]
        self.results = res
        self.status = "done"

    def summary(self):
        """The block a team pastes into the leaderboard."""
        if not self.results:
            return None
        r = self.results
        return {"bench": "paperpilot-bench", "split": self.split, "agent": self.agent_name or self.agent_url,
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "n_items": r["n_items"],
                "per_type": {k: (None if v["primary_mean"] is None else round(v["primary_mean"], 4))
                             for k, v in r["per_type"].items()},
                "hallucination_rate": round(r["hallucination_rate"], 4),
                "macro_avg": None if r["macro_avg"] is None else round(r["macro_avg"], 4),
                "judge": (r.get("judge") or {}).get("model", "none"),
                "corpus_sha256": self.bench.corpora[self.bench.splits[self.split]["corpus_path"]]["sha"][:16]}

    def state(self, full=False):
        out = {"id": self.id, "split": self.split, "agent_url": self.agent_url, "agent_name": self.agent_name,
               "status": self.status, "error": self.error, "judge": self.judge_spec, "budget": self.budget,
               "elapsed": round((self.finished or time.time()) - self.started, 1), "items": list(self.items.values()),
               "has_gold": self.bench.splits[self.split]["gold"] is not None}
        if self.results:
            out["results"] = {k: self.results[k] for k in ("per_type", "hallucination_rate", "macro_avg", "trace_means", "judge")}
            out["summary"] = self.summary()
        return out

    def save(self):
        d = RUNS_DIR / self.id
        d.mkdir(parents=True, exist_ok=True)
        (d / "preds.jsonl").write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in self.preds.values()),
                                       encoding="utf-8")
        (d / "state.json").write_text(json.dumps(self.state(), indent=1), encoding="utf-8")
        if self.results:
            (d / "results.json").write_text(json.dumps(self.results, indent=1, default=str), encoding="utf-8")


class Bench:
    def __init__(self, splits, corpus_path, host, port, default_judge, public_url=None):
        """splits: {name: (tasks, gold) or (tasks, gold, corpus)}; corpus defaults to corpus_path."""
        import hashlib
        self.splits, self.corpora = {}, {}
        for name, spec in splits.items():
            tasks, gold = spec[0], spec[1]
            corpus = str(spec[2] if len(spec) > 2 else corpus_path)
            if not Path(tasks).exists() or not Path(corpus).exists():
                continue
            if corpus not in self.corpora:
                self.corpora[corpus] = {"corpus": scoring.load_corpus(corpus),
                                        "sha": hashlib.sha256(Path(corpus).read_bytes()).hexdigest()}
            self.splits[name] = {"tasks": read_jsonl(tasks), "corpus_path": corpus,
                                 "gold": read_jsonl(gold) if gold and Path(gold).exists() else None}
        self.default_corpus = str(corpus_path)
        os.environ["PAPERPILOT_CORPUS"] = self.default_corpus
        self.corpus = scoring.load_corpus(corpus_path)
        self.corpus_sha = hashlib.sha256(Path(corpus_path).read_bytes()).hexdigest()
        # Agents reach the tools at base_url; behind --host 0.0.0.0 that has to be an address they can route to.
        self.base_url = (public_url or f"http://{host}:{port}").rstrip("/")
        self.default_judge = default_judge
        self.runs = {}
        for d in sorted(RUNS_DIR.glob("*/state.json")) if RUNS_DIR.exists() else []:
            try:
                run = Run.load(self, d.parent)
            except Exception as e:  # one damaged run folder shouldn't stop the console
                print(f"skipped saved run {d.parent.name}: {e}")
                continue
            if run:
                self.runs[run.id] = run

    def judges(self):
        out = ["none"]
        try:
            from judge import ollama_host
            tags = http_json("GET", f"http://{ollama_host()}/api/tags", timeout=2)
            out += [f"ollama:{m['name']}" for m in tags.get("models", []) if "embed" not in m["name"]]
        except Exception:
            pass
        return out

    def info(self):
        return {"splits": {k: {"n": len(v["tasks"]), "has_gold": v["gold"] is not None,
                               "papers": len(self.corpora[v["corpus_path"]]["corpus"].papers)}
                           for k, v in self.splits.items()},
                "judges": self.judges(), "default_judge": self.default_judge,
                "corpus": {"papers": len(self.corpus.papers), "sha256": self.corpus_sha[:16]},
                "tools_url_example": f"{self.base_url}/runs/<run_id>/items/<item_id>/tools"}

    def item_detail(self, run, item_id):
        task = next((t for t in run.tasks if t["id"] == item_id), None)
        if task is None:
            return None
        gold = run.bench.splits[run.split]["gold"]
        g = next((x for x in gold if x["id"] == item_id), None) if gold else None
        rec = next((r for r in (run.results or {}).get("items", []) if r["id"] == item_id), None)
        return {"task": task, "prediction": run.preds.get(item_id), "gold": g, "status": run.items[item_id],
                "metrics": rec["metrics"] if rec else None, "hallucinated_ids": rec["hallucinated_ids"] if rec else None}


def make_handler(bench):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass  # one line per tool call would bury the console

        def send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False, default=str).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def body(self):
            n = int(self.headers.get("Content-Length") or 0)
            try:
                return json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError:
                return None

        def do_GET(self):
            p = self.path.split("?")[0]
            if p in ("/", "/index.html"):
                return self.send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            if p == "/api/info":
                return self.send(200, bench.info())
            if p == "/api/runs":
                return self.send(200, [r.state() | {"items": None} for r in sorted(bench.runs.values(), key=lambda r: r.id, reverse=True)])
            if p == "/tools/schemas":
                return self.send(200, (ROOT / "tools" / "tool_schemas.json").read_bytes())
            m = re.fullmatch(r"/api/runs/([\w-]+)(?:/(preds\.jsonl|summary|items/([\w-]+)))?", p)
            if m and m.group(1) in bench.runs:
                run = bench.runs[m.group(1)]
                if m.group(2) is None:
                    return self.send(200, run.state())
                if m.group(2) == "preds.jsonl":
                    data = "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in run.preds.values()).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/x-ndjson")
                    self.send_header("Content-Disposition", f'attachment; filename="preds_{run.split}_{run.id}.jsonl"')
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    return self.wfile.write(data)
                if m.group(2) == "summary":
                    return self.send(200, run.summary() or {"error": "no scores yet"})
                detail = bench.item_detail(run, m.group(3))
                return self.send(200 if detail else 404, detail or {"error": "unknown item"})
            self.send(404, {"error": f"no route {p}"})

        def do_POST(self):
            p = self.path.split("?")[0]
            body = self.body()
            if body is None:
                return self.send(400, {"error": "body must be JSON"})
            m = re.fullmatch(r"/runs/([\w-]+)/items/([\w-]+)/tools/(\w+)", p)
            if m:
                run = bench.runs.get(m.group(1))
                if run is None:
                    return self.send(404, {"error": f"unknown run {m.group(1)}"})
                if m.group(3) not in TOOL_NAMES:
                    # 200, not 404: models invent tool names, and the error has to reach the
                    # model as text it can correct, like every other tool error.
                    return self.send(200, {"error": f"no tool named {m.group(3)!r}; the tools are {', '.join(sorted(TOOL_NAMES))}"})
                return self.send(200, run.call_tool(m.group(2), m.group(3), body))
            m = re.fullmatch(r"/tools/(\w+)", p)
            if m and m.group(1) in TOOL_NAMES:
                # Unscoped tools, for poking at the corpus while building an agent.
                out = corpus_tools.call_tool(m.group(1), body)
                if out.startswith("error:"):
                    return self.send(200, {"error": out[len("error: "):]})
                return self.send(200, {"result": out if m.group(1) == "read" else json.loads(out)})
            if p == "/api/check_agent":
                url = (body.get("agent_url") or "").rstrip("/")
                try:
                    health = http_json("GET", f"{url}/health", timeout=5)
                    return self.send(200, {"ok": True, "name": health.get("name") if isinstance(health, dict) else None})
                except Exception as e:
                    return self.send(200, {"ok": False, "error": f"{url}/health did not answer: {e}"})
            if p == "/api/runs":
                split = body.get("split")
                if split not in bench.splits:
                    return self.send(400, {"error": f"unknown split {split!r}"})
                if not body.get("agent_url"):
                    return self.send(400, {"error": "agent_url is required"})
                run = Run(bench, body["agent_url"], split, body.get("judge") or bench.default_judge,
                          float(body.get("timeout") or 300), max(1, min(8, int(body.get("workers") or 1))),
                          int(body["budget"]) if body.get("budget") else None, body.get("item_ids"))
                bench.runs[run.id] = run
                threading.Thread(target=run.run, daemon=True).start()
                return self.send(200, {"id": run.id})
            self.send(404, {"error": f"no route {p}"})

    return Handler


def serve(bench, host, port):
    server = ThreadingHTTPServer((host, port), make_handler(bench))
    return server


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--corpus", default=str(ROOT / "corpus" / "papers.jsonl"))
    ap.add_argument("--judge", default="none", help="default judge for runs, e.g. ollama:qwen3.5:9b")
    ap.add_argument("--public-url", help="address agents use to reach this console, when serving beyond localhost "
                    "(e.g. --host 0.0.0.0 --public-url http://192.168.0.12:8765)")
    ap.add_argument("--open", action="store_true", help="open the console in your browser")
    args = ap.parse_args()
    if not Path(args.corpus).exists():
        raise SystemExit("corpus/papers.jsonl is missing; build it with: py build/extract_text.py")
    splits = {s: (ROOT / "tasks" / f"{s}.jsonl", ROOT / "gold" / f"{s}_gold.jsonl") for s in ("dev", "test")}
    # The hard track: recent papers in their own corpus, offered when it has been built.
    hard_corpus = ROOT / "corpus" / "hard" / "papers.jsonl"
    for s in ("dev", "test"):
        splits[f"hard_{s}"] = (ROOT / "tasks" / "hard" / f"{s}.jsonl", ROOT / "gold" / "hard" / f"{s}_gold.jsonl", hard_corpus)
    bench = Bench(splits, args.corpus, args.host, args.port, args.judge, args.public_url)
    server = serve(bench, args.host, args.port)
    print(f"PaperPilot-Bench console at {bench.base_url}  (splits: "
          + ", ".join(f"{k} {v['n']} items{'' if v['has_gold'] else ', no gold'}" for k, v in bench.info()["splits"].items()) + ")")
    try:
        if args.open:
            import webbrowser
            webbrowser.open(bench.base_url)
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
