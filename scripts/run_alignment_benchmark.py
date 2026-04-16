#!/usr/bin/env python3
"""Run the positive/negative graph-alignment benchmark.

Reads a benchmark config JSON listing positive pairs (with gold alignment) and
negative pairs (no gold). For each pair it runs the Hungarian alignment and a
Monte Carlo permutation significance test from `graph_alignment.py`. For
positive pairs it additionally computes precision/recall/F1 vs the gold
alignment and the Z-score of the gold matching.

Output: CSV summary with one row per pair.

Usage:
    python scripts/run_alignment_benchmark.py \
        --config "/path/to/benchmark_config.json" \
        --output "/path/to/results_jaccard.csv" \
        --n-perms 300

The similarity function defaults to `jaccard_sim` from graph_alignment.py.
Pass --sigma-import to plug in a different similarity (e.g. embedding-based)
later, using a dotted-path `module.function`.
"""
from __future__ import annotations

import argparse
import csv
import importlib
import json
import sys
from pathlib import Path

# Make the alignment modules importable. The script lives in
# Authomathics/scripts/, the modules live in Authomathics/src/.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from graph_alignment import (  # noqa: E402
    align_graphs,
    jaccard_sim,
    significance_test,
)
from graph_alignment_eval import score_matching  # noqa: E402
import numpy as np  # noqa: E402


def load_json(p: Path) -> dict:
    with open(p) as f:
        return json.load(f)


def resolve_path(name: str, paths: dict, config_dir: Path) -> Path:
    """Resolve a path reference.

    Accepts these forms:
      "course:paper1_gold.json"    -> paths['course_papers_dir'] / name
      "bench:paper101_gold.json"   -> paths['bench_papers_dir'] / name
      "/abs/path.json"             -> as-is
      "./rel/path.json"            -> config_dir / path
      "rel/path.json"              -> config_dir / path
    """
    if ":" in name and not name.startswith(("/", ".", "\\")):
        prefix, _, rest = name.partition(":")
        # Try {prefix}_papers_dir, {prefix}_dir, then "alignments_dir"
        # for prefix=="align".
        keys_to_try = [f"{prefix}_papers_dir", f"{prefix}_dir"]
        if prefix == "align":
            keys_to_try.append("alignments_dir")
        for key in keys_to_try:
            if key in paths:
                base = Path(paths[key])
                if not base.is_absolute():
                    base = (config_dir / base).resolve()
                return base / rest
        # fallback
        return config_dir / rest
    p = Path(name)
    if p.is_absolute():
        return p
    return (config_dir / p).resolve()


def parse_gold_pairs(alignment_json: dict, key_A: str, key_B: str) -> set:
    """Extract strong (exact/analogous) gold pairs from an alignment JSON.

    Supports the cs_alignment.json style (paper2_nodes, paper21_nodes) and
    any alignment JSON using configurable key names.
    """
    pairs = set()
    for m in alignment_json.get("matches", []):
        mtype = (m.get("match_type") or "").lower()
        if mtype not in ("exact", "analogous"):
            continue
        a_ids = m.get(key_A, []) or []
        b_ids = m.get(key_B, []) or []
        for a in a_ids:
            for b in b_ids:
                pairs.add((a, b))
    return pairs


def precision_recall(pred_matching: dict, gold_pairs: set) -> dict:
    pred_pairs = set(pred_matching.items())
    tp = pred_pairs & gold_pairs
    prec = len(tp) / len(pred_pairs) if pred_pairs else 0.0
    rec = len(tp) / len(gold_pairs) if gold_pairs else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return {"precision": prec, "recall": rec, "f1": f1,
            "tp": len(tp), "fp": len(pred_pairs) - len(tp),
            "fn": len(gold_pairs) - len(tp)}


def eval_pair(pair_cfg: dict, paths: dict, config_dir: Path, sigma_fn,
              n_perms: int, alpha: float, kind: str,
              verbose: bool = True) -> dict:
    """Run alignment + significance on a single pair; add P/R/F1/Z_gold if positive."""
    name = pair_cfg["name"]
    g_a_path = resolve_path(pair_cfg["graph_A"], paths, config_dir)
    g_b_path = resolve_path(pair_cfg["graph_B"], paths, config_dir)
    if not g_a_path.exists() or not g_b_path.exists():
        missing = [str(p) for p in [g_a_path, g_b_path] if not p.exists()]
        if verbose:
            print(f"\n[{kind}] {name}: SKIP (missing: {missing})", flush=True)
        return None
    g_a = load_json(g_a_path)
    g_b = load_json(g_b_path)
    n_a = len(g_a.get("nodes", []))
    n_b = len(g_b.get("nodes", []))

    if verbose:
        print(f"\n[{kind}] {name}: A={n_a} nodes, B={n_b} nodes", flush=True)

    hung = align_graphs(g_a, g_b, sigma_fn=sigma_fn, alpha=alpha)
    sig = significance_test(g_a, g_b, hung["score"], sigma_fn=sigma_fn,
                            alpha=alpha, n_perms=n_perms)

    row = {
        "pair_name": name,
        "type": kind,
        "category": pair_cfg.get("category", ""),
        "n_nodes_A": n_a,
        "n_nodes_B": n_b,
        "n_matches_hung": hung["n_matches"],
        "score_hung": round(hung["score"], 3),
        "null_mean": round(sig["null_mean"], 3),
        "null_std": round(sig["null_std"], 3),
        "z_hung": round(sig["z_score"], 3),
        "p_hung": round(sig["p_value"], 4),
    }

    if kind == "pos" and "alignment" in pair_cfg:
        align_path = resolve_path(pair_cfg["alignment"], paths, config_dir)
        if not align_path.exists():
            if verbose:
                print(f"  WARN: alignment file missing: {align_path}")
            return None
        align_json = load_json(align_path)
        gold_pairs = parse_gold_pairs(
            align_json, pair_cfg["key_A"], pair_cfg["key_B"]
        )
        gold_matching = {}
        for a, b in gold_pairs:
            if a not in gold_matching:
                gold_matching[a] = b

        gold_score_components = score_matching(
            gold_matching, g_a, g_b, sigma_fn=sigma_fn, alpha=alpha,
        )
        gold_score = gold_score_components["total"]
        delta = hung["score"] - gold_score

        null_arr = np.array(sig["null_scores"])
        z_gold = (gold_score - sig["null_mean"]) / (sig["null_std"] + 1e-9)
        p_gold = (1 + int((null_arr >= gold_score).sum())) / (1 + n_perms)

        pr = precision_recall(hung["matching"], gold_pairs)
        row.update({
            "n_gold_pairs": len(gold_pairs),
            "score_gold": round(gold_score, 3),
            "delta": round(delta, 3),
            "precision": round(pr["precision"], 3),
            "recall": round(pr["recall"], 3),
            "f1": round(pr["f1"], 3),
            "tp": pr["tp"],
            "fp": pr["fp"],
            "fn": pr["fn"],
            "z_gold": round(z_gold, 3),
            "p_gold": round(p_gold, 4),
        })
        if verbose:
            print(f"  Hung: score={hung['score']:.2f}, "
                  f"z={sig['z_score']:+.2f}, p={sig['p_value']:.3f}",
                  flush=True)
            print(f"  Gold: score={gold_score:.2f}, z={z_gold:+.2f}, "
                  f"Delta={delta:+.2f}, P={pr['precision']:.2f}, "
                  f"R={pr['recall']:.2f}, F1={pr['f1']:.2f}",
                  flush=True)
    else:
        row.update({
            "n_gold_pairs": "",
            "score_gold": "",
            "delta": "",
            "precision": "",
            "recall": "",
            "f1": "",
            "tp": "",
            "fp": "",
            "fn": "",
            "z_gold": "",
            "p_gold": "",
        })
        if verbose:
            print(f"  Hung: score={hung['score']:.2f}, "
                  f"z={sig['z_score']:+.2f}, p={sig['p_value']:.3f}",
                  flush=True)

    return row


def import_sigma(spec: str):
    """Import a dotted-path `module.function` similarity callable."""
    module_name, _, fn_name = spec.rpartition(".")
    if not module_name:
        raise ValueError(f"sigma spec must be 'module.function', got: {spec}")
    mod = importlib.import_module(module_name)
    return getattr(mod, fn_name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True,
                        help="Path to benchmark_config.json")
    parser.add_argument("--output", required=True,
                        help="Path to write results CSV")
    parser.add_argument("--n-perms", type=int, default=300)
    parser.add_argument("--alpha", type=float, default=0.5)
    parser.add_argument("--sigma-import", default=None,
                        help="Optional dotted-path to a sigma_fn override "
                             "(e.g. mymod.embedding_sim). Defaults to "
                             "graph_alignment.jaccard_sim.")
    parser.add_argument("--sigma-label", default="jaccard",
                        help="Label for the sigma used (saved in CSV).")
    parser.add_argument("--only", default=None,
                        help="Comma-separated pair names to run (debug).")
    parser.add_argument("--course-papers-dir", default=None,
                        help="Override course_papers_dir in config (absolute "
                             "path to course gold JSONs). Useful when the "
                             "default relative path doesn't match local layout.")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config_dir = config_path.parent
    cfg = load_json(config_path)

    # Collect *_papers_dir and alignments_dir entries for resolve_path().
    paths = {k: v for k, v in cfg.items()
             if isinstance(v, str) and (k.endswith("_papers_dir")
                                        or k == "alignments_dir")}
    if args.course_papers_dir:
        paths["course_papers_dir"] = args.course_papers_dir
        print(f"Overriding course_papers_dir -> {args.course_papers_dir}")

    if args.sigma_import:
        sigma_fn = import_sigma(args.sigma_import)
        print(f"Using sigma = {args.sigma_import}")
    else:
        sigma_fn = jaccard_sim
        print("Using sigma = graph_alignment.jaccard_sim (default)")

    only = set(args.only.split(",")) if args.only else None

    rows = []
    for p in cfg.get("positive_pairs", []):
        if only and p["name"] not in only:
            continue
        r = eval_pair(p, paths, config_dir, sigma_fn, args.n_perms,
                      args.alpha, kind="pos")
        if r is not None:
            rows.append(r)
    for p in cfg.get("negative_pairs", []):
        if only and p["name"] not in only:
            continue
        r = eval_pair(p, paths, config_dir, sigma_fn, args.n_perms,
                      args.alpha, kind="neg")
        if r is not None:
            rows.append(r)

    for r in rows:
        r["sigma"] = args.sigma_label

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "pair_name", "type", "category", "sigma",
        "n_nodes_A", "n_nodes_B", "n_matches_hung", "n_gold_pairs",
        "score_hung", "score_gold", "delta",
        "precision", "recall", "f1", "tp", "fp", "fn",
        "null_mean", "null_std",
        "z_hung", "p_hung", "z_gold", "p_gold",
    ]
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"\nWrote {len(rows)} rows to {out_path}")

    pos_z = [r["z_hung"] for r in rows if r["type"] == "pos"]
    neg_z = [r["z_hung"] for r in rows if r["type"] == "neg"]
    print("\n=== Summary ===")
    if pos_z:
        print(f"  Positive pairs (n={len(pos_z)}): "
              f"Z(Hungarian) mean={np.mean(pos_z):+.2f}, "
              f"min={min(pos_z):+.2f}, max={max(pos_z):+.2f}")
    if neg_z:
        print(f"  Negative pairs (n={len(neg_z)}): "
              f"Z(Hungarian) mean={np.mean(neg_z):+.2f}, "
              f"min={min(neg_z):+.2f}, max={max(neg_z):+.2f}")


if __name__ == "__main__":
    main()
