"""Write tasks/items.jsonl. Keys like 'fp:pi-defenses' are internal; IDs are shuffled per type."""
import json
import random
from pathlib import Path

REPO = Path(r"C:\Users\redro\paperpilot-bench")
SCRATCH = Path(__file__).parent

def col(name, typ, setting, unit=None, allowed=None):
    c = {"name": name, "type": typ, "setting": setting}
    if unit:
        c["unit"] = unit
    if allowed:
        c["allowed"] = allowed
    return c

ITEMS = [
    # find_papers
    ("fp:pi-defenses", "find_papers", "dev", False, {"topic": "Defenses against prompt injection attacks on LLM-integrated applications and agents"}),
    ("fp:dense-retrieval", "find_papers", "dev", False, {"topic": "Dense retrieval methods for open-domain question answering"}),
    ("fp:reasoning-prompting", "find_papers", "dev", False, {"topic": "Prompting techniques that elicit step-by-step reasoning from large language models"}),
    ("fp:trap-protein", "find_papers", "dev", True, {"topic": "Protein structure prediction with diffusion models"}),
    ("fp:jailbreak-optimization", "find_papers", "test", False, {"topic": "Automated jailbreak attacks that optimize adversarial prompts or suffixes against aligned language models"}),
    ("fp:misuse-benchmarks", "find_papers", "test", False, {"topic": "Benchmarks for evaluating jailbreak attacks and the misuse robustness of language models"}),
    ("fp:retrieval-lms", "find_papers", "test", False, {"topic": "Language models that retrieve from large text datastores during pre-training or inference"}),
    ("fp:adaptive-retrieval", "find_papers", "test", False, {"topic": "Deciding when to retrieve during generation: adaptive and iterative retrieval-augmented generation"}),
    ("fp:attribution", "find_papers", "test", False, {"topic": "Making language model answers attributable by citing or quoting supporting sources"}),
    ("fp:untrusted-content", "find_papers", "test", False, {"topic": "Security risks when LLMs read untrusted retrieved content or tool outputs"}),
    ("fp:embodied-planning", "find_papers", "test", False, {"topic": "Using large language models to plan actions for embodied agents and robots"}),
    ("fp:multi-agent", "find_papers", "test", False, {"topic": "Multi-agent frameworks in which several LLM agents communicate and collaborate"}),
    ("fp:tool-use", "find_papers", "test", False, {"topic": "Teaching language models to use external tools and APIs"}),
    ("fp:trap-detection", "find_papers", "test", True, {"topic": "Detecting machine-generated text with trained classifiers or statistical tests"}),
    # comparison_table
    ("ct:dense-qa", "comparison_table", "dev", False, {
        "topic": "Retrieval-based open-domain QA systems on Natural Questions",
        "paper_ids": ["2004.04906", "1906.00300", "2002.08909", "2005.11401"],
        "columns": [
            col("nq_exact_match", "numeric", "Natural Questions (open-domain) test-set exact match of the paper's own best model, from its main results table", unit="percent"),
            col("retriever_training", "enum", "how the paper's own retriever is trained relative to the reader or generator",
                allowed=["trained jointly with the reader or generator", "trained separately before the reader"]),
            col("answer_model", "text", "the model that reads retrieved passages and produces the answer"),
        ]}),
    ("ct:reasoning-gsm8k", "comparison_table", "test", False, {
        "topic": "Prompting methods for arithmetic reasoning",
        "paper_ids": ["2201.11903", "2203.11171", "2205.11916", "2211.10435"],
        "columns": [
            col("gsm8k_palm540b", "numeric", "GSM8K accuracy of the paper's own proposed method run with PaLM 540B; baselines copied from other papers don't count", unit="percent"),
            col("exemplars", "enum", "whether the proposed method needs worked examples in the prompt", allowed=["few-shot exemplars", "zero-shot"]),
            col("core_idea", "text", "the core idea of the proposed method, in a few words"),
        ]}),
    ("ct:tool-learning", "comparison_table", "test", False, {
        "topic": "Language models that learn to call tools and APIs",
        "paper_ids": ["2302.04761", "2305.15334", "2307.16789", "2303.17580"],
        "columns": [
            col("base_model_size", "numeric", "parameter count of the paper's own tool-using model, in billions", unit="billion parameters"),
            col("how_tool_use_is_learned", "enum", "how the proposed system acquires tool use", allowed=["fine-tuning on tool-use data", "prompting only"]),
            col("tools", "text", "the tools or API collections the system calls"),
        ]}),
    ("ct:jailbreak-attacks", "comparison_table", "test", False, {
        "topic": "Gradient- and search-based adversarial attacks on language models",
        "paper_ids": ["2307.15043", "2404.02151", "1908.07125", "2306.15447"],
        "columns": [
            col("asr_llama2_7b_chat", "numeric", "attack success rate of the paper's own attack on Llama-2-7B-Chat for harmful behaviors (individual-prompt setting where the paper distinguishes)", unit="percent"),
            col("access_needed", "enum", "the model access the paper's main attack requires",
                allowed=["model gradients (white-box)", "output log-probabilities only", "no gradient or log-probability access"]),
            col("optimization_method", "text", "how the attack searches for its adversarial input"),
        ]}),
    ("ct:adaptive-rag", "comparison_table", "test", False, {
        "topic": "Retrieval-augmented generation methods that interleave retrieval with generation",
        "paper_ids": ["2310.11511", "2305.06983", "2212.10509"],
        "columns": [
            col("num_eval_tasks", "numeric", "number of downstream tasks or datasets the paper's main evaluation covers", unit="count"),
            col("retrieval_trigger", "enum", "when the proposed method retrieves",
                allowed=["at every reasoning step or sentence", "only when the model signals it needs to"]),
            col("generator", "text", "the language model that generates the output in the main experiments"),
        ]}),
    ("ct:pi-defenses", "comparison_table", "test", False, {
        "topic": "Defenses that protect LLM applications against prompt injection",
        "paper_ids": None,
        "columns": [
            col("agentdojo_utility", "numeric", "percentage of AgentDojo tasks solved with the defense enabled", unit="percent"),
            col("approach", "enum", "where the defense acts",
                allowed=["fine-tunes the model", "wraps an unmodified model in a system design"]),
            col("mechanism", "text", "what the defense separates or controls to stop injected instructions"),
        ]}),
    ("ct:trap-diffusion-mia", "comparison_table", "test", True, {
        "topic": "Membership inference attacks against text-to-image diffusion models",
        "paper_ids": None,
        "columns": [
            col("attack_auc", "numeric", "membership inference AUC reported for the paper's attack", unit="AUC"),
            col("access", "enum", "access the attack needs", allowed=["white-box", "black-box"]),
            col("target_model", "text", "the diffusion model attacked"),
        ]}),
    # citation_links
    ("cl:pi-security", "citation_links", "dev", False, {"paper_ids": ["2302.12173", "2211.09527", "2402.06363", "2404.13208", "2503.18813", "2503.00061", "2510.09023", "2307.15043", "1312.6199", "2009.11462"]}),
    ("cl:dense-qa", "citation_links", "test", False, {"paper_ids": ["1704.00051", "1906.00300", "2002.08909", "2004.04906", "2005.11401", "2112.09118", "2208.03299", "2301.12652", "2305.14251", "2204.06092"]}),
    ("cl:reasoning", "citation_links", "test", False, {"paper_ids": ["2201.11903", "2205.11916", "2203.11171", "2211.10435", "2305.10601", "2112.00114", "2110.14168", "2212.10403", "2303.17760", "2308.16505"]}),
    ("cl:embodied", "citation_links", "test", False, {"paper_ids": ["2201.07207", "2204.01691", "2207.05608", "2209.11302", "2302.01560", "2304.11477", "2305.16291", "2210.03629", "2308.03688", "2303.17580"]}),
    ("cl:multi-agent", "citation_links", "test", False, {"paper_ids": ["2303.17760", "2308.00352", "2308.08155", "2308.10848", "2305.14325", "2304.03442", "2307.02485", "2303.11366", "2211.10435", "2201.07207"]}),
    ("cl:alignment", "citation_links", "test", False, {"paper_ids": ["1706.03741", "2203.02155", "2204.05862", "2209.14375", "2212.08073", "2112.09332", "2209.07858", "2202.03286", "1608.04644", "2104.13733"]}),
    # grounded_claims
    ("gc:adaptive-attacks", "grounded_claims", "dev", False, {"question": "How well do published defenses against prompt injection hold up when attackers adapt their attacks to the defense?"}),
    ("gc:cot-scale", "grounded_claims", "dev", False, {"question": "At what model scale does chain-of-thought prompting start to help, and why is this described as an emergent ability?"}),
    ("gc:trap-mamba", "grounded_claims", "dev", True, {"question": "How does the Mamba selective state-space model compare with Transformers of the same size on language-modeling perplexity?"}),
    ("gc:jailbreak-failures", "grounded_claims", "test", False, {"question": "Why does safety training fail to stop jailbreaks, and how do automated attacks take advantage of it?"}),
    ("gc:long-context", "grounded_claims", "test", False, {"question": "Do language models use information equally well wherever it appears in a long context, and how do irrelevant retrieved passages affect them?"}),
    ("gc:parametric-vs-retrieval", "grounded_claims", "test", False, {"question": "How does factual knowledge stored in model parameters compare with retrieval, especially for less popular facts?"}),
    ("gc:self-improvement", "grounded_claims", "test", False, {"question": "How do LLM agents improve on later attempts using feedback or memory, without updating their weights?"}),
    ("gc:helpful-harmless", "grounded_claims", "test", False, {"question": "What tensions between helpfulness and harmlessness do RLHF-trained assistants show, and how have researchers tried to reduce them?"}),
    ("gc:indirect-attacks", "grounded_claims", "test", False, {"question": "How can attackers compromise LLM applications through content the model retrieves, rather than through the user's own prompt?"}),
    ("gc:trap-qlora", "grounded_claims", "test", True, {"question": "According to the QLoRA paper, how much GPU memory does 4-bit NormalFloat quantization need to fine-tune a 65B-parameter model?"}),
    # followup_questions
    ("fu:indirect-injection", "followup_questions", "dev", False, {"topic": "indirect prompt injection", "paper_ids": ["2302.12173", "2503.00061"]}),
    ("fu:long-noisy-context", "followup_questions", "test", False, {"topic": "how language models use long or noisy retrieved context", "paper_ids": ["2307.03172", "2310.01558"]}),
    ("fu:agent-self-improvement", "followup_questions", "test", False, {"topic": "LLM agents that improve from their own past attempts", "paper_ids": ["2303.11366", "2308.10144"]}),
]

PREFIX = {"find_papers": "fp", "comparison_table": "ct", "citation_links": "cl",
          "grounded_claims": "gc", "followup_questions": "fu"}
rng = random.Random(20261109)
ids = {}
for typ, pre in PREFIX.items():
    keys = [k for k, t, *_ in ITEMS if t == typ]
    nums = list(range(1, len(keys) + 1))
    rng.shuffle(nums)
    ids.update({k: f"{pre}-{n:02d}" for k, n in zip(keys, nums)})

rows = [{"id": ids[k], "type": t, "split": s, "trap": trap, "input": inp} for k, t, s, trap, inp in ITEMS]
rows.sort(key=lambda r: r["id"])
(REPO / "tasks" / "items.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
(SCRATCH / "item_keys.json").write_text(json.dumps(ids, indent=1), encoding="utf-8")
from collections import Counter
print(Counter((r["split"], "trap" if r["trap"] else r["type"]) for r in rows))
print(json.dumps(ids))
