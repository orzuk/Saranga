"""Generic LLM-as-judge wrapper with persistent caching.

Method E (and later H, B) all need an LLM to assess natural-language
relationships between paper-graph nodes. This module is the shared call
surface — each method supplies its own prompt template and response parser,
and the wrapper handles:

  - prompt rendering (`template.format(**template_vars)`)
  - SDK call (Anthropic / OpenAI)
  - sqlite caching keyed by (model, prompt_version, hash(template_vars))
  - response parsing into a dict via the supplied callable

The cache lets a multi-day Method E run resume from where it left off
without re-paying. Cache keys include the prompt_version so a prompt
revision invalidates the prior entries.

Schema:
    judgments(
        cache_key TEXT PRIMARY KEY,
        model TEXT, prompt_version TEXT,
        template_vars_json TEXT,
        raw_response TEXT,
        parsed_json TEXT,
        created_at TEXT
    )
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Optional config-driven model resolution (e.g., 'opus' -> 'claude-opus-4-7')
try:
    from config import SOURCES  # noqa: E402
    _SOURCES = SOURCES
except Exception:
    _SOURCES = {}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS judgments (
    cache_key          TEXT PRIMARY KEY,
    model              TEXT,
    prompt_version     TEXT,
    template_vars_json TEXT,
    raw_response       TEXT,
    parsed_json        TEXT,
    created_at         TEXT
);
"""


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def _resolve_model(model: str) -> str:
    """Map 'opus'/'sonnet'/'haiku'/'gpt4o' -> full model ID via config.SOURCES.
    If `model` looks like a full provider model id already, return as-is."""
    if not model:
        return model
    if model in _SOURCES:
        full = _SOURCES[model].get("model")
        if full:
            return full
    return model


def _provider_for(model: str) -> str:
    """Provider sniff: claude-* -> anthropic, gpt-* -> openai,
    qwen*/Qwen/* -> local (OpenAI-compatible endpoint, e.g. vLLM/SGLang server).
    Local endpoint URL comes from $LLM_LOCAL_BASE_URL (default localhost:8000/v1)."""
    m = (model or "").lower()
    if m.startswith("claude"):
        return "anthropic"
    if m.startswith("gpt") or m.startswith("o1") or m.startswith("o3"):
        return "openai"
    if m.startswith("qwen") or m.startswith("deepseek") or m.startswith("llama") \
            or m.startswith("mistral") or m.startswith("gemma"):
        return "local"
    raise ValueError(f"Cannot infer provider for model {model!r}")


def _cache_key(model: str, prompt_version: str, template_vars: dict) -> str:
    blob = json.dumps({"m": model, "v": prompt_version, "t": template_vars},
                      sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass
class JudgeResult:
    parsed: dict
    raw: str
    cached: bool


class LLMJudge:
    """Cached LLM-as-judge wrapper.

    Constructor args:
      model            short key ('opus', 'sonnet', ...) or full model ID
      cache_path       sqlite file for memoization
      prompt_template  string with {placeholders}
      prompt_version   string version tag (any rev invalidates cache entries)
      response_parser  Callable[[str], dict] -> structured judgment
      max_tokens       output cap (default 512)
      system           optional system prompt
    """

    def __init__(self, *,
                 model: str,
                 cache_path: Path,
                 prompt_template: str,
                 prompt_version: str,
                 response_parser: Callable[[str], dict],
                 max_tokens: int = 512,
                 system: Optional[str] = None):
        self.model_short = model
        self.model = _resolve_model(model)
        self.provider = _provider_for(self.model)
        self.cache_path = Path(cache_path)
        self.prompt_template = prompt_template
        self.prompt_version = prompt_version
        self.response_parser = response_parser
        self.max_tokens = max_tokens
        self.system = system
        self.conn = _connect(self.cache_path)
        self._client = None

    def close(self):
        self.conn.close()

    # ── Cache I/O ─────────────────────────────────────────────────────────

    def _cache_get(self, key: str) -> Optional[dict]:
        cur = self.conn.execute(
            "SELECT raw_response, parsed_json FROM judgments WHERE cache_key = ?",
            (key,))
        row = cur.fetchone()
        if not row:
            return None
        raw, parsed_json = row
        try:
            return {"raw": raw, "parsed": json.loads(parsed_json)}
        except Exception:
            return None

    def _cache_put(self, key: str, template_vars: dict, raw: str, parsed: dict):
        self.conn.execute(
            "INSERT OR REPLACE INTO judgments "
            "(cache_key, model, prompt_version, template_vars_json, "
            " raw_response, parsed_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (key, self.model, self.prompt_version,
             json.dumps(template_vars, ensure_ascii=False),
             raw, json.dumps(parsed, ensure_ascii=False),
             datetime.now(timezone.utc).isoformat()))
        self.conn.commit()

    # ── SDK call ──────────────────────────────────────────────────────────

    def _ensure_client(self):
        if self._client is not None:
            return
        if self.provider == "anthropic":
            try:
                from anthropic import Anthropic
            except ImportError as e:
                raise RuntimeError("anthropic SDK not installed; "
                                   "pip install anthropic") from e
            self._client = Anthropic()
        elif self.provider == "openai":
            try:
                from openai import OpenAI
            except ImportError as e:
                raise RuntimeError("openai SDK not installed; "
                                   "pip install openai") from e
            self._client = OpenAI()
        elif self.provider == "local":
            # OpenAI-compatible local endpoint (vLLM, SGLang, llama.cpp server)
            try:
                from openai import OpenAI
            except ImportError as e:
                raise RuntimeError("openai SDK not installed; "
                                   "pip install openai") from e
            base_url = os.environ.get("LLM_LOCAL_BASE_URL",
                                      "http://localhost:8000/v1")
            api_key = os.environ.get("LLM_LOCAL_API_KEY", "dummy")
            self._client = OpenAI(base_url=base_url, api_key=api_key)
        else:
            raise ValueError(f"Unsupported provider {self.provider!r}")

    def _call_llm(self, prompt: str) -> str:
        self._ensure_client()
        if self.provider == "anthropic":
            kwargs = {"model": self.model,
                      "max_tokens": self.max_tokens,
                      "messages": [{"role": "user", "content": prompt}]}
            if self.system:
                kwargs["system"] = self.system
            resp = self._client.messages.create(**kwargs)
            return "".join(b.text for b in resp.content
                           if getattr(b, "type", "") == "text") or ""
        else:  # openai or local (OpenAI-compatible)
            msgs = []
            if self.system:
                msgs.append({"role": "system", "content": self.system})
            msgs.append({"role": "user", "content": prompt})
            kwargs = {"model": self.model, "messages": msgs}
            # 'openai' uses max_completion_tokens (post-o1); local servers
            # like vLLM use the older max_tokens.
            if self.provider == "openai":
                kwargs["max_completion_tokens"] = self.max_tokens
            else:
                kwargs["max_tokens"] = self.max_tokens
                # Open-weight chat models ship a generation_config.json that
                # servers adopt as the default -- Qwen3's asks for temperature
                # 0.6 -- so a judge left unpinned samples a different verdict
                # each run. Pin it here: reproducibility is the whole reason to
                # host the model ourselves. top_k is not in the OpenAI schema,
                # so it travels in extra_body with the vendor extensions.
                kwargs["temperature"] = 0
                kwargs["top_p"] = 1
                kwargs["seed"] = 0
                # Reasoning models otherwise open with a <think> block, which
                # is not free: max_tokens is sized for a verdict, and the
                # thinking alone exhausts it, so the parser sees a response
                # that never reached its VERDICT line. Harmless for servers
                # that do not recognise the key.
                kwargs["extra_body"] = {
                    "top_k": -1,
                    "chat_template_kwargs": {"enable_thinking": False},
                }
            resp = self._client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content or ""

    # ── Public API ────────────────────────────────────────────────────────

    def judge(self, *, dry_run: bool = False, **template_vars) -> JudgeResult:
        """Render the prompt, call the LLM (with caching), parse the response.

        If dry_run=True, returns a stub result without calling the LLM —
        useful for end-to-end pipeline tests when API spend is undesired.
        """
        key = _cache_key(self.model, self.prompt_version, template_vars)
        hit = self._cache_get(key)
        if hit is not None:
            return JudgeResult(parsed=hit["parsed"], raw=hit["raw"], cached=True)

        if dry_run:
            stub_raw = "RELATIONSHIP: UNRELATED\nVERDICT: NO\nJUSTIFICATION: dry-run stub"
            try:
                parsed = self.response_parser(stub_raw)
            except Exception:
                parsed = {"verdict": "NO", "relationship": "UNRELATED",
                          "justification": "dry-run stub"}
            # Don't cache dry-runs — that would poison the real run.
            return JudgeResult(parsed=parsed, raw=stub_raw, cached=False)

        prompt = self.prompt_template.format(**template_vars)
        raw = self._call_llm(prompt)
        try:
            parsed = self.response_parser(raw)
        except Exception as e:
            parsed = {"verdict": "NO", "relationship": "PARSE_ERROR",
                      "justification": f"parse error: {e}",
                      "raw_response": raw}
        self._cache_put(key, template_vars, raw, parsed)
        return JudgeResult(parsed=parsed, raw=raw, cached=False)

    def stats(self) -> dict:
        n = self.conn.execute("SELECT COUNT(*) FROM judgments").fetchone()[0]
        return {"cached_judgments": n, "model": self.model,
                "prompt_version": self.prompt_version}
