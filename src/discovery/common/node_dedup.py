"""Cluster near-identical theorem nodes within the corpus.

Why this matters for Method E: a 2022 paper that restates a 2010 theorem in
new notation will look like a candidate solution to a 1998 open problem if
we just match by signature similarity — but it isn't a fresh resolution, it
just propagates an existing one. We want to attribute candidate resolutions
to the EARLIEST statement of the theorem, not a later restatement.

Approach:
  - read a node-index JSONL (output of common.build_node_index)
  - bucket nodes by shared foundation_id OR shared operator (keeps the
    pairwise comparison set small instead of O(N^2))
  - within each bucket, run union-find: merge two nodes if their
    statement_jaccard >= threshold AND foundation_overlap >= threshold
  - resulting clusters are written to dedup_clusters.jsonl. Each cluster
    has `members` (list of node refs) and `canonical_member` (earliest by
    paper year, tie-broken by paper_id).

Output schema (one cluster per JSONL line):
    {
        "cluster_id": "C00042",
        "canonical": {"paper_id": ..., "node_id": ..., "year": ...},
        "members":   [{"paper_id": ..., "node_id": ..., "year": ...}, ...],
        "size":      N,
    }
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent.parent
for _p in (_SRC, _HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from signature import jaccard  # noqa: E402


@dataclass
class _IndexedNode:
    """In-memory view of one row from a node-index JSONL."""
    paper_id: str
    year: int
    node_id: str
    node_type: str
    foundation_ids: frozenset
    operators: frozenset
    statement_tokens: frozenset

    def key(self) -> str:
        return f"{self.paper_id}::{self.node_id}"


def _load_index(jsonl_path: Path) -> list[_IndexedNode]:
    out: list[_IndexedNode] = []
    with jsonl_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            out.append(_IndexedNode(
                paper_id=r["paper_id"],
                year=int(r.get("year") or 0),
                node_id=r.get("node_id") or "",
                node_type=r.get("node_type") or "",
                foundation_ids=frozenset(r.get("sig_foundation_ids") or []),
                operators=frozenset(r.get("sig_operators") or []),
                statement_tokens=frozenset(r.get("sig_statement_tokens") or []),
            ))
    return out


class _UF:
    """Disjoint-set union for clustering."""
    def __init__(self):
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def _candidate_pairs(nodes: list[_IndexedNode]) -> Iterator[tuple[int, int]]:
    """Yield (i, j) pairs that share at least one foundation_id OR (if both
    have empty foundation_ids) at least one operator.

    This bucketing keeps the pairwise loop tractable. Without it we'd do
    O(N^2) on tens of thousands of theorems. With it we do roughly
    O(N * avg_bucket_size) which is far smaller in practice.
    """
    by_fid: dict[str, list[int]] = {}
    by_op: dict[str, list[int]] = {}
    for i, n in enumerate(nodes):
        if n.foundation_ids:
            for f in n.foundation_ids:
                by_fid.setdefault(f, []).append(i)
        else:
            for op in n.operators:
                by_op.setdefault(op, []).append(i)

    seen: set[tuple[int, int]] = set()

    def _emit_bucket(bucket: list[int], max_bucket: int = 200):
        # Skip mega-buckets (common foundation_ids like a frequently-cited
        # canonical concept). A theorem clusterable to 200+ peers via one
        # foundation_id is almost certainly a vocabulary artifact, not a
        # restatement chain.
        if len(bucket) > max_bucket:
            return
        for ai in range(len(bucket)):
            for bi in range(ai + 1, len(bucket)):
                i, j = bucket[ai], bucket[bi]
                if i > j:
                    i, j = j, i
                if (i, j) in seen:
                    continue
                seen.add((i, j))
                yield i, j

    for bucket in by_fid.values():
        yield from _emit_bucket(bucket)
    for bucket in by_op.values():
        yield from _emit_bucket(bucket)


def cluster_index(
    index_path: Path,
    out_path: Path,
    *,
    statement_threshold: float = 0.85,
    foundation_threshold: float = 0.5,
    require_same_type: bool = True,
) -> dict:
    """Cluster near-identical nodes from a build_node_index JSONL.

    Args:
        statement_threshold: minimum Jaccard on statement_tokens for two
                             nodes to be merged. Conservative default 0.85
                             — text overlap this high typically means
                             literal restatement, not just topic overlap.
        foundation_threshold: minimum Jaccard on foundation_ids (only checked
                              when both sides have non-empty foundation_ids;
                              skipped otherwise).
        require_same_type: only merge nodes of the same node_type
                           (theorem vs lemma, etc.). True by default.

    Writes one JSONL row per cluster (singletons omitted from output).
    Returns a summary dict.
    """
    nodes = _load_index(Path(index_path))
    n = len(nodes)
    uf = _UF()
    n_pairs = 0
    n_merged = 0
    for i, j in _candidate_pairs(nodes):
        n_pairs += 1
        a, b = nodes[i], nodes[j]
        if require_same_type and a.node_type != b.node_type:
            continue
        sj = jaccard(a.statement_tokens, b.statement_tokens)
        if sj < statement_threshold:
            continue
        if a.foundation_ids and b.foundation_ids:
            fj = jaccard(a.foundation_ids, b.foundation_ids)
            if fj < foundation_threshold:
                continue
        uf.union(a.key(), b.key())
        n_merged += 1

    # Collect non-singleton clusters
    clusters: dict[str, list[_IndexedNode]] = {}
    for node in nodes:
        root = uf.find(node.key())
        clusters.setdefault(root, []).append(node)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    n_written = 0
    n_singletons = 0
    with out_path.open("w", encoding="utf-8") as f:
        for cid, (root, members) in enumerate(sorted(clusters.items()), 1):
            if len(members) < 2:
                n_singletons += 1
                continue
            canonical = min(members, key=lambda m: (m.year or 9999, m.paper_id))
            row = {
                "cluster_id": f"C{cid:06d}",
                "canonical": {
                    "paper_id": canonical.paper_id,
                    "node_id": canonical.node_id,
                    "year": canonical.year,
                    "node_type": canonical.node_type,
                },
                "members": [{
                    "paper_id": m.paper_id,
                    "node_id": m.node_id,
                    "year": m.year,
                    "node_type": m.node_type,
                } for m in members],
                "size": len(members),
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            n_written += 1

    print(f"[dedup] nodes={n} pairs_inspected={n_pairs:,} merges={n_merged} "
          f"clusters_out={n_written} singletons_skipped={n_singletons} "
          f"-> {out_path}", file=sys.stderr)
    return {"nodes": n, "pairs": n_pairs, "merges": n_merged,
            "clusters_written": n_written}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--index", required=True, help="Input node-index JSONL")
    ap.add_argument("--out", required=True, help="Output dedup_clusters.jsonl")
    ap.add_argument("--statement-threshold", type=float, default=0.85)
    ap.add_argument("--foundation-threshold", type=float, default=0.5)
    ap.add_argument("--any-type", action="store_true",
                    help="Allow cross-type merges (default: same-type only)")
    args = ap.parse_args()
    cluster_index(Path(args.index), Path(args.out),
                  statement_threshold=args.statement_threshold,
                  foundation_threshold=args.foundation_threshold,
                  require_same_type=not args.any_type)


if __name__ == "__main__":
    main()
