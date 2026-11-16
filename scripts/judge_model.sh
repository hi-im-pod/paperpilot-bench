#!/bin/sh
# Pulls the judge model if it's missing, then checks it's the exact build that
# judged the official rows. Ollama pulls by tag, so a re-tagged upload would
# otherwise change scores without any error. Used by both Docker options.
#
#   sh scripts/judge_model.sh [model]      (default qwen3.5:9b)
#
# JUDGE_DIGEST overrides the expected ID; for models with no known ID the check
# only warns.
set -eu
model="${1:-qwen3.5:9b}"
case "$model" in
  qwen3.5:9b) expected="${JUDGE_DIGEST:-56671c2ab938}" ;;
  *) expected="${JUDGE_DIGEST:-}" ;;
esac

if ! ollama show "$model" >/dev/null 2>&1; then
  echo "Pulling $model. This happens once per volume (6.6 GB for qwen3.5:9b)."
  ollama pull "$model"
fi

actual=$(ollama list | awk -v m="$model" '$1 == m { print $2 }')
if [ -z "$expected" ]; then
  echo "Warning: no known ID for $model ($actual), so scores may not match the official rows."
elif [ "$actual" != "$expected" ]; then
  echo "Error: $model has ID $actual, but the official rows used $expected." >&2
  echo "The tag now points to a different build. Set JUDGE_DIGEST=$actual to use it anyway." >&2
  exit 1
else
  echo "Judge model $model verified ($actual)."
fi
