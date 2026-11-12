# Judge prompts

`scoring/judge.py` uses these verbatim with the pinned local model (default `ollama:qwen3.5:9b`, temperature 0, JSON mode, thinking off; `ollama:gemma4:12b` also works). The judge only covers what string and set math can't: claim support, short-text cell equivalence, and follow-up question quality.

They're written for a 9B model, so each prompt asks one narrow question, gives one example, and fixes the JSON shape. Bump that prompt's entry in `PROMPT_VERSIONS` in `judge.py` whenever you edit it. The version is part of the cache key, so an edit invalidates that prompt's cached decisions and leaves the others alone.

## 1. claim_support

```
You check whether a passage from a research paper supports a claim.

Claim:
{claim}

Passage from the cited paper:
"""
{passage}
"""

Labels:
- "supported": the passage states the claim, or the claim follows directly from it.
  Paraphrase is fine. Numbers in the claim must match the passage.
- "partial": the passage supports part of the claim, but the claim adds something
  the passage doesn't say (an extra number, a broader scope, a stronger conclusion).
- "unsupported": the passage doesn't say this, says something different, or is
  about something else.

Judge only from the passage. Don't use outside knowledge, even if the claim is true.

Example:
Claim: "The method cuts attack success rate to under 5% on all tested models."
Passage: "...our defense lowers attack success rate to 3.1% on Llama-2 and 4.4% on Vicuna..."
Answer: {"label": "partial", "reason": "Passage gives two models; claim says all tested models."}

Answer with JSON only: {"label": "supported" | "partial" | "unsupported", "reason": "<one sentence>"}
```

## 2. text_equiv

```
You compare two short answers for one cell of a research comparison table.

Column: {column}
Setting: {setting}
Reference answer: {gold}
Candidate answer: {pred}

Decide whether the candidate means the same thing as the reference for this column.
Different wording, abbreviations, or a name with or without its citation are fine.
A more general or more specific answer is not the same: "transformer" is not the
same as "GPT-2", and "gradient-based" is not the same as "GCG".

Example:
Column: base_model  Reference: Llama-2-7B-Chat  Candidate: LLaMA 2 7B chat
Answer: {"equivalent": true, "reason": "Same model, different spelling."}

Answer with JSON only: {"equivalent": true | false, "reason": "<one sentence>"}
```

## 3. followup_score

Version 2 (2026-11-12). Version 1 gave nearly every baseline question 5/5/5, while a human reviewer rated the same questions 3.1 on average. This version anchors every score level, and the scorer enforces two caps in code (`apply_followup_caps` in `judge.py`), because a 9B model doesn't apply them reliably.

```
You rate one follow-up research question that an assistant proposed after reading
some papers. Most proposed questions are reasonable. Your job is to separate the
excellent ones from the merely reasonable ones, so use the whole scale.

Topic: {topic}
Papers read: {paper_titles}
Gaps noted by a human expert: {gap_notes}

Question to rate:
{question}

First decide two things:
- gap: copy the phrase from the gap notes that this question addresses most
  directly, or "none" if it addresses none of them.
- parts: how many separate questions it asks. "Does X raise A, and how does that
  compare with Y?" asks 2.

Then score each criterion from 1 to 5:
- specific:
  5 = one testable question that names the method, the setting, and the measurement.
  4 = testable, but one of those three is missing or vague.
  3 = a clear direction but not yet an experiment, or two or more questions at once.
  2 = a broad area with a little detail.
  1 = vague ("How can LLMs be safer?").
- grounded:
  5 = tackles the gap you copied, as the notes or papers state it.
  4 = follows from a stated gap but extends or shifts it.
  3 = related to the papers but to no stated gap.
  2 = related to the topic only.
  1 = unrelated to these papers.
- novel:
  5 = the papers clearly leave it open, and none of them runs this test.
  4 = open, but close to an experiment one of the papers already reports.
  3 = partly answered by one of the papers.
  2 = mostly answered by one of the papers.
  1 = one of these papers already answers it.

A 5 needs every part of its description to hold. When unsure between two scores,
choose the lower one.

Answer with JSON only:
{"gap": "<phrase or none>", "parts": <number>, "specific": <1-5>, "grounded": <1-5>, "novel": <1-5>, "reason": "<one sentence>"}
```

## Validating the judge

Before the presentation, export 30 decisions (`py scoring/judge.py --sample 30 ...`). Then have a teammate who hasn't seen the judge's labels fill in `human_label`, and report agreement and Cohen's kappa. If kappa on `claim_support` comes out below 0.6, change the prompt or the model before trusting the support numbers. Report the follow-up scores with a caveat either way.
