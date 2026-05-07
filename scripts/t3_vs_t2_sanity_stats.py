#!/usr/bin/env python3
"""Cheap T3-vs-T2 overlap sanity stats on the 152 LaTeX-source pair.

For each of the 152 T2 papers that have LaTeX source (i.e., were also
T3-extracted in the cluster eval at /tmp/t3_vs_t2_eval/t3_extractions/),
compute simple per-paper diagnostics that don't require semantic node
alignment:

    - total node count (T2 vs T3)
    - per-type node counts (theorem, definition, proof, equation)
    - conclusion-rate (% theorem-like nodes with non-empty conclusions)
    - anomaly flag (high or medium severity)
    - DAG acyclicity (sanity check, both should be ~99-100%)

Aggregate output: Pearson correlation for count-type metrics; agreement-rate
for boolean metrics.

Run on cluster:
    cd /sci/labs/orzuk/orzuk/github/Authomathics
    python3 scripts/t3_vs_t2_sanity_stats.py

Output: a CSV at /tmp/t3_vs_t2_eval/sanity_stats.csv plus printed summary.
"""
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
T2_DIR = REPO_ROOT / "portal" / "data" / "tier2"
T3_DIR = Path("/tmp/t3_vs_t2_eval/t3_extractions")
OUT_CSV = Path("/tmp/t3_vs_t2_eval/sanity_stats.csv")

THEOREM_LIKE = {"theorem", "lemma", "proposition", "corollary", "claim"}


def load_json(p):
    try:
        return json.load(open(p))
    except Exception:
        return None


def has_cycle(nodes, edges):
    """Trivial cycle detection (Kahn's)."""
    if not nodes or not edges:
        return False
    node_ids = {n.get("id") for n in nodes if isinstance(n, dict)}
    in_degree = {nid: 0 for nid in node_ids}
    adj = defaultdict(list)
    for e in edges:
        if not isinstance(e, dict):
            continue
        s = e.get("source"); t = e.get("target")
        if s in node_ids and t in node_ids:
            adj[s].append(t)
            in_degree[t] += 1
    queue = [nid for nid, d in in_degree.items() if d == 0]
    visited = 0
    while queue:
        u = queue.pop(0)
        visited += 1
        for v in adj[u]:
            in_degree[v] -= 1
            if in_degree[v] == 0:
                queue.append(v)
    return visited != len(node_ids)


def per_paper_stats(d):
    """Return dict of stats for one paper's JSON."""
    if not d:
        return None
    nodes = d.get("nodes", []) or []
    edges = d.get("edges", []) or []
    types = Counter(n.get("type") for n in nodes if isinstance(n, dict))
    # Conclusion rate over theorem-like nodes
    th_like = [n for n in nodes if isinstance(n, dict) and n.get("type") in THEOREM_LIKE]
    n_with_concl = sum(1 for n in th_like if (n.get("conclusions") or [])) if th_like else 0
    concl_rate = n_with_concl / len(th_like) if th_like else None
    return {
        "n_nodes": len(nodes),
        "n_edges": len(edges),
        "n_theorem": types.get("theorem", 0),
        "n_lemma": types.get("lemma", 0),
        "n_proposition": types.get("proposition", 0),
        "n_corollary": types.get("corollary", 0),
        "n_claim": types.get("claim", 0),
        "n_definition": types.get("definition", 0),
        "n_proof": types.get("proof", 0),
        "n_equation": types.get("equation", 0),
        "n_theorem_like": len(th_like),
        "concl_rate": concl_rate,
        "is_acyclic": not has_cycle(nodes, edges),
    }


def main():
    if not T3_DIR.exists():
        print(f"ERROR: T3 extractions dir not found: {T3_DIR}", file=sys.stderr)
        print("Run scripts/run_t3_vs_t2_eval.sh first to populate it.", file=sys.stderr)
        sys.exit(2)

    t3_pids = sorted(d.name for d in T3_DIR.iterdir() if d.is_dir())
    print(f"Found {len(t3_pids)} T3 extraction directories.")

    rows = []
    n_no_t3 = n_no_t2 = 0
    for pid in t3_pids:
        # Locate T3 JSON: parse_batch.py writes to <pid>/json/<paper>.json.
        # Try that first, then fall back to <pid>/*.json (older layouts).
        t3_dir = T3_DIR / pid / "json"
        if t3_dir.is_dir():
            t3_jsons = [p for p in t3_dir.glob("*.json") if "summary" not in p.name.lower()]
        else:
            t3_jsons = [p for p in (T3_DIR / pid).glob("*.json")
                        if "summary" not in p.name.lower()]
        if not t3_jsons:
            n_no_t3 += 1
            continue
        t3 = load_json(t3_jsons[0])
        # Locate T2 JSON
        t2_path = T2_DIR / f"{pid}.json"
        if not t2_path.exists():
            n_no_t2 += 1
            continue
        t2 = load_json(t2_path)

        s2 = per_paper_stats(t2)
        s3 = per_paper_stats(t3)
        if s2 is None or s3 is None:
            continue
        row = {"paper_id": pid}
        for k, v in s2.items():
            row[f"t2_{k}"] = v
        for k, v in s3.items():
            row[f"t3_{k}"] = v
        rows.append(row)

    print(f"  {len(rows)} paper rows | T3 missing: {n_no_t3} | T2 missing: {n_no_t2}")

    if not rows:
        print("No paper rows; nothing to aggregate.", file=sys.stderr)
        sys.exit(1)

    # Write CSV
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"  per-paper rows written to {OUT_CSV}")

    # Aggregate
    def pearson(xs, ys):
        n = len(xs)
        if n < 2:
            return None
        mx = sum(xs) / n; my = sum(ys) / n
        num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        denx = sum((x - mx) ** 2 for x in xs) ** 0.5
        deny = sum((y - my) ** 2 for y in ys) ** 0.5
        if denx == 0 or deny == 0:
            return None
        return num / (denx * deny)

    print()
    print("=== T3 vs T2 sanity stats over the 152-paper LaTeX overlap ===")
    print()
    print(f"{'Metric':<24s} {'T2 mean':>10s} {'T3 mean':>10s} {'Pearson r':>12s}")
    print("-" * 60)
    metrics = [
        "n_nodes", "n_edges",
        "n_theorem", "n_lemma", "n_proposition", "n_corollary", "n_claim",
        "n_definition", "n_proof", "n_equation",
    ]
    for m in metrics:
        xs = [r[f"t2_{m}"] for r in rows]
        ys = [r[f"t3_{m}"] for r in rows]
        r = pearson(xs, ys)
        r_str = f"{r:.3f}" if r is not None else "n/a"
        print(f"{m:<24s} {sum(xs)/len(xs):>10.1f} {sum(ys)/len(ys):>10.1f} {r_str:>12s}")

    # Categorical aggregates
    n_paired = len(rows)
    both_acyclic = sum(1 for r in rows if r["t2_is_acyclic"] and r["t3_is_acyclic"])
    only_t2 = sum(1 for r in rows if r["t2_is_acyclic"] and not r["t3_is_acyclic"])
    only_t3 = sum(1 for r in rows if not r["t2_is_acyclic"] and r["t3_is_acyclic"])
    neither = sum(1 for r in rows if not r["t2_is_acyclic"] and not r["t3_is_acyclic"])
    print()
    print(f"DAG acyclicity agreement (n={n_paired}):")
    print(f"  both acyclic:  {both_acyclic} ({100*both_acyclic/n_paired:.1f}%)")
    print(f"  T2 only:       {only_t2}")
    print(f"  T3 only:       {only_t3}")
    print(f"  neither:       {neither}")

    # Conclusion-rate aggregates (only papers with theorem-like nodes in both tiers)
    t2_concl_rates = [r["t2_concl_rate"] for r in rows if r["t2_concl_rate"] is not None]
    t3_concl_rates = [r["t3_concl_rate"] for r in rows if r["t3_concl_rate"] is not None]
    print()
    if t2_concl_rates and t3_concl_rates:
        m2 = sum(t2_concl_rates) / len(t2_concl_rates)
        m3 = sum(t3_concl_rates) / len(t3_concl_rates)
        print(f"Conclusion-rate (theorem-like with non-empty conclusion):")
        print(f"  T2 mean: {m2:.2f}  (n={len(t2_concl_rates)})")
        print(f"  T3 mean: {m3:.2f}  (n={len(t3_concl_rates)})")
        print(f"  Difference (T2 - T3): {m2 - m3:+.2f}")


if __name__ == "__main__":
    main()
