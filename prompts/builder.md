# Builder prompt: PaperPilot benchmark harness

Paste everything below the line into an AI coding assistant (Claude Code, Codex, Cursor) opened in the `paperpilot-bench` repo. It builds the pipeline, tools, scorer, and baselines. It doesn't write gold labels. People write those, with `prompts/label_draft.md`.

---

You're building the harness for **PaperPilot-Bench**, a benchmark for research-literature agents. An agent gets a research topic or question and has to find relevant papers, fill comparison tables, recover citation links, and answer with claims grounded in verbatim quotes. All of this happens inside a **closed corpus** of about 150 full-text arXiv papers. Another team will build an agent against this benchmark without talking to us, so every interface has to be explicit, and scoring has to be one command.

Read `docs/plan.md` first. It's the approved design. If this prompt and the plan disagree, follow this prompt and tell me where they differed.

## Ground rules

- Python 3.11+. On this Windows machine run Python as `py`, never bare `python`. Dependencies go in `requirements.txt`: `rank_bm25`, `pymupdf`, `rapidfuzz`, `requests`, `ollama`, `numpy`, `pytest`, `anthropic`, `openai`.
- **Tests first for the scorer.** Write `tests/test_score.py` against a three-paper fixture corpus before writing `scoring/score.py`. The fixture papers are fake and must say so in their titles (for example "FIXTURE: Paper A").
- Only `build/` touches the network. `tools/` and `scoring/` must work offline, except that `scoring/judge.py` calls Ollama on localhost.
- Never invent paper IDs, titles, or numbers anywhere outside the test fixtures. If an API call fails, log it and skip the paper. Don't fill the gap.
- Every script takes `--help` and prints what it wrote and how many records.
- Code comments say why, not what.

## Repo layout

```
build/      seeds.json, fetch_corpus.py, extract_text.py, draft_labels.py, assemble_gold.py, make_release.py
corpus/     papers.jsonl, licenses.csv
tools/      corpus_tools.py, tool_schemas.json
tasks/      dev.jsonl, test.jsonl, schemas/<task_type>.json
gold/       dev_gold.jsonl, test_gold.jsonl, citations_s2.jsonl, drafts/, provenance.csv
scoring/    normalize.py, score.py, judge.py
baselines/  llm.py, b0_titles_only.py, b1_search_read.py
prompts/    builder.md, agent.md, judge.md, label_draft.md   (already written)
tests/      fixtures/, test_score.py, test_normalize.py, test_tools.py
README.md   the contract for the Phase 3 team
```

## 1. Corpus pipeline (`build/`)

`build/seeds.json` holds three clusters. The seed IDs below were verified against the arXiv API on 2026-11-09:

```json
{
  "llm_security": ["2307.15043", "2302.12173", "2307.02483"],
  "rag":          ["2005.11401", "2310.11511", "2312.10997"],
  "llm_agents":   ["2210.03629", "2302.04761", "2308.11432"]
}
```

`fetch_corpus.py`:
1. For each seed, call the Semantic Scholar Graph API: `GET https://api.semanticscholar.org/graph/v1/paper/arXiv:{id}/references` and `/citations`, with `fields=externalIds,title,year,citationCount` and `limit=1000`. Keep only papers that have `externalIds.ArXiv`. For citations, keep papers with `citationCount >= 20`, because surveys have thousands of citers and most are noise.
2. For each candidate, fetch its own references (same endpoint) so in-cluster connectivity can be computed. Score each candidate by the number of citation links to other candidates in its cluster.
3. Keep the seeds plus the top candidates, about 50 per cluster. Dedupe across clusters. A paper in two clusters gets both tags; those are the hard distractors.
4. Write `gold/citations_s2.jsonl` (`{"citing": id, "cited": id}`), with both ends in the corpus. It goes in `gold/`, not `corpus/`, because it's the answer key for the citation task. The tools and the scorer never read it.
5. Rate limits: sleep 1.1 s between S2 calls without an API key (use `S2_API_KEY` from the environment if set). Retry 429 and 5xx with exponential backoff, at most 5 tries. Cache every raw response under `build/cache/` so reruns cost nothing.
6. Get licenses from arXiv OAI-PMH (`metadataPrefix=arXiv`) and write them to `corpus/licenses.csv`. Write `unknown` on failure.

`extract_text.py`:
1. Download `https://arxiv.org/pdf/{id}`, waiting 3 s between requests (arXiv's crawling guideline). Cache the PDFs in `build/cache/pdf/`.
2. Extract text with PyMuPDF. Split it into sections on heading lines: numbered (`^\d+(\.\d+)*\.?\s+[A-Z]`) or a known name (Abstract, Introduction, Related Work, Background, Method(s), Approach, Experiments, Results, Evaluation, Discussion, Limitations, Conclusion(s), References, Appendix). Keep **References** as its own section, because the citation task needs it. If no headings are found, write one section called `body`.
3. Write `corpus/papers.jsonl`: `{"id": "2307.15043", "title", "authors": [..], "year", "abstract", "clusters": [..], "sections": [{"name", "text"}]}`. The `id` is the bare arXiv ID without a version.
4. Print the papers that came out with fewer than 3 sections or under 2,000 words, so a person can check them.

## 1b. Label drafting and gold assembly (`build/`)

People write task items by hand in `tasks/items.jsonl`. Each line is a task record (section 4) plus `"split": "dev" | "test"` and `"trap": true | false`. Those two fields are stripped before anything reaches the agent.

`draft_labels.py --type <task_type>` runs the prompts in `prompts/label_draft.md` with the API model (same `--provider` and `--model` flags as `baselines/llm.py`) and writes one file per item to `gold/drafts/<id>.json`. Write drafts as indented JSON with every quote next to its label, so a verifier can check them in a text editor. It skips trap items and items that already have a draft unless `--force` is given. Per type:
- `find_papers`: build the pool from the union of the top 20 BM25 hits (through `corpus_tools.search`, collapsed to papers), the top 20 by embedding similarity of the topic to each title and abstract, and the top 20 the API model picks from the full `id: title` list. For embeddings, use Ollama's `nomic-embed-text` (add the pull command to the README), and cache the vectors in `build/cache/emb.npy`. Then grade the pool in batches of 10.
- `comparison_table`: one call per paper, with that paper's full text.
- `citation_links`: start from `gold/citations_s2.jsonl` restricted to the set, add the reference-list cross-check, and mark every edge where the two sources disagree as `"needs_review": true`.
- `grounded_claims`: candidates are the top 15 papers by BM25 plus embeddings.
- `followup_questions`: the Limitations, Discussion, and Conclusion sections of the given papers.

The verifier edits the draft in place and sets `"verified_by": "<name>"`. A second checker sets `"checked_by"` on a 20% sample. `draft_labels.py --sample-check` picks that sample, stratified by type, with a fixed seed.

`assemble_gold.py` reads `tasks/items.jsonl` and `gold/drafts/`, refuses to run if any non-trap item lacks `verified_by`, and writes:
- `tasks/dev.jsonl` and `tasks/test.jsonl`, with `split` and `trap` stripped
- `gold/dev_gold.jsonl` and `gold/test_gold.jsonl`, in the gold format of section 4
- `gold/provenance.csv`: `id, type, split, drafting_model, verified_by, checked_by`

It prints the item counts per type and split, and the share of `needs_review` citation edges that the verifier changed.

## 2. Normalizer (`scoring/normalize.py`)

`normalize(text) -> str`, used for every quote and cell comparison and for nothing else:
- Unicode NFKC, which also expands ligatures such as `ﬁ` and `ﬂ`.
- Join words hyphenated across a line break: `adver-\nsarial` becomes `adversarial`.
- Map curly quotes to straight quotes, and en and em dashes to `-`.
- Collapse all whitespace to one space, lowercase, and strip.

`parse_number(s) -> float | None`: strip `%`, `,`, `±…` and anything after it, and surrounding text. Return `None` if no number is found.

`numbers_in(text) -> list[str]`: every number token (`\d+(\.\d+)?`) in normalized text, used by the quote check below.

`locate(quote, paper_text) -> (score, start, end) | None`: use `rapidfuzz.fuzz.partial_ratio_alignment(normalize(quote), normalize(paper_text))` to find the best-matching span in the paper. Return `None` when the score is below 90.

**Quote match rule**, used for grounded claims and table evidence: a quote matches when `locate()` finds a span **and** every number in the quote appears exactly in that span. Fuzzy matching alone lets "83.0" pass for "88.0", because one changed character still scores above 90. The number check closes that gap.

## 3. Corpus tools (`tools/corpus_tools.py`)

These four functions are the only way the agent under test sees the corpus:

```python
search(query: str, k: int = 10) -> list[dict]
    # [{"paper_id", "title", "section", "snippet", "score"}], BM25 over
    # ~300-word chunks of every section except References. snippet is <= 300 chars.
read(paper_id: str, section: str | None = None) -> str
    # One section's text, or the whole paper if section is None.
    # An unknown ID raises KeyError("paper not in corpus: ...").
list_sections(paper_id: str) -> list[str]
get_metadata(paper_id: str) -> dict
    # title, authors, year, abstract. NEVER references, clusters, or citation edges.
```

References are excluded from `search()` because otherwise a query would match a title in some other paper's bibliography. `read(id, "References")` still works.

Also write `tools/tool_schemas.json`: the four tools as JSON-schema function definitions, so any agent framework can register them. Add a CLI for manual poking: `py tools/corpus_tools.py search "prompt injection defenses"`.

## 4. Tasks, predictions, and gold

All files are JSONL, one record per line, joined on `id`.

**Task records** (`tasks/*.jsonl`) are what the agent sees. They **never** contain gold or a trap flag:

```json
{"id": "fp-03", "type": "find_papers", "input": {"topic": "Defenses against indirect prompt injection in LLM-integrated apps"}}
{"id": "ct-01", "type": "comparison_table", "input": {"topic": "...", "paper_ids": ["..."] , "columns": [{"name": "attack_success_rate", "type": "numeric", "unit": "percent", "setting": "AdvBench harmful behaviors, Llama-2-7B-Chat"}, {"name": "access", "type": "enum", "allowed": ["white-box", "black-box"]}]}}
{"id": "cl-02", "type": "citation_links", "input": {"paper_ids": ["...", "..."]}}
{"id": "gc-05", "type": "grounded_claims", "input": {"question": "..."}}
{"id": "fu-01", "type": "followup_questions", "input": {"topic": "...", "paper_ids": ["..."]}}
```

In `comparison_table`, `paper_ids` may be `null`, which means "find the papers yourself." Write one schema per task type in `tasks/schemas/`.

**Prediction records** (`preds.jsonl`) are what the agent writes:

```json
{"id": "fp-03", "output": {"ranked_ids": ["..."]}, "abstain": false, "trace": {"steps": 7, "input_tokens": 41200, "output_tokens": 1900, "cost_usd": 0.14}}
```

Output schemas by type:
- `find_papers`: `{"ranked_ids": [str]}`
- `comparison_table`: `{"rows": [{"paper_id": str, "cells": {col: str}, "evidence": {col: str}}]}`
- `citation_links`: `{"edges": [[citing_id, cited_id]]}`
- `grounded_claims`: `{"answer": str, "claims": [{"text": str, "paper_id": str, "quote": str}]}`
- `followup_questions`: `{"questions": [str]}`

Any item may instead set `"abstain": true` with `"output": {"reason": str}`. `trace` is optional, but the baselines must fill it in.

**Gold records** (`gold/*.jsonl`):

```json
{"id": "fp-03", "trap": false, "relevant": {"<id_a>": 2, "<id_b>": 1}, "pooled": ["..."]}
{"id": "ct-01", "trap": false, "rows": {"<arxiv_id>": {"attack_success_rate": "<number from the paper>", "access": "white-box"}}, "row_set_required": false}
{"id": "cl-02", "trap": false, "edges": [["a", "b"]]}
{"id": "gc-05", "trap": false, "supporting_ids": ["..."]}
{"id": "fu-01", "trap": false, "gap_notes": "Limitations sections mention no evaluation on multimodal agents ..."}
{"id": "fp-11", "trap": true}
```

A gold cell may be `"NOT_REPORTED"`. The prediction then has to say `NOT_REPORTED` too.

## 5. Scorer (`scoring/score.py`)

```
py scoring/score.py --tasks tasks/test.jsonl --gold gold/test_gold.jsonl \
    --preds preds.jsonl --judge ollama:qwen3.5:9b --out results.json
```

`--judge none` skips the judge-based metrics and reports them as `null`. The scorer loads the corpus to get the set of valid IDs and the paper text. The corpus path comes from `--corpus`, then the `PAPERPILOT_CORPUS` environment variable, then the default `corpus/papers.jsonl`. `tools/corpus_tools.py` resolves it the same way, so the tests can point both at the fixture corpus.

**Everywhere:**
- Any ID in an output that isn't in the corpus is a **hallucinated ID**. Count it in `hallucination_rate` (the share of items with at least one hallucinated ID) and treat it as wrong in the item's own metric.
- An item with a missing prediction scores 0, not "skipped."
- A **trap item** scores 1 if the agent abstained, or returned an empty `ranked_ids`, `rows`, `edges`, or `claims`, *and* produced no hallucinated ID. Otherwise it scores 0. Trap items are only scored by this rule and are reported as their own bucket.

**Per type** (the primary metric is marked ★):
- `find_papers`: drop duplicate IDs (keep the first), take the top 10. Report Recall@10 = |top10 ∩ relevant| / |relevant|, Precision@10 = |top10 ∩ relevant| / 10, and ★nDCG@10 with gains 0/1/2 from `relevant`. Papers outside `pooled` count as relevance 0.
- `comparison_table`: ★cell accuracy over every gold cell. A missing row makes all its cells wrong. `numeric`: correct if both parse and |pred − gold| ≤ 0.02·|gold| (exact match when gold = 0). `enum`: normalized exact match. `text`: judge `text_equiv`. When `row_set_required` is true, also report row recall. Secondary: the evidence match rate. Evidence matches when it passes the quote match rule *and* the cell's value appears in the located span. There's no word floor here, because PDF table rows often extract as bare numbers like `72.3 45.1 12.0`.
- `citation_links`: drop self-loops and duplicate edges. An edge with an endpoint outside the input set is a false positive. Report precision, recall, and ★F1.
- `grounded_claims`: score the first 10 claims only (so padding with claims doesn't help). A claim's quote matches if `normalize(quote)` has at least 6 words and it passes the quote match rule (section 2) against the cited paper. The word floor stops "the model" from matching every paper. Report `valid_id_rate` and `quote_match_rate`. For each matched claim, call judge `claim_support(claim, passage)` and score supported = 1, partial = 0.5, unsupported = 0. The passage is **the paper's own text**: the located span plus 500 characters on each side, taken from the normalized paper. Never the agent's quote, which could have been edited to fit the claim. If any number in the claim is missing from that passage, score the claim 0 without calling the judge, and count it in `unbacked_number_claims`. Both candidate judges gave half credit to claims with wrong numbers (`docs/judge_comparison.md`). Unmatched claims get 0. `support_rate` is the mean over all scored claims. `supporting_recall` = |cited IDs ∩ supporting_ids| / |supporting_ids|. ★ = 0.5·support_rate + 0.5·supporting_recall.
- `followup_questions`: score the first 5 questions with judge `followup_score`. ★ = mean of the three criteria / 5.

**Output** (`results.json` plus a printed table): per-item metrics, per-type means of every metric, the trap bucket, `hallucination_rate`, the mean of `trace` fields if present, and a `macro_avg` of the per-type ★ metrics with traps as a sixth bucket. Print `macro_avg` last, labeled secondary.

Next to each per-type ★ mean, report a 95% bootstrap confidence interval (1,000 resamples over items, seed 0). Test has only 2–5 items per type, and the interval shows when two agents can't be told apart.

## 6. Judge (`scoring/judge.py`)

Three functions that use the prompts in `prompts/judge.md` verbatim: `claim_support(claim, passage)`, `text_equiv(column, setting, gold, pred)`, and `followup_score(topic, paper_titles, question, gap_notes)`. Call Ollama with `temperature=0`, `seed=0`, and `format="json"`. Parse strictly; on bad JSON retry once, then record `{"label": "error"}`, score it 0, and count the errors in the results.

Cache every call in `scoring/.judge_cache.jsonl`, keyed by sha256 of (model digest, `JUDGE_PROMPT_VERSION`, prompt name, filled prompt). Reruns are then free and deterministic. Write the model tag **and its digest** (from `ollama show` or `/api/tags`) to `results.json`. A tag can be re-pushed with different weights, and the digest is what pins the model.

`py scoring/judge.py --sample 30 --results results.json --out judge_sample.csv` exports 30 random judge decisions with blank `human_label` columns for validation. `--agreement judge_sample.csv` reports percent agreement and Cohen's kappa.

## 7. Baselines (`baselines/`)

`llm.py` is a thin wrapper, `chat(messages, tools=None) -> response`, with `--provider anthropic|openai` and `--model` on every baseline CLI. It reads the API key from the environment and records tokens and cost per call.

- `b0_titles_only.py`: no tools. The system prompt from `prompts/agent.md`, plus a list of every corpus `id: title`, plus the task template. One call per item.
- `b1_search_read.py`: the system prompt and task template from `prompts/agent.md`, with the four corpus tools registered as functions. It loops until the model returns the final JSON or hits 15 tool calls. On the cap, it sends one last message: "Return your final JSON now."

Both write `preds.jsonl` with `trace` filled in, and take `--tasks` and `--out`.

## 8. Release (`build/make_release.py`)

Builds `release/paperpilot-bench-v1.zip` with `corpus/`, `tools/`, `tasks/dev.jsonl`, `tasks/test.jsonl`, `tasks/schemas/`, `gold/dev_gold.jsonl`, `scoring/`, `baselines/`, `prompts/agent.md`, `prompts/judge.md`, `requirements.txt`, and `README.md`.

The shipped `papers.jsonl` is a copy with the `clusters` field removed, since cluster tags hint at `find_papers` relevance. After zipping, assert that the zip contains none of these: `gold/test_gold.jsonl`, `gold/citations_s2.jsonl`, `gold/drafts/`, `gold/provenance.csv`, `tasks/items.jsonl`, `build/`, `scoring/.judge_cache.jsonl`, and any `"clusters"` key in `papers.jsonl`. Fail loudly if any is present.

## 9. README (the Phase 3 contract)

Cover, in this order:
1. A quick start in three commands: install, run B1 on dev, score.
2. The rules: closed corpus, the four tools only, no network or outside APIs (Semantic Scholar would leak the citation answers), cite by corpus ID, and abstain when the corpus doesn't answer.
3. The task types, each with one example input and output.
4. Metrics, as in section 5 above.
5. How test scoring works: the team sends us `preds.jsonl`, and we score it with the held-out gold.
6. The judge model tag, and how to run without it.

## 10. Tests that must pass before you're done

- `test_normalize.py`: ligatures, line-break hyphenation, curly quotes, and whitespace.
- `test_tools.py`: on the fixture corpus, `search` finds the right fixture paper, `read` raises on an unknown ID, and `get_metadata` has no references key.
- `test_score.py`, on the fixture corpus with `--judge none`:
  - perfect predictions give 1.0 on every deterministic metric;
  - empty predictions give 0;
  - one made-up ID sets `hallucination_rate` above 0 and fails that item;
  - a trap item scores 1 on abstain and 0 on any returned ID;
  - a quote with a ligature and a line break still matches after normalizing;
  - a 4-word quote fails the quote check;
  - a quote copied from the paper with one digit changed ("88.0" to "83.0") fails the quote check;
  - table evidence that is a bare number row containing the cell value passes;
  - the release zip contains none of the files in section 8's exclusion list (run `make_release.py` on the fixture repo).
  - a numeric cell within 2% passes and one at 3% fails.
- An integration check: score `gold/dev_gold.jsonl` converted to predictions, and confirm every deterministic metric is 1.0.

When you finish, report what you built, the test output, the corpus stats (papers per cluster, cross-cluster papers, in-corpus citation edges, papers flagged by `extract_text.py`), and anything you couldn't do.
