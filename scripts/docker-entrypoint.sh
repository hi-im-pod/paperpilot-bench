#!/bin/sh
# Entrypoint for the bundled image (docker build --target bundled). With JUDGE
# set, it starts Ollama inside the container, pulls and verifies the model, and
# runs the console with that judge. Without JUDGE it starts the console alone,
# like the plain image, so nobody downloads 6.6 GB they didn't ask for.
set -eu
cd /bench

if [ -z "${JUDGE:-}" ]; then
  export OLLAMA_HOST=host.docker.internal:11434
  exec python app/server.py --host 0.0.0.0 --port 8765 "$@"
fi

ollama serve >/tmp/ollama.log 2>&1 &
ollama_pid=$!
tries=0
until ollama list >/dev/null 2>&1; do
  tries=$((tries + 1))
  if [ "$tries" -gt 60 ]; then
    echo "Ollama didn't start within 60 seconds. Its log:" >&2
    cat /tmp/ollama.log >&2
    exit 1
  fi
  sleep 1
done

sh scripts/judge_model.sh "$JUDGE"

python app/server.py --host 0.0.0.0 --port 8765 --judge "ollama:$JUDGE" "$@" &
server_pid=$!
# This shell is PID 1, so docker stop's SIGTERM lands here. Without passing it
# on, docker stop waits its full 10 seconds and then kills everything.
trap 'kill "$server_pid" "$ollama_pid" 2>/dev/null' INT TERM
wait "$server_pid" || true
kill "$ollama_pid" 2>/dev/null || true
