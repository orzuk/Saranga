#!/usr/bin/env python3
"""Bootstrap 95% CIs for Benchmark 1 macro-F1 over the 10 T1 papers.

Cluster layout: portal/data/tier1/ contains for each arxiv_id triple of
JSONs:
    <arxiv_id>_manual.json     (T1 hand gold)
    <arxiv_id>_anthropic.json  (Claude Opus extraction)
    <arxiv_id>_openai.json     (GPT-4o extraction)

For T3 (regex), we extract from LaTeX on the fly via run_pipeline.py if
not cached.

For each provider, this script:
  1. Runs evaluate_extraction.py (extracted vs gold) per paper -> per-paper macro-F1
  2. Bootstrap-resamples the 10 per-paper F1s (10000 iters) -> mean + 95% CI

Usage:
    python3 scripts/bootstrap_t1_cis.py
        [--t3-tex-base <dir with paperN/source/>]
        [--t3-cache-dir <dir to cache T3 extractions>]
        [--n-iter 10000]
        [--skip-t3]   (skip T3 if no LaTeX dir is available)
"""
import argparse
import csv
import json
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
T1_DIR = REPO / "portal" / "data" / "tier1"
EVAL_SCRIPT = REPO / "src" / "evaluate_extraction.py"
PIPELINE = REPO / "src" / "run_pipeline.py"

THEOREM_LIKE = {"theorem", "lemma", "proposition", "corollary", "claim",
                "conjecture", "problem", "definition", "proof"}


def per_paper_per_type_counts(extracted_path, gold_path):
    """Returns dict {type: (tp, fp, fn)} for the 9 evaluated types."""
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
        out_csv = tf.name
    cmd = [
        sys.executable, str(EVAL_SCRIPT),
        "--extracted", str(extracted_path),
        "--gold",      str(gold_path),
        "--csv",       out_csv,
        "--exclude-origin", "external",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        Path(out_csv).unlink(missing_ok=True)
        return None
    counts = {}
    try:
        for r in csv.DictReader(open(out_csv)):
            cat = (r.get("category") or "").strip()
            typ = (r.get("type") or "").strip().lower()
            if cat == "nodes" and typ in THEOREM_LIKE:
                try:
                    tp = int(r.get("tp") or 0)
                    fp = int(r.get("fp") or 0)
                    fn = int(r.get("fn") or 0)
                    counts[typ] = (tp, fp, fn)
                except ValueError:
                    pass
    finally:
        Path(out_csv).unlink(missing_ok=True)
    return counts


def macro_f1_corpus(per_paper_counts, types):
    """Corpus-level macro-F1: sum TP/FP/FN per type across papers,
    compute F1 per type, average over types where gold>0 (TP+FN>0).
    Matches the paper's reported aggregation."""
    sums = {t: [0, 0, 0] for t in types}
    for counts in per_paper_counts:
        for t in types:
            tp, fp, fn = counts.get(t, (0, 0, 0))
            sums[t][0] += tp
            sums[t][1] += fp
            sums[t][2] += fn
    f1s = []
    for t in types:
        tp, fp, fn = sums[t]
        if tp + fn == 0:
            continue  # no gold for this type at all; skip
        denom = 2 * tp + fp + fn
        f1 = (2 * tp / denom) if denom > 0 else 0.0
        f1s.append(f1)
    return sum(f1s) / len(f1s) if f1s else 0.0


def bootstrap_ci_corpus(per_paper_counts, types, n_iter=10000, seed=42, alpha=0.05):
    n = len(per_paper_counts)
    if n == 0:
        return None
    rng = random.Random(seed)
    means = []
    for _ in range(n_iter):
        sample = [per_paper_counts[rng.randrange(n)] for _ in range(n)]
        means.append(macro_f1_corpus(sample, types))
    means.sort()
    lo = means[int(n_iter * alpha / 2)]
    hi = means[int(n_iter * (1 - alpha / 2))]
    return macro_f1_corpus(per_paper_counts, types), lo, hi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--t3-tex-base", default="/sci/labs/orzuk/orzuk/projects/Authomathics/arxiv/full_papers_advanced",
                    help="Dir with subdirs for each arxiv id (paper LaTeX source)")
    ap.add_argument("--t3-cache-dir", default="/tmp/bootstrap_t3_cache",
                    help="Cache dir for T3 extractions")
    ap.add_argument("--skip-t3", action="store_true")
    ap.add_argument("--n-iter", type=int, default=10000)
    args = ap.parse_args()

    # Find the 10 manual gold papers; derive arxiv_id from filename
    manual_papers = sorted(T1_DIR.glob("*_manual.json"))
    manual_papers = [p for p in manual_papers if "candes_tao" not in p.name and "sinkhorn" not in p.name]
    print(f"Found {len(manual_papers)} T1 manual gold papers (excluding case-study golds).")

    arxiv_ids = [p.stem.replace("_manual", "") for p in manual_papers]
    print(f"  IDs: {arxiv_ids}")

    # Run evaluations
    providers = {
        "Opus (Anthropic)": "_anthropic",
        "GPT-4o (OpenAI)":  "_openai",
    }

    results = {}
    for prov_name, suffix in providers.items():
        per_paper_counts_list = []
        for aid, gold in zip(arxiv_ids, manual_papers):
            ext = T1_DIR / f"{aid}{suffix}.json"
            if not ext.exists():
                print(f"  [{prov_name}] missing {ext.name}")
                continue
            counts = per_paper_per_type_counts(ext, gold)
            if counts is None:
                print(f"  [{prov_name}] eval failed on {aid}")
                continue
            per_paper_counts_list.append(counts)
        results[prov_name] = per_paper_counts_list

    # T3 extraction if requested
    if not args.skip_t3:
        cache = Path(args.t3_cache_dir)
        cache.mkdir(parents=True, exist_ok=True)
        print()
        print(f"Running T3 (regex) extraction on T1 papers; cache at {cache}")
        t3_macros = []
        for aid, gold in zip(arxiv_ids, manual_papers):
            t3_ext = cache / f"{aid}.json"
            if not t3_ext.exists():
                # Look for LaTeX source
                tex_dir = None
                for cand_root in [Path(args.t3_tex_base)] + [Path(p) for p in args.t3_tex_base.split(",") if p]:
                    for sub in cand_root.rglob(f"*{aid.split('v')[0]}*"):
                        if sub.is_dir() and any(sub.glob("*.tex")):
                            tex_dir = sub
                            break
                    if tex_dir: break
                if tex_dir is None:
                    print(f"  [T3] no LaTeX source for {aid} under {args.t3_tex_base}; skipping")
                    continue
                # Run T3 extraction
                with tempfile.TemporaryDirectory() as tmp:
                    out_dir = Path(tmp) / aid
                    proc = subprocess.run([
                        sys.executable, str(PIPELINE),
                        "--operations", "parse,validate",
                        "--extract-mode", "regex",
                        "--tex-dir", str(tex_dir),
                        "--out-dir", str(out_dir),
                    ], capture_output=True, text=True, timeout=180)
                    if proc.returncode != 0:
                        print(f"  [T3] extraction failed on {aid}")
                        continue
                    cands = list((out_dir / "json").glob("*.json")) if (out_dir / "json").exists() else \
                            [p for p in out_dir.glob("*.json") if p.name != "parse_summary.json"]
                    if not cands:
                        print(f"  [T3] no extraction output for {aid}")
                        continue
                    shutil.copy(cands[0], t3_ext)
            counts = per_paper_per_type_counts(t3_ext, gold)
            if counts is None:
                print(f"  [T3] eval failed on {aid}")
                continue
            t3_macros.append(counts)
        results["T3 (regex)"] = t3_macros

    # Per-type breakdown for each provider
    types_ordered = ["definition", "theorem", "lemma", "proposition", "corollary",
                     "claim", "conjecture", "problem", "proof"]
    for prov_name, per_paper_counts_list in results.items():
        print()
        print(f"=== Per-type breakdown for {prov_name} (corpus-aggregated over n={len(per_paper_counts_list)} papers) ===")
        if not per_paper_counts_list:
            print("  no successful evals")
            continue
        print(f"{'Type':<14s} {'TP':>5s} {'FP':>5s} {'FN':>5s} {'Precision':>10s} {'Recall':>8s} {'F1':>8s}")
        print("-" * 60)
        for t in types_ordered:
            tp = sum(c.get(t, (0,0,0))[0] for c in per_paper_counts_list)
            fp = sum(c.get(t, (0,0,0))[1] for c in per_paper_counts_list)
            fn = sum(c.get(t, (0,0,0))[2] for c in per_paper_counts_list)
            if tp + fn == 0:
                print(f"{t:<14s} {tp:>5d} {fp:>5d} {fn:>5d} {'(no gold)':>10s} {'':>8s} {'':>8s}")
                continue
            prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            rec  = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            denom = 2*tp + fp + fn
            f1 = (2*tp / denom) if denom > 0 else 0.0
            print(f"{t:<14s} {tp:>5d} {fp:>5d} {fn:>5d} {prec:>10.3f} {rec:>8.3f} {f1:>8.3f}")

    print()
    print(f"=== Macro-F1 aggregate + bootstrap 95% CI ({args.n_iter} iters) ===")
    print(f"{'Provider':<22s} {'macro-F1':>10s}  {'95% CI':>20s}  {'n papers':>10s}")
    print("-" * 70)
    for name, per_paper_counts_list in results.items():
        ci = bootstrap_ci_corpus(per_paper_counts_list, types_ordered, n_iter=args.n_iter)
        if ci is None:
            print(f"{name:<22s} no successful evals")
            continue
        mean, lo, hi = ci
        print(f"{name:<22s} {mean:>10.3f}  [{lo:.3f}, {hi:.3f}]    {len(per_paper_counts_list):>10d}")


if __name__ == "__main__":
    main()
