#!/usr/bin/env python3
"""TRACE.md — a readable, paper-by-paper account of what a distillation run did.

REPORT.md answers "how well did it score". This answers "what actually
happened": for each paper, in the order the pipeline executes, what the base
parser missed, what the teacher said about each miss, which rules came out,
which were pruned and on what evidence, and what changed as a result.

Nothing is truncated here — REPORT.md clips reasoning to ~220 chars to stay
skimmable, which is exactly what makes it useless for auditing the teacher.

Read-only: it re-renders artifacts the run already wrote. No LLM calls, no
parsing, no edits. Safe to run repeatedly, including on an in-flight run.

    python scripts/make_run_trace.py --eval-dir <dir> [--max-fn-per-group N]
"""
import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path


def _read_csv(p):
    if not Path(p).is_file():
        return []
    with open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _fence(code, lang=""):
    """Render code in a fence, escaping any fence the content itself contains."""
    body = (code or "").strip()
    if not body:
        return "_(none)_"
    body = body.replace("```", "``​`")
    return f"```{lang}\n{body}\n```"


def _pct(x):
    return "n/a" if x is None else f"{x:.3f}"


def build_trace(eval_dir, max_fn=None):
    eval_dir = Path(eval_dir)
    out = eval_dir / "TRACE.md"
    L = []
    def w(s=""):
        L.append(s)

    log = json.load(open(eval_dir / "iteration_log.json", encoding="utf-8"))

    # analyze rows: group -> paper -> [row]; the run appends cumulatively, so a
    # row's paper_id is what ties it to the step that produced it.
    rows_by = defaultdict(lambda: defaultdict(list))
    for gdir in sorted((eval_dir / "groups").glob("*")):
        if not gdir.is_dir():
            continue
        for r in _read_csv(gdir / "cumulative_analyze.csv"):
            rows_by[gdir.name][r.get("paper_id", "")].append(r)

    # Prune decisions. prune_rules() is called with eval_dir=<eval>/groups/<g>,
    # so each group writes its own log there — not one file at the root.
    prune_events = []
    for pl in sorted(eval_dir.glob("groups/*/prune_log.jsonl")) + \
              ([eval_dir / "prune_log.jsonl"]
               if (eval_dir / "prune_log.jsonl").is_file() else []):
        for line in pl.read_text(encoding="utf-8").splitlines():
            try:
                prune_events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    w("# Distillation run — step-by-step trace")
    w(f"\n_eval-dir: `{eval_dir}` · {len(log)} paper(s) · "
      f"re-rendered read-only from run artifacts_\n")

    w("## How one paper is processed\n")
    w("Each paper goes through the same five steps. Steps 3 and 4 are the only "
      "ones that call the LLM; dark-knowledge detection and pruning are "
      "deterministic.\n")
    w("| # | step | what happens | LLM? |")
    w("|---|---|---|---|")
    w("| 1 | parse | run the base parser + every rule distilled so far over the `.tex` | no |")
    w("| 2 | dark knowledge | diff that against the teacher's JSON → the **false negatives** | no |")
    w("| 3 | analyze | send the FNs in batches, ask why each was missed and for a rule | **yes** |")
    w("| 4 | aggregate | merge the accumulated suggestions into the group's rule file | **yes** |")
    w("| 5 | prune | re-score every rule over all papers so far; drop those above the FDR gate | no |")
    w("\nPruning uses `FDR = FP/(FP+TP)` counted over **papers 1..N only** — "
      "papers not yet reached are never part of the decision. A pruned rule is "
      "commented out, so it cannot fire again and is never reconsidered.\n")

    if prune_events:
        alphas = {d["alpha"] for e in prune_events for d in e["decisions"]}
        if alphas:
            w(f"_This run's gate: alpha = {', '.join(f'{a:g}' for a in sorted(alphas))}._\n")

    w("---\n")

    for i, entry in enumerate(log, 1):
        pid = entry["paper_id"]
        w(f"## Paper {i}/{len(log)} — `{pid}`\n")

        b = {t: v["baseline"] for t, v in entry.get("per_type", {}).items()}
        p = {t: v["post"] for t, v in entry.get("per_type", {}).items()}
        w(f"**Step 1-2 — parse, then diff against the teacher.** "
          f"Base parser vs teacher JSON left **{entry.get('total_fns', 0)} "
          f"false negative(s)** to learn from"
          + (f" ({entry.get('already_covered', 0)} already covered by existing rules)."
             if entry.get("already_covered") else ".") + "\n")

        moved = [(t, b[t]["f1"], p[t]["f1"]) for t in b
                 if b[t]["n_gold"] or p[t]["n_extracted"]]
        if moved:
            w("| type | gold | base F1 | post F1 | Δ |")
            w("|---|---|---|---|---|")
            for t, fb, ff in sorted(moved, key=lambda x: -(x[2] - x[1])):
                d = ff - fb
                w(f"| {t} | {b[t]['n_gold']} | {fb:.3f} | {ff:.3f} | "
                  f"{d:+.3f}{' ✅' if d > 0 else ''} |")
            w("")

        for gkey in sorted(rows_by):
            rs = rows_by[gkey].get(pid, [])
            if not rs:
                continue
            with_rule = [r for r in rs if (r.get("llm_suggested_rule") or "").strip()]
            declined = [r for r in rs
                        if not (r.get("llm_suggested_rule") or "").strip()
                        and (r.get("llm_reasoning") or "").strip()]
            lost = [r for r in rs
                    if not (r.get("llm_suggested_rule") or "").strip()
                    and not (r.get("llm_reasoning") or "").strip()]

            w(f"### Step 3-4 — group `{gkey}`: {len(rs)} missed structure(s)\n")
            w(f"- teacher proposed a rule for **{len(with_rule)}**")
            if declined:
                w(f"- teacher **declined** on {len(declined)} (explained why, no rule "
                  f"— this is legitimate, not a failure)")
            if lost:
                w(f"- ⚠️ **{len(lost)} returned empty** (no rule AND no reasoning) — "
                  f"teacher signal was lost, not declined")
            w("")

            shown = rs if max_fn is None else rs[:max_fn]
            for n, r in enumerate(shown, 1):
                gt = (r.get("gold_text") or "").strip()
                w(f"<details>\n<summary><b>{n}. {r.get('structure_type', gkey)}</b> — "
                  f"<code>{gt[:110].replace('<', '&lt;')}…</code></summary>\n")
                w("**What the teacher missed:**\n")
                w(_fence(gt, "latex"))
                w("\n**Why it was missed:**\n")
                w((r.get("llm_reasoning") or "_(none recorded)_").strip())
                w("\n**Rule it suggested:**\n")
                w(_fence(r.get("llm_suggested_rule"), "python"))
                w("\n</details>\n")
            if max_fn is not None and len(rs) > max_fn:
                w(f"_…{len(rs) - max_fn} more in "
                  f"`groups/{gkey}/cumulative_analyze.csv`._\n")

        # step 5 — prune decisions taken while this paper was the newest one
        ev = [e for e in prune_events if e["papers_scored"] and
              e["papers_scored"][-1] == pid]
        if ev:
            w("### Step 5 — prune\n")
            judged = [e for e in ev if e["decisions"]]
            if judged:
                w("| group | rule | TP | FP | FDR | alpha | verdict |")
                w("|---|---|---|---|---|---|---|")
                for e in judged:
                    for d in sorted(e["decisions"], key=lambda x: x["fdr"]):
                        mark = "**PRUNED**" if d["verdict"] == "prune" else "keep"
                        w(f"| {e['structure_type']} | `{d['rule']}` | {d['tp']} | "
                          f"{d['fp']} | {d['fdr']:.3f} | {d['alpha']:g} | {mark} |")
                w("")
            for e in ev:
                if not e["decisions"]:
                    w(f"- `{e['structure_type']}`: "
                      f"{e.get('note', 'gate ran, no rule judged')}")
            w(f"\n_Scored over {len(ev[0]['papers_scored'])} paper(s) so far._\n")
        else:
            w("### Step 5 — prune\n")
            w("_No prune record for this paper. Runs made before "
              "`prune_log.jsonl` existed have none — the gate still ran; see "
              "the `# PRUNED` markers in `groups/<g>/distilled_rules.py`._\n")

        w(f"**Result:** {entry.get('cumulative_rules', 0)} cumulative rule(s) · "
          f"{entry.get('total_llm_calls', 0)} LLM call(s) · "
          f"${entry.get('total_cost_usd', 0):.4f} · "
          f"{entry.get('wall_time_seconds', 0):.0f}s\n")
        w("---\n")

    tot_c = sum(e.get("total_cost_usd", 0) for e in log)
    tot_k = sum(e.get("total_llm_calls", 0) for e in log)
    w("## Run totals\n")
    w(f"- papers: {len(log)}")
    w(f"- LLM calls: {tot_k}")
    w(f"- cost: ${tot_c:.4f}")
    if log:
        w(f"- final cumulative rules: {log[-1].get('cumulative_rules', 0)}")
    w("\n_Scores are in `REPORT.md`. Raw artifacts: "
      "`groups/<g>/cumulative_analyze.csv`, `prune_log.jsonl`, "
      "`snapshots/step_NN_<paper>/`._")

    out.write_text("\n".join(L), encoding="utf-8")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-dir", required=True)
    ap.add_argument("--max-fn-per-group", type=int, default=None,
                    help="cap FN detail per group per paper (default: all)")
    args = ap.parse_args()
    print(f"wrote {build_trace(args.eval_dir, args.max_fn_per_group)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
