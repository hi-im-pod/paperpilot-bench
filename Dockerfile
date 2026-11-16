# The console in a container. The image rebuilds both corpora from arXiv while
# it builds (about 15 minutes, since arXiv asks for 3 seconds between
# downloads), so `docker run` starts in seconds afterwards. Build it yourself
# rather than pulling a published image: most papers' licenses forbid
# redistributing their text, which is also why the text isn't in git.
FROM python:3.12-slim AS bench

WORKDIR /bench
ENV PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Only what the corpus build reads, so that editing other code reuses this
# layer instead of downloading every PDF again.
COPY build/common.py build/extract_text.py build/selected.jsonl build/
COPY build/hard/selected.jsonl build/hard/
COPY tools/corpus_tools.py tools/
COPY corpus/papers.sha256 corpus/
COPY corpus/hard/papers.sha256 corpus/hard/
# extract_text.py only warns on a checksum mismatch; here a mismatch fails the
# build, because gold quotes may not line up with a different text.
RUN python build/extract_text.py \
 && python build/extract_text.py --track hard \
 && rm -rf build/cache \
 && python -c "import sys; sys.path.insert(0, 'tools'); from corpus_tools import corpus_sha256 as h; \
bad = [d for d in ('corpus', 'corpus/hard') if h(d + '/papers.jsonl') != open(d + '/papers.sha256').read().split()[0]]; \
sys.exit('corpus checksum mismatch in ' + ', '.join(bad) + '; gold quotes may not line up' if bad else 0)"

COPY . .

# The judge runs in Ollama on the host. Pass --judge ollama:qwen3.5:9b to use it,
# or use the bundled target or compose.yaml below to run Ollama in Docker too.
ENV OLLAMA_HOST=host.docker.internal:11434

EXPOSE 8765
# 0.0.0.0 so the port mapping reaches the server. --public-url is the tools
# address the console hands to agents; localhost fits an agent running on the
# host. An agent in another container needs that container's view instead.
ENTRYPOINT ["python", "app/server.py", "--host", "0.0.0.0", "--port", "8765"]
CMD ["--public-url", "http://localhost:8765"]

# Ollama inside the container: docker build --target bundled -t paperpilot-bench:ollama .
# The binary comes from the pinned Ollama image, the same version that judged the
# official rows (0.40.16; an auto-update to it changed 2 of 44 known-answer cases).
# mlx_cuda_v13 is left out, 2 GB that the host install which made those rows
# doesn't have, so the judge runs on the same llama.cpp backend.
FROM bench AS bundled
COPY --from=ollama/ollama:0.40.16 /usr/bin/ollama /usr/bin/ollama
COPY --from=ollama/ollama:0.40.16 --exclude=mlx_cuda_v13 /usr/lib/ollama /usr/lib/ollama
ENV OLLAMA_HOST=127.0.0.1:11434 NVIDIA_VISIBLE_DEVICES=all NVIDIA_DRIVER_CAPABILITIES=compute,utility
ENTRYPOINT ["sh", "scripts/docker-entrypoint.sh"]
CMD ["--public-url", "http://localhost:8765"]

# The default target stays the plain image, with no Ollama.
FROM bench
