#!/usr/bin/env python3
"""Per-rule accounting: what did each distilled rule actually buy us?

A distillation run reports one aggregate F1, which says nothing about whether
the rules are individually earning their place. This attributes every extraction
to the rule that produced it (each rule emits its own `rule_name`, which the
prune step already keys off) and reports, per rule:

    matches   how many spans it produced across the corpus
    TP / FP   how those scored against the silver gold
    papers    how many distinct papers it fired on
    verdict   DEAD (never fired), FP-ONLY (fires, never right), or a precision

Dead rules matter: we paid an LLM to write them, they are shipped in the parser,
they cost regex time on every paper in the 100k corpus, and they contribute
nothing. A rule firing on exactly one paper is the other thing to watch — that
is memorisation of the paper it was distilled from, not a generalisation.

Read-only: it re-runs existing rules over existing papers and writes a report.
No LLM calls, and it never edits a rule file.

Usage:
    python scripts/rule_match_report.py \
        --eval-dir src/LLMVersion/merged_eval_silver_001_011_v3 \
        --tex-dir /path/to/alignment/papers \
        --match-mode m1
"""

import argparse
import csv
import importlib.util
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "src" / "LLMVersion"))
sys.path.insert(0, str(REPO / "src"))

import match_modes as mm
import silver_distillation_sequential as seq
from silver_distillation_sequential import FNAME_MAP, _find_main_tex
from silver_distillation_merged import base_method_groups, load_gold_texts

TYPES = list(FNAME_MAP.keys())


def load_group_module(path: Path, gkey: str):
    spec = importlib.util.spec_from_file_location(f"rules_{gkey}_{id(path)}",
                                                  str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def declared_rules(mod) -> set:
    """Module-level compiled patterns — the rules that COULD fire."""
    return {n for n in dir(mod)
            if isinstance(getattr(mod, n), re.Pattern)
            and "EXCL" not in n.upper()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-dir", required=True)
    ap.add_argument("--tex-dir", required=True)
    ap.add_argument("--papers", default=None,
                    help="comma list (default: the run's iteration_log)")
    ap.add_argument("--snapshot", default=None,
                    help="snapshot dir name (default: highest step_NN)")
    ap.add_argument("--threshold", type=float, default=0.7)
    ap.add_argument("--match-mode", default="m1", choices=["m1", "m3"])
    ap.add_argument("--cover", type=float, default=0.7)
    ap.add_argument("--match-metric", default="containment",
                    choices=["jaccard", "containment"])
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    seq.set_match_metric(args.match_metric)
    eval_dir = (REPO / args.eval_dir).resolve() if not Path(args.eval_dir).is_absolute() \
        else Path(args.eval_dir)
    tex_dir = Path(args.tex_dir)
    gold_dir = eval_dir / "silver_gold"

    snaps = sorted((eval_dir / "snapshots").glob("step_*"))
    snap = (eval_dir / "snapshots" / args.snapshot) if args.snapshot else \
        (snaps[-1] if snaps else eval_dir)
    groups_root = snap / "groups" if (snap / "groups").is_dir() else eval_dir / "groups"

    if args.papers:
        papers = [p.strip() for p in args.papers.split(",") if p.strip()]
    else:
        log = json.load(open(eval_dir / "iteration_log.json", encoding="utf-8"))
        papers = [e["paper_id"] for e in log]

    groups = base_method_groups(TYPES)
    gold = {t: load_gold_texts(gold_dir / FNAME_MAP[t]) for t in TYPES}

    print(f"snapshot : {snap.name}")
    print(f"papers   : {len(papers)}")
    print(f"mode     : {args.match_mode} (metric={args.match_metric} @ {args.threshold})\n")

    stats = defaultdict(lambda: {"matches": 0, "tp": 0, "fp": 0,
                                 "papers": set(), "group": ""})
    declared = {}

    for gkey, gtypes in groups.items():
        gfile = groups_root / gkey / "distilled_rules.py"
        if not gfile.exists():
            continue
        try:
            mod = load_group_module(gfile, gkey)
        except Exception as e:
            print(f"  [skip] {gkey}: {e}")
            continue
        fn = getattr(mod, f"extract_distilled_{gkey}", None)
        if fn is None:
            print(f"  [skip] {gkey}: no entry point")
            continue
        for name in declared_rules(mod):
            declared[name] = gkey
            stats[name]["group"] = gkey

        # gold for this group's types, plus all-type gold for m3 support
        for pid in papers:
            main_tex = _find_main_tex(tex_dir / pid / "source")
            if not main_tex:
                continue
            text = Path(main_tex).read_text(encoding="utf-8", errors="replace")
            try:
                results = fn(text) or []
            except Exception as e:
                print(f"  [warn] {gkey} raised on {pid}: {e}")
                continue
            group_gold = [g for t in gtypes for g in gold[t].get(pid, [])]
            all_gold = [g for t in TYPES for g in gold[t].get(pid, [])]
            texts = [r.get("raw_latex", "") for r in results]
            verdicts = mm.classify_extractions(
                texts, group_gold, args.threshold, mode=args.match_mode,
                support_texts=all_gold, cover=args.cover)
            for r, ok in zip(results, verdicts):
                name = r.get("rule_name") or "<unnamed>"
                s = stats[name]
                s["matches"] += 1
                s["tp" if ok else "fp"] += 1
                s["papers"].add(pid)
                s["group"] = s["group"] or gkey

    rows = []
    for name, gkey in sorted(declared.items()):
        s = stats[name]
        rows.append({"rule_name": name, "group": s["group"] or gkey,
                     "matches": s["matches"], "tp": s["tp"], "fp": s["fp"],
                     "n_papers": len(s["papers"])})
    for name, s in stats.items():                      # fired but not declared
        if name not in declared:
            rows.append({"rule_name": name, "group": s["group"],
                         "matches": s["matches"], "tp": s["tp"], "fp": s["fp"],
                         "n_papers": len(s["papers"])})

    def verdict(r):
        if r["matches"] == 0:
            # An underscore-prefixed pattern is usually a HELPER (used inside
            # another rule for cleaning or negative filtering), so it never
            # emits a rule_name and never "fires" by this measure. Counting
            # those as dead extraction rules would overstate the waste.
            return ("unused (or helper)" if r["rule_name"].startswith("_")
                    else "DEAD — never fired")
        if r["tp"] == 0:
            return "FP-ONLY — never right"
        if r["n_papers"] == 1:
            return f"single-paper (P={r['tp']/r['matches']:.2f})"
        return f"P={r['tp'] / r['matches']:.2f}"

    rows.sort(key=lambda r: (-r["matches"], r["rule_name"]))
    print(f"{'rule':<34} {'group':<12} {'match':>6} {'TP':>5} {'FP':>5} "
          f"{'papers':>7}  verdict")
    print("-" * 100)
    for r in rows:
        print(f"{r['rule_name'][:33]:<34} {r['group']:<12} {r['matches']:>6} "
              f"{r['tp']:>5} {r['fp']:>5} {r['n_papers']:>7}  {verdict(r)}")

    dead = [r for r in rows
            if r["matches"] == 0 and not r["rule_name"].startswith("_")]
    helpers = [r for r in rows
               if r["matches"] == 0 and r["rule_name"].startswith("_")]
    fponly = [r for r in rows if r["matches"] and r["tp"] == 0]
    single = [r for r in rows if r["n_papers"] == 1 and r["matches"]]
    tot_m = sum(r["matches"] for r in rows)
    tot_tp = sum(r["tp"] for r in rows)
    print("-" * 100)
    print(f"{len(rows)} pattern(s): {len(dead)} DEAD extraction rule(s), "
          f"{len(helpers)} unused/helper, {len(fponly)} FP-only, "
          f"{len(single)} fired on a single paper only")
    print(f"{tot_m} match(es) total, {tot_tp} TP "
          f"({tot_tp / tot_m * 100:.0f}% precision)" if tot_m else "no matches")
    if dead:
        print(f"\nDEAD extraction rules (paid for, shipped, never fire):")
        for r in dead:
            print(f"  {r['group']:<12} {r['rule_name']}")

    out = Path(args.out) if args.out else eval_dir / "rule_match_report.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["rule_name", "group", "matches",
                                          "tp", "fp", "n_papers"])
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
