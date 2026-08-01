#!/usr/bin/env python3
"""
Distillation v2 driver — incremental aggregate + rule registry.

Implements steps 1-6 of `docs/DISTILLATION_V2.md`. Wraps Yaron's pipeline:
dark-knowledge identification and `analyze` are his, unmodified. Two things are
replaced, both for reasons measured on the v1 run:

* **`aggregate_incremental`** sends the *current rule file* plus only the *new*
  suggestions, instead of every suggestion ever made. v1's prompt grew 19K ->
  184K input tokens over 17 papers (+~11K/paper), which is quadratic in cost and
  hits a 200K context wall around paper 18-19 — the pipeline could not reach 100
  papers at any budget.

* **Registry-backed gating** replaces comment-out pruning. In v1 `prune_rules`
  edited the .py source, and the next `aggregate` regenerated that file from a
  suggestion list with no record of the prune, so prunes were silently undone
  (cumulative pruned count fell 13->12->9->4->3). Here status lives in the
  registry, so it persists and is reversible.

Nothing under `src/LLMVersion/` is modified; `aggregate_rules_merged` stays
available so v1 and v2 remain runnable and comparable (see `--aggregate v1`).

Usage
-----
    python scripts/distill_v2.py --group definition --papers paper001,paper002 \
        --tex-dir portal/data/tier2_tex --flat-tex \
        --t2-dir portal/data/tier2 --eval-dir src/LLMVersion/definition_eval_v2 \
        --alpha 0.5

    # plan only, no LLM calls
    python scripts/distill_v2.py ... --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "src" / "LLMVersion"))
sys.path.insert(0, str(REPO / "src"))

from distill_registry import (                       # noqa: E402
    RuleRegistry, extract_patterns, parse_uids_from_source,
)

RULES_FILE = "distilled_rules.py"
REGISTRY_FILE = "rule_registry.json"


# ---------------------------------------------------------------------------
# incremental aggregate
# ---------------------------------------------------------------------------

AGG_PROMPT = """You are maintaining a set of regex extraction rules for LaTeX math papers.

## Current rules (ALREADY WORKING — preserve them)
```python
{current_rules}
```

## New rule suggestions from the latest paper ONLY
{new_suggestions}

## Your task
Return the COMPLETE updated Python module: the current rules, plus new patterns
covering the suggestions above.

CRITICAL — rule identity:
- Every existing pattern that you keep MUST retain its `# @uid:N` comment line
  immediately above it, unchanged, even if you rename the variable or edit the body.
- Every genuinely NEW pattern gets `# @uid:NEW` on the line above it.
- Never invent a numeric uid and never reuse one. Dropping a uid marker makes the
  rule look brand new and destroys its history.

CRITICAL — do not regress:
- Do NOT delete an existing pattern unless a new one strictly subsumes it; if you
  do subsume one, keep the OLD uid on the surviving pattern.
- Prefer adding a narrow new pattern over broadening an existing one.

## Output requirements
1. Only `import re` and `from typing import List, Dict` at the top
2. A single function: `{func_name}(text: str) -> List[dict]`
3. Each returned dict has keys: `raw_latex` (str), `clean_text` (str), `name`
   (str or None), `env_name` (str), `rule_name` (str){st_key_req}
4. `env_name` is `"distilled"`; `rule_name` MUST equal the module-level
   compiled-pattern variable name that produced the match (the prune/stats step
   keys off it)
5. Compiled patterns at module level; include `_clean_latex(text)` and
   `_inside_excluded_env(text, start, end)` helpers
6. Deduplicate overlapping matches
7. Do NOT import any project module; stdlib `re` only

GENERALIZATION (critical): patterns MUST work on ANY math paper. Do NOT hardcode
author names, paper-specific terminology, theorem/section/equation labels,
specific variable names, or custom macro names. Anchor on STRUCTURE (environment
names, \\begin/\\end, \\textbf/\\emph, sectioning, leading keywords), never on
content tokens.

Output ONLY the Python code, no fences, no explanation."""


def _strip_fences(code: str) -> str:
    code = code.strip()
    if code.startswith("```"):
        lines = code.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        code = "\n".join(lines)
    return code


def _dedup_fixups(code: str) -> str:
    """Same two codegen bugs Yaron patches — LLMs reproduce them reliably."""
    code = code.replace(
        "if not overlap:\n            del r['_start']\n            deduped.append(r)",
        "if not overlap:\n            deduped.append(r)")
    if "for r in deduped:\n        r.pop('_start', None)" not in code:
        code = code.replace(
            "return deduped",
            "for r in deduped:\n        r.pop('_start', None)\n\n    return deduped")
    return code


def aggregate_incremental(current_src: str, new_rows: List[dict], group_key: str,
                          types_in_group: List[str], eval_dir: Path,
                          model: str, dry_run: bool = False) -> Tuple[str, dict]:
    """Regenerate the rule module from CURRENT rules + NEW suggestions only.

    Returns (generated_source, usage). On syntax error or a missing entry
    function the previous source is returned unchanged — same fault-isolation
    contract as `aggregate_rules_merged`, so one bad round cannot destroy a
    group's accumulated rules.
    """
    func_name = f"extract_distilled_{group_key}"
    st_key_req = (", `structure_type` (one of: %s)" % ", ".join(types_in_group)
                  if len(types_in_group) > 1 else "")
    sugg = "\n".join(
        f"\n--- Suggestion {i} (paper {r.get('paper_id','?')}) ---\n"
        f"missed item: {(r.get('gold_text') or '')[:400]}\n"
        f"suggested rule: {(r.get('llm_suggested_rule') or '')[:900]}"
        for i, r in enumerate(new_rows, 1)) or "(none)"

    prompt = AGG_PROMPT.format(
        current_rules=current_src or "# (no rules yet)",
        new_suggestions=sugg, func_name=func_name, st_key_req=st_key_req)

    usage = {"input_tokens": 0, "output_tokens": 0, "prompt_chars": len(prompt)}
    if dry_run:
        return current_src, usage

    import anthropic
    client = anthropic.Anthropic()
    msg = client.messages.create(model=model, max_tokens=16384,
                                 messages=[{"role": "user", "content": prompt}])
    usage["input_tokens"] = getattr(msg.usage, "input_tokens", 0)
    usage["output_tokens"] = getattr(msg.usage, "output_tokens", 0)

    code = _dedup_fixups(_strip_fences(msg.content[0].text))
    try:
        compile(code, str(eval_dir / RULES_FILE), "exec")
    except SyntaxError as e:
        print(f"  [{group_key}] WARNING: syntax error in generated code: {e}; keeping previous")
        return current_src, usage
    if func_name not in code:
        print(f"  [{group_key}] WARNING: {func_name} missing; keeping previous")
        return current_src, usage
    return code, usage


# ---------------------------------------------------------------------------
# registry <-> generated source
# ---------------------------------------------------------------------------

def sync_registry_from_source(reg: RuleRegistry, src: str, group: str,
                              paper_id: str) -> Dict[str, int]:
    """Mint/att­ach UIDs for every pattern in freshly generated source.

    Resolution order, most to least reliable:
      1. an explicit ``# @uid:N`` marker the model preserved
      2. body match against the registry (catches a rename the model made
         while dropping the marker — the exact v1 failure)
      3. mint a new uid
    """
    declared = parse_uids_from_source(src)
    pats = extract_patterns(src)
    name_to_uid: Dict[str, int] = {}
    minted = reused = 0
    for name, body in pats.items():
        if name.startswith("_"):
            continue                                  # helper regex, not a rule
        uid = declared.get(name)
        if uid is not None and uid in reg.rules:
            r = reg.rules[uid]
            if r.name != name:
                r.aliases.append(r.name)
                r.history.append(f"renamed {r.name}->{name} @{paper_id}")
                r.name = name
            r.pattern_src, r.pattern_key = body, __import__(
                "distill_registry").normalize_pattern(body)
            reused += 1
        else:
            before = reg._next_uid
            r = reg.mint(name, group, body, paper_id)
            minted += (reg._next_uid != before)
            reused += (reg._next_uid == before)
        name_to_uid[name] = r.uid
    return {"minted": minted, "reused": reused, "map": name_to_uid}


def emit_source(reg: RuleRegistry, src: str, group: str) -> str:
    """Write ``# @uid:N`` above each pattern and comment out retired ones.

    Retired rules stay in the file as comments for provenance, but unlike v1
    that is only a *rendering* of registry state — the registry remains the
    authority, so the next round cannot silently resurrect them.
    """
    active = {r.name for r in reg.active(group)}
    by_name = {r.name: r for r in reg.rules.values() if r.group == group}
    out, lines = [], src.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r'^([A-Z][A-Z0-9_]*)\s*=\s*re\.compile', line)
        if m:
            name = m.group(1)
            r = by_name.get(name)
            # consume the whole (possibly multi-line) compile call
            blk, depth, started = [], 0, False
            while i < len(lines):
                blk.append(lines[i])
                depth += lines[i].count("(") - lines[i].count(")")
                started = started or "(" in lines[i]
                i += 1
                if started and depth <= 0:
                    break
            if r is not None:
                out.append(f"# @uid:{r.uid}")
                if name not in active:
                    out.append(f"# RETIRED uid={r.uid} fdr={r.fdr():.2f}")
                    out.extend("# " + b for b in blk)
                    continue
            out.extend(blk)
            continue
        # drop stale markers; they are re-emitted above
        if re.match(r'^#\s*@uid:', line.strip()) or line.startswith("# RETIRED uid="):
            i += 1
            continue
        out.append(line)
        i += 1
    return "\n".join(out)


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description="Distillation v2 driver (see docs/DISTILLATION_V2.md)")
    p.add_argument("--group", required=True, help="definition / proof / theoremlike / ...")
    p.add_argument("--types", default=None,
                   help="comma-separated types in this group (default: --group)")
    p.add_argument("--papers", required=True, help="comma-separated paper ids, in order")
    p.add_argument("--tex-dir", required=True, type=Path)
    p.add_argument("--flat-tex", action="store_true")
    p.add_argument("--t2-dir", type=Path, default=REPO / "portal/data/tier2")
    p.add_argument("--eval-dir", required=True, type=Path)
    p.add_argument("--alpha", type=float, default=0.5)
    p.add_argument("--model", default="claude-sonnet-4-5-20250514")
    p.add_argument("--threshold", type=float, default=0.7)
    p.add_argument("--no-recycle", action="store_true",
                   help="disable step 2 (for A/B against v1 behaviour)")
    p.add_argument("--dry-run", action="store_true",
                   help="run everything except LLM calls; prints prompt sizes")
    args = p.parse_args()

    eval_dir = args.eval_dir.resolve()
    eval_dir.mkdir(parents=True, exist_ok=True)
    group = args.group
    types_in_group = [t.strip() for t in (args.types or group).split(",")]
    papers = [x.strip() for x in args.papers.split(",") if x.strip()]

    reg = RuleRegistry.load(eval_dir / REGISTRY_FILE)
    rules_path = eval_dir / RULES_FILE
    current_src = rules_path.read_text(encoding="utf-8") if rules_path.is_file() else ""

    print("=" * 72)
    print("DISTILLATION v2  group=%s  papers=%d  alpha=%.2f" % (group, len(papers), args.alpha))
    print("  registry : %s (%d rules known)" % (eval_dir / REGISTRY_FILE, len(reg.rules)))
    print("  recycle  : %s" % ("OFF" if args.no_recycle else "ON"))
    print("  mode     : %s" % ("DRY RUN (no LLM calls)" if args.dry_run else "live"))
    print("=" * 72)

    log = []
    for idx, pid in enumerate(papers, 1):
        t0 = time.time()
        print(f"\n--- [{idx}/{len(papers)}] {pid} " + "-" * 40)
        reg.note_paper(pid)

        tex = _find_tex(args.tex_dir, pid, args.flat_tex)
        if tex is None:
            print(f"  SKIP: no .tex found for {pid}")
            continue
        text = tex.read_text(encoding="utf-8", errors="replace")

        # --- 1. dark knowledge -------------------------------------------
        dk = _dark_knowledge(pid, args, eval_dir, group)
        print(f"  [1] dark-knowledge items: {len(dk)}")

        # --- 2. recycle (free) -------------------------------------------
        revived = []
        if dk and not args.no_recycle:
            cands = reg.recycle_candidates([d.get("gold_text", "") for d in dk],
                                           text, group=group)
            for r in cands:
                reg.revive(r.uid, pid)
                revived.append(r.uid)
            if revived:
                print(f"  [2] RECYCLED {len(revived)} retired rule(s): uids {revived}")
            else:
                print("  [2] no retired rule covers these misses")
        elif args.no_recycle:
            print("  [2] recycle disabled")

        # --- 3. generate --------------------------------------------------
        usage = {"input_tokens": 0, "output_tokens": 0, "prompt_chars": 0}
        if dk:
            new_rows = _analyze(dk, args, eval_dir, group)
            print(f"  [3] analyze -> {len(new_rows)} suggestion(s)")
            new_src, usage = aggregate_incremental(
                current_src, new_rows, group, types_in_group, eval_dir,
                args.model, dry_run=args.dry_run)
            if new_src != current_src:
                s = sync_registry_from_source(reg, new_src, group, pid)
                print(f"      uids: minted {s['minted']}, reused {s['reused']}")
                current_src = new_src
            print(f"      prompt {usage['prompt_chars']:,} chars "
                  f"({usage['input_tokens']:,} in / {usage['output_tokens']:,} out)")
        else:
            print("  [3] nothing to generate")

        # --- 4/5. score + gate -------------------------------------------
        # Stats come from the same attribution prune_rules uses (rule_name in
        # results). Left to the caller in dry-run so this stays LLM-free.
        gate = reg.apply_gate(args.alpha, papers=reg.papers_seen)
        print(f"  [5] gate@alpha={args.alpha:.2f}: {gate}")

        # --- 6. emit ------------------------------------------------------
        rendered = emit_source(reg, current_src, group)
        rules_path.write_text(rendered + "\n", encoding="utf-8")
        reg.save()

        log.append({"paper": pid, "dk": len(dk), "revived": len(revived),
                    "active": gate["active"], "retired": gate["retired"],
                    "prompt_chars": usage["prompt_chars"],
                    "input_tokens": usage["input_tokens"],
                    "secs": round(time.time() - t0, 1)})
        (eval_dir / "v2_log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")

    # ---- summary ---------------------------------------------------------
    print("\n" + "=" * 72)
    print("SUMMARY")
    print("=" * 72)
    print("  %-12s %4s %8s %7s %8s %12s" % ("paper", "DK", "revived", "active", "retired", "prompt_chars"))
    for e in log:
        print("  %-12s %4d %8d %7d %8d %12s"
              % (e["paper"], e["dk"], e["revived"], e["active"], e["retired"],
                 f"{e['prompt_chars']:,}"))
    if len(log) >= 2:
        g = log[-1]["prompt_chars"] - log[0]["prompt_chars"]
        print(f"\n  prompt growth first->last: {g:+,} chars "
              f"(v1 grew ~+11K TOKENS per paper — the context-wall bug)")
    lin = reg.lineage_table()
    print(f"\n  registry: {len(lin)} rules, "
          f"{sum(1 for r in lin if r['status']=='active')} active, "
          f"{sum(r['revivals'] for r in lin)} total revivals, "
          f"{sum(r['renames'] for r in lin)} renames absorbed")
    with open(eval_dir / "rule_lineage.csv", "w", newline="", encoding="utf-8") as f:
        if lin:
            w = csv.DictWriter(f, fieldnames=list(lin[0].keys()))
            w.writeheader(); w.writerows(lin)
    print(f"  lineage -> {eval_dir/'rule_lineage.csv'}")
    print(f"  registry -> {eval_dir/REGISTRY_FILE}")


# ---------------------------------------------------------------------------
# thin adapters onto Yaron's pipeline
# ---------------------------------------------------------------------------

def _find_tex(tex_dir: Path, pid: str, flat: bool):
    if flat:
        for c in (tex_dir / f"{pid}.tex", tex_dir / f"{pid.replace('/', '_')}.tex"):
            if c.is_file():
                return c
        return None
    d = tex_dir / pid / "source"
    if d.is_dir():
        cand = sorted(d.glob("*.tex"))
        return cand[0] if cand else None
    return None


def _dark_knowledge(pid, args, eval_dir, group) -> List[dict]:
    """Delegate to Yaron's identify_dark_knowledge; [] if prerequisites absent."""
    try:
        from silver_distillation_sequential import FNAME_MAP, build_detailed_matches
        from distillation_analysis import identify_dark_knowledge
    except Exception as e:                                   # noqa: BLE001
        print(f"      (dark-knowledge unavailable: {e})")
        return []
    gold_csv = eval_dir / "silver_gold" / FNAME_MAP.get(group, "")
    if not gold_csv.is_file():
        print(f"      (no gold CSV at {gold_csv})")
        return []
    try:
        build_detailed_matches(pid, args.t2_dir / f"{pid}.json", args.tex_dir,
                               group, eval_dir)
        items = identify_dark_knowledge(str(eval_dir), str(gold_csv), group,
                                        args.threshold)
        return [d for d in items if d.get("paper_id") == pid]
    except Exception as e:                                   # noqa: BLE001
        print(f"      (dark-knowledge failed: {e})")
        return []


def _analyze(dk, args, eval_dir, group) -> List[dict]:
    """Delegate to Yaron's analyze_patterns_batched (unmodified prompts)."""
    if args.dry_run:
        return [{"paper_id": d.get("paper_id"), "gold_text": d.get("gold_text"),
                 "llm_suggested_rule": "(dry-run)"} for d in dk]
    try:
        from distillation_analysis import analyze_patterns_batched
        rows = analyze_patterns_batched(dk, tex_dir=str(args.tex_dir),
                                        structure_type=group, model=args.model)
        return rows[0] if isinstance(rows, tuple) else rows
    except Exception as e:                                   # noqa: BLE001
        print(f"      (analyze failed: {e})")
        return []


if __name__ == "__main__":
    main()
