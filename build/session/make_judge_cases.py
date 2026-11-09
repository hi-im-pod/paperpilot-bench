"""Writes scoring/judge_eval_cases.jsonl. Passages are verbatim from four seed-paper abstracts."""
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(r"C:\Users\redro\paperpilot-bench")
sys.path.insert(0, str(REPO / "scoring"))
from normalize import normalize  # noqa: E402

R = ("Furthermore, on two interactive decision making benchmarks (ALFWorld and WebShop), ReAct outperforms "
     "imitation and reinforcement learning methods by an absolute success rate of 34% and 10% respectively")
R2 = ("Concretely, on question answering (HotpotQA) and fact verification (Fever), ReAct overcomes prevalent issues "
      "of hallucination and error propagation in chain-of-thought reasoning by interacting with a simple Wikipedia "
      "API, and generating human-like task-solving trajectories that are more interpretable than baselines without "
      "reasoning traces.")
G = ("However, instead of relying on manual engineering, our approach automatically produces these adversarial "
     "suffixes by a combination of greedy and gradient-based search techniques, and also improves over past "
     "automatic prompt generation methods.")
G2 = ("Specifically, we train an adversarial attack suffix on multiple prompts (i.e., queries asking for many "
      "different types of objectionable content), as well as multiple models (in our case, Vicuna-7B and 13B).")
A = ("We compare two RAG formulations, one which conditions on the same retrieved passages across the whole "
     "generated sequence, and another which can use different passages per token.")
A2 = ("We fine-tune and evaluate our models on a wide range of knowledge-intensive NLP tasks and set the state of "
      "the art on three open domain QA tasks, outperforming parametric seq2seq models and task-specific "
      "retrieve-and-extract architectures.")
I = ("We demonstrate our attacks\u2019 practical viability against both real-world systems, such as Bing\u2019s GPT-4 "
     "powered Chat and code-completion engines, and synthetic applications built on GPT-4.")
I3 = ("Despite the increasing integration and reliance on LLMs, effective mitigations of these emerging threats "
      "are currently lacking.")

CLAIMS = [
    (R, "ReAct beats imitation and RL methods on ALFWorld by an absolute 34% success rate.", "supported", "paraphrase"),
    (R, "ReAct beats imitation and RL methods on ALFWorld by an absolute 43% success rate.", "unsupported", "wrong number"),
    (R, "ReAct improves success rate by 34% on ALFWorld and also sets the state of the art on HotpotQA.", "partial", "adds a result"),
    (R, "ReAct outperforms reinforcement learning methods by 10% on ALFWorld.", "unsupported", "number from the other benchmark"),
    (R, "On WebShop, ReAct's absolute success-rate gain over imitation and RL baselines is 10%.", "supported", "paraphrase"),
    (R, "ReAct beats imitation and RL baselines on ALFWorld and WebShop, and is the first method to exceed human "
        "performance on WebShop.", "partial", "adds a claim"),
    (R2, "ReAct reduces hallucination in chain-of-thought reasoning on HotpotQA by querying a Wikipedia API.", "supported", "paraphrase"),
    (R2, "ReAct eliminates all hallucination on HotpotQA and Fever.", "partial", "stronger conclusion"),
    (G, "The attack finds adversarial suffixes using greedy and gradient-based search.", "supported", "paraphrase"),
    (G, "The attack's adversarial suffixes are written by hand by human red-teamers.", "unsupported", "contradiction"),
    (G2, "The suffix was trained on Vicuna-7B and Vicuna-13B.", "supported", "paraphrase"),
    (G2, "The suffix was trained on Llama-2-7B-Chat and Vicuna-13B.", "unsupported", "wrong model"),
    (G2, "The suffix was trained on Vicuna-7B and 13B and transfers to every production model with a 100% success rate.",
     "partial", "adds a claim"),
    (A, "The paper compares a RAG variant that uses the same passages for the whole output with one that can switch "
        "passages per token.", "supported", "paraphrase"),
    (A, "The paper compares three RAG formulations.", "unsupported", "wrong count"),
    (A, "Indirect prompt injection lets attackers exfiltrate user data.", "unsupported", "unrelated passage"),
    (A2, "RAG sets the state of the art on three open-domain QA tasks.", "supported", "paraphrase"),
    (A2, "RAG sets the state of the art on every knowledge-intensive task it was evaluated on.", "partial", "broader scope"),
    (A2, "RAG reaches 56.8% exact match on Natural Questions.", "unsupported", "number not in passage"),
    (I, "The indirect prompt injection attacks were shown to work against Bing's GPT-4-powered chat.", "supported", "paraphrase"),
    (I3, "The paper reports that effective mitigations against these threats already exist.", "unsupported", "contradiction"),
    (I3, "According to the authors, effective defenses against these threats are currently missing.", "supported", "paraphrase"),
]
EQUIV = [
    ("base_model", "Llama-2-7B-Chat", "LLaMA 2 7B chat", True),
    ("base_model", "Vicuna-13B", "Vicuna-7B", False),
    ("retriever", "BM25", "Okapi BM25", True),
    ("retriever", "DPR", "dense passage retriever (DPR)", True),
    ("attack_method", "GCG", "gradient-based", False),
    ("base_model", "GPT-2", "transformer", False),
    ("dataset", "HotpotQA", "Hotpot QA", True),
    ("dataset", "Natural Questions", "TriviaQA", False),
    ("defense", "perplexity filtering", "perplexity filter", True),
    ("defense", "paraphrasing", "retokenization", False),
    ("generator", "BART-large", "BART", False),
    ("agent_framework", "ReAct", "Reason+Act (ReAct) prompting", True),
    ("base_model", "GPT-4", "GPT-4o", False),
    ("metric", "attack success rate", "ASR", True),
    ("knowledge_source", "Wikipedia", "Wikidata", False),
    ("access", "white-box", "gradient access (white-box)", True),
]
GCG_T = "Universal and Transferable Adversarial Attacks on Aligned Language Models"
REACT_T = "ReAct: Synergizing Reasoning and Acting in Language Models"
RAG_T = "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks"
INJ_T = "Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection"
FOLLOWUP = [
    ("jailbreak attacks on aligned LLMs", [GCG_T], "Suffixes are evaluated without perplexity-based defenses.",
     "Does a perplexity filter with a threshold tuned on benign prompts block GCG suffixes on Vicuna-7B, and how much "
     "success does a fluency-constrained GCG variant recover?", "How can we make language models safer?", "vague"),
    ("reasoning-and-acting agents", [REACT_T],
     "ReAct relies on few-shot prompting and a simple Wikipedia API; fine-tuning with more data is left open.",
     "Does fine-tuning a 7B model on 3,000 ReAct trajectories close the gap to few-shot PaLM-540B on HotpotQA exact match?",
     "What is the future of AI agents?", "vague"),
    ("retrieval-augmented generation", [RAG_T], "The document index is fixed after training; refreshing it is not studied.",
     "How does RAG-Sequence accuracy on Natural Questions change when the Wikipedia index is swapped for a 2023 dump "
     "without retraining the generator?", "Is retrieval useful?", "vague"),
    ("indirect prompt injection", [INJ_T], "Effective mitigations are lacking.",
     "Do instruction-hierarchy fine-tuning and spotlighting reduce indirect prompt injection success on the paper's "
     "synthetic GPT-4 email-assistant application?", "Can prompt injection be solved?", "vague"),
    ("reasoning-and-acting agents", [REACT_T], "ReAct is evaluated with a small, fixed action space on ALFWorld.",
     "Does ReAct's advantage on ALFWorld hold when the admissible action space is enlarged tenfold?",
     "Does ReAct outperform imitation and reinforcement learning baselines on ALFWorld?", "already answered by the paper"),
    ("retrieval-augmented generation", [RAG_T], "Only a handful of retrieved passages per query are used.",
     "Does retrieving 50 instead of 5 passages per query help RAG-Token on TriviaQA, or does the generator ignore the "
     "extra passages?", "Which jailbreak suffixes work best against Claude?", "unrelated to the papers"),
]

rows = []
for i, (p, c, lab, why) in enumerate(CLAIMS, 1):
    rows.append({"id": f"cs-{i:02d}", "kind": "claim_support", "inputs": {"claim": c, "passage": normalize(p)},
                 "expected": lab, "note": why})
for i, (col, g, pr, lab) in enumerate(EQUIV, 1):
    rows.append({"id": f"te-{i:02d}", "kind": "text_equiv",
                 "inputs": {"column": col, "setting": "main results table", "gold": g, "pred": pr}, "expected": lab})
for i, (topic, titles, gaps, good, bad, why) in enumerate(FOLLOWUP, 1):
    rows.append({"id": f"fq-{i:02d}", "kind": "followup_pair",
                 "inputs": {"topic": topic, "paper_titles": titles, "gap_notes": gaps, "better": good, "worse": bad},
                 "note": f"the worse question is {why}"})
out = REPO / "scoring" / "judge_eval_cases.jsonl"
out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
print(len(rows), dict(Counter(r["kind"] for r in rows)),
      dict(Counter(r["expected"] for r in rows if r["kind"] == "claim_support")))
