#!/usr/bin/env python3
"""Compare two model extractions per paper and compute agreement.

Given two JSON files in the unified {metadata, nodes, edges} schema (e.g.,
gold.json from Opus and gold_qwenT.json from Qwen), compute:
  - Nodes matched between the two (precision/recall/F1).
  - Edges matched between the two.
  - A consensus JSON containing only nodes+edges both models agree on.
  - A per-paper agreement CSV row.

Run on a directory of papers:

  python3 consensus_intersect.py \\
      --base-dir /sci/labs/orzuk/orzuk/projects/Authomathics/alignment_benchmark \\
      --suffix-a "" \\
      --suffix-b _qwenT \\
      --out-suffix _consensus_opus_qwen \\
      --report-csv agreement_opus_qwen.csv

Suffix "" means gold.json. Suffix "_qwenT" means gold_qwenT.json.

The agreement CSV has one row per paper:
  paper_id, n_a, n_b, n_match, node_jaccard, P_a_to_b, R_a_to_b, F1
plus the same five for edges.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# --- Import shared primitives from src/graph_alignment.py.
# This keeps tokenization, node-text extraction, Jaccard, and the σ registry
# consistent across consensus_intersect (T2), eval_against_gold (future T1),
# and run_alignment_benchmark (T3). See docs/graph_compare_design.md.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))
from graph_alignment import (  # noqa: E402
    tokenize,
    node_text,
    type_compat,
    _raw_jaccard as jaccard,
)


def node_type(n: Dict) -> str:
    return str(n.get("type", "")).lower()


def name_canonical(s: str) -> Tuple[str, ...]:
    """Canonical form of a name for exact matching: sorted token tuple.
    Two names are 'exactly equivalent' iff they tokenize to the same set."""
    return tuple(sorted(tokenize(str(s or ""))))


# =============================================================================
# Match nodes between two models
# =============================================================================

def match_nodes(
    nodes_a: List[Dict],
    nodes_b: List[Dict],
    name_match_required: bool = False,
    jaccard_threshold: float = 0.4,
    match_mode: str = "many-to-many",
    type_compat_threshold: float = 0.5,
) -> List[Tuple[int, int]]:
    """Return list of (i, j) where nodes_a[i] corresponds to nodes_b[j].

    Modes:
      - "many-to-many" (DEFAULT): each B node matches at most one A node;
        each A node may match MULTIPLE B nodes. Handles granularity mismatch
        where one model aggregates concepts and the other splits them
        (typical when comparing different LLMs' extractions).
      - "strict" (1-to-1): both sides match at most once. Use when both views
        have the same granularity (rare in multi-LLM consensus).
      - name_match_required=True: Pass 1 only (exact name); strictest.

    Pass 2 (the fallback) uses NAME-only Jaccard with the type_compat matrix
    from graph_alignment.py (so theorem↔lemma scores high, theorem↔definition
    scores low). Names are short and stable; full statement text varies too
    much to be reliable.
    """
    matches: List[Tuple[int, int]] = []
    used_b: Set[int] = set()

    # Pass 1: exact (type, canonical-name) — always one-to-one
    name_index_b: Dict[Tuple[str, Tuple[str, ...]], List[int]] = {}
    for j, nb in enumerate(nodes_b):
        key = (node_type(nb), name_canonical(nb.get("name", "")))
        if key[1]:
            name_index_b.setdefault(key, []).append(j)

    for i, na in enumerate(nodes_a):
        key = (node_type(na), name_canonical(na.get("name", "")))
        if not key[1]:
            continue
        for j in name_index_b.get(key, []):
            if j in used_b:
                continue
            matches.append((i, j))
            used_b.add(j)
            break

    if name_match_required or match_mode == "name-only":
        return matches

    # Pass 2: name-token Jaccard with type_compat
    if match_mode == "many-to-many":
        # Each unmatched B node finds its best-matching A by name-Jaccard.
        # A nodes can be claimed by multiple B's (no used_a constraint).
        for j, nb in enumerate(nodes_b):
            if j in used_b:
                continue
            name_b_tokens = tokenize(str(nb.get("name", "")))
            if not name_b_tokens:
                continue
            tb = node_type(nb)
            best_i, best_score = -1, 0.0
            for i, na in enumerate(nodes_a):
                ta = node_type(na)
                tc = type_compat(ta, tb)
                if tc < type_compat_threshold:
                    continue
                name_a_tokens = tokenize(str(na.get("name", "")))
                if not name_a_tokens:
                    continue
                score = jaccard(name_a_tokens, name_b_tokens) * tc
                if score > best_score:
                    best_i, best_score = i, score
            if best_i >= 0 and best_score >= jaccard_threshold:
                matches.append((best_i, j))
                used_b.add(j)
        return matches

    # match_mode == "strict": 1-to-1 Pass 2 on name tokens
    matched_a = {i for i, _ in matches}
    for i, na in enumerate(nodes_a):
        if i in matched_a:
            continue
        ta = node_type(na)
        name_a_tokens = tokenize(str(na.get("name", "")))
        if not name_a_tokens:
            continue
        best_j, best_score = -1, 0.0
        for j, nb in enumerate(nodes_b):
            if j in used_b:
                continue
            tb = node_type(nb)
            tc = type_compat(ta, tb)
            if tc < type_compat_threshold:
                continue
            name_b_tokens = tokenize(str(nb.get("name", "")))
            if not name_b_tokens:
                continue
            score = jaccard(name_a_tokens, name_b_tokens) * tc
            if score > best_score:
                best_j, best_score = j, score
        if best_j >= 0 and best_score >= jaccard_threshold:
            matches.append((i, best_j))
            used_b.add(best_j)

    return matches


def match_edges(
    edges_a: List[Dict],
    edges_b: List[Dict],
    node_match: List[Tuple[int, int]],
    nodes_a: List[Dict],
    nodes_b: List[Dict],
) -> List[Tuple[int, int]]:
    """An edge in A is matched if both its endpoints are matched to nodes in
    B and the corresponding edge exists in B."""
    a_id_to_b_id: Dict[str, str] = {}
    for i, j in node_match:
        ida = nodes_a[i].get("id")
        idb = nodes_b[j].get("id")
        if ida and idb:
            a_id_to_b_id[str(ida)] = str(idb)

    b_edge_set: Set[Tuple[str, str]] = {
        (str(e.get("source", "")), str(e.get("target", ""))) for e in edges_b
    }

    matches: List[Tuple[int, int]] = []
    for i, ea in enumerate(edges_a):
        sa = str(ea.get("source", ""))
        ta = str(ea.get("target", ""))
        sb = a_id_to_b_id.get(sa)
        tb = a_id_to_b_id.get(ta)
        if sb is None or tb is None or (sb, tb) not in b_edge_set:
            continue
        # Find j (the matching index in edges_b) — first hit
        for j, eb in enumerate(edges_b):
            if str(eb.get("source", "")) == sb and str(eb.get("target", "")) == tb:
                matches.append((i, j))
                break
    return matches


# =============================================================================
# Per-paper agreement
# =============================================================================

def compare_paper(
    path_a: Path,
    path_b: Path,
    name_match_required: bool = False,
    jaccard_threshold: float = 0.6,
) -> Optional[Dict]:
    if not path_a.exists() or not path_b.exists():
        return None
    try:
        with open(path_a) as f:
            ja = json.load(f)
        with open(path_b) as f:
            jb = json.load(f)
    except Exception as e:
        print(f"  [WARN] failed to load {path_a.name} or {path_b.name}: {e}")
        return None

    nodes_a, nodes_b = ja.get("nodes", []), jb.get("nodes", [])
    edges_a, edges_b = ja.get("edges", []), jb.get("edges", [])
    n_a, n_b = len(nodes_a), len(nodes_b)
    e_a, e_b = len(edges_a), len(edges_b)

    nm = match_nodes(nodes_a, nodes_b, name_match_required, jaccard_threshold)
    em = match_edges(edges_a, edges_b, nm, nodes_a, nodes_b)
    n_m = len(nm)
    e_m = len(em)

    matched_a = {i for i, _ in nm}
    matched_b = {j for _, j in nm}
    only_a_nodes = [nodes_a[i] for i in range(n_a) if i not in matched_a]
    only_b_nodes = [nodes_b[j] for j in range(n_b) if j not in matched_b]

    # Consensus = the matched nodes from A (canonical), plus matched edges from A
    consensus = {
        "metadata": {
            **ja.get("metadata", {}),
            "consensus_of": [str(path_a.name), str(path_b.name)],
            "n_consensus_nodes": n_m,
            "n_consensus_edges": e_m,
        },
        "nodes": [nodes_a[i] for i, _ in nm],
        "edges": [edges_a[i] for i, _ in em],
    }

    return {
        "n_a": n_a, "n_b": n_b, "n_match": n_m,
        "e_a": e_a, "e_b": e_b, "e_match": e_m,
        "only_a_nodes": only_a_nodes, "only_b_nodes": only_b_nodes,
        "consensus": consensus,
    }


def metric_row(r: Dict, paper_id: str) -> Dict:
    n_a, n_b, n_m = r["n_a"], r["n_b"], r["n_match"]
    e_a, e_b, e_m = r["e_a"], r["e_b"], r["e_match"]
    n_jacc = n_m / (n_a + n_b - n_m) if (n_a + n_b - n_m) else 0.0
    n_p = n_m / n_a if n_a else 0.0
    n_r = n_m / n_b if n_b else 0.0
    n_f1 = 2 * n_p * n_r / (n_p + n_r) if (n_p + n_r) else 0.0
    e_jacc = e_m / (e_a + e_b - e_m) if (e_a + e_b - e_m) else 0.0
    e_p = e_m / e_a if e_a else 0.0
    e_r = e_m / e_b if e_b else 0.0
    e_f1 = 2 * e_p * e_r / (e_p + e_r) if (e_p + e_r) else 0.0
    return {
        "paper_id": paper_id,
        "n_a": n_a, "n_b": n_b, "n_match": n_m,
        "node_jaccard": f"{n_jacc:.3f}",
        "node_precision": f"{n_p:.3f}",
        "node_recall": f"{n_r:.3f}",
        "node_f1": f"{n_f1:.3f}",
        "e_a": e_a, "e_b": e_b, "e_match": e_m,
        "edge_jaccard": f"{e_jacc:.3f}",
        "edge_precision": f"{e_p:.3f}",
        "edge_recall": f"{e_r:.3f}",
        "edge_f1": f"{e_f1:.3f}",
    }


# =============================================================================
# Main
# =============================================================================

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Compute pairwise agreement between two model extractions."
    )
    ap.add_argument("--base-dir", type=Path, required=True,
                    help="alignment_benchmark dir (parent of papers/)")
    ap.add_argument("--suffix-a", default="_opus_4_7",
                    help='suffix of model A (default: "_opus_4_7" = gold_opus_4_7.json)')
    ap.add_argument("--suffix-b", required=True,
                    help='suffix of model B (e.g. "_deepseek_r" = gold_deepseek_r.json)')
    ap.add_argument("--out-suffix", default="",
                    help='if set, also write a consensus JSON to gold<out-suffix>.json '
                         'next to the inputs')
    ap.add_argument("--report-csv", type=Path, default=Path("agreement_report.csv"))
    ap.add_argument("--paper-ids", default="",
                    help="comma-separated paperN list (default: all where both files exist)")
    ap.add_argument("--name-only", action="store_true",
                    help="require exact (type, normalized name) match; no Jaccard fallback")
    ap.add_argument("--jaccard-threshold", type=float, default=0.6,
                    help="min Jaccard for fallback match (default 0.6)")
    ap.add_argument("--verbose", "-v", action="store_true",
                    help="per-paper printout including only-A/only-B node names")
    args = ap.parse_args()

    papers_dir = args.base_dir / "papers"
    if not papers_dir.exists():
        sys.exit(f"[ERROR] papers/ not found under {args.base_dir}")

    # Build paper list
    if args.paper_ids:
        paper_ids = [s.strip() for s in args.paper_ids.split(",") if s.strip()]
    else:
        paper_ids = sorted(p.name for p in papers_dir.iterdir() if p.is_dir())

    fa_name = f"gold{args.suffix_a}.json"
    fb_name = f"gold{args.suffix_b}.json"
    print(f"[INFO] comparing {fa_name} vs {fb_name} across {len(paper_ids)} papers")

    rows: List[Dict] = []
    sum_a = sum_b = sum_m = 0
    sum_ea = sum_eb = sum_em = 0
    n_papers_compared = 0

    for pid in paper_ids:
        d = papers_dir / pid
        fa = d / fa_name
        fb = d / fb_name
        if not fa.exists() or not fb.exists():
            continue

        r = compare_paper(fa, fb, args.name_only, args.jaccard_threshold)
        if r is None:
            continue
        n_papers_compared += 1

        # Optional consensus JSON
        if args.out_suffix:
            out_path = d / f"gold{args.out_suffix}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(r["consensus"], f, ensure_ascii=False, indent=2)

        row = metric_row(r, pid)
        rows.append(row)
        sum_a += r["n_a"]; sum_b += r["n_b"]; sum_m += r["n_match"]
        sum_ea += r["e_a"]; sum_eb += r["e_b"]; sum_em += r["e_match"]

        # Brief printout
        print(f"  {pid:<10}  nodes A:{r['n_a']:3d} B:{r['n_b']:3d} ∩:{r['n_match']:3d}"
              f"  J={row['node_jaccard']}  F1={row['node_f1']}    "
              f"edges A:{r['e_a']:3d} B:{r['e_b']:3d} ∩:{r['e_match']:3d}  J={row['edge_jaccard']}")

        if args.verbose:
            if r["only_a_nodes"]:
                print(f"    only A: {[n.get('name', '?')[:50] for n in r['only_a_nodes'][:5]]}"
                      f"{' …' if len(r['only_a_nodes']) > 5 else ''}")
            if r["only_b_nodes"]:
                print(f"    only B: {[n.get('name', '?')[:50] for n in r['only_b_nodes'][:5]]}"
                      f"{' …' if len(r['only_b_nodes']) > 5 else ''}")

    # Aggregate
    if n_papers_compared == 0:
        print("[ERROR] no papers had both files present.")
        return 1

    micro_node_jacc = sum_m / (sum_a + sum_b - sum_m) if (sum_a + sum_b - sum_m) else 0.0
    micro_node_p = sum_m / sum_a if sum_a else 0.0
    micro_node_r = sum_m / sum_b if sum_b else 0.0
    micro_node_f1 = 2 * micro_node_p * micro_node_r / (micro_node_p + micro_node_r) if (micro_node_p + micro_node_r) else 0.0
    micro_edge_jacc = sum_em / (sum_ea + sum_eb - sum_em) if (sum_ea + sum_eb - sum_em) else 0.0

    print()
    print(f"[SUMMARY] {n_papers_compared} papers compared")
    print(f"  Total nodes  A:{sum_a}  B:{sum_b}  matched:{sum_m}")
    print(f"  Node micro-Jaccard: {micro_node_jacc:.3f}   micro-F1: {micro_node_f1:.3f}")
    print(f"  Total edges  A:{sum_ea}  B:{sum_eb}  matched:{sum_em}")
    print(f"  Edge micro-Jaccard: {micro_edge_jacc:.3f}")

    # CSV
    if rows:
        with open(args.report_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"[INFO] per-paper report -> {args.report_csv}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
