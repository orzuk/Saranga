#!/usr/bin/env python3
"""
Canonicalization A/B test:  run the cross-paper alignment benchmark with
Jaccard sigma on canonicalized JSONs, then diff results against the
existing Jaccard-on-original baseline.

Pipeline:
  1. Read benchmark_config.json.
  2. For every paper JSON referenced (positive + negative pairs),
     load it, canonicalize it, save as <basename>_canonical.json.
  3. Write a new config file benchmark_config_canonical.json that points
     to the canonical JSONs.
  4. Invoke run_alignment_benchmark.py with:
        --config  <canonical config>
        --sigma-import scripts.canonicalize.jaccard_canonical_sigma.sigma
        --output  results_jaccard_canonical.csv
  5. Diff the result CSV against baseline_results/results_jaccard_combined.csv
     and print a per-pair markdown table with deltas in z_hung, z_gold, f1.

Usage:
  cd /mnt/c/Code/Github/Authomathics
  python -m scripts.canonicalize.run_canonicalization_ab_test \\
      --benchmark-dir alignment_benchmark \\
      --n-perms 500

Options:
  --skip-preprocess     Don't re-canonicalize (use existing *_canonical.json)
  --skip-benchmark      Don't rerun alignment (use existing result CSV)
  --dry-run             Print the plan without executing

Outputs (under benchmark-dir):
  papers/paper*_canonical.json       canonical paper JSONs
  config/benchmark_config_canonical.json
  results_jaccard_canonical.csv
  results_jaccard_canonical_vs_baseline.md    diff report
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from copy import deepcopy
from pathlib import Path

# Make repo scripts importable
_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

from scripts.canonicalize.core import canonicalize_paper  # noqa: E402


# ---------------------------------------------------------------------------
# Paper-path extraction: walk the config and find every JSON reference
# ---------------------------------------------------------------------------

def _find_paper_refs(config: dict, papers_dir: Path) -> list[Path]:
    """Return list of paper JSON paths referenced in the config.

    The benchmark config uses prefixed references like:
        "graph_A": "course:paper2_gold.json"
        "graph_B": "bench:paper101_gold.json"
        "alignment": "align:cs_alignment.json"
    We extract only graph_A / graph_B (papers), ignore align:*.
    """
    refs: set[Path] = set()

    def _walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, str) and v.endswith(".json"):
                    if "alignment" in k.lower():
                        continue
                    # Strip prefix if present (course:, bench:, align:, etc.)
                    fname = v.split(":", 1)[-1] if ":" in v else v
                    candidate = papers_dir / Path(fname).name
                    if candidate.exists():
                        refs.add(candidate)
                else:
                    _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(config)
    return sorted(refs)


# ---------------------------------------------------------------------------
# Step 1 -- canonicalize every referenced paper JSON
# ---------------------------------------------------------------------------

def preprocess_papers(paper_paths: list[Path], force: bool = False) -> dict:
    """Canonicalize each referenced paper. Writes <basename>_canonical.json
    alongside the original. Returns a mapping  original_name -> canonical_name.
    """
    mapping = {}
    for p in paper_paths:
        # From paper2_gold.json -> paper2_canonical.json
        name = p.name
        if "_gold" in name:
            canonical_name = name.replace("_gold.json", "_canonical.json")
        else:
            canonical_name = name.replace(".json", "_canonical.json")
        canonical_path = p.with_name(canonical_name)
        mapping[name] = canonical_name

        if canonical_path.exists() and not force:
            print(f"  [skip] {canonical_name} already exists")
            continue

        try:
            with open(p, encoding="utf-8") as f:
                paper = json.load(f)
        except Exception as e:
            print(f"  [fail] {p.name}: cannot read ({e})")
            continue

        try:
            canonical = canonicalize_paper(paper, prose_rewrites=False)
        except Exception as e:
            print(f"  [fail] {p.name}: canonicalize error ({e})")
            continue

        tmp = canonical_path.with_suffix(canonical_path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(canonical, f, indent=2)
        os.rename(tmp, canonical_path)
        print(f"  [ok]   {canonical_name}")

    return mapping


# ---------------------------------------------------------------------------
# Step 2 -- rewrite config to point at canonical JSONs
# ---------------------------------------------------------------------------

def make_canonical_config(original_config: dict, name_map: dict) -> dict:
    """Deep-copy config and replace every paper-JSON filename found in the
    name_map with its canonical counterpart. Preserves prefix (course:, etc.).
    """
    cfg = deepcopy(original_config)

    def _rewrite(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, str) and v.endswith(".json"):
                    if "alignment" in k.lower():
                        continue
                    # Strip prefix (course:, bench:), look up in name_map,
                    # re-attach prefix
                    if ":" in v:
                        prefix, fname = v.split(":", 1)
                    else:
                        prefix, fname = "", v
                    base = Path(fname).name
                    if base in name_map:
                        new_fname = fname.replace(base, name_map[base])
                        obj[k] = f"{prefix}:{new_fname}" if prefix else new_fname
                else:
                    _rewrite(v)
        elif isinstance(obj, list):
            for item in obj:
                _rewrite(item)

    _rewrite(cfg)
    return cfg


# ---------------------------------------------------------------------------
# Step 3 -- run the alignment benchmark
# ---------------------------------------------------------------------------

def run_benchmark(config_path: Path, output_csv: Path, n_perms: int,
                  benchmark_dir: Path, dry_run: bool = False) -> bool:
    """Invoke scripts/run_alignment_benchmark.py with the canonical sigma."""
    cmd = [
        sys.executable,
        str(_REPO / "scripts" / "run_alignment_benchmark.py"),
        "--config", str(config_path),
        "--sigma-import", "scripts.canonicalize.jaccard_canonical_sigma.sigma",
        "--n-perms", str(n_perms),
        "--output", str(output_csv),
    ]
    print("  cmd:", " ".join(cmd))
    if dry_run:
        return True
    # Pass PYTHONPATH so `scripts.canonicalize.*` imports resolve in the subprocess.
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{_REPO}:{env.get('PYTHONPATH', '')}"
    start = time.time()
    result = subprocess.run(cmd, cwd=str(_REPO), env=env)
    elapsed = time.time() - start
    print(f"  elapsed: {elapsed:.1f}s, exit code: {result.returncode}")
    return result.returncode == 0


# ---------------------------------------------------------------------------
# Step 4 -- diff against baseline
# ---------------------------------------------------------------------------

def diff_results(baseline_csv: Path, canonical_csv: Path, report_path: Path):
    """Load both CSVs, compute per-pair deltas, write a markdown report."""
    try:
        import pandas as pd
    except ImportError:
        print("  pandas not available; skipping diff. Install pandas and rerun.")
        return

    if not baseline_csv.exists():
        print(f"  baseline csv not found at {baseline_csv}")
        return
    if not canonical_csv.exists():
        print(f"  canonical csv not found at {canonical_csv}")
        return

    base = pd.read_csv(baseline_csv)
    can = pd.read_csv(canonical_csv)

    keep_cols = ["pair_name", "type", "z_hung", "z_gold", "f1", "score_hung"]
    keep_cols = [c for c in keep_cols if c in base.columns and c in can.columns]
    base = base[keep_cols].rename(columns={c: f"{c}_base" for c in keep_cols if c != "pair_name"})
    can = can[keep_cols].rename(columns={c: f"{c}_can" for c in keep_cols if c != "pair_name"})

    merged = base.merge(can, on="pair_name", how="outer")
    for metric in ("z_hung", "z_gold", "f1", "score_hung"):
        if f"{metric}_base" in merged.columns and f"{metric}_can" in merged.columns:
            merged[f"delta_{metric}"] = merged[f"{metric}_can"] - merged[f"{metric}_base"]

    # Build markdown
    lines = []
    lines.append("# Canonicalization A/B Report\n")
    lines.append(f"- Baseline: `{baseline_csv}`")
    lines.append(f"- Canonical: `{canonical_csv}`")
    lines.append("")

    # Split by pair type
    for t in sorted(merged["type_base"].dropna().unique() if "type_base" in merged.columns else ["pos", "neg"]):
        sub = merged[(merged.get("type_base") == t) | (merged.get("type_can") == t)]
        if len(sub) == 0:
            continue
        lines.append(f"## {t.upper()} pairs")
        lines.append("")
        cols = ["pair_name"]
        for m in ("z_hung", "z_gold", "f1"):
            if f"{m}_base" in sub.columns:
                cols += [f"{m}_base", f"{m}_can", f"delta_{m}"]
        header = "| " + " | ".join(cols) + " |"
        sep = "|" + "|".join(["---"] * len(cols)) + "|"
        lines.append(header)
        lines.append(sep)
        for _, row in sub.iterrows():
            cells = []
            for c in cols:
                val = row.get(c, "")
                if isinstance(val, float):
                    cells.append(f"{val:+.3f}" if "delta" in c else f"{val:.3f}")
                else:
                    cells.append(str(val) if val == val else "")
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")

        # Aggregate summary for this type
        for m in ("z_hung", "z_gold"):
            if f"{m}_base" in sub.columns and f"{m}_can" in sub.columns:
                base_mean = sub[f"{m}_base"].mean()
                can_mean = sub[f"{m}_can"].mean()
                lines.append(f"- Mean {m}: base={base_mean:+.3f}, canonical={can_mean:+.3f}, "
                             f"delta={can_mean - base_mean:+.3f}")
        lines.append("")

    report_path.write_text("\n".join(lines))
    print(f"  report written to {report_path}")

    # Print the short summary to stdout
    print("\n".join(lines[-10:]))


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--benchmark-dir",
                    default=str(_REPO / "alignment_benchmark"),
                    help="Path to the benchmark package root")
    ap.add_argument("--n-perms", type=int, default=500,
                    help="Permutations per pair for the Z-score null")
    ap.add_argument("--baseline-csv", default=None,
                    help="Path to the baseline CSV (default: "
                         "<benchmark-dir>/baseline_results/results_jaccard_combined.csv)")
    ap.add_argument("--skip-preprocess", action="store_true",
                    help="Skip canonicalization (use existing *_canonical.json)")
    ap.add_argument("--skip-benchmark", action="store_true",
                    help="Skip alignment run (diff only)")
    ap.add_argument("--force-preprocess", action="store_true",
                    help="Re-canonicalize even if *_canonical.json exists")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the plan without executing the benchmark")
    args = ap.parse_args()

    benchmark_dir = Path(args.benchmark_dir).resolve()
    papers_dir = benchmark_dir / "papers"
    config_path = benchmark_dir / "config" / "benchmark_config.json"
    canonical_config_path = benchmark_dir / "config" / "benchmark_config_canonical.json"
    canonical_csv = benchmark_dir / "results_jaccard_canonical.csv"
    baseline_csv = (Path(args.baseline_csv) if args.baseline_csv
                    else benchmark_dir / "baseline_results" / "results_jaccard_combined.csv")
    report_path = benchmark_dir / "results_jaccard_canonical_vs_baseline.md"

    # Sanity checks
    if not config_path.exists():
        sys.exit(f"benchmark config not found: {config_path}")
    if not papers_dir.exists():
        sys.exit(f"papers dir not found: {papers_dir}")

    with open(config_path, encoding="utf-8") as f:
        original_config = json.load(f)

    print("=" * 72)
    print("STEP 1 -- canonicalize paper JSONs")
    print("=" * 72)
    paper_paths = _find_paper_refs(original_config, papers_dir)
    print(f"  found {len(paper_paths)} referenced paper JSON(s)")
    if args.skip_preprocess:
        # Build name_map by convention (assumes _gold -> _canonical)
        name_map = {}
        for p in paper_paths:
            src = p.name
            dst = src.replace("_gold.json", "_canonical.json") if "_gold" in src \
                else src.replace(".json", "_canonical.json")
            if (papers_dir / dst).exists():
                name_map[src] = dst
        print(f"  --skip-preprocess: found {len(name_map)} existing canonical JSONs")
    else:
        name_map = preprocess_papers(paper_paths, force=args.force_preprocess)

    print()
    print("=" * 72)
    print("STEP 2 -- write canonical config")
    print("=" * 72)
    canonical_config = make_canonical_config(original_config, name_map)
    with open(canonical_config_path, "w", encoding="utf-8") as f:
        json.dump(canonical_config, f, indent=2)
    print(f"  wrote {canonical_config_path.relative_to(benchmark_dir)}")

    print()
    print("=" * 72)
    print("STEP 3 -- run alignment benchmark with canonical sigma")
    print("=" * 72)
    if args.skip_benchmark:
        print("  --skip-benchmark set; skipping")
    else:
        ok = run_benchmark(canonical_config_path, canonical_csv, args.n_perms,
                           benchmark_dir, dry_run=args.dry_run)
        if not ok and not args.dry_run:
            sys.exit("alignment benchmark failed; aborting")

    print()
    print("=" * 72)
    print("STEP 4 -- diff canonical vs baseline")
    print("=" * 72)
    if args.dry_run:
        print("  dry run -- skipping diff")
    else:
        diff_results(baseline_csv, canonical_csv, report_path)

    print()
    print("Done.")


if __name__ == "__main__":
    main()
