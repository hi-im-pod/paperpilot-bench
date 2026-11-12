# PaperPilot Astra benchmark-v2 compliance audit

Audit UTC: 2026-11-10T07:09:49.943435+00:00

## Outcome

Report the frozen 26/30 main and 12/15 hard predictions, all seven missing IDs and the strict malformed-help rejection mechanism. Do not add excluded answers, retry, or describe this as independently proven full compliance. Compare scores using the full track denominators and identify the custom Astra/Codex runner separately from the published original collector.

## Verified coverage and counts

| Track | Tasks / evidence | Frozen predictions | Commands | Logged calls | Successful calls | Usage help | Corpus errors |
|---|---:|---:|---:|---:|---:|---:|---:|
| main | 30 / 30 | 26 | 411 | 322 | 317 | 30 | 1 |
| hard | 15 / 15 | 12 | 195 | 150 | 146 | 15 | 1 |

Total: 45 tasks, 606 completed shell commands, 472 logged calls, 463 successful tool responses. Starts/completions are paired without double-counting. All shell exit codes were zero; this does **not** imply tool success.

Successful calls mean wrapper success markers (including empty search results), not help/error responses. Task IDs, task totals, frozen prediction IDs/counts/hashes and all complete prediction hashes reconcile. No evidence tasks are missing.

- **main missing predictions:** ct-06, fp-01, fp-09, gc-07.
- **main frozen SHA-256:** `3e1f5109f3361a5fafa5cadcd9cfde3afc368ceac569f3c8cecee56164eb7855` (matches manifest).
- **hard missing predictions:** hfp-05, hfu-01, hgc-05.
- **hard frozen SHA-256:** `81db961e10d93314b5a388c6259ca180118444aeeae581ece1229362261b5d63` (matches manifest).

## Seven strict rejections

Every event below is `item_2`, completed at line 7 of that task’s `events.jsonl`; line 6 is its start. Each is calls.jsonl line 1. Each returned only `unknown command; see python tool.py` with exit code 0. None returned paper information.

| Task | Exact arguments after tool.py | Logged item / command | All log rows | Successful calls |
|---|---|---|---:|---:|
| main/ct-06 | `--task-id ct-06 --help` | `--task-id` / `ct-06` | 8 | 7 |
| main/fp-01 | `--task-id fp-01 --help` | `--task-id` / `fp-01` | 12 | 11 |
| main/fp-09 | `--help --task-id fp-09` | `--help` / `--task-id` | 16 | 15 |
| main/gc-07 | `--task-id gc-07 --help` | `--task-id` / `gc-07` | 7 | 6 |
| hard/hfp-05 | `--task-id hfp-05 --help` | `--task-id` / `hfp-05` | 16 | 15 |
| hard/hfu-01 | `--help --task-id hfu-01` | `--help` / `--task-id` | 14 | 13 |
| hard/hgc-05 | `--task-id hgc-05 --help` | `--task-id` / `hgc-05` | 7 | 6 |

The wrapper logs arguments before rejecting unknown commands (`baselines/claude_code_workspace.py:38–59`). The custom runner rejects wrong item IDs **or** invalid command names **or** more than 15 total rows (`orchestrate.py:265–268`). All seven trigger wrong-ID/invalid-command checks; fp-09 and hfp-05 also contain 16 total rows (one invalid help row plus 15 successful corpus calls). This is a literal harness violation, not observed acquisition of a 16th paper-information response. These failures stay excluded. Original `collect()` does not implement the custom rejection check (`claude_code_workspace.py:141–168`).

## Access and concurrency observations

- Observed commands read only README.md, agent.md and tasks.jsonl for instructions; run the supplied tool.py through the specified Python; or write their own answer. No direct corpus/lib, outside-data, other-task, prior-prediction or memory-file read was observed.
- No network/web/MCP/subagent item was observed. No shell command overlap, task execution overlap, or concurrent tool invocation syntax was found.
- Two file_change items target only the current answer: main/ct-03 (add) and main/gc-02 (update). Answer JSON serialization/validation and answer-directory creation do not supply research evidence.
- Two correctly identified corpus calls returned errors and consumed budget without success markers: main/ct-02 requested a missing section (the error disclosed available section names), and hard/hgc-01 requested a paper not in the corpus. These are not classified as successful calls; both remain counted in logged/valid-task calls.

  - `main/ct-02`, events line 15, `item_6`: ` ct-02 read 2503.18813 'Title and abstract'"` → `error: "no section 'Title and abstract' in 2503.18813; sections: ['Front matter', '1. Introduction', 'Acknowledgements', 'References', 'A. Extended Related Work', 'B. Full results tables', 'C. Baseline results']"`.
  - `hard/hgc-01`, events line 15, `item_6`: ` hgc-01 read 2605.27157"` → `error: 'paper not in corpus: 2605.27157'`.

## Per-task counts

| Track/task | Retained status | Commands | Log rows | Successful calls | Invalid rows |
|---|---|---:|---:|---:|---:|
| main/cl-01 | complete | 18 | 15 | 15 | 0 |
| main/cl-02 | complete | 18 | 15 | 15 | 0 |
| main/cl-03 | complete | 18 | 15 | 15 | 0 |
| main/cl-04 | complete | 17 | 14 | 14 | 0 |
| main/cl-06 | complete | 18 | 15 | 15 | 0 |
| main/ct-02 | complete | 14 | 11 | 10 | 0 |
| main/ct-03 | complete | 6 | 4 | 4 | 0 |
| main/ct-04 | complete | 7 | 4 | 4 | 0 |
| main/ct-05 | complete | 9 | 6 | 6 | 0 |
| main/ct-06 | failed | 11 | 8 | 7 | 1 |
| main/ct-07 | complete | 10 | 7 | 7 | 0 |
| main/fp-01 | failed | 15 | 12 | 11 | 1 |
| main/fp-02 | complete | 11 | 8 | 8 | 0 |
| main/fp-03 | complete | 14 | 11 | 11 | 0 |
| main/fp-05 | complete | 17 | 14 | 14 | 0 |
| main/fp-07 | complete | 17 | 14 | 14 | 0 |
| main/fp-08 | complete | 16 | 13 | 13 | 0 |
| main/fp-09 | failed | 19 | 16 | 15 | 1 |
| main/fp-10 | complete | 18 | 15 | 15 | 0 |
| main/fp-13 | complete | 16 | 13 | 13 | 0 |
| main/fp-14 | complete | 16 | 13 | 13 | 0 |
| main/fu-01 | complete | 18 | 15 | 15 | 0 |
| main/fu-02 | complete | 18 | 15 | 15 | 0 |
| main/gc-02 | complete | 12 | 9 | 9 | 0 |
| main/gc-03 | complete | 8 | 5 | 5 | 0 |
| main/gc-06 | complete | 12 | 9 | 9 | 0 |
| main/gc-07 | failed | 10 | 7 | 6 | 1 |
| main/gc-08 | complete | 10 | 7 | 7 | 0 |
| main/gc-09 | complete | 9 | 6 | 6 | 0 |
| main/gc-10 | complete | 9 | 6 | 6 | 0 |
| hard/hcl-01 | complete | 18 | 15 | 15 | 0 |
| hard/hct-01 | complete | 6 | 3 | 3 | 0 |
| hard/hct-02 | complete | 7 | 4 | 4 | 0 |
| hard/hct-03 | complete | 9 | 6 | 6 | 0 |
| hard/hfp-02 | complete | 17 | 14 | 14 | 0 |
| hard/hfp-04 | complete | 18 | 15 | 15 | 0 |
| hard/hfp-05 | failed | 19 | 16 | 15 | 1 |
| hard/hfp-06 | complete | 18 | 15 | 15 | 0 |
| hard/hfp-08 | complete | 18 | 15 | 15 | 0 |
| hard/hfu-01 | failed | 17 | 14 | 13 | 1 |
| hard/hgc-01 | complete | 8 | 5 | 4 | 0 |
| hard/hgc-02 | complete | 7 | 4 | 4 | 0 |
| hard/hgc-03 | complete | 11 | 8 | 8 | 0 |
| hard/hgc-04 | complete | 12 | 9 | 9 | 0 |
| hard/hgc-05 | failed | 10 | 7 | 6 | 1 |

## Limits and preservation

- Observational log/source audit, not OS-level filesystem/network tracing: absence of visible prohibited reads is not proof that no hidden access occurred.
- Model reliance on parametric paper memory cannot be established or excluded from command logs. Semantic claim/quote grounding and answer correctness were not rescored.
- Protected-file integrity was checked by the original runner before accepting/rejecting tasks; its before-hash maps were not persisted. This audit verifies runner source hash and frozen/evidence hashes, not historical protected-file reads or temporary modifications.
- The custom runner is stricter than original collect(): it rejects any wrong-ID/unknown-command log row and any total log length above 15; original collect() counts per item and does not run this rejection check.
- Unlogged usage calls may omit task ID under the original usage path. They return only documentation and do not consume a logged corpus call; the custom runner accepts them.
- Tools execute installed Python and PowerShell outside workspaces as required by the provided instructions; those executable references are not treated as prohibited outside research-data reads.

Read-only verification: 402 frozen, evidence, status, call-log and answer files hashed before/after this audit; all unchanged. Both frozen prediction hashes match their manifest. Source hashes of the original workspace builder, prompt and custom runner match recorded run metadata. No gold or scoring files were opened. No statuses, predictions, answers, tools or benchmark files were written.

The accompanying audit.json contains every command verbatim with event line references, response hashes, per-task call logs, precise rejection records, and preservation hashes. Audit scripts and reports are outside benchmark-v2 and its frozen area.
