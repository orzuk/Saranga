"""A stand-in for the `anthropic` package, for running distillation without an
API key or network. Put tests/stub_teacher first on PYTHONPATH.

It answers the three kinds of teacher request the drivers make, by recognising
the prompt:
  analyze  (merged algorithm)  -> a JSON array of per-item suggestions
  aggregate (merged algorithm) -> a small valid rule file for the group
  units    (unit algorithm)    -> a JSON rule {regex, type, span, ...} built from
                                  the examples' first words
Every reply reports token usage, so cost accounting runs as for real.
"""
import json
import re

STUB = True          # distillation_analysis.ensure_api_key: no key needed


class _Usage:
    def __init__(self, i, o):
        self.input_tokens, self.output_tokens = i, o
        self.cache_read_input_tokens = 0
        self.cache_creation_input_tokens = 0


class _Text:
    def __init__(self, t):
        self.type, self.text = "text", t


class _Msg:
    def __init__(self, text, prompt_len):
        self.content = [_Text(text)]
        self.usage = _Usage(prompt_len // 4, len(text) // 4)
        self.stop_reason = "end_turn"


_GROUP_FN = re.compile(r"extract_distilled_([a-z_]+)\(text")


def _reply(system, user):
    full = (system if isinstance(system, str) else
            " ".join(b.get("text", "") for b in (system or []))) + "\n" + user
    if "Python engineer consolidating" in user:              # merged: aggregate
        m = _GROUP_FN.search(user) or re.search(r"`extract_distilled_([a-z_]+)", user)
        g = m.group(1) if m else "definition"
        return f'''import re
from typing import List, Dict
try:
    from latex_clean import clean_latex_to_text as _clean_latex
except Exception:
    _clean_latex = lambda s: s

STUB_WE_SAY = re.compile(r"[^.\\n]*\\bwe say that\\b[^.]*\\.", re.I)


def extract_distilled_{g}(text: str) -> List[dict]:
    out = []
    for m in STUB_WE_SAY.finditer(text):
        raw = m.group(0).strip()
        out.append({{"raw_latex": raw, "clean_text": _clean_latex(raw), "name": None,
                     "env_name": "distilled", "rule_name": "STUB_WE_SAY",
                     "structure_type": "{g if g != 'theoremlike' else 'claim'}"}})
    return out
'''
    if "UNIT RULE" in full:                                   # unit algorithm
        words = re.findall(r"^EXAMPLE \d+: (\S+(?: \S+)?)", user, re.M)
        lead = words[0] if words else "We say"
        t = (re.search(r"TARGET TYPE: (\w+)", user) or re.search(r"(\w+)$", "definition")).group(1)
        return json.dumps({"regex": r"^\s*" + re.escape(lead) + r"\b", "type": t,
                           "span": "unit", "flags": "i",
                           "name": "stub_" + re.sub(r"\W+", "_", lead.lower())[:20],
                           "reasoning": "stub: anchored on the examples' opening words"})
    n = len(re.findall(r"^### Item \d+", user, re.M)) or 1  # merged: analyze
    return json.dumps([{"index": k, "reasoning": "stub",
                        "suggested_code": "STUB = re.compile(r'we say that')"}
                       for k in range(n)])


class _Stream:
    def __init__(self, msg):
        self._m = msg

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self._m


class _Messages:
    def create(self, model=None, max_tokens=None, system=None, messages=None, **kw):
        user = messages[-1]["content"]
        import os
        if os.environ.get("STUB_TEACHER_LOG"):           # for debugging the drivers' prompts
            with open(os.environ["STUB_TEACHER_LOG"], "a", encoding="utf-8") as fh:
                fh.write("=" * 60 + "\n" + user + "\n")
        return _Msg(_reply(system, user), len(user))

    def stream(self, **kw):
        return _Stream(self.create(**kw))


class Anthropic:
    def __init__(self, *a, **kw):
        self.messages = _Messages()
