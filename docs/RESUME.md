# Where we left off (2026-11-12)

Phase 2 is built, published, and human-checked: both tracks, the console, the leaderboard, setup scripts and Docker, and the review of a 20% gold sample and 30 judge decisions. What remains is the presentation (Nov 16) and two optional items under **Next** at the bottom. The sections below are a running log, oldest first.

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
- **Leaderboard page.** https://claude.ai/artifact/WDm8vrjf8kRVfsn4QVM8q8, built from `leaderboard/leaderboard.html`. (Later: shared with anyone who has the link, with official rows for both tracks.)
- **Number words count as numbers** in quote and claim checks (two to twenty).
- **Citation checker.** `build/ref_match.py` agreed with a manual reading of the reference lists on all 18 disputed edges.

## Done in the second session (2026-11-09, afternoon)

- **Pushed** everything to GitHub.
- **Judge validation, stand-in.** 30 decisions from both baselines, labeled by Claude and marked as not human: `docs/judge_validation.csv`, with the write-up in `docs/judge_validation.md`. Claims agreed 22/22, but every label was "supported", so kappa is undefined. Equivalence agreed 2/3, and follow-up ratings differed by a mean of 0.2. `judge.py` now samples from several results files and filters agreement by labeler.
- **Judge comparison refreshed.** With the number check, Qwen's error is 1.0 against Gemma's 2.0. Qwen stays the default.
- **Leaderboard seeded** with the B1 and B0 test rows in `official`. A write test at contributor level was refused, so the rules hold.

## Open items as of 2026-11-09 (status updated 2026-11-12)

1. ~~Share the leaderboard with the class.~~ Done: shared with anyone who has the link.
2. Teammates:
   - ~~re-check the marked drafts~~ Done 2026-11-12 (see **Human review** below).
   - ~~add human labels to `docs/judge_validation.csv`~~ Done 2026-11-11 by 형중.
   - review `scoring/judge_eval_cases.jsonl`. **Still open**: those expected labels are Claude's drafts.
3. ~~Decide on frontier headroom.~~ Done: the hard track.
4. Presentation (Nov 16).

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
- **Items.** 20 items, 5 dev and 15 test, in `tasks/hard/`, with gold in `gold/hard/`. The gold-copy gate passes. A 5-item sample is marked for a second check; it was added to the review page and checked on 2026-11-12.
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

## Deployability (done 2026-11-10)

- **Setup scripts.** `scripts/setup.ps1` and `scripts/setup.sh` create `.venv`, install requirements, and build both corpora. `setup.sh` was tested from a fresh clone. `.gitattributes` keeps `.sh` and the Dockerfile on LF, since a Windows checkout gave `setup.sh` CRLF endings that broke bash.
- **Dockerfile.** Builds both corpora into the image and runs the console on 0.0.0.0 with `--public-url http://localhost:8765`. Built and tested on 2026-11-10 after installing Docker Desktop and WSL 2.
- **Console.** Reloads finished runs from `app/runs/` at startup. New flags `--open` and `--public-url`. A misspelled tool name now returns `{"error": ...}` with status 200 instead of a 404, and `examples/http_agent.py` passes HTTP errors back to the model. Qwen invents tool names, and both bugs together crashed whole items.
- **Corpus checksums changed, text didn't.** The Docker build showed that a Linux build hashed differently from ours: Python on Windows wrote `papers.jsonl` with CRLF endings, and the checksum hashed raw bytes. `write_jsonl` now always writes LF, and `corpus_tools.corpus_sha256` hashes with CRLF read as LF, so older Windows builds still match. New checksums: main `2f1b5a2f8a4cc589`, hard `27a806089e549c3a` (old ones are kept in each `FREEZE.json`). The leaderboard accepts both, and its official rows now carry the new values.
- **README** rewritten, with screenshots in `docs/img/`. The leaderboard screenshot comes from a local copy of the page with a mock database holding the official rows.
- **Leaderboard** now has a table per track, accepts hard-track dev entries, and no longer claims test gold is held back.

## Human review (done 2026-11-11 and 2026-11-12)

- **Judge decisions.** 형중 labeled all 30 sampled decisions, blind to the judge. Claim support agreed 14/22; 6 of the 8 disagreements were wording-only, from reading the rubric more strictly than intended, and 2 were real cases of the judge accepting a claim beyond its quote. Follow-up ratings: judge 4.9 against human 3.1. Write-up in `docs/judge_validation.md`.
- **Gold sample.** Garrett checked all 12 sampled items (7 main, 5 hard). 11 confirmed as drafted. On cl-03 he marked CAMEL as not citing Reflexion; the edge was kept, because CAMEL's reference [105] is Reflexion (arXiv:2303.11366) under its v1 title. The reasoning is in `gold/drafts/cl-03.json` (`review_note`) and `docs/review_report.md`. No gold answers changed, and the gold-copy gate still scores 1.0 on both tracks.
- **One labeler per half.** Each half has a single reviewer, so there's no inter-annotator agreement. Say so in the presentation.
- **To fold in more reviews:** list the page's `items` and `reviews` collections with ArtifactData into one folder, then run `build/apply_reviews.py --export <dir> --names <names.json>`, then `build/assemble_gold.py` for each track (`--track hard` for the hard one) to refresh `provenance.csv`. Reviewers need Contributor access, by email invite, to save.
- **Fixed on the way:** `assemble_gold.py --track hard` used to read the main track's items by default and overwrite the hard-track files. Its inputs now follow `--track`.

## Next
1. **Local-model test runs.** Cut on 2026-11-10 because the GPU is shared; only Qwen's dev run exists. To run them: `b1_search_read.py --tasks tasks/test.jsonl --provider ollama --model qwen3.5:9b`, the same with `gemma4:12b`, and the hard track with `PAPERPILOT_CORPUS=corpus/hard/papers.jsonl`. At about 3 minutes per item, all four take several hours. Score with `--judge ollama:qwen3.5:9b`, add rows to the README and the leaderboard's `official` collection.
2. **Optional: tighten the follow-up metric.** The human check shows the judge rates follow-up questions about 1.8 points too high. Options are a stricter rubric in `prompts/judge.md` (bump `JUDGE_PROMPT_VERSION`), or reporting follow-ups as a known-lenient metric. Also add a paraphrase example to the claim-support rubric, since most human disagreements came from reading it strictly.
3. **Optional: review `scoring/judge_eval_cases.jsonl`**, the known-answer cases behind `docs/judge_comparison.md`.
4. **Presentation (Nov 16).** Findings are in this file and in `docs/judge_validation.md`.
