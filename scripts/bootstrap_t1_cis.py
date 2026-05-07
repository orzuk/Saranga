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


def per_paper_per_type_f1(extracted_path, gold_path):
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
        return None
    f1 = {}
    try:
        for r in csv.DictReader(open(out_csv)):
            cat = (r.get("category") or "").strip()
            typ = (r.get("type") or "").strip().lower()
            if cat == "nodes" and typ in THEOREM_LIKE:
                try: f1[typ] = float(r.get("f1") or "0")
                except ValueError: pass
    finally:
        Path(out_csv).unlink(missing_ok=True)
    return f1


def macro_f1(per_type_f1):
    types = list(THEOREM_LIKE)
    return sum(per_type_f1.get(t, 0.0) for t in types) / len(types)


def bootstrap_ci(values, n_iter=10000, seed=42, alpha=0.05):
    n = len(values)
    if n == 0: return None
    rng = random.Random(seed)
    means = []
    for _ in range(n_iter):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo = means[int(n_iter * alpha / 2)]
    hi = means[int(n_iter * (1 - alpha / 2))]
    return sum(values) / n, lo, hi


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
        per_paper_macros = []
        for aid, gold in zip(arxiv_ids, manual_papers):
            ext = T1_DIR / f"{aid}{suffix}.json"
            if not ext.exists():
                print(f"  [{prov_name}] missing {ext.name}")
                continue
            f1s = per_paper_per_type_f1(ext, gold)
            if f1s is None:
                print(f"  [{prov_name}] eval failed on {aid}")
                continue
            per_paper_macros.append(macro_f1(f1s))
        results[prov_name] = per_paper_macros

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
            f1s = per_paper_per_type_f1(t3_ext, gold)
            if f1s is None:
                print(f"  [T3] eval failed on {aid}")
                continue
            t3_macros.append(macro_f1(f1s))
        results["T3 (regex)"] = t3_macros

    # Bootstrap and print
    print()
    print(f"=== Benchmark 1 macro-F1 over T1 (n=10), bootstrap 95% CIs ({args.n_iter} iters) ===")
    print(f"{'Provider':<22s} {'mean':>8s}  {'95% CI':>20s}  {'n':>4s}")
    print("-" * 60)
    for name, vals in results.items():
        ci = bootstrap_ci(vals, n_iter=args.n_iter)
        if ci is None:
            print(f"  {name:<20s} no successful evals")
            continue
        mean, lo, hi = ci
        print(f"{name:<22s} {mean:>8.3f}  [{lo:.3f}, {hi:.3f}]    {len(vals):>4d}")


if __name__ == "__main__":
    main()
