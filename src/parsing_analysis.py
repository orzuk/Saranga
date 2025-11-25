#!/usr/bin/env python3
import json
from pathlib import Path
from collections import Counter, defaultdict

from math_paper_parser import PaperGraph  # already in your repo


def analyze_graph(pg: PaperGraph):
    """Return a dict with diagnostic stats for one parsed paper."""
    G = pg.to_networkx()  # or your helper; otherwise just rebuild as in paper_to_network

    # kinds
    kinds = Counter(obj.kind for obj in pg.objects.values())

    # degree stats
    deg = dict(G.degree())
    isolated = [n for n, d in deg.items() if d == 0]

    # isolated per kind
    iso_by_kind = Counter(pg.objects[n].kind for n in isolated)

    # orphan proofs = proofs not connected to any theorem/lemma/...
    statement_kinds = {"theorem", "lemma", "proposition", "corollary", "claim", "conjecture"}
    orphan_proofs = []
    for n, data in G.nodes(data=True):
        if data.get("kind") != "proof":
            continue
        nbrs = set(G.predecessors(n)) | set(G.successors(n))
        if not any(G.nodes[m].get("kind") in statement_kinds for m in nbrs):
            orphan_proofs.append(n)

    return {
        "num_objects": len(pg.objects),
        "kinds": dict(kinds),
        "num_edges": G.number_of_edges(),
        "num_isolated": len(isolated),
        "isolated_by_kind": dict(iso_by_kind),
        "num_orphan_proofs": len(orphan_proofs),
        "orphan_proofs": orphan_proofs,
    }


def main(root_dir: str):
    root = Path(root_dir)
    rows = []
    for json_path in sorted(root.rglob("*.json")):
        paper_id = json_path.stem
        data = json.loads(json_path.read_text(encoding="utf-8"))
        pg = PaperGraph.from_dict(data)
        stats = analyze_graph(pg)
        stats["paper_id"] = paper_id
        rows.append(stats)

    # crude print; you can pretty-print or dump CSV
    for r in rows:
        print("\n=== ", r["paper_id"], " ===")
        print("Kinds:", r["kinds"])
        print("Edges:", r["num_edges"],
              "Isolated:", r["num_isolated"],
              "Isolated by kind:", r["isolated_by_kind"])
        print("Orphan proofs:", r["num_orphan_proofs"], r["orphan_proofs"])


if __name__ == "__main__":
    import sys
    main(sys.argv[1])
