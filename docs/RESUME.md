# Where we left off (2026-11-09)

Paused partway through `docs/phase2_execution.md`. Steps 2–4 and the front end are built. Step 5 and the publishing tasks remain.

## Done

- **Corpus frozen.** 138 papers, `corpus/FREEZE.json`. `fetch_corpus.py` refuses to run.
- **40 task items.** `tasks/items.jsonl`: 10 dev, 30 test, 5 traps.
- **Gold for all 35 non-trap items.** `gold/drafts/`, assembled into `gold/*_gold.jsonl`. The gold-copy gate scores 1.0 on every deterministic metric.
  - Claude drafted and checked the gold. A 20% sample is marked `second_check_requested` for teammates; none of it is human-checked yet.
  - One gold error was caught and fixed: GCG's Llama-2-7B-Chat individual-behavior success rate is 56, not 88. The blind table baseline found it.
- **Baselines on test**, in `baselines/runs/`:

  | Run | Macro |
  |---|---|
  | B1, blind Claude Code subagents with tools | 0.972 |
  | B0, titles only | 0.934 |

  Also, local Qwen 3.5 9B on **dev** scored a 0.22 macro.
- **Run console.** `app/server.py` with `app/static/index.html`, the HTTP agent contract, `examples/http_agent.py`, and the test in `tests/test_app.py`.
- **Leaderboard page.** https://claude.ai/artifact/WDm8vrjf8kRVfsn4QVM8q8, built from `leaderboard/leaderboard.html`. It's private to Garrett and has no rows yet.
- **Number words count as numbers** in quote and claim checks (two to twenty).
- **Citation checker.** `build/ref_match.py` agreed with a manual reading of the reference lists on all 18 disputed edges.

## Done in the second session (2026-11-09, afternoon)

- **Pushed** everything to GitHub.
- **Judge validation, stand-in.** 30 decisions from both baselines, labeled by Claude and marked as not human: `docs/judge_validation.csv`, with the write-up in `docs/judge_validation.md`. Claims agreed 22/22, but every label was "supported", so kappa is undefined. Equivalence agreed 2/3, and follow-up ratings differed by a mean of 0.2. `judge.py` now samples from several results files and filters agreement by labeler.
- **Judge comparison refreshed.** With the number check, Qwen's error is 1.0 against Gemma's 2.0. Qwen stays the default.
- **Leaderboard seeded** with the B1 and B0 test rows in `official`. A write test at contributor level was refused, so the rules hold.

## Not done yet

1. **Share the leaderboard** with the class. Only Garrett can do this, from the page's Share menu. Contributors can post; viewers can only read.
2. **Teammates:**
   - re-check the 7 marked drafts
   - add human labels to `docs/judge_validation.csv`, using their own name in `labeler`
   - review `scoring/judge_eval_cases.jsonl`
3. **Decide on frontier headroom** (see the findings below). The options are a harder item set inside the frozen corpus, or reporting the ceiling as a limitation.
4. **Presentation** (Nov 16).

## Findings for the presentation

- **Ceiling and memorization.** Titles-only Claude scores 0.93, close to the 0.97 it gets with tools. Its grounded-claims quotes, written from memory, matched the paper text. The corpus is mostly famous 2017–2023 papers that frontier models have memorized.
  - Citation links is the task where tools matter most: 0.78 titles-only, 1.00 with tools.
  - Qwen 9B scores 0.22, so the bench does separate weak agents from strong ones.
  - Fixes for frontier headroom: add post-2024 papers, numbers buried in tables, more traps, and stricter per-claim settings.
- **Shared model.** Claude wrote the gold and Claude ran the strong baseline, so some agreement is shared judgment. This is the reason for the human 20% check.
- **Narrow gold supporting sets.** On gc-09 the B1 agent cited reasonable papers that the gold doesn't list. One option: an "also acceptable" set.

## How to resume

- **Python.** Use `.venv\Scripts\python.exe`. Bare `python` hits the Microsoft Store stub.
- **Console.** Start it with `.venv\Scripts\python app\server.py --judge ollama:qwen3.5:9b`, then open http://127.0.0.1:8765. Chrome needs `127.0.0.1`; `localhost` fails.
- **Session scripts.** The scripts that wrote the items and gold are in `build/session/`. They expect `lab.py` and `item_keys.json` beside them. `make_gold.py` regenerates `gold/drafts/`; after any change, rerun `draft_labels.py --sample-check` and `assemble_gold.py`.
- **Blind workspaces.** `baselines/claude_code_workspace.py make|collect`. Keep workspaces outside the repo. Subagents also wrote into the session scratchpad, but their transcripts show no reads of the gold files.

## Hard track, in progress (paused 2026-11-09 evening)

Done:
- **Corpus.** 95 papers, all first submitted July–October 2026, in 9 subtopics. Frozen in `corpus/hard/FREEZE.json` (sha `2d2a109d…`). Built from `build/hard/selected.jsonl` with `extract_text.py --track hard`.
- **Console.** It serves `hard_dev` and `hard_test` once `tasks/hard/{dev,test}.jsonl` and `gold/hard/*_gold.jsonl` exist.
- **Review page.** https://claude.ai/artifact/1SKtkn7kN5JwLseD135KNq, seeded with 7 gold items and 30 judge decisions. Garrett still needs to share it. When reviews come in, export `items` and `reviews` with ArtifactData `out_dir`, then run `py build/apply_reviews.py --export <dir>`.

Next: write about 20 hard items (5 dev, 15 test) and their gold, then run blind baselines B1 and B0 on hard test. The expected result is that B0 collapses on the hard track.

Planned items. All values below were checked against the abstracts or the full text.
- **Find papers (7).** Dev: training-based or adaptive indirect-prompt-injection defenses; new RAG-poisoning attack methods (defenses grade 0). Test: poisoned-document defenses in RAG; MCP and tool-ecosystem security; reasoning-model jailbreaks and alignment; new agent memory architectures (evaluation studies grade 0); deep-research benchmarks and error analyses.
- **Table, dev, MCP security** (2610.04378, 2609.26761, 2610.22301):
  - mean ASR: 64.4 / 74.4 / NOT_REPORTED
  - type: benchmark / attack / measurement study
  - scale: 125 scenarios over 25 attack types, nine models, 3,375 trials / LiveMCPBench, four scenarios / 21,097 servers from nine registries
- **Table, test, injection defenses** (COPA 2608.19982, SecOPD 2608.21500, CoER 2609.07529, CoDeL 2609.34463):
  - absolute adaptive ASR: NOT_REPORTED / 9.0 / 0.2 / NOT_REPORTED. COPA and CoDeL give only relative reductions.
  - feedback: SecOPD token-level, the other three sequence-level
- **Table, test, RAG poisoning attacks:**
  - defenses evaluated: DenialRAG 5, CamoDocs 7, PURPOSE 3 (conflict-resolution methods), KidnapRAG 3 (Sandwich, Spotlighting, RAGDefender)
  - access: all four are black-box
- **Table, test, agent memory:**
  - LoCoMo accuracy with a GPT-4o-mini backbone, full method: REALM 2609.16053 75.97 (Table 1); MemCode 2610.19472 79.55 (after consolidation, from its contributions list); EMIR² 2609.32584 NOT_REPORTED (it generates with Gemini 2.5 Flash)
  - structure: graph / discrete codebook / state-evolving memory graph
- **Citations (1, test).** The prompt-injection-defense set: 5 of the corpus's 8 edges are there (`build/hard/ref_edges.json`).
- **Traps (2).** Check candidate topics against the hard corpus before using them.
