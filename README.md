# PaperPilot-Bench

A closed-world benchmark for research-literature agents. Given a topic or question, an agent must find relevant papers, fill comparison tables, recover citation links, answer with claims backed by verbatim quotes, and propose follow-up questions. It works inside a fixed corpus of full-text arXiv papers on LLM security, retrieval-augmented generation, and LLM agents.

## Quick start

```
py -m venv .venv && .venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python build\extract_text.py
.venv\Scripts\python baselines\b1_search_read.py --tasks tasks\dev.jsonl --out preds.jsonl --provider anthropic
.venv\Scripts\python scoring\score.py --tasks tasks\dev.jsonl --gold gold\dev_gold.jsonl --preds preds.jsonl --judge ollama:qwen3.5:9b
```

The second line builds the corpus. The paper text isn't in this repo, because 81 of the 138 papers are under arXiv's default license, which doesn't allow redistribution. `build/extract_text.py` downloads each paper's PDF from arXiv at the exact version we used (listed in `build/selected.jsonl`), splits it into sections, and writes `corpus/papers.jsonl`. It takes about 10 minutes, since arXiv asks for 3 seconds between requests. It ends by checking the result against `corpus/papers.sha256`. If it prints a mismatch, your corpus differs from ours and gold quotes may not line up, so tell us.

On macOS or Linux, use `python3 -m venv .venv` and `.venv/bin/python`. For the judge, install [Ollama](https://ollama.com) and run `ollama pull qwen3.5:9b`. To score without it, pass `--judge none`.

The baselines read `ANTHROPIC_API_KEY` (or an `ant auth login` profile) for `--provider anthropic` and `OPENAI_API_KEY` for `--provider openai`. `--provider ollama` runs a local model for free, which is enough to check that your plumbing works.

## Rules

1. **Closed corpus.** Your agent may learn about papers only through the four tools in `tools/corpus_tools.py`. No web access and no outside APIs. Semantic Scholar and similar services would hand over the citation answers.
2. **Cite by corpus ID.** IDs are bare arXiv numbers such as `2210.03629`. Any ID that isn't in `corpus/papers.jsonl` counts as a hallucinated citation.
3. **Quote verbatim.** Quotes are checked against the paper text, and every number in a quote must appear exactly.
4. **Abstain when the corpus doesn't answer.** Some items are traps with no correct answer in the corpus. Abstaining on those scores full marks, and returning any paper scores zero.
5. **One JSON object per item**, in the schemas below.

Your agent can be built any way you like: any model, any framework, any prompt. `prompts/agent.md` is our reference prompt and `baselines/b1_search_read.py` is our reference agent. Both are starting points, not requirements.

## The hard track

The main corpus is well-known 2017–2023 work, and frontier models know much of it by heart. With only the paper titles, Claude scored 0.93 on our test set, against 0.97 with the tools. The hard track uses 95 papers first submitted from July to October 2026, after current models' training data. There, an agent has to read.

- **Corpus:** `corpus/hard/papers.jsonl`. Build it with `py build/extract_text.py --track hard`; it's checked against `corpus/hard/papers.sha256`.
- **Tasks:** `tasks/hard/dev.jsonl` (5 items) and `tasks/hard/test.jsonl` (15 items), with dev gold in `gold/hard/dev_gold.jsonl`.
- **Scoring:** the same scorer and metrics, with `--corpus corpus/hard/papers.jsonl`. The console lists the hard splits once the corpus is built.

## Connect your agent

The easiest way to attempt the bench is the run console:

```
.venv\Scripts\python app\server.py
```

Open http://127.0.0.1:8765 (on Windows, use the IP: some setups block `localhost` in the browser). Enter your agent's URL, pick dev or test, and run. The console shows each item as it finishes, colored by score. Select an item to see its output beside the gold. Scores come per task type, with 95% intervals. The console uses only Python's standard library.

Your agent is an HTTP server in any language, with two routes:

| Route | What the bench sends | What your agent returns |
|---|---|---|
| `GET /health` | nothing | `200`, optionally `{"name": "my-agent v2"}` |
| `POST /solve` | `{"task": {...}, "tools_url": "...", "run_id": "...", "item_id": "..."}` | `{"abstain": false, "output": {...}, "trace": {...}}` |

While solving, call the corpus tools at `tools_url`: `POST {tools_url}/search` with `{"query", "k"}`, `/read` with `{"paper_id", "section"}`, `/list_sections` with `{"paper_id"}`, and `/get_metadata` with `{"paper_id"}`. Each returns `{"result": ...}` or `{"error": "..."}`. Each item gets its own `tools_url`, so the console counts your tool calls per item. If the run sets a tool budget, calls past it return an error.

`examples/http_agent.py` is a complete agent that follows this contract. Run `py examples/http_agent.py --provider ollama` for a free local test, or use `--provider anthropic` or `openai` with a key.

**Test runs.** Test gold isn't shipped. The console answers every test item, then offers `preds.jsonl` to download. Send that file to us, and we score it and post the result on the leaderboard.

**Leaderboard.** Dev runs can be self-reported: in a finished run, choose **Copy leaderboard entry** and paste it into the leaderboard page. The page is linked from the class announcement; open it signed in to claude.ai.

**Using a coding agent instead of an API.** `baselines/claude_code_workspace.py make` builds a folder holding only the corpus, the tasks, the agent prompt, and a `tool.py` that logs every call and enforces the budget. Any coding agent (Claude Code, Codex, Cursor) can work in that folder blind to the gold. `claude_code_workspace.py collect` turns its answers into a predictions file. Our strong baseline was produced this way.

## The tools

| Tool | Returns |
|---|---|
| `search(query, k=10)` | `[{paper_id, title, section, snippet, score}]`. BM25 over ~300-word chunks of every section except References, plus each paper's title and abstract. |
| `read(paper_id, section=None)` | One section's text. Section numbers are optional, so `"Results"` finds `"4 Results"`. Without a section, the whole paper (often 50k+ tokens). |
| `list_sections(paper_id)` | Section names in order. |
| `get_metadata(paper_id)` | Title, authors, year, abstract. |

`tools/tool_schemas.json` has all four as JSON-schema function definitions. `tools.corpus_tools.call_tool(name, args)` dispatches a call and returns errors as text, so your agent can recover. To poke around by hand, run `py tools/corpus_tools.py search "prompt injection defenses"`.

## Files

| Path | What it is |
|---|---|
| `corpus/papers.jsonl` | One paper per line: `id, title, authors, year, abstract, sections[{name, text}]`. Built locally by `build/extract_text.py`; not in git |
| `corpus/papers.sha256` | Checksum of our `papers.jsonl`, so a rebuild can be checked |
| `corpus/licenses.csv` | arXiv license per paper |
| `tasks/dev.jsonl`, `tasks/test.jsonl` | Task items. No gold, no trap flags |
| `gold/dev_gold.jsonl` | Gold for dev only. Test gold is held back |
| `tasks/schemas/*.json` | Input and output schema per task type |

## Task types

Every prediction line is `{"id": ..., "abstain": false, "output": {...}, "trace": {...}}`. To abstain, send `{"id": ..., "abstain": true, "output": {"reason": "..."}}`. `trace` is optional; if you include `steps`, `input_tokens`, `output_tokens`, and `cost_usd`, the scorer reports their means.

**find_papers.** Find the corpus papers relevant to a topic.

```json
{"id": "fp-03", "type": "find_papers", "input": {"topic": "Defenses against indirect prompt injection"}}
{"id": "fp-03", "abstain": false, "output": {"ranked_ids": ["2302.12173", "..."]}}
```

**comparison_table.** Fill typed columns for a set of papers. Each column names the exact setting (dataset, model, metric) its value must come from. `paper_ids: null` means you choose the papers.

```json
{"id": "ct-01", "type": "comparison_table", "input": {"topic": "...", "paper_ids": ["..."],
  "columns": [{"name": "attack_success_rate", "type": "numeric", "unit": "percent", "setting": "AdvBench, Llama-2-7B-Chat"},
              {"name": "access", "type": "enum", "allowed": ["white-box", "black-box"]}]}}
{"id": "ct-01", "abstain": false, "output": {"rows": [{"paper_id": "...",
  "cells": {"attack_success_rate": "<number>", "access": "white-box"},
  "evidence": {"attack_success_rate": "<verbatim sentence or table row>"}}]}}
```

Use `NOT_REPORTED` for a value the paper doesn't give.

**citation_links.** Say which papers in a set cite which others.

```json
{"id": "cl-02", "type": "citation_links", "input": {"paper_ids": ["a", "b", "c"]}}
{"id": "cl-02", "abstain": false, "output": {"edges": [["a", "b"], ["c", "a"]]}}
```

Each edge is `[citing, cited]`.

**grounded_claims.** Answer a question with claims, each tied to a paper and a verbatim quote.

```json
{"id": "gc-05", "type": "grounded_claims", "input": {"question": "..."}}
{"id": "gc-05", "abstain": false, "output": {"answer": "...",
  "claims": [{"text": "...", "paper_id": "...", "quote": "<at least 6 words, copied from the paper>"}]}}
```

**followup_questions.** Propose 3–5 research questions the given papers leave open.

```json
{"id": "fu-01", "type": "followup_questions", "input": {"topic": "...", "paper_ids": ["..."]}}
{"id": "fu-01", "abstain": false, "output": {"questions": ["..."]}}
```

## Metrics

Each type has one primary metric (★). Results are reported per type with a 95% bootstrap confidence interval. Test has only a few items per type, so check the interval before calling one agent better than another. The macro average across types is printed last and is secondary.

| Type | Metrics |
|---|---|
| find_papers | ★nDCG@10 with graded relevance (0/1/2), Recall@10, Precision@10. Duplicates are dropped, and only the top 10 count. |
| comparison_table | ★Cell accuracy. Numeric cells are correct within 2% relative; enum cells must match exactly after normalizing; text cells are judged. A missing row makes all its cells wrong. Secondary: evidence match rate, where a numeric cell's quote must be in the paper and contain the value. |
| citation_links | ★Edge F1. Edges with an endpoint outside the input set are false positives. |
| grounded_claims | ★0.5 × support rate + 0.5 × supporting-paper recall. Only the first 10 claims count. A claim earns support only if its quote is in the cited paper (fuzzy match ≥ 90, every number exact, at least 6 words). Every number in the claim must also appear in the paper's text at that spot, or the claim scores 0 without reaching the judge. The judge then decides whether that text supports the claim. |
| followup_questions | ★Judge rubric: specific, grounded, and novel, each 1–5, averaged and scaled to 0–1. Only the first 5 questions count. |
| traps | 1 if you abstain or return an empty list with no invented IDs, else 0. |

Also reported: **hallucination rate**, the share of items whose output contains at least one ID outside the corpus. A missing prediction scores 0.

## How test scoring works

Run your agent on `tasks/test.jsonl` and send us the predictions file. We score it against the held-out gold with the same command and judge, and send back `results.json`. Use dev, which ships with gold, for everything else.

## The judge

The judge decides claim support, short-text cell equivalence, and follow-up quality. Everything else is string and set math. It's `qwen3.5:9b`, run locally through Ollama at temperature 0, with the prompts in `prompts/judge.md`. `results.json` records the model's digest, and every decision is cached, so a rerun gives the same scores. `gemma4:12b` also works (`--judge ollama:gemma4:12b`), but scores are only comparable between runs that used the same judge.

Use `--judge none` to skip the judge. Judge-based metrics then come back as `null`, and grounded-claims and follow-up items have no primary score.

## Running the tests

```
.venv\Scripts\python -m pytest -q
```

The tests use a three-paper fixture corpus (`tests/fixtures/`), so they need neither the real corpus nor network access.

## For our team

The design is in `docs/plan.md`. Building the corpus and labels uses `build/`, which doesn't ship to Phase 3:

1. `py build/fetch_corpus.py` picks the papers and the S2 citation edges. `py build/extract_text.py` downloads the PDFs and splits them into sections. **The corpus was frozen on 2026-11-09 (`corpus/FREEZE.json`), and `fetch_corpus.py` now refuses to run.** Semantic Scholar's data changes, so a fresh fetch can pick a different paper set and break every drafted label. To drop a paper, add it to `_exclude` in `build/seeds.json` before the freeze, not after.
2. Write task items in `tasks/items.jsonl`; `prompts/label_draft.md` says how. Then run `py build/draft_labels.py --type <type> --provider anthropic` and verify each file in `gold/drafts/`.
3. `py build/draft_labels.py --sample-check` marks the 20% second-check sample.
4. `py build/assemble_gold.py --perfect-preds gold/dev_perfect.jsonl` writes the task and gold files. Scoring that file must give 1.0 on every deterministic metric; anything less points at a gold quote that doesn't match the corpus.
5. `py build/make_release.py` builds the Phase 3 zip and refuses to include held-back files.
