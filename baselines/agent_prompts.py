"""Build agent prompts from prompts/agent.md and turn model text into prediction records."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENT_MD = ROOT / "prompts" / "agent.md"


def _blocks(md):
    """Map each heading to the first fenced block under it."""
    out = {}
    for m in re.finditer(r"^#{2,3} ([^\n]+?)[ \t]*\n+```\n(.*?)\n```", md, re.S | re.M):
        out[m.group(1).strip()] = m.group(2)
    return out


def load():
    blocks = _blocks(AGENT_MD.read_text(encoding="utf-8"))
    return blocks["System prompt"], {k: v for k, v in blocks.items() if k != "System prompt"}


def _columns(cols):
    lines = []
    for c in cols:
        extra = c.get("unit") or ("allowed: " + ", ".join(c["allowed"]) if c.get("allowed") else "")
        lines.append(f"- {c['name']} | {c['type']} | {extra} | {c.get('setting', '')}")
    return "\n".join(lines)


def task_prompt(templates, task):
    t, inp = templates[task["type"]], task["input"]
    ids = inp.get("paper_ids")
    t = re.sub(r"\{paper_ids[^}]*\}", ", ".join(ids) if ids else "Find the relevant papers yourself (at most 6).", t)
    t = re.sub(r"\{one line per column[^}]*\}", _columns(inp.get("columns", [])), t)
    for key in ("topic", "question"):
        t = t.replace("{" + key + "}", str(inp.get(key, "")))
    return t


def parse_final(text):
    """The last JSON object in the text, or None. Models sometimes wrap it in fences or prose."""
    text = (text or "").strip()
    candidates = [text] + re.findall(r"```(?:json)?\s*(.*?)```", text, re.S)
    start = text.find("{")
    if start >= 0:
        candidates.append(text[start:text.rfind("}") + 1])
    for c in reversed(candidates):
        try:
            obj = json.loads(c)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    return None


def to_prediction(task_id, text, trace):
    obj = parse_final(text)
    trace = {**trace, "parse_error": obj is None}
    if obj is None:
        trace["raw_text"] = (text or "")[:2000]
        return {"id": task_id, "abstain": False, "output": {}, "trace": trace}
    if "output" in obj or "abstain" in obj:
        return {"id": task_id, "abstain": bool(obj.get("abstain")), "output": obj.get("output") or {}, "trace": trace}
    # Some models drop the wrapper and return the output object itself.
    return {"id": task_id, "abstain": False, "output": obj, "trace": trace}
