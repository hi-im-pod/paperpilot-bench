# Astra run (gpt-6-astra, high reasoning, Codex CLI)

An external run on both test splits, made on 2026-11-10 with a custom strict runner around `baselines/claude_code_workspace.py`, and received on 2026-11-12. `manifest.json` and `run-metadata.json` record the commit, corpus and task checksums, Codex settings, and prediction checksums; `audit.md` is the run's own compliance audit.

- **Coverage.** 26 of 30 main items and 12 of 15 hard items have predictions. The runner rejected 7 items whose first tool call was malformed (`--task-id ... --help`); those score 0.
- **Scoring.** `astra_high_test.results.json` was rescored here on 2026-11-12 with follow-up rubric v2. Only follow-ups changed (0.98 to 0.86); every claim and table decision matched the original. `hard_astra_high_test.results.json` is the original scoring: the hard track's only follow-up item (hfu-01) is missing, so the rubric change can't affect it.
- **Judge drift.** Rescoring the hard predictions from scratch flipped 2 borderline decisions (one table cell, one claim) with the same model digest, likely from an Ollama update. The leaderboard keeps the original decisions, as it does for every row.
