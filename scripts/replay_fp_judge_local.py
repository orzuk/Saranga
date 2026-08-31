#!/usr/bin/env python3
"""Replay the FP-judge decisions against a LOCAL vLLM model, and compare.

`fp_judge.csv` already holds Claude's verdict plus the exact snippet it judged,
so measuring how well an open-weight judge agrees costs nothing but inference:
we re-ask the SAME question, in the SAME prompt, and diff the answers.

Prompt fidelity is not approximated — `fp_judge.judge_batch` is called directly
with a shim client whose `.messages.create()` speaks to an OpenAI-compatible
endpoint instead of Anthropic. Any future edit to the real prompt is therefore
picked up here automatically.

Two knobs matter for interpreting the result:
  --batch-size 1   isolates the model's judgement from index-alignment drift,
                   which is the failure mode a smaller model shows first.
  --match-mode     must equal what produced the CSV (m1 = today's default).

Usage:
    export LLM_LOCAL_BASE_URL=http://salmon-02:8000/v1
    python scripts/replay_fp_judge_local.py \
        --csv src/LLMVersion/merged_eval_silver_001_011_v3/fp_judge.csv
"""

import argparse
import csv
import json
import os
import sys
import time
import re
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src" / "LLMVersion"))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

import fp_judge

VERDICTS = ("GENUINE", "FALSE_POSITIVE")


class _Usage:
    """Stands in for anthropic's usage object; token accounting is not the point."""
    input_tokens = 0
    output_tokens = 0


#: A fenced block, with or without a language tag, and any prose either side.
_FENCE = re.compile(r"^.*?```(?:[A-Za-z0-9_+-]*)?\s*(.*?)\s*```.*$", re.S)


def _unwrap(text: str) -> str:
    """Return the bare JSON array from a chat model's reply.

    The prompt asks for an array and no fences. Qwen complies; Mistral wraps it
    in ``` anyway, and a wrapped array parses as nothing at all -- every row
    comes back MISSING, which reads like the model refused rather than like a
    formatting difference. Strip the wrapper rather than weaken the prompt, so
    the two judges are still answering the same question.

    Ġ is the byte-level BPE marker for a leading space, and it reaching the
    client means the detokenizer never mapped it back. Repair it here so the
    reason text stays legible; the verdict field is unaffected either way.
    """
    t = (text or "").strip()
    m = _FENCE.match(t)
    if m:
        t = m.group(1).strip()
    if "\u0120" in t:
        t = t.replace("\u0120", " ")
    # Prose before or after the array is likewise the model being chatty.
    i, j = t.find("["), t.rfind("]")
    if i != -1 and j > i:
        t = t[i:j + 1]
    return t


class _Block:
    def __init__(self, text):
        self.text = text


class _Msg:
    def __init__(self, text):
        self.content = [_Block(text)]
        self.usage = _Usage()


class LocalMessages:
    """`client.messages.create(...)` on top of /v1/chat/completions.

    Anthropic puts the system prompt in its own argument (optionally as a list
    of cache_control'd blocks); the OpenAI schema wants it as the first message,
    and rejects the cache_control key outright — vLLM caches prefixes on its own
    anyway, so the hint is simply dropped.
    """

    def __init__(self, base_url, model, timeout, retries):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.timeout = timeout
        self.retries = retries

    @staticmethod
    def _system_text(system):
        if isinstance(system, str):
            return system
        return "".join(b.get("text", "") for b in system or [])

    def create(self, *, model=None, max_tokens=2048, system=None, messages=None):
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            # Qwen3 ships generation_config.json with temperature 0.6 / top_p
            # 0.95 / top_k 20, which vLLM adopts unless each request overrides
            # them. A sampling judge is not reproducible, so pin all three.
            "temperature": 0, "top_p": 1, "top_k": -1, "seed": 0,
            # Without this Qwen3 wraps every answer in a <think> block and the
            # JSON array never parses.
            "chat_template_kwargs": {"enable_thinking": False},
            "messages": ([{"role": "system", "content": self._system_text(system)}]
                         + list(messages or [])),
        }
        data = json.dumps(payload).encode()
        last = None
        for attempt in range(self.retries):
            try:
                req = urllib.request.Request(
                    self.url, data=data,
                    headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    body = json.load(r)
                return _Msg(_unwrap(body["choices"][0]["message"]["content"]))
            except (urllib.error.URLError, OSError, KeyError, ValueError) as e:
                last = e
                time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"local endpoint failed after {self.retries} tries: {last}")


class LocalClient:
    def __init__(self, base_url, model, timeout, retries):
        self.messages = LocalMessages(base_url, model, timeout, retries)


def main():
    p = argparse.ArgumentParser(description="Replay fp_judge.csv on a local model")
    p.add_argument("--csv", required=True, help="existing fp_judge.csv (Claude verdicts)")
    p.add_argument("--base-url", default=os.environ.get("LLM_LOCAL_BASE_URL"))
    p.add_argument("--model", default="qwen3-32b-awq-int4")
    p.add_argument("--match-mode", default="m1", choices=["m1", "m3"],
                   help="must equal the mode that produced --csv")
    p.add_argument("--batch-size", type=int, default=10,
                   help="10 mirrors fp_judge; 1 removes index-alignment as a variable")
    p.add_argument("--limit", type=int, default=0, help="only the first N rows (smoke test)")
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--retries", type=int, default=3)
    p.add_argument("--out", default=None, help="default: <csv dir>/fp_judge_local.csv")
    args = p.parse_args()

    if not args.base_url:
        sys.exit("set --base-url or $LLM_LOCAL_BASE_URL (e.g. http://salmon-02:8000/v1)")

    src = Path(args.csv).resolve()
    rows = list(csv.DictReader(open(src, encoding="utf-8")))
    if args.limit:
        rows = rows[:args.limit]
    if not rows:
        sys.exit(f"no rows in {src}")

    client = LocalClient(args.base_url, args.model, args.timeout, args.retries)
    out_path = Path(args.out) if args.out else src.parent / "fp_judge_local.csv"

    # The prompt is built per type, so replay type by type; row order inside a
    # type is preserved to keep the comparison row-aligned with the source CSV.
    by_type = defaultdict(list)
    for i, r in enumerate(rows):
        by_type[r["type"]].append(i)

    verdicts = [None] * len(rows)
    reasons = [""] * len(rows)
    t0 = time.time()
    for stype, idxs in sorted(by_type.items()):
        for b in range(0, len(idxs), args.batch_size):
            chunk = idxs[b:b + args.batch_size]
            snippets = [rows[i]["snippet"] for i in chunk]
            by_index, _ = fp_judge.judge_batch(
                client, args.model, stype, snippets, match_mode=args.match_mode)
            for k, i in enumerate(chunk):
                obj = by_index.get(k)
                # A missing index is a real failure mode, not a verdict: record
                # it so it cannot silently masquerade as agreement.
                verdicts[i] = (obj or {}).get("verdict", "MISSING")
                reasons[i] = (obj or {}).get("reason", "")
            done = sum(v is not None for v in verdicts)
            print(f"  [{stype}] {done}/{len(rows)} judged "
                  f"({time.time() - t0:.0f}s)", flush=True)

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "type", "paper_id", "claude_verdict", "local_verdict", "agree",
            "local_reason", "claude_reason", "snippet"])
        w.writeheader()
        for i, r in enumerate(rows):
            w.writerow({
                "type": r["type"], "paper_id": r["paper_id"],
                "claude_verdict": r["verdict"], "local_verdict": verdicts[i],
                "agree": int(r["verdict"] == verdicts[i]),
                "local_reason": reasons[i], "claude_reason": r.get("reason", ""),
                "snippet": r["snippet"],
            })

    # ---- report ----
    n = len(rows)
    agree = sum(1 for i, r in enumerate(rows) if r["verdict"] == verdicts[i])
    missing = sum(1 for v in verdicts if v == "MISSING")
    print(f"\nreplayed {n} rows from {src.name}  "
          f"(model={args.model}, batch={args.batch_size}, mode={args.match_mode})")
    print(f"wrote {out_path}\n")
    print(f"overall agreement : {agree}/{n} = {agree / n:.1%}")
    if missing:
        print(f"unparsed/missing  : {missing}  <- index drift, not a verdict")

    print("\nconfusion (rows = Claude, cols = local)")
    cols = list(VERDICTS) + (["MISSING"] if missing else [])
    print(f"{'':<16}" + "".join(f"{c:>16}" for c in cols))
    for cv in VERDICTS:
        cells = []
        for lv in cols:
            cells.append(sum(1 for i, r in enumerate(rows)
                             if r["verdict"] == cv and verdicts[i] == lv))
        print(f"{cv:<16}" + "".join(f"{c:>16}" for c in cells))

    # The headline claim is that judging LIFTS precision by forgiving FPs the
    # silver under-labelled. A judge that forgives far more than Claude is not a
    # better judge, it is a rubber stamp — so compare the rates directly.
    c_gen = sum(1 for r in rows if r["verdict"] == "GENUINE")
    l_gen = sum(1 for v in verdicts if v == "GENUINE")
    print(f"\nforgiven as GENUINE   Claude {c_gen}/{n} = {c_gen / n:.1%}"
          f"   |   local {l_gen}/{n} = {l_gen / n:.1%}")
    if l_gen > c_gen:
        print("  local is MORE permissive -> would inflate adjusted precision")
    elif l_gen < c_gen:
        print("  local is LESS permissive -> would understate adjusted precision")

    print("\nper type")
    print(f"{'type':<14}{'n':>5}{'agree':>8}{'rate':>8}")
    for stype in sorted(by_type):
        idxs = by_type[stype]
        a = sum(1 for i in idxs if rows[i]["verdict"] == verdicts[i])
        print(f"{stype:<14}{len(idxs):>5}{a:>8}{a / len(idxs):>7.0%}")

    print(f"\ndisagreements to read by hand: {n - agree}")
    print(f"  awk -F, 'NR==1||$5==0' {out_path}")


if __name__ == "__main__":
    main()
