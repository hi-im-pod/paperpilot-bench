#!/usr/bin/env bash
# One-time setup on macOS, Linux, or Git Bash on Windows: a virtualenv, the
# dependencies, and both corpora rebuilt from arXiv (about 25 minutes, because
# arXiv asks for 3 seconds between downloads). Safe to rerun: downloads are cached.
set -euo pipefail
cd "$(dirname "$0")/.."

PY=${PYTHON:-}
if [ -z "$PY" ]; then
  for c in python3 python py; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then PY=$c; break; fi
  done
fi
[ -n "$PY" ] || { echo "Python 3.11 or newer is required (set PYTHON=/path/to/python)." >&2; exit 1; }

[ -d .venv ] || "$PY" -m venv .venv
VPY=.venv/bin/python
[ -x "$VPY" ] || VPY=.venv/Scripts/python.exe   # Windows layout under Git Bash

"$VPY" -m pip install --quiet --upgrade pip
"$VPY" -m pip install --quiet -r requirements.txt

echo "Building the main corpus (138 papers)..."
"$VPY" build/extract_text.py
echo "Building the hard-track corpus (95 papers)..."
"$VPY" build/extract_text.py --track hard

if command -v ollama >/dev/null 2>&1; then
  echo "Ollama found. For judged metrics, run: ollama pull qwen3.5:9b"
else
  echo "Ollama not found. Scoring still works with --judge none; install Ollama for judged metrics."
fi
echo
echo "Done. Start the console with:  $VPY app/server.py --open"
