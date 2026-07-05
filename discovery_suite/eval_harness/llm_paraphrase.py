"""LLM-backed paraphraser for the semantic obfuscation levels (L2-L4).

Returns a ``Paraphraser`` callback ``(text, level_int) -> str`` that the planter
plugs into ``obfuscate``. Backed by the existing ``common.llm_judge.LLMJudge``
so we inherit its sqlite caching — the same (model, prompt_version, text, level)
never re-pays, which makes planted eval runs reproducible and cheap to re-run.

Levels (semantic, meaning-preserving):
    L2 paraphrase   same claim, new surface form / wording
    L3 structural   same result, re-shaped statement (split/merge, reordered)
    L4 conceptual   same idea, restated in a different subfield's vocabulary
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (_REPO_ROOT / "src", _REPO_ROOT / "src" / "discovery"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from common.llm_judge import LLMJudge  # noqa: E402

_INSTRUCTIONS = {
    2: ("Paraphrase the following mathematical passage. Preserve its exact meaning "
        "and every quantitative claim, but change the wording and phrasing. Keep any "
        "LaTeX/math notation valid."),
    3: ("Restate the following mathematical passage so it makes the SAME claim but "
        "with a different structure: split or merge sentences, reorder the logic, and "
        "rephrase, while preserving the result exactly. Keep LaTeX/math valid."),
    4: ("Re-express the underlying idea of the following mathematical passage using the "
        "vocabulary and framing of a different but related subfield, so the surface "
        "form differs substantially while the essential result is preserved."),
}

_PROMPT = (
    "{instruction}\n\n"
    "Return ONLY the rewritten passage, no preamble.\n\n"
    "PASSAGE:\n{text}"
)
_PROMPT_VERSION = "obf_paraphrase_v1"


def _parse(raw: str) -> dict:
    return {"text": (raw or "").strip()}


def make_paraphraser(
    *,
    model: str = "haiku",
    cache_path: Optional[Path] = None,
    dry_run: bool = False,
    max_tokens: int = 1024,
):
    """Build a Paraphraser callback. dry_run=True returns the input unchanged
    (no spend) so pipelines stay runnable without an API key."""
    cache_path = Path(cache_path) if cache_path else (_REPO_ROOT / "discovery_suite" /
                                                      "eval_harness" / "runs" /
                                                      "paraphrase_cache.sqlite")
    judge = LLMJudge(
        model=model,
        cache_path=cache_path,
        prompt_template=_PROMPT,
        prompt_version=_PROMPT_VERSION,
        response_parser=_parse,
        max_tokens=max_tokens,
        system="You are a precise mathematical copy-editor.",
    )

    def paraphrase(text: str, level: int) -> str:
        # dry_run: no API spend — return input unchanged. (The LLMJudge dry-run
        # stub is a judging verdict, useless as paraphrase output, so we
        # short-circuit here instead of forwarding dry_run to the judge.)
        if dry_run:
            return text
        instruction = _INSTRUCTIONS.get(level, _INSTRUCTIONS[2])
        res = judge.judge(instruction=instruction, text=text)
        out = (res.parsed or {}).get("text", "").strip()
        return out or text   # fall back to original if the model returned nothing

    return paraphrase
