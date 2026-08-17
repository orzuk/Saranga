#!/usr/bin/env python3
"""Base rules vs distilled rules, scored per split (train / test tiers)
========================================================================
Reproduces the train-vs-held-out comparison WITHOUT any distillation or LLM
calls: it takes an existing distillation run's snapshots, installs the baseline
(step_00) and the FINAL rule set in turn, parses every paper, and scores both
against the silver gold built from `corpus/silver/`.

Everything comes from the in-repo corpus:
  * papers + splits  -> corpus/silver/metadata.csv   (train=17, test=60)
  * silver gold      -> corpus/silver/<model>__<prompt>/<paper>.json
  * LaTeX            -> corpus/silver/tex/<paper>.tex

Groups reported: `train`, and each test `tier` (A_matched_ML, B_math_shift).
Numbers are POOLED (micro) node-level TP/FP/FN over all types, which is the
convention the reports use.

Usage:
    python scripts/eval_base_vs_distilled_split.py \
        --eval-dir src/LLMVersion/merged_eval_silver_001_011_v3 \
        --prompt-version v4.1 --match-metric containment --threshold 0.7
"""

import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "src" / "LLMVersion"))
sys.path.insert(0, str(REPO / "src"))

import silver_distillation_sequential as seq
from silver_distillation_sequential import FNAME_MAP, convert_t2_to_gold_csv
from silver_distillation_merged import parse_buckets, metrics, load_gold_texts

TYPES = list(FNAME_MAP.keys())


def build_tex_tree(rows, dest: Path) -> Path:
    """parse_buckets expects <tex_dir>/<pid>/source/*.tex; the corpus is flat."""
    if dest.exists():
        shutil.rmtree(dest)
    for r in rows:
        src = REPO / r["tex_path"]
        if not src.exists():
            continue
        d = dest / r["paper_id"] / "source"
        d.mkdir(parents=True, exist_ok=True)
        os.symlink(src, d / f"{r['paper_id']}.tex")
    return dest


def build_gold(rows, dest: Path) -> Path:
    """One gold CSV per type, covering every paper (convert_* appends)."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    for r in rows:
        jp = REPO / r["json_path"]
        if not jp.exists():
            continue
        for t in TYPES:
            convert_t2_to_gold_csv(jp, t, dest)
    return dest


def prf(d):
    tp, fp, fn = d["tp"], d["fp"], d["fn"]
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    return p, r, f1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-dir", default="src/LLMVersion/merged_eval_silver_001_011_v3")
    ap.add_argument("--prompt-version", default="v4.1",
                    help="which extraction config in metadata.csv to score against")
    ap.add_argument("--match-metric", default="containment",
                    choices=["jaccard", "containment"])
    ap.add_argument("--threshold", type=float, default=0.7)
    ap.add_argument("--work-dir", default=None, help="scratch dir for tex tree + gold")
    ap.add_argument("--out", default=None, help="per-paper CSV (default <eval-dir>/split_eval.csv)")
    ap.add_argument("--baseline-snapshot", default=None)
    ap.add_argument("--final-snapshot", default=None)
    ap.add_argument("--cache", default=None,
                    help="JSON cache of parsed buckets; reused if present so "
                         "re-scoring (other metric/threshold) needs no re-parse")
    args = ap.parse_args()

    seq._MATCH_METRIC = args.match_metric

    eval_dir = (REPO / args.eval_dir).resolve()
    snaps = sorted((eval_dir / "snapshots").glob("step_*"))
    base_snap = (eval_dir / "snapshots" / args.baseline_snapshot) if args.baseline_snapshot \
        else next(s for s in snaps if s.name.startswith("step_00"))
    final_snap = (eval_dir / "snapshots" / args.final_snapshot) if args.final_snapshot \
        else snaps[-1]

    rows = [r for r in csv.DictReader(open(REPO / "corpus/silver/metadata.csv", encoding="utf-8"))
            if r["prompt_version"] == args.prompt_version and r["has_tex"] == "yes"]
    # group label: train, or test-<tier>
    for r in rows:
        r["group"] = "train" if r["split"] == "train" else f"test-{r['tier']}"

    work = Path(args.work_dir) if args.work_dir else eval_dir / "_split_eval"
    work.mkdir(parents=True, exist_ok=True)
    print(f"baseline snapshot : {base_snap.name}")
    print(f"final snapshot    : {final_snap.name}")
    print(f"match metric      : {args.match_metric} @ {args.threshold}")
    print(f"papers            : {len(rows)} ({args.prompt_version})")
    for g in sorted({r['group'] for r in rows}):
        print(f"    {g:<22} {sum(1 for r in rows if r['group'] == g)}")

    tex_dir = build_tex_tree(rows, work / "tex")
    gold_dir = build_gold(rows, work / "gold")
    gold = {t: load_gold_texts(gold_dir / FNAME_MAP[t]) for t in TYPES}

    pooled = defaultdict(lambda: {"base": {"tp": 0, "fp": 0, "fn": 0},
                                  "final": {"tp": 0, "fp": 0, "fn": 0}})
    per_type = defaultdict(lambda: {"base": {"tp": 0, "fp": 0, "fn": 0},
                                    "final": {"tp": 0, "fp": 0, "fn": 0}})
    # (group, type) -> counts, so a per-type gating counterfactual can be scored
    # per split without re-parsing.
    grp_type = defaultdict(lambda: {"base": {"tp": 0, "fp": 0, "fn": 0},
                                    "final": {"tp": 0, "fp": 0, "fn": 0}})
    out_rows = []

    cache_path = Path(args.cache) if args.cache else work / "buckets_cache.json"

    # The two sides age differently, so they cannot share one cache key:
    #   base  - parsed with NO distilled rules. Independent of the rule set, so
    #           it stays valid across runs and is the expensive half worth keeping.
    #   final - parsed with the CURRENT rules. Changes whenever distillation adds
    #           or prunes a rule, so reusing it across runs silently reports the
    #           previous run's rules as if they were the new ones.
    # Fingerprint the rule files and only reuse `final` when they are unchanged.
    def _rules_fingerprint(snap):
        h = hashlib.sha256()
        for f in sorted(Path(snap).rglob("distilled_rules.py")):
            h.update(f.relative_to(snap).as_posix().encode())
            h.update(f.read_bytes())
        return h.hexdigest()[:16]

    fp = _rules_fingerprint(final_snap)
    cache = {}
    if cache_path.exists():
        raw = json.load(open(cache_path, encoding="utf-8"))
        cache = raw.get("papers", {}) if isinstance(raw.get("papers"), dict) else {}
        old_fp = raw.get("rules_fingerprint") if isinstance(raw, dict) else None
        stale = old_fp != fp
        print(f"bucket cache: {cache_path} ({len(cache)} papers), "
              f"rules fingerprint {old_fp} -> {fp}"
              + ("  [final side STALE, will re-parse]" if stale else "  [reusable]"))
        if stale:
            for v in cache.values():
                v.pop("final", None)
    print(f"rules fingerprint: {fp}")

    n_reused_b = n_reused_f = 0
    for i, r in enumerate(rows, 1):
        pid, grp = r["paper_id"], r["group"]
        ent = cache.setdefault(pid, {})
        if "base" in ent:
            bb = ent["base"]
            n_reused_b += 1
        else:
            bb = ent["base"] = parse_buckets(pid, tex_dir, TYPES, eval_dir=base_snap)
        if "final" in ent:
            fb = ent["final"]
            n_reused_f += 1
        else:
            fb = ent["final"] = parse_buckets(pid, tex_dir, TYPES, eval_dir=final_snap)
        rec = {"paper_id": pid, "group": grp, "tier": r["tier"], "category": r["primary_category"]}
        for tag, buckets in (("base", bb), ("final", fb)):
            for t in TYPES:
                m = metrics(buckets[t], gold[t].get(pid, []), args.threshold)
                for k in ("tp", "fp", "fn"):
                    pooled[grp][tag][k] += m[k]
                    per_type[t][tag][k] += m[k]
                    grp_type[(grp, t)][tag][k] += m[k]
                    rec[f"{tag}_{k}"] = rec.get(f"{tag}_{k}", 0) + m[k]
        p_b, r_b, f_b = prf({k: rec[f"base_{k}"] for k in ("tp", "fp", "fn")})
        p_f, r_f, f_f = prf({k: rec[f"final_{k}"] for k in ("tp", "fp", "fn")})
        rec.update(base_f1=round(f_b, 4), final_f1=round(f_f, 4))
        out_rows.append(rec)
        print(f"[{i:>3}/{len(rows)}] {pid:<10} {grp:<20} base F1 {f_b:.3f} -> final F1 {f_f:.3f}")

    print("\n" + "=" * 78)
    print("POOLED (micro) — base vs final distilled rules")
    print("=" * 78)
    order = ["train", "test-B_math_shift", "test-A_matched_ML"]
    for grp in [g for g in order if g in pooled] + [g for g in pooled if g not in order]:
        n = sum(1 for r in rows if r["group"] == grp)
        print(f"\n{grp}  ({n} papers)")
        for tag in ("base", "final"):
            d = pooled[grp][tag]
            p, rc, f1 = prf(d)
            print(f"  {tag:<6} F1 {f1:.3f}  (P {p:.3f}, R {rc:.3f} | "
                  f"TP {d['tp']}, FP {d['fp']}, FN {d['fn']})")
        _, _, fb = prf(pooled[grp]["base"])
        _, _, ff = prf(pooled[grp]["final"])
        print(f"  dF1    {ff - fb:+.3f}")

    print("\nPer-type dF1 (all papers pooled)")
    print(f"  {'type':<14} {'gold':>6} {'base F1':>8} {'final F1':>9} {'dF1':>7}")
    for t in TYPES:
        d = per_type[t]
        ngold = d["base"]["tp"] + d["base"]["fn"]
        if ngold == 0:
            continue
        _, _, fb = prf(d["base"])
        _, _, ff = prf(d["final"])
        print(f"  {t:<14} {ngold:>6} {fb:>8.3f} {ff:>9.3f} {ff - fb:>+7.3f}")

    # ---- counterfactual: keep distilled rules ONLY where they help ----------
    # A distilled rule can only ADD extractions, so on types the base parser
    # already saturates it can only add FPs. Decide per type on TRAIN, then
    # apply that decision to the held-out splits (no test peeking).
    keep = set()
    for t in TYPES:
        d = grp_type[("train", t)]
        if d["base"]["tp"] + d["base"]["fn"] == 0:
            continue
        _, _, fb = prf(d["base"])
        _, _, ff = prf(d["final"])
        if ff > fb:
            keep.add(t)
    print(f"\nTypes where distillation helps on TRAIN (gate learned on train only):"
          f"\n  keep   : {sorted(keep)}"
          f"\n  discard: {sorted(t for t in TYPES if t not in keep)}")
    print("\nGATED pooled (distilled rules applied only to kept types)")
    for grp in [g for g in order if g in pooled]:
        g_c = {"tp": 0, "fp": 0, "fn": 0}
        for t in TYPES:
            src = grp_type[(grp, t)]["final" if t in keep else "base"]
            for k in g_c:
                g_c[k] += src[k]
        _, _, fb = prf(pooled[grp]["base"])
        _, _, ff = prf(pooled[grp]["final"])
        p, rc, f1 = prf(g_c)
        print(f"  {grp:<20} base {fb:.3f} | ungated {ff:.3f} | gated {f1:.3f} "
              f"({f1 - fb:+.3f} vs base)  [P {p:.3f} R {rc:.3f}]")

    # ALWAYS rewrite: the old `if not exists` guard meant a cache written once
    # was never refreshed, so a later run reused the earlier run's `final` side.
    json.dump({"rules_fingerprint": fp, "papers": cache},
              open(cache_path, "w", encoding="utf-8"))
    print(f"\nWrote bucket cache {cache_path} "
          f"(reused base for {n_reused_b}/{len(rows)}, final for {n_reused_f}/{len(rows)})")

    out = Path(args.out) if args.out else eval_dir / "split_eval.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)
    summary = {g: dict(v) for g, v in pooled.items()}
    json.dump(summary, open(out.with_suffix(".json"), "w", encoding="utf-8"), indent=2)
    print(f"\nWrote {out}\nWrote {out.with_suffix('.json')}")


if __name__ == "__main__":
    main()
