"""Reference agent for the PaperPilot-Bench HTTP contract. Copy it and swap in your own logic.

py examples/http_agent.py --provider ollama                 # free, local qwen3.5:9b
py examples/http_agent.py --provider anthropic --port 8001  # needs ANTHROPIC_API_KEY

Then point the console (py app/server.py) at http://127.0.0.1:8001.

It answers GET /health and POST /solve. For each task it runs the B1 loop:
the system prompt and task template from prompts/agent.md, the four corpus
tools (called over HTTP at the tools_url the bench sends), and a final JSON answer.
"""
import argparse
import json
import sys
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "baselines"))
import agent_prompts  # noqa: E402
from llm import Agent, add_provider_args  # noqa: E402

SCHEMAS = json.loads((ROOT / "tools" / "tool_schemas.json").read_text(encoding="utf-8"))


def http_tools(tools_url):
    def call(name, args):
        req = urllib.request.Request(f"{tools_url}/{name}", data=json.dumps(args or {}).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            out = json.loads(resp.read())
        if "error" in out:
            return f"error: {out['error']}"
        r = out["result"]
        return r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)
    return call


def make_handler(agent, max_tool_calls):
    system, templates = agent_prompts.load()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def send(self, code, obj):
            data = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/health":
                return self.send(200, {"name": f"reference-b1 ({agent.provider}:{agent.model})"})
            self.send(404, {"error": "not found"})

        def do_POST(self):
            if self.path != "/solve":
                return self.send(404, {"error": "not found"})
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
            task = req["task"]
            text, trace = agent.run(system, agent_prompts.task_prompt(templates, task), SCHEMAS,
                                    http_tools(req["tools_url"]), max_tool_calls)
            pred = agent_prompts.to_prediction(task["id"], text, trace)
            print(f"{task['id']}: steps={trace['steps']} parse_error={pred['trace']['parse_error']}", flush=True)
            self.send(200, {"abstain": pred["abstain"], "output": pred["output"], "trace": pred["trace"]})

    return Handler


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8001)
    ap.add_argument("--max-tool-calls", type=int, default=15)
    add_provider_args(ap)
    args = ap.parse_args()
    agent = Agent(args.provider, args.model, args.effort)
    print(f"reference agent ({agent.provider}:{agent.model}) on http://{args.host}:{args.port}")
    ThreadingHTTPServer((args.host, args.port), make_handler(agent, args.max_tool_calls)).serve_forever()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
