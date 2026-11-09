# Judge model comparison

`qwen3.5:9b` stays the default judge. With the scorer's claim-number check in place, it scored claims with half the error of `gemma4:12b` (1.0 vs 2.0 over 22 cases), never rejected a correct claim, and ranked all six follow-up pairs correctly. The margin is small: 44 known-answer cases can show which errors each model makes, but not settle a close call. The plan's human validation on real benchmark outputs decides what ships.

Reproduce with `py scoring/judge_eval.py --models qwen3.5:9b gemma4:12b`. The raw answers are in `docs/judge_eval_results.json`. Run on 2026-11-09, RTX 5070 Ti Laptop GPU (12 GB).

## The cases

`scoring/judge_eval_cases.jsonl` has three kinds of case:

- **22 claim-support cases.** Each pairs a passage copied verbatim from the abstract of one of four seed papers (GCG, ReAct, RAG, indirect prompt injection) with a claim. The expected labels are 9 supported, 5 partial, and 8 unsupported. The unsupported claims include a changed number, a number taken from the wrong benchmark, a wrong model, a wrong count, a contradiction, and an unrelated passage.
- **16 short-text equivalence pairs.** Eight are the same thing written differently. Eight are different things, such as Vicuna-13B vs Vicuna-7B, or GCG vs "gradient-based".
- **6 follow-up question pairs.** Each pairs a specific, open question with a worse one: vague (4 pairs), already answered by the paper (1), or unrelated to the papers (1).

Claude drafted the expected labels while building the harness, so **a teammate should review them**.

## Results

"With number check" is what the scorer actually awards: a claim containing a number that isn't in the passage is unsupported, and the judge is never asked. Since the second run, the check also treats the words two to twenty as numbers. These results are from that run.

| | qwen3.5:9b | gemma4:12b |
|---|---|---|
| Claim labels right, judge alone | 18/22 | 19/22 |
| Claim labels right, with number check | 20/22 | 19/22 |
| Kappa vs expected, with number check | 0.86 | 0.79 |
| Supported vs not, right | 22/22 | 21/22 |
| Support-score error, judge alone | 2.0 | 2.0 |
| **Support-score error, with number check** | **1.0** | **2.0** |
| Equivalence pairs right | 16/16 | 16/16 |
| Follow-up pairs ordered correctly | 6/6 | 5/6 |
| Same answers on a second pass | 44/44 | 44/44 |
| JSON errors | 0 | 0 |

Support-score error weights each claim the way the scorer does (supported 1, partial 0.5, unsupported 0) and sums the absolute differences from the expected label. Speed varied more between runs than between models: Qwen took 0.9 s per call in one run and 6.3 s in another, depending on what else the GPU was doing. So speed isn't a factor.

## Where each one failed

**Judge alone.** Qwen gave "partial" to four claims that should be "unsupported":
- cs-02, a wrong number (43% where the paper says 34%)
- cs-04, a number taken from the other benchmark
- cs-12, a wrong model
- cs-15, a wrong count

Gemma made two of the same mistakes (cs-04, cs-12). It also rejected a correct paraphrase, cs-05: "On WebShop, ReAct's absolute success-rate gain over imitation and RL baselines is 10%". And it gave 5/5/5 to a follow-up question the paper already answers (fq-05).

**What the number check changes:**
- It fixes cs-02 for Qwen.
- It fixes cs-12 for both models: "Llama-2-7B-Chat" contains a 2 that the passage doesn't.
- It fixes cs-15 for Qwen, now that number words count: "three" against a passage that says "two".
- It misses cs-04, because the 10% is in the passage, just attached to the other benchmark.
- It costs one case for both models. cs-13 is labeled "partial" because it adds a "100% success rate" claim, and the check now scores it 0.

## The number rule and "partial"

The judge prompt calls a claim "partial" when it adds an extra number the passage lacks. The scorer is stricter, and in that case it awards 0, not 0.5. That fits the rest of the benchmark, where quotes must also match numbers exactly. But it means a claim mixing a backed fact with an unbacked number earns nothing. If the team prefers half credit there, drop the check in `score_grounded_claims` and accept the judge's leniency on wrong numbers instead.
