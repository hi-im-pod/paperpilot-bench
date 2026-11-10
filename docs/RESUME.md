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

## Hard track (done 2026-11-10)

- **Corpus.** 95 papers first submitted July–October 2026, frozen in `corpus/hard/FREEZE.json`.
- **Items.** 20 items, 5 dev and 15 test, in `tasks/hard/`, with gold in `gold/hard/`. The gold-copy gate passes. A 5-item sample is marked for a second check; it isn't in the review page yet.
- **Baselines on hard test** (`baselines/runs/hard_*`), now on the leaderboard:

  | Agent | Macro | Tables | Citations | Claims | Find papers |
  |---|---|---|---|---|---|
  | B1, Claude subagents with tools | 0.97 | 0.94 | 1.00 | 0.96 | 0.93 |
  | B0, titles only | 0.61 | 0.23 | 0.00 | 0.50 | 0.96 |

  On v1, B0 scored 0.93, so the hard track restores headroom for frontier models.
- **Scorer fix.** Quotes no longer match a paper's title or front matter. Before the fix, titles-only "grounded" claims on the hard track by quoting titles, scoring 0.97. No other baseline score changed, and both gold gates still pass.
- **Still weak at telling agents apart:**
  - find-papers: titles alone find the right papers
  - follow-up questions: the judge gave both baselines 0.97

  Candidates for the next round: stricter find-papers topics that need body text, and a stricter follow-up rubric.

## Next
1. Teammates use the review page (shared?) and the leaderboard (now shared with anyone who has the link).
2. Optionally add the 5 hard second-check items to the review page: `build/review_items.py --drafts gold/hard/drafts` needs `--corpus` support first.
3. Presentation (Nov 16).
