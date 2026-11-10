# The console in a container. The image rebuilds both corpora from arXiv while
# it builds (about 15 minutes, since arXiv asks for 3 seconds between
# downloads), so `docker run` starts in seconds afterwards. Build it yourself
# rather than pulling a published image: most papers' licenses forbid
# redistributing their text, which is also why the text isn't in git.
FROM python:3.12-slim

WORKDIR /bench
ENV PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN python build/extract_text.py \
 && python build/extract_text.py --track hard \
 && rm -rf build/cache

# The judge runs in Ollama on the host. Pass --judge ollama:qwen3.5:9b to use it.
ENV OLLAMA_HOST=host.docker.internal:11434

EXPOSE 8765
# 0.0.0.0 so the port mapping reaches the server. --public-url is the tools
# address the console hands to agents; localhost fits an agent running on the
# host. An agent in another container needs that container's view instead.
ENTRYPOINT ["python", "app/server.py", "--host", "0.0.0.0", "--port", "8765"]
CMD ["--public-url", "http://localhost:8765"]
