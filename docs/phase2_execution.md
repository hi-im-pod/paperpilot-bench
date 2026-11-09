# Phase 2 execution plan

The corpus was frozen on 2026-11-09 (`corpus/FREEZE.json`). This plan covers the rest: task items, gold labels, baselines, judge validation, and a front end that lets other teams connect their agent. With no API key on hand, the Claude Code session that built the harness does the labeling, and blind Claude subagents run the strong baseline. Every API path (`--provider anthropic|openai|ollama`) stays wired in for anyone who has a key.

## Decisions

| Question | Decision |
|---|---|
| Who writes gold | Claude (this session) drafts and checks every item against the paper text. Teammates re-check a stratified 20% sample before Nov 16. |
| Strong baseline | Blind Claude subagents, one per task type, run in a copy of the repo with all gold removed. They use only the corpus tools. |
| Front end | Local web app, plus a hosted leaderboard where teams post their scores. |
| Agent contract | HTTP, any language. The bench POSTs each task to the agent, and the agent calls the corpus tools over HTTP. |

## Step 2: task items (40)

| Type | Dev | Test |
|---|---|---|
| find_papers | 3 | 9 |
| comparison_table | 1 | 5 |
| citation_links | 1 | 5 |
| grounded_claims | 2 | 6 |
| followup_questions | 1 | 2 |
| traps (spread across types) | 2 | 3 |
| **Total** | **10** | **30** |

- A third of the find-papers topics cross two clusters.
- Comparison tables use 3–4 papers, each with at least one numeric, one enum, and one text column.
- Every trap is checked against the corpus to confirm it has no answer there.

## Step 3: gold labels

- **find_papers:** pool candidates with BM25 plus embeddings (the tools in `draft_labels.py`, minus the LLM), then grade every pooled paper 0/1/2, reading the text where the abstract isn't enough.
- **comparison_table:** fill each cell from the paper text, with a verbatim quote.
- **citation_links:** start from the S2 edges, then add a new deterministic check that matches each paper's reference list against the other papers' titles and arXiv IDs. Review every edge where the two disagree by reading the reference entry.
- **grounded_claims:** supporting papers, each with a verbatim quote.
- **followup_questions:** gap notes from the limitations and discussion sections.

Provenance: `drafting_model` is `claude-session`, `verified_by` is `claude-session (self-check)`, and `checked_by` stays empty for teammates. `draft_labels.py --sample-check` marks the 20% sample.

Gate: `assemble_gold.py --perfect-preds` must score 1.0 on every deterministic metric, which proves every gold quote matches the corpus.

## Step 4: baselines on test

- **B1, strong (Claude, blind).** Five subagents, one per task type. Each works in a scratch copy holding only the corpus, the tools, its task items, and `prompts/agent.md`. A logging wrapper around the tools counts each item's tool calls. The subagents are instructed not to look elsewhere on disk; they aren't technically sandboxed.
- **B0, titles only.** One subagent gets the ID and title list and no tools.
- **Floor.** The existing B1 runs on local `qwen3.5:9b`.

## Step 5: judge validation

- Score the baselines with the judge, then export 30 judge decisions.
- Claude labels the 30 as a stand-in, and the agreement is reported, **clearly marked as Claude, not human**. The CSV stays open for teammates to add the human labels the plan calls for.
- Teammates also review the expected labels in `scoring/judge_eval_cases.jsonl`.

## Front end

**Local app.** `py app/server.py` opens a page at `http://127.0.0.1:8765`. The page does four things:
- takes the agent's URL and checks it answers (`GET /health`)
- picks a split, dev or test
- runs items live, with per-item status, tool-call counts, and time
- shows per-type scores with confidence intervals, plus each item's output beside the gold (dev only)

If the gold for a split isn't present, as with test for other teams, the page offers `preds.jsonl` for download to send to us.

**Agent contract (HTTP).**
- The agent exposes `POST /solve`. It receives `{"task": {...}, "tools_url": "http://.../runs/<run>/items/<item>/tools"}` and returns a prediction: `{"abstain", "output", "trace"}`.
- The tools are `POST {tools_url}/search`, `/read`, `/list_sections`, and `/get_metadata`, with the same arguments as `tools/corpus_tools.py`.
- `tools_url` is scoped to one item, so tool calls are counted automatically.
- Per-item timeout: 300 s by default.

**Reference agent.** `examples/http_agent.py` wraps the B1 loop as an HTTP agent, with `--provider anthropic|openai|ollama`. Teams can copy it.

**Hosted leaderboard.** A claude.ai page with a shared table. A team pastes the summary block the local app produces; the page records the team, agent, split, per-type scores, and hallucination rate. Test-set rows come from our scoring of submitted predictions.

**Dependencies.** Python's standard library only (`http.server`), plus vanilla JS. Nothing new to install.

## Order

1. Deterministic citation checker, then task items, then gold, then the assembly gate.
2. Front end and reference agent, with tests. Built while the baseline subagents run.
3. Baselines, then scoring, then judge validation.
4. Leaderboard page.
5. Commit and push.
