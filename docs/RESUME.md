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

## Not done yet

1. **Judge validation (step 5).** Export 30 judge decisions from `baselines/runs/b1_claude_test.results.json`:

   ```
   py scoring/judge.py --sample 30 --results baselines/runs/b1_claude_test.results.json --out judge_sample.csv
   ```

   The scorer doesn't save `judge_decisions` into results files from the CLI; check that first. Then label the decisions, marking any Claude stand-in labels as not human, and leave the CSV for teammates.
2. **Refresh `docs/judge_comparison.md`.** With number words added, Qwen's support-score error under the number check fell to 1.0, against Gemma's 2.0. Rerun with `py scoring/judge_eval.py --out docs/judge_eval_results.json` and update the tables.
3. **Seed the leaderboard's `official` collection** with the B1 and B0 test rows. Use ArtifactData on the URL above, with docs shaped like `Run.summary()` in `app/server.py`.
4. **Share the leaderboard** with the class. Only Garrett can do this, from the page's Share menu. Contributors can post; viewers can only read.
5. **Push.** Commits after `3217458` aren't on GitHub yet: the freeze, the items and gold, the console, and the baselines. The repo is public, and Garrett chose to publish the answer keys too.
6. **Teammates** re-check the 7 marked drafts, and review `scoring/judge_eval_cases.jsonl`.
7. **Presentation** (Nov 16).

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
