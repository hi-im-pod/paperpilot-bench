import re
import sys

from conftest import ROOT, TASKS

sys.path.insert(0, str(ROOT / "baselines"))
import agent_prompts as ap  # noqa: E402


def test_every_task_type_has_a_template():
    _, templates = ap.load()
    assert set(templates) == {t["type"] for t in TASKS}


def test_task_prompts_leave_no_placeholders():
    _, templates = ap.load()
    for task in TASKS:
        prompt = ap.task_prompt(templates, task)
        # Placeholders are lowercase words in braces; JSON examples start with a quote.
        assert not re.search(r"\{[a-z_]+( [^}\"]*)?\}", prompt), (task["id"], prompt)


def test_parse_final_handles_fences_and_prose():
    assert ap.parse_final('{"a": 1}') == {"a": 1}
    assert ap.parse_final('Here you go:\n```json\n{"a": 2}\n```') == {"a": 2}
    assert ap.parse_final('Thinking... then {"a": 3}') == {"a": 3}
    assert ap.parse_final("no json here") is None


def test_to_prediction_unwraps_and_flags_parse_errors():
    p = ap.to_prediction("x", '{"abstain": true, "output": {"reason": "none"}}', {})
    assert p["abstain"] and p["output"] == {"reason": "none"}
    bare = ap.to_prediction("x", '{"ranked_ids": ["a"]}', {})
    assert bare["output"] == {"ranked_ids": ["a"]}
    bad = ap.to_prediction("x", "sorry", {})
    assert bad["trace"]["parse_error"] and bad["trace"]["raw_text"] == "sorry"
