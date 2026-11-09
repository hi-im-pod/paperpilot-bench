"""Shared helpers for the build scripts: paths, cached HTTP, JSONL."""
import hashlib
import json
import os
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "build" / "cache"
USER_AGENT = "paperpilot-bench/0.1 (course benchmark build script)"


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path, records):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


class CachedClient:
    """HTTP client that caches every response body on disk.

    Reruns of the build must not hit the APIs again: S2 allows about one
    request per second without a key, and arXiv asks for 3 s between requests.
    """

    def __init__(self, name, min_interval, headers=None, timeout=60, tries=5):
        self.dir = CACHE / name
        self.dir.mkdir(parents=True, exist_ok=True)
        self.min_interval = min_interval
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        if headers:
            self.session.headers.update(headers)
        self._last = 0.0
        self.timeout = timeout
        self.tries = tries

    def _key(self, method, url, params, body):
        raw = json.dumps([method, url, params, body], sort_keys=True)
        return self.dir / (hashlib.sha256(raw.encode()).hexdigest()[:32])

    def request(self, method, url, params=None, json_body=None, binary=False):
        tries = self.tries
        path = self._key(method, url, params, json_body)
        if path.exists():
            data = path.read_bytes()
            return data if binary else data.decode("utf-8")
        for attempt in range(tries):
            wait = self.min_interval - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
            try:
                r = self.session.request(method, url, params=params, json=json_body, timeout=self.timeout)
            except requests.RequestException as e:
                print(f"  network error ({e}); retry {attempt + 1}/{tries}")
                time.sleep(2 ** attempt * 2)
                continue
            if r.status_code == 429 or r.status_code >= 500:
                print(f"  HTTP {r.status_code} on {url}; retry {attempt + 1}/{tries}")
                time.sleep(min(2 ** attempt * 3, 120))
                continue
            if r.status_code != 200:
                print(f"  HTTP {r.status_code} on {url}; skipping")
                return None
            path.write_bytes(r.content)
            return r.content if binary else r.text
        print(f"  gave up on {url}")
        return None


def s2_client():
    key = os.environ.get("S2_API_KEY")
    headers = {"x-api-key": key} if key else None
    # The keyless S2 pool is shared by everyone and throttles in bursts; a batch
    # that gives up after 5 tries drops up to 100 papers, so wait it out longer.
    return CachedClient("s2", min_interval=0.2 if key else 1.1, headers=headers, tries=10)


def arxiv_client():
    return CachedClient("arxiv", min_interval=3.0, timeout=180)


def bare_arxiv_id(raw):
    """'2307.15043v2' or 'arXiv:2307.15043' -> '2307.15043'."""
    raw = raw.split(":")[-1].split("/abs/")[-1]
    if "v" in raw and raw.rsplit("v", 1)[-1].isdigit():
        raw = raw.rsplit("v", 1)[0]
    return raw
