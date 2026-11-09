"""Write gold/drafts/*.json for every non-trap item, from labels decided in this session."""
import json
import sys
from pathlib import Path

SCRATCH = Path(__file__).parent
sys.path.insert(0, str(SCRATCH))
import lab  # noqa: E402

REPO = lab.REPO
sys.path.insert(0, str(REPO / "build"))
from ref_match import cites  # noqa: E402

KEYS = json.loads((SCRATCH / "item_keys.json").read_text())
ITEMS = {i["id"]: i for i in map(json.loads, (REPO / "tasks" / "items.jsonl").read_text(encoding="utf-8").splitlines())}
DRAFTS = REPO / "gold" / "drafts"
DRAFTS.mkdir(parents=True, exist_ok=True)
PROV = {"drafting_model": "claude-session", "verified_by": "claude-session (self-check)", "checked_by": None}

# ---------- find_papers: (grade-2 set, grade-1 set) ----------
FP = {
    "fp:pi-defenses": ({"2402.06363", "2503.18813", "2404.13208", "2503.00061", "2510.09023"},
                       {"2302.12173", "2603.19469", "2510.23883", "2402.07867", "2402.00888"}),
    "fp:dense-retrieval": ({"2004.04906", "1906.00300", "2002.08909", "2112.09118"},
                           {"2005.11401", "2208.03299", "1704.00051", "2009.02252", "2209.10063"}),
    "fp:reasoning-prompting": ({"2201.11903", "2205.11916", "2203.11171", "2305.10601", "2112.00114", "2211.10435"},
                               {"2212.10403", "2212.10509", "2305.14992", "2210.03629"}),
    "fp:jailbreak-optimization": ({"2307.15043", "2404.02151", "2306.15447", "2303.04381", "2510.09023"},
                                  {"1908.07125", "2104.13733", "2202.03286", "2503.00061"}),
    "fp:misuse-benchmarks": ({"2404.01318", "2402.04249", "2402.10260", "2403.03218"},
                             {"2009.11462", "2401.10019", "2209.07858"}),
    "fp:retrieval-lms": ({"2002.08909", "2112.04426", "1911.00172", "2208.03299", "2302.00083", "2301.12652", "2005.11401"},
                         {"2310.11511", "2203.05115", "2312.10997"}),
    "fp:adaptive-retrieval": ({"2305.06983", "2310.11511", "2212.10509", "2305.15294", "2212.10511"},
                              {"2310.04408", "2212.14024", "2312.10997", "2310.01558"}),
    "fp:attribution": ({"2203.11147", "2305.14627", "2112.09332"},
                       {"2305.14251", "2209.14375", "2201.08239", "2310.11511"}),
    "fp:untrusted-content": ({"2302.12173", "2402.07867", "2503.00061", "2503.18813"},
                             {"2402.06363", "2404.13208", "2510.23883", "2603.19469", "2402.00888", "2510.09023"}),
    "fp:embodied-planning": ({"2201.07207", "2204.01691", "2207.05608", "2209.11302", "2302.01560", "2304.11477", "2305.16291", "2307.02485"},
                             {"2305.14992", "2210.03629"}),
    "fp:multi-agent": ({"2303.17760", "2308.00352", "2308.08155", "2308.10848", "2307.02485", "2305.14325"},
                       {"2304.03442", "2308.11432"}),
    "fp:tool-use": ({"2302.04761", "2305.15334", "2307.16789", "2303.17580", "2305.17126", "2304.08354"},
                    {"2302.07842", "2211.10435", "2112.09332", "2210.03629"}),
}


def find_papers(key):
    item = ITEMS[KEYS[key]]
    two, one = FP[key]
    pool = lab.pool(item["input"]["topic"])
    for pid in two | one:
        pool.setdefault(pid, ["added by verifier"])
    grades = [{"paper_id": pid, "title": lab.title(pid), "grade": 2 if pid in two else 1 if pid in one else 0,
               "evidence": "", "found_by": src} for pid, src in pool.items()]
    grades.sort(key=lambda g: -g["grade"])
    return {"grades": grades}


# ---------- comparison_table ----------
def cell(value, pid=None, pattern=None, note=""):
    quote = lab.raw_find(pid, pattern) if pattern else ""
    if pattern and not quote:
        raise SystemExit(f"quote not found in {pid}: {pattern}")
    return {"value": value, "quote": (quote or "").strip(), "section": "", "note": note}


NR = {"value": "NOT_REPORTED", "quote": "", "section": "", "note": ""}
CT = {
    "ct:dense-qa": {
        "2004.04906": {"nq_exact_match": cell("41.5", "2004.04906", r"compared to ORQA \(41\.5% vs\. 33\.3%\) in the open Natural Questions setting"),
                       "retriever_training": cell("trained separately before the reader"),
                       "answer_model": cell("BERT-based extractive reader")},
        "1906.00300": {"nq_exact_match": cell("33.3", "1906.00300", r"Test Natural Questions 26\.5 4\.0 4\.7 33\.3"),
                       "retriever_training": cell("trained jointly with the reader or generator"),
                       "answer_model": cell("BERT-based extractive reader")},
        "2002.08909": {"nq_exact_match": cell("40.4", "2002.08909", r"Dense Retr\.\+Transformer REALM 40\.4 40\.7 42\.9"),
                       "retriever_training": cell("trained jointly with the reader or generator"),
                       "answer_model": cell("BERT-style Transformer extractive reader")},
        "2005.11401": {"nq_exact_match": cell("44.5", "2005.11401", r"substantially below the 44\.5 that RAG-Sequence achieves"),
                       "retriever_training": cell("trained jointly with the reader or generator"),
                       "answer_model": cell("BART-large seq2seq generator")},
    },
    "ct:reasoning-gsm8k": {
        "2201.11903": {"gsm8k_palm540b": cell("56.9", "2201.11903", r"Chain of thought 56\.9 \(\+39\.0\)"),
                       "exemplars": cell("few-shot exemplars"),
                       "core_idea": cell("few-shot exemplars that show intermediate reasoning steps before the answer")},
        "2203.11171": {"gsm8k_palm540b": cell("74.4", "2203.11171", r"Self-consistency 93\.7 \(\+1\.8\) 99\.3 \(\+4\.6\) 81\.9 \(\+7\.9\) 48\.3 \(\+12\.5\) 86\.6 \(\+7\.6\) 74\.4 \(\+17\.9\)"),
                       "exemplars": cell("few-shot exemplars"),
                       "core_idea": cell("sample several chain-of-thought reasoning paths and take the majority-vote answer")},
        "2205.11916": {"gsm8k_palm540b": cell("43.0", "2205.11916", r"PaLM 540B: Zero-Shot-CoT 66\.1 43\.0"),
                       "exemplars": cell("zero-shot"),
                       "core_idea": cell("add \"Let's think step by step\" to the prompt to trigger reasoning without examples")},
        "2211.10435": {"gsm8k_palm540b": {**NR, "note": "PAL runs Codex; its PaLM-540B row is a chain-of-thought baseline copied from Wei et al."},
                       "exemplars": cell("few-shot exemplars"),
                       "core_idea": cell("generate a program whose execution by a Python interpreter gives the answer")},
    },
    "ct:tool-learning": {
        "2302.04761": {"base_model_size": cell("6.7", "2302.04761", r"Toolformer, which is based on a pretrained GPT-J model \(Wang and Komatsuzaki, 2021\) with 6\.7B parameters"),
                       "how_tool_use_is_learned": cell("fine-tuning on tool-use data"),
                       "tools": cell("calculator, Q&A system, search engine, translation system, calendar")},
        "2305.15334": {"base_model_size": cell("7", "2305.15334", r"We then finetune Gorilla, a LLaMA-7B-based model"),
                       "how_tool_use_is_learned": cell("fine-tuning on tool-use data"),
                       "tools": cell("machine-learning model APIs from HuggingFace, TorchHub and TensorHub (APIBench)")},
        "2307.16789": {"base_model_size": cell("7", "2307.16789", r"We fine-tune LLaMA-2 7B model"),
                       "how_tool_use_is_learned": cell("fine-tuning on tool-use data"),
                       "tools": cell("16,464 real-world REST APIs from RapidAPI (ToolBench)")},
        "2303.17580": {"base_model_size": {**NR, "note": "uses ChatGPT/GPT-4 as controller; parameter count not stated"},
                       "how_tool_use_is_learned": cell("prompting only"),
                       "tools": cell("expert AI models hosted on Hugging Face")},
    },
    "ct:jailbreak-attacks": {
        "2307.15043": {"asr_llama2_7b_chat": cell("56", "2307.15043", r"GCG \(ours\) 57\.0 0\.3 56\.0 88\.0 84\.0",
                                                   note="Table 1, individual Harmful Behavior column; the text's 88% is the multiple-behaviors train setting"),
                       "access_needed": cell("model gradients (white-box)"),
                       "optimization_method": cell("greedy coordinate gradient search over adversarial suffix tokens")},
        "2404.02151": {"asr_llama2_7b_chat": cell("100", "2404.02151", r"Llama-2-Chat-7B Meta Full Prompt \+ Random Search \+ Self-Transfer 92% 100%"),
                       "access_needed": cell("output log-probabilities only"),
                       "optimization_method": cell("random search over an adversarial suffix to maximize the log-probability of a target token such as \"Sure\"")},
        "1908.07125": {"asr_llama2_7b_chat": {**NR, "note": "2019 paper; attacks classification, reading comprehension and GPT-2"},
                       "access_needed": cell("model gradients (white-box)"),
                       "optimization_method": cell("gradient-guided search over trigger tokens")},
        "2306.15447": {"asr_llama2_7b_chat": {**NR, "note": "text attacks evaluated on GPT-2, LLaMA and Vicuna, not Llama-2-7B-Chat"},
                       "access_needed": cell("model gradients (white-box)"),
                       "optimization_method": cell("gradient-based optimization of adversarial inputs, notably adversarial images against multimodal models")},
    },
    "ct:adaptive-rag": {
        "2310.11511": {"num_eval_tasks": cell("6", "2310.11511", r"Empirical results on six tasks, including reasoning and long-form generation"),
                       "retrieval_trigger": cell("only when the model signals it needs to"),
                       "generator": cell("Llama 2 (7B and 13B) fine-tuned with reflection tokens")},
        "2305.06983": {"num_eval_tasks": cell("4", "2305.06983", r"We evaluate FLARE on 4 diverse tasks/datasets involving generating long outputs"),
                       "retrieval_trigger": cell("only when the model signals it needs to"),
                       "generator": cell("GPT-3.5 (text-davinci-003)")},
        "2212.10509": {"num_eval_tasks": cell("4", "2212.10509", r"on four datasets: HotpotQA, 2WikiMultihopQA, MuSiQue, and IIRC"),
                       "retrieval_trigger": cell("at every reasoning step or sentence"),
                       "generator": cell("GPT-3 (code-davinci-002) and Flan-T5")},
    },
    "ct:pi-defenses": {
        "2402.06363": {"agentdojo_utility": NR, "approach": cell("fine-tunes the model"),
                       "mechanism": cell("separates the trusted prompt from untrusted data with special delimiters in a structured query and trains the model to follow only the prompt")},
        "2404.13208": {"agentdojo_utility": NR, "approach": cell("fine-tunes the model"),
                       "mechanism": cell("trains the model to prioritize system and user instructions over instructions in lower-privileged inputs such as tool outputs")},
        "2503.18813": {"agentdojo_utility": cell("77", "2503.18813", r"We demonstrate effectiveness of CaMeL by solving 77% of tasks with provable security \(compared to 84% with an undefended system\) in AgentDojo"),
                       "approach": cell("wraps an unmodified model in a system design"),
                       "mechanism": cell("separates control flow from data flow and enforces security policies when tools are called")},
    },
}

# ---------- grounded_claims: [(paper_id, quote regex, why)] ----------
GC = {
    "gc:adaptive-attacks": [
        ("2503.00061", r"In this paper, we evaluate eight different defenses and bypass all of them using adaptive attacks, consistently achieving an attack success rate of over 50%", "Adaptive attacks bypass all eight IPI defenses evaluated."),
        ("2510.09023", r"we bypass 12 recent defenses \(based on a diverse set of techniques\) with attack success rate above 90% for most", "Adaptive attacks bypass 12 recent defenses with high success rates.")],
    "gc:cot-scale": [
        ("2201.11903", r"chain-of-thought prompting does not positively impact performance for small models, and only yields performance gains when used with models of ∼100B parameters", "Chain-of-thought gains appear only around 100B parameters."),
        ("2206.07682", r"we also consider the technique an emergent ability", "A technique that only helps above a scale threshold is called emergent.")],
    "gc:jailbreak-failures": [
        ("2307.02483", r"We hypothesize two failure modes of safety training: competing objectives and mismatched generalization", "Two failure modes explain jailbreaks."),
        ("2307.15043", r"aims to maximize the probability that the model produces an affirmative response \(rather than refusing to answer\)", "GCG optimizes a suffix toward an affirmative response."),
        ("2404.02151", r"then we apply random search on a suffix to maximize a target logprob", "Simple adaptive attacks use random search on a suffix.")],
    "gc:long-context": [
        ("2307.03172", r"performance is often highest when relevant information occurs at the beginning or end of the input context, and significantly degrades when models must access relevant information in the middle of long contexts", "Models use information in the middle of long contexts worst."),
        ("2310.01558", r"current RALMs are not robust to irrelevant retrieved context, causing them to perform worse on certain tasks", "Irrelevant retrieved context hurts retrieval-augmented models.")],
    "gc:parametric-vs-retrieval": [
        ("1909.01066", r"We present an in-depth analysis of the relational knowledge already present \(without fine-tuning\) in a wide range of state-of-theart pretrained language models", "Pretrained LMs hold relational knowledge."),
        ("2002.08910", r"performs competitively with open-domain systems that explicitly retrieve answers from an external knowledge source", "Closed-book models compete with retrieval systems as they scale."),
        ("2212.10511", r"we devise a new method for retrieval augmentation that improves performance and reduces inference costs by only retrieving non-parametric memories when necessary", "Retrieval helps most for long-tail knowledge, so retrieve only when needed.")],
    "gc:self-improvement": [
        ("2303.11366", r"Reflexion agents verbally reflect on task feedback signals, then maintain their own reflective text in an episodic memory buffer to induce better decision-making in subsequent trials", "Reflexion stores verbal reflections in memory."),
        ("2308.10144", r"learning from agent experiences without requiring parametric updates", "ExpeL learns from experience without parametric updates."),
        ("2303.17651", r"SELF-REFINE does not require any supervised training data, additional training, or reinforcement learning", "Self-Refine improves outputs with self-feedback and no training."),
        ("2305.16291", r"an ever-growing skill library of executable code for storing and retrieving complex behaviors", "Voyager reuses a growing skill library.")],
    "gc:helpful-harmless": [
        ("2204.05862", r"There is a tension between helpfulness and harmlessness, which can be measured at the level of both preference modeling and RLHF-trained policies", "Helpfulness and harmlessness are in tension."),
        ("2212.08073", r"An AI assistant that answers all questions with “I don’t know” would be harmless, but of course it would also be completely useless", "Constitutional AI aims for harmless but non-evasive answers."),
        ("2203.02155", r"This is an example of an “alignment tax” since our alignment procedure comes at the cost of lower performance on certain tasks", "Alignment can cost performance on some tasks.")],
    "gc:indirect-attacks": [
        ("2302.12173", r"exploit LLM-integrated applications by strategically injecting prompts into data likely to be retrieved", "Indirect prompt injection plants instructions in retrieved data."),
        ("2402.07867", r"an attacker could inject a few malicious texts into the knowledge database of a RAG system to induce an LLM to generate an attacker-chosen target answer", "PoisonedRAG corrupts the knowledge database.")],
}
GC_ANSWER = {
    "gc:adaptive-attacks": "Poorly: adaptive attacks bypassed all eight indirect prompt injection defenses tested in one study and twelve recent defenses in another, usually with high success rates.",
    "gc:cot-scale": "Chain-of-thought prompting helps only for models of roughly 100B parameters; below that it does not improve performance, which is why it is described as emergent.",
    "gc:jailbreak-failures": "Safety training fails through competing objectives and mismatched generalization; automated attacks such as GCG and random-search suffix attacks optimize inputs that push the model toward an affirmative answer.",
    "gc:long-context": "No: models use information at the start or end of a long context best and degrade in the middle, and irrelevant retrieved passages can make retrieval-augmented models worse.",
    "gc:parametric-vs-retrieval": "Large models store a lot of factual knowledge and can rival retrieval systems, but they struggle with less popular facts, where retrieval helps most.",
    "gc:self-improvement": "Agents keep verbal reflections, extracted insights, self-feedback, or skill libraries in memory or context and reuse them on later attempts, with no weight updates.",
    "gc:helpful-harmless": "Training for helpfulness can make models harmful and vice versa; Constitutional AI aims for harmless but non-evasive answers, and RLHF can impose an alignment tax.",
    "gc:indirect-attacks": "By planting instructions or false content in data the application retrieves, such as web pages or a RAG knowledge base, attackers steer the model without touching the user's prompt.",
}

FU = {
    "fu:indirect-injection": "Both papers leave open how to defend against indirect prompt injection: the first finds effective mitigations lacking and calls for evaluating deception potential with user studies; the second breaks eight defenses with white-box adaptive attacks and calls for black-box and grey-box attacks and for testing combined defenses.",
    "fu:long-noisy-context": "Models struggle to use information in the middle of long contexts, and reader performance saturates well before retriever recall; the role of architecture, query-aware contextualization and instruction tuning is only studied preliminarily. Robustness to irrelevant retrieved context is shown in-domain, with a general robust retrieval-augmented model left open and the NLI filter discarding relevant passages.",
    "fu:agent-self-improvement": "Reflexion limits long-term memory to a sliding window and suggests vector or SQL memory stores; it can settle in local minima, and test-driven code feedback is unreliable for non-deterministic or impure functions. ExpeL is limited to text observations and closed-source API models, and its insights must fit in the context window, so lifelong learning would need retrieval over insights.",
}
FU_GAPS = {
    "fu:long-noisy-context": [("2307.03172", "the performance of language model readers saturates far before retriever recall"),
                              ("2310.01558", "we are hopeful our work could inspire future research towards a general RALM that is robust to irrelevant context")],
    "fu:agent-self-improvement": [("2303.11366", "we encourage future work to extend the memory component of Reflexion with more advanced structures such as vector embedding databases or traditional SQL databases"),
                                  ("2308.10144", "extra retrieval steps for insights might be needed for truly lifelong learning agents to ensure a manageable context window size")],
    "fu:indirect-injection": [("2302.12173", "effective mitigations of these emerging threats are currently lacking"),
                              ("2503.00061", "studying black-box and grey-box attacks is also crucial for a more comprehensive evaluation")],
}


def write(key, body):
    item = ITEMS[KEYS[key]]
    draft = {"id": item["id"], "type": item["type"], "input": item["input"], **body, **PROV}
    (DRAFTS / f"{item['id']}.json").write_text(json.dumps(draft, indent=2, ensure_ascii=False), encoding="utf-8")


def main():
    s2 = {(e["citing"], e["cited"]) for e in map(json.loads, (REPO / "gold" / "citations_s2.jsonl").read_text(encoding="utf-8").splitlines())}
    n = 0
    for key in FP:
        write(key, find_papers(key)); n += 1
    for key, rows in CT.items():
        write(key, {"rows": rows, "rows_were_searched": ITEMS[KEYS[key]]["input"]["paper_ids"] is None}); n += 1
    for key in [k for k in KEYS if k.startswith("cl:")]:
        ids = ITEMS[KEYS[key]]["input"]["paper_ids"]
        edges = []
        for a in ids:
            for b in ids:
                if a == b:
                    continue
                ref, ev = cites(a, b, lab.PAPERS)
                in_s2 = (a, b) in s2
                if ref or in_s2:
                    # Verified this session: every reference-list-only edge was confirmed in the
                    # citing paper's references, and every S2-only edge was absent from them.
                    edges.append({"citing": a, "cited": b, "in_s2": in_s2, "in_reference_list": ref,
                                  "reference_evidence": ev, "needs_review": ref != in_s2, "keep": ref})
        write(key, {"edges": edges}); n += 1
    for key, sup in GC.items():
        supporting = []
        for pid, pattern, why in sup:
            q = lab.raw_find(pid, pattern)
            if not q or not lab.check_quote(pid, q):
                raise SystemExit(f"{key}: quote not found or not matching in {pid}")
            supporting.append({"paper_id": pid, "quote": q.strip(), "why": why})
        write(key, {"supporting": supporting, "draft_answer": GC_ANSWER[key]}); n += 1
    for key, notes in FU.items():
        gaps = []
        for pid, q in FU_GAPS[key]:
            if not lab.check_quote(pid, q):
                raise SystemExit(f"{key}: gap quote not in {pid}")
            gaps.append({"paper_id": pid, "quote": q})
        write(key, {"gaps": gaps, "gap_notes": notes}); n += 1
    print(f"wrote {n} drafts")


if __name__ == "__main__":
    main()
