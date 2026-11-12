# Judge validation on real outputs

A teammate, 형중, labeled the 30 judge decisions below on the label review page (2026-11-11). Their labels are in `docs/judge_validation.csv` with `labeler` set to 형중, next to an earlier stand-in set from the Claude Code session (marked as not human). Reproduce with:

```
py scoring/judge.py --agreement docs/judge_validation.csv --labeler 형중
```

## The sample

There are 30 judge decisions (`qwen3.5:9b`, temperature 0), drawn at random (seed 0) from the scored test runs of both Claude baselines. Duplicates across the two runs were removed. The sample holds 22 claim-support decisions, 5 follow-up ratings, and 3 table-cell equivalences. The reviewer never saw the judge's answer.

## Results

| Decision | n | Human vs. judge |
|---|---|---|
| Claim support | 22 | 14/22 agree (64%). Kappa is 0, but uninformative: the judge said "supported" on all 22, so it has only one class |
| Table-cell equivalence | 3 | 2/3 agree, kappa 0.40 |
| Follow-up rubric (1 to 5 per criterion) | 5 | Mean absolute difference 2.0 on specific, 2.0 on grounded, 1.6 on novel. Human mean 3.1, judge mean 4.9 |

**Follow-up questions.** The judge is far more lenient than the human. On no question did the two come within one point on average, and the human rated every question lower. This confirms what the baselines suggested: both scored 0.97 on follow-ups, so the metric barely separates agents.

### Rubric v2 (2026-11-12)

The follow-up prompt was rewritten in response (`prompts/judge.md`, `PROMPT_VERSIONS["followup_score"] = 2`):

- Every level of each criterion has an anchor, and the prompt asks for the lower score when unsure.
- The judge first copies the gap-note phrase the question addresses (or "none") and counts how many separate questions it asks.
- The scorer then enforces two caps in code (`apply_followup_caps`): specific is at most 3 for a question with two or more parts, and grounded is at most 3 when no gap applies. Four of the five rated questions asked two things at once.

Results:

| Check | v1 | v2 |
|---|---|---|
| Mean absolute distance from the human, 5 questions (in-sample) | 1.87 | 1.20 |
| Known-answer pairs ranked correctly (`judge_eval.py`) | 6/6 | 6/6, mean gap 1.8 points |
| Follow-up score, main B1 / B0 | 0.97 / 0.95 | 0.84 / 0.83 |
| Follow-up score, hard B1 / B0 | 0.97 / 0.97 | 0.87 / 0.80 |

Read these with care:

- **In-sample.** The five human-rated questions shaped the rubric, so the drop from 1.87 to 1.20 is a sanity check, not a validation. A fresh human-labeled sample would be needed to claim the judge now matches people.
- **Novelty stays saturated.** The judge rated every question 5 on novelty under both rubrics, while the human gave 2 to 4. The judge sees paper titles and gap notes, not the papers' text, so it can't tell whether a paper already ran the proposed test. Fixing that would mean giving it the papers, which a 9B model with a short prompt handles poorly.
- **Still a weak discriminator.** With one or two follow-up items per split, B1 and B0 differ by 0.01 on the main track and 0.07 on the hard track, both within noise.

Only follow-up decisions were re-judged. Claim and table-cell decisions came from the cache, and every other score is unchanged.

**Claim support.** All 8 disagreements go one way: the human said "partly supported" where the judge said "supported". The human's notes put them in two groups:

- **Wording only (6 of 8):** judge-12, 17, 22, 25, 26, 29. The notes cite missing exact phrases, for example "marginally improves" against "add little", "datasets" against "benchmarks", and several say "based on strict text matching". The rubric counts a claim as supported when the passage "states it, or it follows directly", so a paraphrase should pass. These reflect a stricter reading of the rubric than intended, not judge errors.
- **Substantive (2 of 8):** judge-03, where the passage supports only half of what the claim says, and judge-10, where the passage never states that Vicuna is an open model. In both, the judge accepted a claim that goes beyond its passage.

Under the rubric as written, agreement is about 20/22. Reported raw, it is 14/22. The two substantive cases are the useful finding: on real outputs the judge sometimes lets a claim go slightly beyond its quote.

**Table cells.** The one disagreement, judge-02, has the judge calling two cell values equivalent and the human calling them different. The stand-in set disagreed with the judge on a different cell (the "adversarially aligned" paper, 2306.15447), so both disagreements are borderline paraphrases.

## Limitations

- **One labeler.** With one human, there is no inter-annotator agreement, so we cannot separate judge error from labeler variation. The wording-only disagreements suggest the rubric text needs an explicit paraphrase example.
- **Strong-agent outputs only.** The sample comes from the Claude baselines, whose claims were nearly all correct. It tests whether the judge rejects good claims more than whether it catches bad ones. The known-answer cases in `docs/judge_comparison.md` cover the second question: wrong numbers, wrong models, contradictions, and over-broad claims.
- **Small n.** 22 claims, 5 follow-ups, and 3 cells. Treat the percentages as rough.
