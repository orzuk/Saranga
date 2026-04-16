#!/usr/bin/env python3
"""Multi-dimensional alignment benchmark.

Instead of collapsing similarity into one score, this script computes a profile
(Z_statement, Z_proof) per pair. Different categories in our taxonomy map to
distinct profile patterns:

  parallel_rediscovery / competing_frameworks:
      high Z_statement, varying Z_proof
  alternative_proof:
      high Z_statement, LOW Z_proof   (same theorem, different proof machinery)
  extension / specialization:
      varying Z_statement, high Z_concept-shared (not implemented yet)

Method
------
For each pair (A, B):
  1. Solve Hungarian on sigma_statement -> matching M*
  2. Score M* under both sigma_statement and sigma_proof separately
  3. Permutation null: for each permutation of B's node content,
     re-solve Hungarian on sigma_statement, score the resulting matching
     under BOTH sigmas. This gives a null distribution for each axis that
     conditions on "matched via statement similarity" -- the right null.
  4. Report Z_stmt, Z_proof for the Hungarian matching and for the gold.

Config: reuses alignment_benchmark/benchmark_config.json.
Output: CSV with pair_name, category, Z_stmt_H, Z_proof_H, Z_stmt_G, Z_proof_G,
        plus raw observed scores and null means.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import numpy as np  # noqa: E402
from graph_alignment import (  # noqa: E402
    align_graphs,
    jaccard_statement,
    jaccard_proof,
)


# ── Config / path resolution (copied from run_alignment_benchmark.py) ─────────
def load_json(p: Path) -> dict:
    with open(p) as f:
        return json.load(f)


def resolve_path(name: str, paths: dict, config_dir: Path) -> Path:
    if ":" in name and not name.startswith(("/", ".", "\\")):
        prefix, _, rest = name.partition(":")
        keys_to_try = [f"{prefix}_papers_dir", f"{prefix}_dir"]
        if prefix == "align":
            keys_to_try.append("alignments_dir")
        for key in keys_to_try:
            if key in paths:
                base = Path(paths[key])
                if not base.is_absolute():
                    base = (config_dir / base).resolve()
                return base / rest
        return config_dir / rest
    p = Path(name)
    if p.is_absolute():
        return p
    return (config_dir / p).resolve()


def parse_gold_pairs(alignment_json: dict, key_A: str, key_B: str) -> dict:
    """Return gold_matching as a dict a_id -> b_id (first b per a)."""
    gold_matching = {}
    for m in alignment_json.get("matches", []):
        if (m.get("match_type") or "").lower() not in ("exact", "analogous"):
            continue
        a_ids = m.get(key_A, []) or []
        b_ids = m.get(key_B, []) or []
        for a in a_ids:
            for b in b_ids:
                if a not in gold_matching:
                    gold_matching[a] = b
    return gold_matching


# ── Scoring under an arbitrary sigma ─────────────────────────────────────────
def score_matching(matching: dict, graph_a: dict, graph_b: dict, sigma_fn) -> float:
    """Sum sigma over matched pairs."""
    a_by_id = {n["id"]: n for n in graph_a.get("nodes", [])}
    b_by_id = {n["id"]: n for n in graph_b.get("nodes", [])}
    s = 0.0
    for aid, bid in matching.items():
        if aid in a_by_id and bid in b_by_id:
            s += sigma_fn(a_by_id[aid], b_by_id[bid])
    return s


def permute_graph_b(graph_b: dict, rng: random.Random) -> dict:
    """Permute node content while preserving edges (same ids, swapped payload)."""
    nodes = graph_b.get("nodes", [])
    perm = list(range(len(nodes)))
    rng.shuffle(perm)
    ids = [n["id"] for n in nodes]
    shuffled = []
    for new_idx, old_idx in enumerate(perm):
        n_new = dict(nodes[old_idx])
        n_new["id"] = ids[new_idx]
        shuffled.append(n_new)
    return {"nodes": shuffled, "edges": graph_b.get("edges", [])}


# ── Multi-dim null + Z ───────────────────────────────────────────────────────
def multidim_null(graph_a, graph_b, n_perms=200, alpha=0.5, seed=42, verbose=False):
    """Return null distributions of (score_stmt, score_proof) where each draw
    solves Hungarian on sigma_statement over a permuted B.

    Returns arrays null_stmt, null_proof of length n_perms.
    """
    rng = random.Random(seed)
    null_stmt, null_proof = [], []
    for t in range(n_perms):
        g_b_perm = permute_graph_b(graph_b, rng)
        res = align_graphs(graph_a, g_b_perm, sigma_fn=jaccard_statement,
                           alpha=alpha, n_iters=3, verbose=False)
        m = res["matching"]
        null_stmt.append(score_matching(m, graph_a, g_b_perm, jaccard_statement))
        null_proof.append(score_matching(m, graph_a, g_b_perm, jaccard_proof))
        if verbose and (t + 1) % 50 == 0:
            print(f"    perm {t+1}/{n_perms}", flush=True)
    return np.array(null_stmt), np.array(null_proof)


def z_from(obs, null):
    mu = float(null.mean())
    sd = float(null.std()) + 1e-9
    return (obs - mu) / sd, mu, sd


# ── Per-pair eval ────────────────────────────────────────────────────────────
def eval_pair(pair_cfg, paths, config_dir, n_perms, alpha, kind,
              verbose=True):
    name = pair_cfg["name"]
    g_a_path = resolve_path(pair_cfg["graph_A"], paths, config_dir)
    g_b_path = resolve_path(pair_cfg["graph_B"], paths, config_dir)
    if not g_a_path.exists() or not g_b_path.exists():
        if verbose:
            print(f"[{kind}] {name}: SKIP (missing)")
        return None
    g_a = load_json(g_a_path)
    g_b = load_json(g_b_path)

    if verbose:
        print(f"\n[{kind}] {name}: A={len(g_a.get('nodes', []))}, "
              f"B={len(g_b.get('nodes', []))}", flush=True)

    # Hungarian on sigma_statement
    hung = align_graphs(g_a, g_b, sigma_fn=jaccard_statement, alpha=alpha)
    M_hung = hung["matching"]

    # Observed scores under both sigmas
    obs_stmt_H = score_matching(M_hung, g_a, g_b, jaccard_statement)
    obs_proof_H = score_matching(M_hung, g_a, g_b, jaccard_proof)

    # Gold matching + its scores
    obs_stmt_G = obs_proof_G = None
    n_gold = 0
    if kind == "pos" and "alignment" in pair_cfg:
        align_path = resolve_path(pair_cfg["alignment"], paths, config_dir)
        if align_path.exists():
            gold_matching = parse_gold_pairs(
                load_json(align_path),
                pair_cfg["key_A"], pair_cfg["key_B"])
            obs_stmt_G = score_matching(gold_matching, g_a, g_b, jaccard_statement)
            obs_proof_G = score_matching(gold_matching, g_a, g_b, jaccard_proof)
            n_gold = len(gold_matching)

    # Null (shared across both sigmas -- one set of permutations)
    null_stmt, null_proof = multidim_null(g_a, g_b, n_perms=n_perms, alpha=alpha,
                                          verbose=verbose)
    z_stmt_H, mu_s, sd_s = z_from(obs_stmt_H, null_stmt)
    z_proof_H, mu_p, sd_p = z_from(obs_proof_H, null_proof)

    z_stmt_G = z_proof_G = None
    if obs_stmt_G is not None:
        z_stmt_G, _, _ = z_from(obs_stmt_G, null_stmt)
        z_proof_G, _, _ = z_from(obs_proof_G, null_proof)

    row = {
        "pair_name": name,
        "type": kind,
        "category": pair_cfg.get("category", ""),
        "n_nodes_A": len(g_a.get("nodes", [])),
        "n_nodes_B": len(g_b.get("nodes", [])),
        "n_matches_hung": hung["n_matches"],
        "n_gold_pairs": n_gold,
        "score_stmt_H": round(obs_stmt_H, 3),
        "score_proof_H": round(obs_proof_H, 3),
        "score_stmt_G": round(obs_stmt_G, 3) if obs_stmt_G is not None else "",
        "score_proof_G": round(obs_proof_G, 3) if obs_proof_G is not None else "",
        "null_mean_stmt": round(mu_s, 3),
        "null_mean_proof": round(mu_p, 3),
        "null_std_stmt": round(sd_s, 3),
        "null_std_proof": round(sd_p, 3),
        "z_stmt_H": round(z_stmt_H, 3),
        "z_proof_H": round(z_proof_H, 3),
        "z_stmt_G": round(z_stmt_G, 3) if z_stmt_G is not None else "",
        "z_proof_G": round(z_proof_G, 3) if z_proof_G is not None else "",
    }

    if verbose:
        def fmt(x):
            return f"{x:+.2f}" if x is not None else "  --"
        print(f"  Hung: Z_stmt={fmt(z_stmt_H)}, Z_proof={fmt(z_proof_H)}")
        if z_stmt_G is not None:
            print(f"  Gold: Z_stmt={fmt(z_stmt_G)}, Z_proof={fmt(z_proof_G)}")
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--n-perms", type=int, default=200)
    parser.add_argument("--alpha", type=float, default=0.5)
    parser.add_argument("--course-papers-dir", default=None)
    parser.add_argument("--only", default=None)
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config_dir = config_path.parent
    cfg = load_json(config_path)

    paths = {k: v for k, v in cfg.items()
             if isinstance(v, str)
             and (k.endswith("_papers_dir") or k == "alignments_dir")}
    if args.course_papers_dir:
        paths["course_papers_dir"] = args.course_papers_dir

    only = set(args.only.split(",")) if args.only else None
    rows = []
    for p in cfg.get("positive_pairs", []):
        if only and p["name"] not in only:
            continue
        r = eval_pair(p, paths, config_dir, args.n_perms, args.alpha, kind="pos")
        if r is not None:
            rows.append(r)
    for p in cfg.get("negative_pairs", []):
        if only and p["name"] not in only:
            continue
        r = eval_pair(p, paths, config_dir, args.n_perms, args.alpha, kind="neg")
        if r is not None:
            rows.append(r)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else []
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"\nWrote {len(rows)} rows to {out}")

    pos_stmt = [r["z_stmt_H"] for r in rows if r["type"] == "pos"]
    pos_proof = [r["z_proof_H"] for r in rows if r["type"] == "pos"]
    neg_stmt = [r["z_stmt_H"] for r in rows if r["type"] == "neg"]
    neg_proof = [r["z_proof_H"] for r in rows if r["type"] == "neg"]
    print("\n=== Summary (Hungarian) ===")
    if pos_stmt:
        print(f"  Positives (n={len(pos_stmt)}): "
              f"Z_stmt mean={np.mean(pos_stmt):+.2f}, "
              f"Z_proof mean={np.mean(pos_proof):+.2f}")
    if neg_stmt:
        print(f"  Negatives (n={len(neg_stmt)}): "
              f"Z_stmt mean={np.mean(neg_stmt):+.2f}, "
              f"Z_proof mean={np.mean(neg_proof):+.2f}")


if __name__ == "__main__":
    main()
