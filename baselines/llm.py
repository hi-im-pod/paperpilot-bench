"""One agent loop per provider, so the baselines don't care which model runs them.

Providers:
  anthropic  Claude through the Anthropic SDK (credentials from ANTHROPIC_API_KEY or `ant auth login`)
  openai     OpenAI chat completions (OPENAI_API_KEY)
  ollama     a local model through Ollama's native API; free, for smoke tests
"""
import json
import os

# $ per 1M tokens (input, output). Unknown models report cost as None rather than a guess.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00), "claude-sonnet-5-5": (2.00, 10.00), "claude-haiku-5-5": (0.10, 0.50),
    "claude-fable-5-1": (10.00, 50.00),
}
DEFAULT_MODELS = {"anthropic": "claude-opus-5-5", "openai": "gpt-5", "ollama": "qwen3.5:9b"}
TOOL_RESULT_CHARS = 30000
# Ollama's default context is a few thousand tokens, far too small for an agent loop.
OLLAMA_NUM_CTX = 32768
FINAL_NUDGE = "Tool budget used up. Return your final JSON now."


def add_provider_args(ap):
    ap.add_argument("--provider", choices=["anthropic", "openai", "ollama"], default="anthropic")
    ap.add_argument("--model", help=f"default per provider: {DEFAULT_MODELS}")
    ap.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"],
                    help="Claude effort level (Claude only; omitted means the model's default)")


def clip(text):
    # A whole paper can be 50k+ tokens; one oversized read shouldn't blow the context.
    if len(text) <= TOOL_RESULT_CHARS:
        return text
    return text[:TOOL_RESULT_CHARS] + f"\n[truncated at {TOOL_RESULT_CHARS} characters; read one section at a time]"


class Agent:
    def __init__(self, provider, model=None, effort=None):
        self.provider = provider
        self.model = model or DEFAULT_MODELS[provider]
        self.effort = effort
        if provider == "anthropic":
            import anthropic
            self.client = anthropic.Anthropic()
        elif provider == "ollama":
            import ollama
            # OLLAMA_HOST=0.0.0.0 is a server bind address; clients can't connect to it on Windows.
            self.client = ollama.Client(host=os.environ.get("OLLAMA_HOST", "127.0.0.1:11434").replace("0.0.0.0", "127.0.0.1"))
        else:
            import openai
            self.client = openai.OpenAI()

    def cost(self, tin, tout):
        if self.provider == "ollama":
            return 0.0
        p = PRICES.get(self.model)
        return None if p is None else round((tin * p[0] + tout * p[1]) / 1e6, 6)

    def run(self, system, user, tools=None, call_tool=None, max_tool_calls=15):
        """Run to a final text answer. Returns (text, trace)."""
        fn = {"anthropic": self._run_anthropic, "openai": self._run_openai, "ollama": self._run_ollama}[self.provider]
        text, trace = fn(system, user, tools or [], call_tool, max_tool_calls)
        trace["cost_usd"] = self.cost(trace["input_tokens"], trace["output_tokens"])
        trace["model"] = self.model
        return text, trace

    def _run_anthropic(self, system, user, tools, call_tool, cap):
        defs = [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in tools]
        messages = [{"role": "user", "content": user}]
        trace = {"steps": 0, "input_tokens": 0, "output_tokens": 0, "stop_reason": None, "hit_cap": False}
        while True:
            kwargs = dict(model=self.model, max_tokens=16000, system=system, messages=messages,
                          cache_control={"type": "ephemeral"})
            if defs:
                kwargs["tools"] = defs
                if trace["hit_cap"]:
                    # Past the cap, a text answer is the only option left.
                    kwargs["tool_choice"] = {"type": "none"}
            if self.effort:
                kwargs["output_config"] = {"effort": self.effort}
            resp = self.client.messages.create(**kwargs)
            u = resp.usage
            trace["input_tokens"] += u.input_tokens + (u.cache_read_input_tokens or 0) + (u.cache_creation_input_tokens or 0)
            trace["output_tokens"] += u.output_tokens
            trace["stop_reason"] = resp.stop_reason
            # Thinking blocks must go back unchanged, so append the whole content list.
            messages.append({"role": "assistant", "content": resp.content})
            if resp.stop_reason == "pause_turn":
                continue
            uses = [b for b in resp.content if b.type == "tool_use"]
            if resp.stop_reason != "tool_use" or not uses or trace["hit_cap"]:
                return "".join(b.text for b in resp.content if b.type == "text"), trace
            results = []
            for b in uses:
                if trace["steps"] >= cap:
                    results.append({"type": "tool_result", "tool_use_id": b.id, "content": FINAL_NUDGE, "is_error": True})
                else:
                    trace["steps"] += 1
                    results.append({"type": "tool_result", "tool_use_id": b.id, "content": clip(call_tool(b.name, b.input))})
            if trace["steps"] >= cap:
                trace["hit_cap"] = True
                results.append({"type": "text", "text": FINAL_NUDGE})
            messages.append({"role": "user", "content": results})

    def _run_openai(self, system, user, tools, call_tool, cap):
        defs = [{"type": "function", "function": t} for t in tools]
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        trace = {"steps": 0, "input_tokens": 0, "output_tokens": 0, "stop_reason": None, "hit_cap": False}
        while True:
            kwargs = dict(model=self.model, messages=messages)
            if defs:
                kwargs["tools"] = defs
                if trace["hit_cap"]:
                    kwargs["tool_choice"] = "none"
            resp = self.client.chat.completions.create(**kwargs)
            if resp.usage:
                trace["input_tokens"] += resp.usage.prompt_tokens or 0
                trace["output_tokens"] += resp.usage.completion_tokens or 0
            choice = resp.choices[0]
            trace["stop_reason"] = choice.finish_reason
            msg = choice.message
            messages.append(msg.model_dump(exclude_none=True))
            if not msg.tool_calls or trace["hit_cap"]:
                return msg.content or "", trace
            for tc in msg.tool_calls:
                if trace["steps"] >= cap:
                    content = FINAL_NUDGE
                else:
                    trace["steps"] += 1
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = None
                    if isinstance(args, dict):
                        content = clip(call_tool(tc.function.name, args))
                    else:
                        content = "error: tool arguments were not valid JSON"
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})
            if trace["steps"] >= cap:
                trace["hit_cap"] = True
                messages.append({"role": "user", "content": FINAL_NUDGE})

    def _run_ollama(self, system, user, tools, call_tool, cap):
        defs = [{"type": "function", "function": t} for t in tools]
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        trace = {"steps": 0, "input_tokens": 0, "output_tokens": 0, "stop_reason": None, "hit_cap": False}
        while True:
            # Past the cap the tools are withheld; Ollama has no tool_choice="none".
            resp = self.client.chat(model=self.model, messages=messages,
                                    tools=defs if defs and not trace["hit_cap"] else None,
                                    think=False, options={"num_ctx": OLLAMA_NUM_CTX})
            trace["input_tokens"] += resp.prompt_eval_count or 0
            trace["output_tokens"] += resp.eval_count or 0
            trace["stop_reason"] = resp.done_reason
            msg = resp.message
            messages.append({"role": "assistant", "content": msg.content or "",
                             **({"tool_calls": msg.tool_calls} if msg.tool_calls else {})})
            if not msg.tool_calls or trace["hit_cap"]:
                return msg.content or "", trace
            for tc in msg.tool_calls:
                if trace["steps"] >= cap:
                    content = FINAL_NUDGE
                else:
                    trace["steps"] += 1
                    args = tc.function.arguments if isinstance(tc.function.arguments, dict) else None
                    content = clip(call_tool(tc.function.name, args)) if args is not None                         else "error: tool arguments were not valid JSON"
                messages.append({"role": "tool", "content": content, "tool_name": tc.function.name})
            if trace["steps"] >= cap:
                trace["hit_cap"] = True
                messages.append({"role": "user", "content": FINAL_NUDGE})
