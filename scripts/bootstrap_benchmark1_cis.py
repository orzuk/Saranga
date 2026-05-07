#!/usr/bin/env python3
"""Bootstrap 95% CIs for Benchmark 1 macro-F1 over the T1 papers.

Computes per-paper F1 for each provider (Claude Opus, T3 regex, GPT-4o)
on each of the 9 evaluated types, then bootstrap-resamples the 10 T1
papers (10000 iterations) to estimate 95% CIs on macro-F1.

Run on cluster (or anywhere with portal/data/tier1/ + a
provider_extractions/ dir):

    python3 scripts/bootstrap_benchmark1_cis.py \\
        --t1-dir portal/data/tier1 \\
        --opus-dir <opus T1 extractions> \\
        --t3-dir <T3 T1 extractions> \\
        --gpt4o-dir <gpt4o T1 extractions>

Output: prints macro-F1 mean + 95% CI per provider.
"""
import argparse
import csv
import json
import random
import subprocess
import sys
from pathlib import Path

THEOREM_LIKE = {"theorem", "lemma", "proposition", "corollary", "claim",
                "conjecture", "problem", "definition", "proof"}


def per_paper_per_type_f1(extracted_path, gold_path, eval_script):
    """Run evaluate_extraction.py once and parse the per-type F1s.

    Returns: dict mapping {type: f1, ...} for the 9 evaluated types.
    """
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
        out_csv = tf.name
    cmd = [
        sys.executable, str(eval_script),
        "--extracted", str(extracted_path),
        "--gold",      str(gold_path),
        "--csv",       out_csv,
        "--exclude-origin", "external",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        return None
    f1_per_type = {}
    try:
        for r in csv.DictReader(open(out_csv)):
            cat = (r.get("category") or "").strip()
            typ = (r.get("type") or "").strip().lower()
            if cat == "nodes" and typ in THEOREM_LIKE:
                try:
                    f1_per_type[typ] = float(r.get("f1") or "0")
                except ValueError:
                    pass
    except Exception:
        return None
    return f1_per_type


def macro_f1(per_type_f1):
    """Macro-average over the 9 types (treats missing types as 0)."""
    types = list(THEOREM_LIKE)
    return sum(per_type_f1.get(t, 0.0) for t in types) / len(types)


def bootstrap_ci(per_paper_f1s, n_iter=10000, alpha=0.05):
    """Bootstrap 95% CI on the mean macro-F1 across papers."""
    n = len(per_paper_f1s)
    if n == 0:
        return None
    rng = random.Random(42)
    means = []
    for _ in range(n_iter):
        sample = [per_paper_f1s[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo = means[int(n_iter * alpha / 2)]
    hi = means[int(n_iter * (1 - alpha / 2))]
    return sum(per_paper_f1s) / n, lo, hi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--t1-dir", required=True, help="Path to T1 gold JSONs (paper*.json)")
    ap.add_argument("--opus-dir", help="Path to Opus T1 extractions (same paper IDs as T1)")
    ap.add_argument("--t3-dir",   help="Path to T3 T1 extractions")
    ap.add_argument("--gpt4o-dir", help="Path to GPT-4o T1 extractions")
    ap.add_argument("--eval-script", default="src/evaluate_extraction.py")
    ap.add_argument("--n-iter", type=int, default=10000)
    args = ap.parse_args()

    t1_dir = Path(args.t1_dir).resolve()
    eval_script = Path(args.eval_script).resolve()
    if not eval_script.exists():
        print(f"ERROR: eval script not found: {eval_script}", file=sys.stderr)
        sys.exit(2)

    t1_papers = sorted(t1_dir.glob("paper*.json"))
    if not t1_papers:
        print(f"ERROR: no paper*.json in {t1_dir}", file=sys.stderr)
        sys.exit(2)
    print(f"Found {len(t1_papers)} T1 gold papers.")

    providers = []
    for name, d in [("Opus", args.opus_dir), ("T3", args.t3_dir), ("GPT-4o", args.gpt4o_dir)]:
        if d:
            providers.append((name, Path(d).resolve()))
    if not providers:
        print("Pass at least one of --opus-dir / --t3-dir / --gpt4o-dir", file=sys.stderr)
        sys.exit(2)

    print()
    for name, prov_dir in providers:
        per_paper_macros = []
        for t1_path in t1_papers:
            ext_path = prov_dir / t1_path.name
            if not ext_path.exists():
                # Try without _manual or other suffix variants
                stem = t1_path.stem
                cands = list(prov_dir.glob(f"{stem}*.json"))
                if cands:
                    ext_path = cands[0]
                else:
                    continue
            f1s = per_paper_per_type_f1(ext_path, t1_path, eval_script)
            if f1s is None:
                continue
            per_paper_macros.append(macro_f1(f1s))

        n = len(per_paper_macros)
        if n == 0:
            print(f"  {name}: no successful evaluations")
            continue
        result = bootstrap_ci(per_paper_macros, n_iter=args.n_iter)
        if result is None:
            print(f"  {name}: bootstrap failed")
            continue
        mean, lo, hi = result
        print(f"  {name:>8s}: macro-F1 = {mean:.3f} [{lo:.3f}, {hi:.3f}]  (95% CI, n={n}, {args.n_iter} bootstrap iters)")


if __name__ == "__main__":
    main()
