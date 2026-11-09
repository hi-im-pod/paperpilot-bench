import json
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from conftest import FIXTURE_CORPUS, ROOT, perfect_preds

sys.path.insert(0, str(ROOT / "app"))
import server as app  # noqa: E402


def post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=10).read())


def get(url):
    return json.loads(urllib.request.urlopen(url, timeout=10).read())


class FakeAgent(BaseHTTPRequestHandler):
    """Calls one tool per item over HTTP, then returns the perfect fixture answer."""
    answers = {p["id"]: p for p in perfect_preds()}

    def log_message(self, *a):
        pass

    def reply(self, obj):
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.reply({"name": "fake-agent"})

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        hits = post(req["tools_url"] + "/search", {"query": "retrieval", "k": 2})
        assert "result" in hits
        missing = post(req["tools_url"] + "/read", {"paper_id": "9999.99999"})
        assert "error" in missing
        a = self.answers[req["task"]["id"]]
        self.reply({"abstain": a["abstain"], "output": a["output"]})


def start(server):
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_run_through_the_console(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "RUNS_DIR", tmp_path)
    tasks, gold = tmp_path / "t.jsonl", tmp_path / "g.jsonl"
    from conftest import GOLD, TASKS
    tasks.write_text("\n".join(json.dumps(t) for t in TASKS), encoding="utf-8")
    gold.write_text("\n".join(json.dumps(g) for g in GOLD), encoding="utf-8")

    agent = start(ThreadingHTTPServer(("127.0.0.1", 0), FakeAgent))
    bench_srv = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    port = bench_srv.server_address[1]
    bench_srv.server_close()
    bench = app.Bench({"dev": (tasks, gold), "test": (tasks, None)}, FIXTURE_CORPUS, "127.0.0.1", port, "none")
    start(app.serve(bench, "127.0.0.1", port))
    base, agent_url = f"http://127.0.0.1:{port}", f"http://127.0.0.1:{agent.server_address[1]}"

    assert get(base + "/api/info")["splits"]["dev"] == {"n": len(TASKS), "has_gold": True, "papers": 3}
    assert post(base + "/api/check_agent", {"agent_url": agent_url}) == {"ok": True, "name": "fake-agent"}
    run_id = post(base + "/api/runs", {"agent_url": agent_url, "split": "dev", "workers": 2})["id"]
    for _ in range(100):
        state = get(f"{base}/api/runs/{run_id}")
        if state["status"] not in ("running", "scoring"):
            break
        time.sleep(0.1)
    assert state["status"] == "done", state
    assert all(i["steps"] == 2 for i in state["items"])
    assert state["results"]["per_type"]["find_papers"]["primary_mean"] == 1.0
    assert state["results"]["per_type"]["traps"]["primary_mean"] == 1.0
    assert state["summary"]["agent"] == "fake-agent"
    detail = get(f"{base}/api/runs/{run_id}/items/fp-1")
    assert detail["gold"]["relevant"] and detail["prediction"]["trace"]["tool_calls"] == 2

    # A split with no gold returns predictions to download, not scores.
    run2 = post(base + "/api/runs", {"agent_url": agent_url, "split": "test", "budget": 1})["id"]
    for _ in range(100):
        state2 = get(f"{base}/api/runs/{run2}")
        if state2["status"] not in ("running", "scoring"):
            break
        time.sleep(0.1)
    assert state2["status"] == "no_gold" and "results" not in state2
    # Budget 1: the second tool call per item is refused, so steps stop at 1.
    assert all(i["steps"] == 1 for i in state2["items"])
    preds = urllib.request.urlopen(f"{base}/api/runs/{run2}/preds.jsonl").read().decode().splitlines()
    assert len(preds) == len(TASKS)
