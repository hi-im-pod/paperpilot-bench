# Judge validation on real outputs

**The labels below are a stand-in from the Claude Code session, not human labels.** The plan calls for a teammate to label the same 30 decisions. Their labels go in `docs/judge_validation.csv` with their name in the `labeler` column. Then run:

```
py scoring/judge.py --agreement docs/judge_validation.csv --labeler "<name>"
```

## The sample

There are 30 judge decisions (`qwen3.5:9b`, temperature 0), drawn at random (seed 0) from the scored test runs of both Claude baselines. Duplicates across the two runs were removed. The sample holds 22 claim-support decisions, 5 follow-up ratings, and 3 table-cell equivalences.

## Results

| Decision | n | Agreement with stand-in labels |
|---|---|---|
| Claim support | 22 | 22/22. Kappa is undefined, because every label on both sides is "supported" |
| Table-cell equivalence | 3 | 2/3 |
| Follow-up rubric (1–5 per criterion) | 5 | Mean absolute difference 0.2 on each of specific, grounded, and novel |

The one equivalence disagreement concerns the "adversarially aligned" paper (2306.15447). Gold: "gradient-based optimization of adversarial inputs, notably adversarial images against multimodal models." Prediction: "gradient-based adversarial perturbation of the input image for multimodal models; brute-force search to show existing text attacks are too weak." The judge said not equivalent. The stand-in label says equivalent. Either reading is defensible.

## What this sample can't show

All 59 claim decisions on the strong baseline came back "supported", and every one checked here was supported. So this sample shows the judge doesn't wrongly reject good claims. It says nothing about whether the judge catches bad ones, because strong agents produced none.

Two other checks cover that side:
- **The known-answer cases** in `docs/judge_comparison.md`. These include wrong numbers, wrong models, contradictions, and over-broad claims. The judge gave half credit to some wrong claims, and the scorer's number check now catches the ones with wrong numbers.
- **Weaker agents' claims**, such as the local Qwen B1 run. Labeling those would test rejection on real outputs. Qwen's dev claims never reached the judge, though, because none of its quotes matched the papers. A weaker agent with valid quotes but wrong claims would be the useful next sample.
