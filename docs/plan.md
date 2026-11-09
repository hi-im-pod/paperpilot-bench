# PaperPilot benchmark plan

## Context

Phase 2 of the course project: build a benchmark that measures whether an agent can do what PaperPilot promises. That means going from a research topic to relevant papers, comparison tables, citation relationships, and follow-up questions. In Phase 3 another team builds an agent against this benchmark, so it has to run from one zip and one command, with no help from us. It's due November 16 (one week from today), with a 15-minute in-class presentation.

Constraints from the conversation:
- **Closed corpus.** The agent sees papers only through a tool we provide.
- **Full text.** About 150 arXiv papers across several subfields.
- **Tasks.** Find papers, comparison table, citation links, grounded claims.
- **Labor.** 3–4 people at about 5 hours each, with LLM-drafted labels that humans verify.
- **Models.** An API model drafts labels and runs baselines. A pinned local model (Ollama) is the judge, so anyone can reproduce scores for free.
- **Baselines.** Two, run before the presentation.
- **Prompts.** Four, listed below.

Calls I made that you should check, each marked **(my call)** below: the subfields, the item counts, adding follow-up questions and trap items, the dev/test split, the project location, and the judge model.

## Layout

A new `paperpilot-bench` repo **(my call)**, with `git init`.

```
paperpilot-bench/
  build/        fetch_corpus.py, extract_text.py, draft_labels.py   (our tooling, not shipped)
  corpus/       papers.jsonl   {id, title, authors, year, abstract, sections:[{name, text}]}
  tools/        corpus_tools.py   search(), read(), list_sections(), get_metadata()
  tasks/        dev.jsonl (with gold), test.jsonl (no gold), schemas/*.json
  gold/         test_gold.jsonl   (held back, not in the Phase 3 zip)
  scoring/      score.py, judge.py, normalize.py
  baselines/    b0_titles_only.py, b1_search_read.py
  prompts/      builder.md, agent.md, judge.md, label_draft.md
  README.md     the Phase 3 contract
```

Python, with `rank_bm25`, `pymupdf`, `rapidfuzz`, `requests`, and `ollama`. On this machine, run Python as `py`, since bare `python` hits the Store stub.

## Corpus (freeze by Nov 11)

Random arXiv pulls give almost no citations between corpus papers, and the citation task needs them. So the corpus grows outward from seed papers instead:

1. Pick three clusters **(my call)**: LLM security (jailbreaks, prompt injection), RAG, and LLM agents. Choose 2–3 well-cited seed papers per cluster.
2. `fetch_corpus.py` pulls each seed's references and citers from the Semantic Scholar Graph API, keeps papers that have an arXiv ID, ranks them by in-cluster connectivity, and caps each cluster at about 50. Papers that sit in two clusters are kept on purpose as hard distractors.
3. `extract_text.py` downloads the PDFs, extracts text with PyMuPDF, splits it into sections by heading, and normalizes ligatures, hyphenation, and whitespace. Every quote check uses the same normalizer.
4. Gold citation edges come from the S2 references, filtered to corpus IDs, then spot-checked against 10 reference sections because S2 misses some.
5. Licensing: record each paper's arXiv license. For sharing inside the class that's probably fine. If not, ship the IDs plus the fetch script instead of the text.

## Tool API (what the Phase 3 agent gets)

- `search(query, k=10)` returns `[{paper_id, title, section, snippet, score}]`. BM25 over section chunks.
- `read(paper_id, section=None)` returns the section text, or the full text if no section is given.
- `list_sections(paper_id)` returns the section names.
- `get_metadata(paper_id)` returns title, authors, year, and abstract. **Not references**, since those are the citation-task answers.

Rules in the README: no network, no outside APIs (S2 would hand over the citation answers), and the corpus tools are the only source. Cite papers by corpus ID. An ID outside the corpus counts as a hallucinated citation.

## Tasks and metrics

About 40 items **(my call)**. Release 10 as `dev` with gold and hold back about 30 as `test` **(my call)**, so the other team can't tune to the gold.

| Task | n | Input | Output schema | Metric |
|---|---|---|---|---|
| Find papers | 12 | topic or question | `{ranked_ids: [..]}` | Recall@10, Precision@10, nDCG@10 |
| Comparison table | 6 | topic, 4–5 paper IDs or "find them", typed columns, fixed setting (dataset, model, metric) | `{rows: [{paper_id, cells: {col: value}, evidence: {col: quote}}]}` | Cell accuracy. Numeric within 2% relative, enum exact after normalizing, short text by judge |
| Citation links | 6 | set S of 8–12 IDs | `{edges: [[citing, cited], ..]}` | Edge precision, recall, F1 |
| Grounded claims | 8 | question | `{answer, claims: [{text, paper_id, quote}]}` | Valid-ID rate, quote match (normalized `rapidfuzz.partial_ratio` ≥ 90), support rate (judge), recall of gold supporting papers |
| Follow-up questions | 3 **(my call)** | topic + papers | `{questions: [..]}` | Judge rubric 1–5: specific, grounded in a real gap, not already answered in the corpus |
| Traps | 5 **(my call)** | spread across task types: no relevant papers, or asks about a paper not in the corpus | same schema as the host task | Correct abstention. Any invented ID fails the item |

Gold rules that keep scoring deterministic:
- **Retrieval relevance by pooling.** Merge the top 20 from BM25, embeddings, and an LLM ranking. A human marks each pooled paper relevant or not. Unpooled papers count as not relevant.
- **Table columns carry a type** (numeric, enum, or short text), and each task names the exact setting. Papers often report several numbers, and without a fixed setting the gold is ambiguous.
- **Reporting.** Scores are per task, plus hallucination rate, steps, and tokens/cost. A macro average is shown only as a secondary number.

## Labeling (Nov 11–13)

1. `draft_labels.py` sends each task with the relevant papers through `prompts/label_draft.md` to the API model.
2. One teammate verifies every draft against the paper text and fixes it. Split by task type: 4 people × about 10 items.
3. A second teammate re-checks a random 20%. Report percent agreement (and kappa for relevance).
4. Rough cost: 20–30 minutes per retrieval topic, about an hour per table. That fits about 18 hours.

## Judge (pinned local model)

`judge.py` calls Ollama at a pinned tag, `qwen3.5:9b` (fits the 12 GB GPU with room for context; `gemma4:12b` is the alternate) **(my call)**, with temperature 0. The judge is used only for claim support, short-text cells, and the follow-up rubric. Everything else is string or set math.

Validation: a teammate hand-labels 30 judge decisions, and we report agreement and Cohen's kappa. This is the evaluating-LLMs lecture applied to our own grader, and it makes a slide.

## Baselines (Nov 13–14)

- **B0, titles only.** API model, no tools, given the list of corpus IDs and titles. It shows what reading full text adds and how much it hallucinates.
- **B1, search then read then answer.** API model with the four tools in a simple loop, capped at about 15 steps.

Run both on `test`. Report per-task scores, hallucination rate, steps, and cost. If B1 isn't clearly better than B0, or either one maxes out a task, adjust the difficulty before the 16th.

## The four prompts (`prompts/`)

1. **`builder.md`.** For an AI coding assistant to scaffold the repo. It contains the layout above, the tool API signatures, every JSON schema, the scorer's command line (`py scoring/score.py --tasks tasks/test.jsonl --gold gold/test_gold.jsonl --preds preds.jsonl --judge ollama:<tag>`), the normalizer rules, and "tests first for `score.py` with hand-made perfect, empty, and hallucinated predictions."
2. **`agent.md`.** One shared system prompt (closed corpus, tools only, cite by ID, quote verbatim, abstain when nothing in the corpus answers) plus one template per task type, each with its output schema inline. B1 uses it, and it ships to Phase 3 as the reference prompt.
3. **`judge.md`.** Three short rubrics: claim support (supported, partial, or unsupported, given the claim and the quoted passage), short-text cell equivalence (yes or no), and the follow-up rubric (1–5 on three criteria). Each rubric returns strict JSON with a one-line reason.
4. **`label_draft.md`.** Per task type: given the task and the paper texts, draft gold in the task's schema, with a quote for every number or claim so the verifier can check it quickly.

## Schedule

- **Mon Nov 9–Tue 10.** Repo scaffold from `builder.md`, corpus fetch and extract. Pick seeds and draft task items.
- **Wed 11.** Freeze the corpus. Draft labels with the LLM.
- **Wed 11–Fri 13.** Human verification, 20% second pass. Scorer finished and tested.
- **Fri 13–Sat 14.** Judge validation (30 items). Run B0 and B1.
- **Sun 15.** Results tables and slides. Build the Phase 3 zip (corpus, tools, dev with gold, test without gold, scorer, README).
- **Mon 16.** Present.

Presentation outline (15 min): the goal and why a closed world → the corpus and how it was built → the five task types with one example each → metrics and gold-making → judge agreement → baseline results → the Phase 3 contract.

## Verification

- `score.py` unit tests: perfect predictions score 1.0 on every metric, empty predictions score 0, a single out-of-corpus ID is flagged as a hallucination, and a quote with a ligature or line break still matches after normalizing.
- Run the scorer on the dev gold as predictions and confirm every metric is 1.0.
- Fresh-clone check: a teammate who didn't build it unzips the Phase 3 bundle on another machine, runs B1 on dev, and gets the same scores using only the README.
- Spot-check 5 citation edges and 5 table cells by hand against the PDFs after the corpus freeze.
